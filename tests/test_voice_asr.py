import pytest

from aiassistant.voice.module import VoiceModule
from aiassistant.voice.asr.asr_backends.stub import StubASR
from aiassistant.voice.asr.asr_backends.base import ASRBackend
from aiassistant.bus.bus import MessageBus


class TestStubASR:
    def test_transcribe_returns_placeholder(self):
        stub = StubASR()
        result = stub.transcribe(b'fake_audio')
        assert 'text' in result
        assert 'confidence' in result
        assert 'language' in result

    def test_is_instance_of_base(self):
        assert isinstance(StubASR(), ASRBackend)


class TestVoiceModule:
    """The merged voice module: ASR selection and the transcribe path.

    The old lifecycle internals these tests used (_start_listening, _backend)
    are gone by design: one FSM and one audio owner replaced them (ADR-0005).
    """

    def test_module_name(self):
        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub"}})
        assert mod.module_name == "voice"

    def test_stub_backend_selected(self):
        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub", "hotwords": []}})
        assert mod.asr_backend_name == "stub"

    @pytest.mark.asyncio
    async def test_stub_backend_builds(self):
        from aiassistant.voice.asr.asr_backends.stub import StubASR

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub"}})
        assert await mod.setup()
        assert isinstance(mod._asr, StubASR)

    @pytest.mark.asyncio
    async def test_unknown_backend_fails_setup_cleanly(self):
        """ADR-0018: an unknown backend is a hard error, not a stub fallback."""
        from aiassistant.voice.factory import VoiceConfigError

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"asr": {"backend": "does-not-exist"}}})
        assert await mod.setup() is False
        assert mod._asr is None

    @pytest.mark.asyncio
    async def test_config_is_read_from_the_voice_section(self):
        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {
            "backend": "stub", "hotwords": ["hey assistant"],
            "listen": {"mode": "wake"},
        }})
        assert mod.hotwords == ["hey assistant"]
        assert mod.listen_mode == "wake"

    @pytest.mark.asyncio
    async def test_transcribe_publishes_and_creates_a_turn(self):
        """The full ASR hand-off: a queued utterance becomes a voice turn."""
        import asyncio
        import threading

        from aiassistant.bus import topics

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"asr": {"backend": "stub"},
                                          "listen": {"mode": "open"}}})
        await mod.setup()
        mod.disable_audio()
        await mod.start()

        done = threading.Event()

        class FakeASR:
            def transcribe(self, audio_bytes):
                done.set()
                return {"text": "turn on the lights", "confidence": 0.9}

        mod._asr = FakeASR()
        transcripts, inputs = [], []
        bus.subscribe(topics.VOICE_TRANSCRIBED, lambda t, p: transcripts.append(p))
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))

        mod._on_utterance(b"fake wav")
        await asyncio.get_running_loop().run_in_executor(None, done.wait, 2.0)
        for _ in range(50):
            if inputs:
                break
            await asyncio.sleep(0.01)

        assert transcripts[0]["text"] == "turn on the lights"
        assert inputs[0]["channel"] == topics.CHANNEL_VOICE
        await mod.stop()

    @pytest.mark.asyncio
    async def test_asr_failure_is_classified_not_raised(self):
        import asyncio
        import threading

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"asr": {"backend": "stub"}}})
        await mod.setup()
        mod.disable_audio()
        await mod.start()

        done = threading.Event()

        class BrokenASR:
            def transcribe(self, audio_bytes):
                done.set()
                raise RuntimeError("decoder exploded")

        mod._asr = BrokenASR()
        errors = []
        bus.subscribe("agent.turn.error", lambda t, p: errors.append(p))
        mod._on_utterance(b"junk")  # must not raise on the worker
        await asyncio.get_running_loop().run_in_executor(None, done.wait, 2.0)
        for _ in range(50):
            if errors:
                break
            await asyncio.sleep(0.01)
        assert errors and errors[0]["class"] == "audio"
        await mod.stop()

    @pytest.mark.asyncio
    async def test_empty_transcript_produces_no_turn(self):
        import asyncio
        import threading

        from aiassistant.bus import topics

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"asr": {"backend": "stub"},
                                          "listen": {"mode": "open"}}})
        await mod.setup()
        mod.disable_audio()
        await mod.start()

        done = threading.Event()

        class SilentASR:
            def transcribe(self, audio_bytes):
                done.set()
                return {"text": "   ", "confidence": 0.1}

        mod._asr = SilentASR()
        inputs = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))
        mod._on_utterance(b"noise")
        await asyncio.get_running_loop().run_in_executor(None, done.wait, 2.0)
        await asyncio.sleep(0.05)
        assert inputs == []
        await mod.stop()

class TestWhisperBackend:
    """Tests for standalone WhisperBackend (backend: whisper in config)."""

    def test_has_lifecycle_methods(self):
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend
        backend = WhisperBackend()
        assert hasattr(backend, "start")
        assert hasattr(backend, "stop")

    def test_start_stop_lifecycle(self):
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend
        backend = WhisperBackend()
        backend.start()
        assert backend._running is True
        backend.stop()
        assert backend._running is False

    def test_transcribe_writes_valid_wav(self):
        """transcribe() should write a valid WAV file before passing to whisper."""
        import numpy as np
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend

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
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend
        from aiassistant.voice.asr.asr_backends.base import ASRBackend
        assert isinstance(WhisperBackend(), ASRBackend)


class TestFunASRBackend:
    """Tests for standalone FunASRBackend (backend: funasr in config)."""

    def test_has_lifecycle_methods(self):
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend
        backend = FunASRBackend()
        assert hasattr(backend, "start")
        assert hasattr(backend, "stop")

    def test_start_stop_lifecycle(self):
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend
        backend = FunASRBackend()
        backend.start()
        assert backend._running is True
        backend.stop()
        assert backend._running is False

    def test_transcribe_writes_valid_wav(self):
        """transcribe() should write a valid WAV file before passing to FunASR."""
        import numpy as np
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend

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
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend
        from aiassistant.voice.asr.asr_backends.base import ASRBackend
        assert isinstance(FunASRBackend(), ASRBackend)
