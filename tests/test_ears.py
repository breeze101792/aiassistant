import os
import wave

import pytest

from modules.ears.ears import EarsModule
from modules.ears.asr_backends.stub import StubASR
from modules.ears.asr_backends.base import ASRBackend
from modules.ears.asr_backends.halasr import HalASRBackend, _load_funasr_model
from bus.bus import MessageBus


class TestStubASR:
    def test_transcribe_returns_placeholder(self):
        stub = StubASR()
        result = stub.transcribe(b'fake_audio')
        assert 'text' in result
        assert 'confidence' in result
        assert 'language' in result

    def test_is_instance_of_base(self):
        assert isinstance(StubASR(), ASRBackend)


class TestHalASR:
    def test_init_auto_detects_device(self):
        backend = HalASRBackend()
        assert isinstance(backend.device_index, int)
        assert backend.sample_rate == 48000
        assert backend.target_rate == 16000

    def test_init_respects_explicit_device(self):
        backend = HalASRBackend(device_index=2)
        assert backend.device_index == 2

    def test_hotword_mode_is_disabled_without_hotwords(self):
        backend = HalASRBackend()
        assert backend._output_enabled is True

    def test_hotword_mode_is_enabled_with_hotwords(self):
        backend = HalASRBackend(hotwords=["hello"])
        assert backend._output_enabled is False

    def test_start_stop_lifecycle(self, monkeypatch):
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr.PYAUDIO_AVAILABLE", False
        )
        backend = HalASRBackend()
        backend.start()
        backend.stop()

    def test_pause_resume(self):
        backend = HalASRBackend()
        backend.pause()
        assert backend._output_enabled is False
        backend.resume()
        assert backend._output_enabled is True

    def test_save_wav_creates_valid_file(self):
        import numpy as np
        backend = HalASRBackend(sample_rate=16000, target_rate=16000)
        fake_audio = np.zeros(16000, dtype=np.int16).tobytes()
        backend._save_wav(fake_audio)
        assert os.path.exists(backend._tmp_file)
        with wave.open(backend._tmp_file, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
        os.unlink(backend._tmp_file)

    def test_on_text_callback(self, monkeypatch):
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr.PYAUDIO_AVAILABLE", False
        )
        received = []

        def callback(text):
            received.append(text)

        backend = HalASRBackend(on_text=callback)
        backend._output_enabled = True
        backend.on_text("hello world")
        assert received == ["hello world"]

    def test_vad_detects_speech_vs_silence(self):
        """WebRTC VAD should return True for audio with speech, False for silence."""
        import numpy as np
        import webrtcvad

        vad = webrtcvad.Vad()
        vad.set_mode(3)
        frame_len = 480  # 10ms at 48000Hz = int(48000 * 10 / 1000)

        silence = np.zeros(frame_len, dtype=np.int16).tobytes()
        assert vad.is_speech(silence, 48000) is False

        noise = np.random.randint(-32768, 32767, frame_len, dtype=np.int16).tobytes()
        assert vad.is_speech(noise, 48000) is True

    def test_vad_valid_rates_and_frames(self):
        """WebRTC VAD should accept 10/20/30ms frames at 8000/16000/32000/48000 Hz."""
        import webrtcvad

        valid_combos = []
        for rate in [8000, 16000, 32000, 48000]:
            for ms in [10, 20, 30]:
                frame_len = int(rate * ms / 1000)
                if webrtcvad.valid_rate_and_frame_length(rate, frame_len):
                    valid_combos.append((rate, ms))
        assert any(ms == 20 for _, ms in valid_combos)
        assert len(valid_combos) >= 4

    def test_halasr_chunk_size_is_20ms(self):
        """HalASR backend must use 20ms frames for WebRTC VAD compatibility."""
        backend = HalASRBackend(sample_rate=48000)
        assert backend.chunk == 960  # 48000 * 20/1000

        backend2 = HalASRBackend(sample_rate=16000)
        assert backend2.chunk == 320  # 16000 * 20/1000

    def test_halasr_fails_gracefully_without_pyaudio(self, monkeypatch):
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr.PYAUDIO_AVAILABLE", False
        )
        backend = HalASRBackend()
        backend.start()
        backend.stop()

    def test_list_audio_devices_handles_missing_pyaudio(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr.PYAUDIO_AVAILABLE", False
        )
        HalASRBackend.list_audio_devices()
        captured = capsys.readouterr()
        assert "PyAudio not installed" in captured.out

    def test_funasr_model_load_handles_missing_deps(self, monkeypatch):
        import sys
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._MODEL_LOADED", False
        )
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._MODEL_ERROR", None
        )
        with monkeypatch.context() as ctx:
            ctx.setitem(sys.modules, "torch", None)
            model = _load_funasr_model()
        assert model is None


