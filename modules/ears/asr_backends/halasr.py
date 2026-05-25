"""HalASR backend — continuous speech recognition with PyAudio + WebRTC VAD + FunASR.

Produces transcribed text via a callback, typically wired to publish on the message bus.
"""

import logging
import os
import queue
import threading
import time
import traceback
import warnings
import wave

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_LOADED = False
_MODEL_ERROR = None


def _load_funasr_model():
    """Lazy-load FunASR model. Returns None if dependencies are missing."""
    global _MODEL_LOADED, _MODEL_ERROR
    if _MODEL_LOADED:
        return _MODEL_ERROR  # None on success, or None on failure either way — cached result

    try:
        import torch
    except ImportError:
        _MODEL_ERROR = None
        _MODEL_LOADED = True
        logger.error(
            "PyTorch is required for FunASR. Install it: pip install torch"
        )
        return None

    try:
        from funasr import AutoModel
        model = AutoModel(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            disable_update=True,
            disable_log=True,
            disable_pbar=True,
        )
        _MODEL_LOADED = True
        return model
    except ImportError:
        _MODEL_ERROR = None
        _MODEL_LOADED = True
        logger.error(
            "FunASR not installed. Run: pip install funasr"
        )
        return None
    except Exception as e:
        _MODEL_ERROR = None
        _MODEL_LOADED = True
        logger.error(f"Failed to load FunASR model: {e}")
        return None


# Whisper support — module-level lazy load (mirrors FunASR pattern above)
_WHISPER_MODEL = None
_WHISPER_MODEL_LOADED = False


def _load_whisper_model(model_name="base"):
    """Lazy-load Whisper model. Returns the model or None on failure."""
    global _WHISPER_MODEL, _WHISPER_MODEL_LOADED
    if _WHISPER_MODEL_LOADED:
        return _WHISPER_MODEL

    try:
        import whisper
        warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
        _WHISPER_MODEL = whisper.load_model(model_name)
        _WHISPER_MODEL_LOADED = True
        logger.info(f"Whisper model loaded: {model_name}")
        return _WHISPER_MODEL
    except ImportError:
        _WHISPER_MODEL_LOADED = True
        logger.error("openai-whisper not installed. Run: pip install openai-whisper")
        return None
    except Exception as e:
        _WHISPER_MODEL_LOADED = True
        logger.error(f"Failed to load Whisper model: {e}")
        return None


def _whisper_recognize(wav_path: str) -> str:
    """Transcribe a WAV file using Whisper. Returns transcribed text or empty string."""
    model = _load_whisper_model()
    if model is None:
        return ""
    try:
        result = model.transcribe(wav_path)
        return result.get("text", "").strip()
    except Exception:
        logger.error(traceback.format_exc())
        return ""


# Optional imports — fail gracefully if not installed
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    pyaudio = None

try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    webrtcvad = None

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    librosa = None


