"""Voice factory tests (ADR-0018): selection by name, hard errors, lazy imports.

REQ-BACKEND-002: an unknown backend is a hard error naming the value, never a
silent fallback. Each backend is imported lazily, so an uninstalled optional
dependency is only an error when that backend is actually selected.
"""

import builtins
import subprocess
import sys

import pytest

from aiassistant.voice.factory import (
    DEFAULT_ASR_BACKEND,
    DEFAULT_TTS_BACKEND,
    DEFAULT_VAD_BACKEND,
    HALASR_REMOVED,
    VoiceConfigError,
    create_asr,
    create_tts,
    create_vad,
)

# Optional backends that must not be imported unless selected. ``webrtcvad``
# also needs pkg_resources, which a minimal venv lacks.
OPTIONAL_MODULES = ("faster_whisper", "funasr", "whisper", "webrtcvad")


class TestCreateVAD:
    def test_default_is_energy(self):
        from aiassistant.voice.vad import EnergyVAD

        vad = create_vad({})
        assert isinstance(vad, EnergyVAD)
        assert DEFAULT_VAD_BACKEND == "energy"

    def test_energy_threshold_is_read(self):
        vad = create_vad({"backend": "energy", "energy_threshold": 0.5})
        assert vad.threshold == 0.5

    def test_energy_uses_the_documented_default_when_unset(self):
        from aiassistant.voice.vad import ENERGY_THRESHOLD

        assert create_vad({"backend": "energy"}).threshold == ENERGY_THRESHOLD

    def test_unknown_vad_names_the_value(self):
        with pytest.raises(VoiceConfigError, match="nonsense"):
            create_vad({"backend": "nonsense"})

    def test_webrtc_without_the_dependency_names_the_fix(self):
        try:
            import webrtcvad  # noqa: F401
        except Exception:
            pass
        else:
            pytest.skip("webrtcvad is importable here")
        with pytest.raises(RuntimeError, match="webrtcvad is not installed"):
            create_vad({"backend": "webrtc"})


class TestCreateASR:
    def test_default_is_offline_faster_whisper(self):
        """No default may require a key or a paid service."""
        from aiassistant.voice.asr.asr_backends.faster_whisper import (
            FasterWhisperBackend,
        )

        backend = create_asr({})
        assert isinstance(backend, FasterWhisperBackend)
        assert DEFAULT_ASR_BACKEND == "faster_whisper"

    def test_stub_selects_the_stub(self):
        from aiassistant.voice.asr.asr_backends.stub import StubASR

        assert isinstance(create_asr({"backend": "stub"}), StubASR)

    def test_whisper_server_targets_a_self_hosted_endpoint(self):
        from aiassistant.voice.asr.asr_backends.whisper_server import (
            WhisperServerBackend,
        )

        backend = create_asr({
            "backend": "whisper_server",
            "model": "whisper-1",
            "base_url": "http://192.168.1.10:8080/v1",
        })
        assert isinstance(backend, WhisperServerBackend)
        assert backend.model == "whisper-1"
        assert backend.base_url == "http://192.168.1.10:8080/v1"

    def test_whisper_server_preflight_requires_an_explicit_url(self):
        """There is no hosted default endpoint to fall back to."""
        backend = create_asr({"backend": "whisper_server"})
        assert backend.preflight()
        ready = create_asr({"backend": "whisper_server",
                            "base_url": "http://127.0.0.1:8080/v1"})
        assert ready.preflight() == ""

    def test_whisper_server_key_falls_back_to_its_named_env(self, monkeypatch):
        monkeypatch.setenv("ASR_API_KEY", "env-key")
        backend = create_asr({"backend": "whisper_server",
                              "base_url": "http://127.0.0.1:8080/v1"})
        assert backend.api_key == "env-key"

    def test_whisper_server_config_key_beats_the_environment(self, monkeypatch):
        monkeypatch.setenv("ASR_API_KEY", "env-key")
        backend = create_asr({"backend": "whisper_server",
                              "base_url": "http://127.0.0.1:8080/v1",
                              "api_key": "cfg-key"})
        assert backend.api_key == "cfg-key"

    def test_hosted_backends_are_removed(self):
        """No hosted or paid service ships in this project."""
        for name in ("groq", "openai"):
            with pytest.raises(VoiceConfigError, match="removed"):
                create_asr({"backend": name})

    def test_whisper_selects_whisper(self):
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend

        assert isinstance(create_asr({"backend": "whisper"}), WhisperBackend)

    def test_funasr_selects_funasr(self):
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend

        assert isinstance(create_asr({"backend": "funasr"}), FunASRBackend)

    def test_faster_whisper_selects_faster_whisper(self):
        from aiassistant.voice.asr.asr_backends.faster_whisper import (
            FasterWhisperBackend,
        )

        assert isinstance(create_asr({"backend": "faster_whisper"}), FasterWhisperBackend)

    def test_faster_whisper_reads_model_and_language(self):
        backend = create_asr({
            "backend": "faster_whisper", "model": "small", "language": "en",
        })
        assert backend.model_name == "small"
        assert backend.language == "en"

    def test_unknown_backend_is_a_hard_error_naming_the_value(self):
        with pytest.raises(VoiceConfigError, match="does-not-exist"):
            create_asr({"backend": "does-not-exist"})

    def test_halasr_raises_the_removal_message(self):
        """ADR-0018 removed halasr; the error must name the replacements."""
        with pytest.raises(VoiceConfigError, match="removed in ADR-0018"):
            create_asr({"backend": "halasr"})

    def test_halasr_message_names_the_replacements(self):
        assert "funasr" in HALASR_REMOVED
        assert "faster_whisper" in HALASR_REMOVED

    def test_name_matching_is_case_and_space_insensitive(self):
        from aiassistant.voice.asr.asr_backends.stub import StubASR

        assert isinstance(create_asr({"backend": "  STUB  "}), StubASR)