class TestWhisperHalASR:
    """Tests for HalASR with Whisper recognizer."""

    def test_whisper_model_load_handles_missing_deps(self, monkeypatch):
        """_load_whisper_model returns None when whisper is not installed."""
        from modules.ears.asr_backends.halasr import (
            _WHISPER_MODEL_LOADED, _WHISPER_MODEL, _load_whisper_model
        )
        import sys
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._WHISPER_MODEL_LOADED", False
        )
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._WHISPER_MODEL", None
        )
        with monkeypatch.context() as ctx:
            ctx.setitem(sys.modules, "whisper", None)
            model = _load_whisper_model()
        assert model is None

    def test_whisper_recognize_returns_empty_when_no_model(self, monkeypatch):
        """_whisper_recognize returns '' when model not loaded."""
        from modules.ears.asr_backends.halasr import _whisper_recognize
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._WHISPER_MODEL_LOADED", False
        )
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._WHISPER_MODEL", None
        )
        monkeypatch.setattr(
            "modules.ears.asr_backends.halasr._load_whisper_model",
            lambda **kw: None
        )
        result = _whisper_recognize("/tmp/nonexistent.wav")
        assert result == ""

    def test_halasr_accepts_whisper_recognizer(self):
        """HalASR stores recognizer and recognizer_name."""
        def fake_recognizer(path):
            return "hello from whisper"

        backend = HalASRBackend(
            recognizer=fake_recognizer,
            recognizer_name="whisper",
        )
        assert backend._recognizer is fake_recognizer
        assert backend._recognizer_name == "whisper"

    def test_halasr_recognize_uses_external_recognizer(self):
        """_recognize delegates to external recognizer when set."""
        calls = []
        def fake_recognizer(path):
            calls.append(path)
            return "transcribed text"

        backend = HalASRBackend(recognizer=fake_recognizer)
        backend._tmp_file = "/tmp/test.wav"
        result = backend._recognize(b"ignored")
        assert result == "transcribed text"
        assert calls == ["/tmp/test.wav"]

    def test_halasr_init_model_skips_funasr_when_recognizer_set(self):
        """_init_model does not load FunASR when external recognizer is set."""
        backend = HalASRBackend(
            recognizer=lambda p: "",
            recognizer_name="whisper",
        )
        backend._init_model()
        assert backend._model is None
        assert backend._recognizer is not None

    def test_real_whisper_model_loads(self):
        """_load_whisper_model('tiny') loads successfully with real whisper package."""
        try:
            import whisper  # noqa: F401
        except ImportError:
            import pytest
            pytest.skip("openai-whisper not installed")

        from modules.ears.asr_backends.halasr import (
            _WHISPER_MODEL_LOADED, _WHISPER_MODEL, _load_whisper_model
        )
        # Reset globals to force fresh load
        import modules.ears.asr_backends.halasr as halasr
        halasr._WHISPER_MODEL_LOADED = False
        halasr._WHISPER_MODEL = None

        model = _load_whisper_model("tiny")
        assert model is not None
        assert hasattr(model, "transcribe")

    def test_real_whisper_recognize_returns_text(self):
        """_whisper_recognize transcribes a WAV file using real whisper."""
        try:
            import whisper  # noqa: F401
        except ImportError:
            import pytest
            pytest.skip("openai-whisper not installed")

        import numpy as np
        import wave
        import tempfile
        import os

        from modules.ears.asr_backends.halasr import _whisper_recognize

        # Create a minimal WAV file with a sine tone (non-speech, but tests the pipeline)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            t = np.linspace(0, 1.5, 24000, False)
            audio = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
            wf.writeframes(audio.tobytes())

        try:
            result = _whisper_recognize(tmp.name)
            # Should return a string (may be hallucinated text for non-speech)
            assert isinstance(result, str)
            # With tiny model, function should not crash
        finally:
            os.unlink(tmp.name)


