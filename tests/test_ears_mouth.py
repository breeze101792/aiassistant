import os
import tempfile
import wave

import pytest

from modules.ears.ears import EarsModule
from modules.ears.asr_backends.stub import StubASR
from modules.ears.asr_backends.base import ASRBackend
from modules.ears.asr_backends.halasr import HalASRBackend, _load_funasr_model
from modules.mouth.mouth import MouthModule
from modules.mouth.tts_backends.text import TextTTS
from modules.mouth.tts_backends.base import TTSBackend
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
        # should not crash

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

        # Generate loud noise
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
        # At minimum, 20ms frames should be valid at all rates
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
        backend.start()  # should not crash, just log error
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
        # Simulate torch not installed
        with monkeypatch.context() as ctx:
            ctx.setitem(sys.modules, "torch", None)
            model = _load_funasr_model()
        assert model is None


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
        # Prevent real audio thread from spawning in test
        monkeypatch.setattr(ears._backend, "start", lambda: None)
        await ears.start()
        assert ears._state == 'listening'  # halasr auto-starts


class TestTextTTS:
    def test_speak_prints_to_stdout(self, capsys):
        tts = TextTTS()
        tts.speak('Hello world')
        captured = capsys.readouterr()
        assert 'Hello world' in captured.out

    def test_is_instance_of_base(self):
        assert isinstance(TextTTS(), TTSBackend)


class TestMouthModule:
    def test_module_name(self):
        bus = MessageBus()
        mouth = MouthModule(bus, {'backend': 'text'})
        assert mouth.module_name == 'mouth'

    def test_text_backend_selected(self):
        bus = MessageBus()
        mouth = MouthModule(bus, {'backend': 'text'})
        assert mouth.backend_name == 'text'