class TestCreateTTS:
    def test_default_is_edge_tts(self):
        from aiassistant.voice.tts.tts_backends.edge_tts import EdgeTTSBackend

        backend = create_tts({})
        assert isinstance(backend, EdgeTTSBackend)
        assert DEFAULT_TTS_BACKEND == "edge_tts"

    def test_text_selects_text(self):
        from aiassistant.voice.tts.tts_backends.text import TextTTS

        assert isinstance(create_tts({"backend": "text"}), TextTTS)

    def test_edge_tts_reads_voice_and_speed(self):
        backend = create_tts({"backend": "edge_tts", "voice": "en-GB-RyanNeural",
                              "speed": 1.5})
        assert backend.voice == "en-GB-RyanNeural"
        assert backend.speed == 1.5

    def test_unknown_tts_names_the_value(self):
        with pytest.raises(VoiceConfigError, match="espeak"):
            create_tts({"backend": "espeak"})


class TestLazyImports:
    def test_selecting_one_backend_attempts_no_optional_import(self, monkeypatch):
        """The factory must not import a backend it was not asked for."""
        attempted: list[str] = []
        real_import = builtins.__import__

        def spy(name, *args, **kwargs):
            attempted.append(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", spy)
        create_asr({"backend": "stub"})
        create_vad({"backend": "energy"})
        create_tts({"backend": "text"})

        for optional in OPTIONAL_MODULES:
            assert not any(optional in name for name in attempted), (
                f"{optional} was imported while selecting a different backend"
            )

    def test_importing_the_factory_pulls_no_optional_backend(self):
        """A fresh interpreter proves the module import itself is lazy."""
        code = (
            "import sys\n"
            "from aiassistant.voice import factory\n"
            "bad = [m for m in sys.modules "
            "if any(o in m for o in "
            "('faster_whisper', 'funasr', 'whisper', 'webrtcvad'))]\n"
            "print(','.join(sorted(bad)))\n"
        )
        result = subprocess.run([sys.executable, "-c", code],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "", (
            f"optional backends imported at factory import: {result.stdout.strip()}"
        )


class TestPreflightAtSetup:
    """A backend that cannot run must fail once at setup, not on every segment.

    `setup()` calls `preflight()`; a message means voice is disabled cleanly.
    """

    def test_default_backend_reports_a_missing_package(self, monkeypatch):
        import builtins

        from aiassistant.voice.asr.asr_backends.faster_whisper import (
            FasterWhisperBackend,
        )

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("no faster_whisper")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        problem = FasterWhisperBackend().preflight()
        assert "faster-whisper is not installed" in problem

    def test_stub_backend_needs_nothing(self):
        assert create_asr({"backend": "stub"}).preflight() == ""


class TestFasterWhisperDefaults:
    """The offline default must not require a GPU. CTranslate2's 'auto' picks
    CUDA and fails without libcublas, so cpu is the shipped default."""

    def test_default_device_is_cpu(self):
        backend = create_asr({"backend": "faster_whisper"})
        assert backend.device == "cpu"
        assert backend.compute_type == "int8"

    def test_device_can_be_overridden(self):
        backend = create_asr({"backend": "faster_whisper", "device": "cuda",
                              "compute_type": "float16"})
        assert backend.device == "cuda"
        assert backend.compute_type == "float16"