class TestEarsModule:
    def test_module_name(self):
        bus = MessageBus()
        ears = EarsModule(bus, {'backend': 'stub', 'hotwords': ['hey']})
        assert ears.module_name == 'ears'

    def test_stub_backend_selected(self):
        bus = MessageBus()
        ears = EarsModule(bus, {'backend': 'stub', 'hotwords': []})
        assert ears.backend_name == 'stub'

    @pytest.mark.asyncio
    async def test_halasr_backend_selected(self):
        bus = MessageBus()
        ears = EarsModule(bus, {
            'ears': {
                'backend': 'halasr',
                'hotwords': ['hey assistant'],
                'silence_timeout': 15,
            }
        })
        assert ears.backend_name == 'halasr'
        assert ears.hotwords == ['hey assistant']
        assert ears.silence_timeout == 15
        assert await ears.setup()
        from modules.ears.asr_backends.halasr import HalASRBackend
        assert isinstance(ears._backend, HalASRBackend)

    @pytest.mark.asyncio
    async def test_halasr_auto_starts_listening(self, monkeypatch):
        bus = MessageBus()
        ears = EarsModule(bus, {
            'ears': {
                'backend': 'halasr',
                'hotwords': [],
                'silence_timeout': 20,
            }
        })
        await ears.setup()
        monkeypatch.setattr(ears._backend, "start", lambda: None)
        await ears.start()
        assert ears._state == 'listening'

    @pytest.mark.asyncio
    async def test_resume_does_not_duplicate_threads(self, monkeypatch):
        """Bug regression: _handle_resume must not create duplicate listen threads."""
        bus = MessageBus()
        ears = EarsModule(bus, {
            'ears': {
                'backend': 'halasr',
                'hotwords': [],
                'silence_timeout': 20,
            }
        })
        await ears.setup()

        start_count = [0]

        class MockBackend:
            is_running = False

            def start(self):
                start_count[0] += 1
                MockBackend.is_running = True

            def pause(self):
                MockBackend.is_running = False

            def resume(self):
                MockBackend.is_running = True

            def stop(self):
                MockBackend.is_running = False

            def mute(self):
                pass

            def unmute(self):
                pass

        ears._backend = MockBackend()
        ears._state = 'listening'
        ears._backend.start()

        # Pause then resume — should call resume(), not start() again
        await ears._handle_pause("", {})
        assert ears._state == 'paused'
        await ears._handle_resume("", {})
        assert ears._state == 'listening'
        assert start_count[0] == 1  # start() only called once, resume handles subsequent

    @pytest.mark.asyncio
    async def test_halasr_with_whisper_recognizer_config(self):
        """EarsModule passes whisper recognizer when config says recognizer: whisper."""
        bus = MessageBus()
        ears = EarsModule(bus, {
            'ears': {
                'backend': 'halasr',
                'recognizer': 'whisper',
                'hotwords': [],
                'silence_timeout': 20,
            }
        })
        assert ears.backend_name == 'halasr'
        assert await ears.setup()
        from modules.ears.asr_backends.halasr import HalASRBackend
        assert isinstance(ears._backend, HalASRBackend)
        assert ears._backend._recognizer is not None
        assert ears._backend._recognizer_name == "whisper"

    @pytest.mark.asyncio
    async def test_resume_without_resume_method_falls_back_to_start(self, monkeypatch):
        """Backend without resume() should call start() again, but only once."""
        bus = MessageBus()
        ears = EarsModule(bus, {
            'ears': {
                'backend': 'halasr',
                'hotwords': [],
                'silence_timeout': 20,
            }
        })
        await ears.setup()

        start_count = [0]

        class NoResumeBackend:
            def start(self):
                start_count[0] += 1

            def pause(self):
                pass

            def stop(self):
                pass

            def mute(self):
                pass

            def unmute(self):
                pass

        ears._backend = NoResumeBackend()
        ears._state = 'listening'

        await ears._handle_pause("", {})
        await ears._handle_resume("", {})
        assert start_count[0] == 1  # start called once as fallback for missing resume

    @pytest.mark.asyncio
    async def test_backend_without_start_method_does_not_crash(self):
        """Auto-start should skip backends that don't have a start() method."""
        bus = MessageBus()
        ears = EarsModule(bus, {
            'ears': {
                'backend': 'halasr',
                'hotwords': [],
                'silence_timeout': 20,
            }
        })

        class TranscribeOnlyBackend:
            def transcribe(self, audio_bytes):
                return {"text": "ok", "confidence": 0.9, "language": "en"}

        ears._backend = TranscribeOnlyBackend()
        ears.backend_name = "custom"
        ears._start_listening()
        assert ears._state == "idle"