class HalASRBackend:
    """Continuous speech recognition using PyAudio, WebRTC VAD, and FunASR.

    Parameters
    ----------
    on_text : callable
        Called with the transcribed text string when a segment is recognized.
    device_index : int
        PyAudio input device index.
    sample_rate : int
        Microphone sample rate (default 48000).
    target_rate : int
        Resample to this rate for ASR (default 16000).
    hotwords : list[str] | None
        Wake words for hotword mode. If set, only outputs when a hotword is spoken.
    silence_duration : float
        Seconds of silence before ending a recording segment.
    speech_timeout : float
        Seconds before auto-muting output in hotword mode.
    vad_mode : int
        WebRTC VAD aggressiveness (0-3).
    """

    def __init__(
        self,
        on_text=None,
        on_recording_start=None,
        on_recording_end=None,
        device_index=None,
        sample_rate=48000,
        target_rate=16000,
        hotwords=None,
        silence_duration=1.0,
        speech_timeout=20.0,
        vad_mode=3,
        recognizer=None,
        recognizer_name=None,
    ):
        self.on_text = on_text
        self.on_recording_start = on_recording_start
        self.on_recording_end = on_recording_end
        self.sample_rate = sample_rate
        self.target_rate = target_rate
        self.hotwords = hotwords or []
        self.silence_duration = silence_duration
        self.speech_timeout = speech_timeout
        self.vad_mode = vad_mode

        self.chunk = int(sample_rate * 20 / 1000)  # 20ms frames
        self._recognizer = recognizer
        self._recognizer_name = recognizer_name
        self._running = False
        self._thread = None
        self._audio = None
        self._model = None
        self._tmp_file = "/tmp/aiassistant_asr.wav"
        self._last_speech_time = 0.0
        self._muted = False
        self._output_enabled = True
        self._output_enabled = len(self.hotwords) == 0  # no hotwords → always on

        # Auto-detect default input device
        self.device_index = device_index
        if self.device_index is None and PYAUDIO_AVAILABLE:
            try:
                audio = pyaudio.PyAudio()
                default_info = audio.get_default_input_device_info()
                self.device_index = default_info.get("index", 0)
                audio.terminate()
            except Exception:
                self.device_index = 0

    @staticmethod
    def list_audio_devices():
        """Print available input devices and supported sample rates."""
        if not PYAUDIO_AVAILABLE:
            print("PyAudio not installed. Run: pip install pyaudio")
            return

        test_rates = [8000, 16000, 22050, 44100, 48000, 96000]
        audio = pyaudio.PyAudio()
        device_count = audio.get_device_count()

        print("Audio input devices:")
        for i in range(device_count):
            info = audio.get_device_info_by_index(i)
            if info.get("maxInputChannels") > 0:
                print(f"  [{i}] {info['name']} (max inputs: {info['maxInputChannels']}, "
                      f"default rate: {int(info['defaultSampleRate'])} Hz)")
                supported = []
                for rate in test_rates:
                    try:
                        audio.is_format_supported(rate, input_device=info["index"],
                                                   input_channels=1, input_format=pyaudio.paInt16)
                        supported.append(str(rate))
                    except ValueError:
                        pass
                if supported:
                    print(f"      supported rates: {', '.join(supported)}")
        audio.terminate()

    def _init_model(self):
        if self._model is not None:
            return
        if self._recognizer is not None:
            if self._recognizer_name == "whisper":
                _load_whisper_model()
            return
        self._model = _load_funasr_model()
        if self._model is not None:
            logger.info("FunASR model loaded")

    def _recognize(self, audio_data: bytes) -> str:
        self._init_model()
        if self._recognizer is not None:
            return self._recognizer(self._tmp_file)
        if self._model is None:
            return ""
        try:
            result = self._model.generate(input=self._tmp_file)
            if result and len(result) > 0:
                return result[0].get("text", "").strip()
        except Exception:
            logger.error(traceback.format_exc())
        return ""

    def _save_wav(self, audio_data: bytes):
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        if LIBROSA_AVAILABLE and self.sample_rate != self.target_rate:
            audio_float = audio_np.astype(np.float32) / 32768.0
            audio_float = librosa.resample(
                audio_float,
                orig_sr=self.sample_rate,
                target_sr=self.target_rate,
            )
            audio_np = (audio_float * 32767.0).astype(np.int16)
            out_rate = self.target_rate
        else:
            out_rate = self.sample_rate

        with wave.open(self._tmp_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(out_rate)
            wf.writeframes(audio_np.astype(np.int16).tobytes())

    def start(self):
        if not PYAUDIO_AVAILABLE:
            logger.error("PyAudio not installed — cannot start ASR")
            return
        if not WEBRTCVAD_AVAILABLE:
            logger.error("WebRTC VAD not installed — cannot start ASR")
            return

        # Check model availability early so the user knows immediately
        if self._recognizer_name == "whisper":
            try:
                import whisper  # noqa: F401
            except ImportError:
                logger.error("openai-whisper not installed — ASR will not transcribe. Run: pip install openai-whisper")
        else:
            try:
                import torch  # noqa: F401
            except ImportError:
                logger.error("torch not installed — ASR will not transcribe. Run: pip install torch")

        # Preload ASR model so first transcription doesn't lag
        self._init_model()

        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info(f"HalASR started — device={self.device_index}, rate={self.sample_rate}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._audio:
            self._audio.terminate()
            self._audio = None
        logger.info("HalASR stopped")

    def mute(self):
        """Mute output and discard buffered audio during TTS playback."""
        self._output_enabled = False
        self._muted = True
        logger.debug("HalASR muted")

    def unmute(self):
        """Unmute and resume normal listening."""
        self._muted = False
        self._output_enabled = True
        self._last_speech_time = time.time()
        logger.debug("HalASR unmuted")

    def pause(self):
        self._output_enabled = False
        logger.debug("HalASR output paused")

    def resume(self):
        self._output_enabled = True
        self._last_speech_time = time.time()
        logger.debug("HalASR output resumed")

    def _listen_loop(self):
        vad = webrtcvad.Vad()
        vad.set_mode(self.vad_mode)

        self._audio = pyaudio.PyAudio()

        try:
            stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk,
                input_device_index=self.device_index,
            )
        except OSError as e:
            logger.error(
                f"Failed to open microphone device {self.device_index}: {e}. "
                f"Use HalASRBackend.list_audio_devices() to find valid devices."
            )
            return

        logger.info("Listening continuously...")
        self._last_speech_time = time.time()

        while self._running:
            audio_chunks = []
            recording = False
            last_voice_time = time.time()

            try:
                while self._running:
                    data = stream.read(self.chunk, exception_on_overflow=False)
                    is_speech = vad.is_speech(data, self.sample_rate)

                    if is_speech and not recording:
                        logger.debug("Voice detected, recording...")
                        recording = True
                        if self.on_recording_start:
                            self.on_recording_start()

                    if is_speech:
                        last_voice_time = time.time()

                    if recording:
                        audio_chunks.append(data)
                    else:
                        audio_chunks = [data]

                    silence_elapsed = time.time() - last_voice_time
                    if recording and silence_elapsed > self.silence_duration:
                        logger.debug("Silence — ending segment")
                        break
            except OSError:
                break

            if not recording or not audio_chunks:
                continue

            if self._muted:
                logger.debug("Muted — discarding segment")
                continue

            if self.on_recording_end:
                self.on_recording_end()

            # Process the recorded segment
            try:
                audio_data = b"".join(audio_chunks)
                self._save_wav(audio_data)
                text = self._recognize(audio_data)

                if text:
                    # Check hotwords
                    if not self._output_enabled:
                        for hw in self.hotwords:
                            if hw.lower() in text.lower():
                                self._output_enabled = True
                                self._last_speech_time = time.time()
                                logger.info(f"Hotword detected: {hw}")
                                break

                    # Hotword timeout
                    if self.hotwords and time.time() - self._last_speech_time > self.speech_timeout:
                        self._output_enabled = False

                    if self._output_enabled and self.on_text:
                        self.on_text(text)
                        self._last_speech_time = time.time()

            except Exception:
                logger.error(traceback.format_exc())

        stream.stop_stream()
        stream.close()
        self._audio.terminate()
        self._audio = None
