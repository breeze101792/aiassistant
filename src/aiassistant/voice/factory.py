"""Voice backend factory.

Selects the VAD, ASR, and TTS backends from config. An unknown value is a hard
error naming the value, never a silent fallback to a default (REQ-BACKEND-002).
The reasoning factory (``reasoning/factory.py``) established this rule; voice
adopts it after the stub fallback hid a broken mic path for weeks (ADR-0018).

Each backend is imported lazily, so an uninstalled optional dependency is only
an error when that backend is actually selected.
"""

import logging
import os

from aiassistant.voice.asr.asr_backends.base import ASRBackend
from aiassistant.voice.tts.tts_backends.base import TTSBackend
from aiassistant.voice.vad import (
    ENERGY_THRESHOLD,
    WEBRTC_AGGRESSIVENESS,
    VADBackend,
)

logger = logging.getLogger(__name__)

# Documented defaults. ASR is offline by default (faster-whisper): no api key,
# no account, no hosted provider. The only network backend targets a server you
# run yourself, with no built-in endpoint.
DEFAULT_ASR_BACKEND = "faster_whisper"
DEFAULT_TTS_BACKEND = "edge_tts"
DEFAULT_VAD_BACKEND = "energy"

HALASR_REMOVED = (
    "voice backend 'halasr' was removed in ADR-0018; use 'faster_whisper' "
    "(offline, default), 'whisper_server' (self-hosted), 'whisper', 'funasr', "
    "or 'stub'"
)


class VoiceConfigError(ValueError):
    """Raised when the configured voice backend cannot be constructed."""


def create_vad(cfg: dict) -> VADBackend:
    """Build a VAD from a ``voice.vad``-shaped section."""
    name = (cfg.get("backend") or DEFAULT_VAD_BACKEND).strip().lower()

    if name == "energy":
        from aiassistant.voice.vad import EnergyVAD

        threshold = cfg.get("energy_threshold")
        return EnergyVAD(threshold=ENERGY_THRESHOLD if threshold is None else threshold)

    if name == "webrtc":
        from aiassistant.voice.vad import WebRTCVAD

        aggressiveness = cfg.get("aggressiveness")
        return WebRTCVAD(
            aggressiveness=WEBRTC_AGGRESSIVENESS if aggressiveness is None
            else aggressiveness
        )

    raise VoiceConfigError(
        f"Unknown voice.vad.backend {name!r}. Supported: 'energy', 'webrtc'."
    )


def create_asr(cfg: dict) -> ASRBackend:
    """Build an ASR backend from a ``voice.asr``-shaped section.

    No backend here requires an API key or a hosted account. The network
    backend (``local_whisper``) targets a server you run yourself.
    """
    name = (cfg.get("backend") or DEFAULT_ASR_BACKEND).strip().lower()

    if name == "stub":
        from aiassistant.voice.asr.asr_backends.stub import StubASR

        return StubASR()

    if name == "faster_whisper":
        from aiassistant.voice.asr.asr_backends.faster_whisper import (
            FasterWhisperBackend,
        )

        return FasterWhisperBackend(
            model=cfg.get("model") or "base",
            device=cfg.get("device") or "cpu",
            compute_type=cfg.get("compute_type") or "int8",
            language=cfg.get("language", ""),
        )

    if name == "whisper_server":
        from aiassistant.voice.asr.asr_backends.whisper_server import (
            WhisperServerBackend,
        )

        # Key support is generic: use config, then the named env var. A
        # self-hosted server ignores the key entirely.
        api_key_env = cfg.get("api_key_env") or "ASR_API_KEY"
        return WhisperServerBackend(
            model=cfg.get("model") or "whisper-1",
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key") or os.environ.get(api_key_env, ""),
            language=cfg.get("language", ""),
            api_key_env=api_key_env,
        )

    if name == "whisper":
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend

        return WhisperBackend(model=cfg.get("model") or "base")

    if name == "funasr":
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend

        return FunASRBackend()

    if name == "halasr":
        raise VoiceConfigError(HALASR_REMOVED)

    if name in ("groq", "openai"):
        raise VoiceConfigError(
            f"voice.asr.backend {name!r} was removed: this project ships no "
            f"hosted or paid ASR service. Use 'faster_whisper' (offline, "
            f"default) or 'whisper_server' with voice.asr.base_url set to your "
            f"own server."
        )

    raise VoiceConfigError(
        f"Unknown voice.asr.backend {name!r}. Supported: 'faster_whisper', "
        f"'whisper_server', 'whisper', 'funasr', 'stub'."
    )


def create_tts(cfg: dict) -> TTSBackend:
    """Build a TTS backend from a ``voice.tts``-shaped section."""
    name = (cfg.get("backend") or DEFAULT_TTS_BACKEND).strip().lower()

    if name == "edge_tts":
        from aiassistant.voice.tts.tts_backends.edge_tts import EdgeTTSBackend

        return EdgeTTSBackend(
            voice=cfg.get("voice") or "en-US-AriaNeural",
            speed=cfg.get("speed", 1.0),
        )

    if name == "text":
        from aiassistant.voice.tts.tts_backends.text import TextTTS

        return TextTTS()

    raise VoiceConfigError(
        f"Unknown voice.tts.backend {name!r}. Supported: 'edge_tts', 'text'."
    )