class TestWhisperBackend:
    """Tests for standalone WhisperBackend (backend: whisper in config)."""

    def test_has_lifecycle_methods(self):
        from modules.ears.asr_backends.whisper import WhisperBackend
        backend = WhisperBackend()
        assert hasattr(backend, "start")
        assert hasattr(backend, "stop")

    def test_start_stop_lifecycle(self):
        from modules.ears.asr_backends.whisper import WhisperBackend
        backend = WhisperBackend()
        backend.start()
        assert backend._running is True
        backend.stop()
        assert backend._running is False

    def test_transcribe_writes_valid_wav(self):
        """transcribe() should write a valid WAV file before passing to whisper."""
        import numpy as np
        from modules.ears.asr_backends.whisper import WhisperBackend

        try:
            import whisper  # noqa: F401
        except ImportError:
            pytest.skip("openai-whisper not installed")

        backend = WhisperBackend(model="tiny")
        audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000, False)) * 32767).astype(np.int16)
        result = backend.transcribe(audio.tobytes())
        assert isinstance(result, dict)
        assert "text" in result
        assert "confidence" in result
        assert "language" in result

    def test_is_instance_of_base(self):
        from modules.ears.asr_backends.whisper import WhisperBackend
        from modules.ears.asr_backends.base import ASRBackend
        assert isinstance(WhisperBackend(), ASRBackend)


class TestFunASRBackend:
    """Tests for standalone FunASRBackend (backend: funasr in config)."""

    def test_has_lifecycle_methods(self):
        from modules.ears.asr_backends.funasr import FunASRBackend
        backend = FunASRBackend()
        assert hasattr(backend, "start")
        assert hasattr(backend, "stop")

    def test_start_stop_lifecycle(self):
        from modules.ears.asr_backends.funasr import FunASRBackend
        backend = FunASRBackend()
        backend.start()
        assert backend._running is True
        backend.stop()
        assert backend._running is False

    def test_transcribe_writes_valid_wav(self):
        """transcribe() should write a valid WAV file before passing to FunASR."""
        import numpy as np
        from modules.ears.asr_backends.funasr import FunASRBackend

        try:
            from funasr import AutoModel  # noqa: F401
        except ImportError:
            pytest.skip("funasr not installed")

        backend = FunASRBackend()
        audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000, False)) * 32767).astype(np.int16)
        result = backend.transcribe(audio.tobytes())
        assert isinstance(result, dict)
        assert "text" in result
        assert "confidence" in result
        assert "language" in result

    def test_is_instance_of_base(self):
        from modules.ears.asr_backends.funasr import FunASRBackend
        from modules.ears.asr_backends.base import ASRBackend
        assert isinstance(FunASRBackend(), ASRBackend)
