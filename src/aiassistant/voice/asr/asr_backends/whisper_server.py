"""ASR via a self-hosted Whisper HTTP server (an OpenAI-compatible endpoint).

One class, one shape. A new endpoint is another class in this shape selected by
``voice.factory.create_asr`` — never a change to the pipeline. This backend is
provider-neutral: it hardcodes no hosted service.

No key is required. The usual target is a self-hosted Whisper server on your own
machine or LAN (for example ``whisper.cpp``'s ``server`` example), which needs no
``api_key``. Set ``voice.asr.base_url`` to point at one. If a deployment does
require a key, set ``voice.asr.api_key`` (or the environment variable named by
``voice.asr.api_key_env``); that support is generic, not tied to any provider.

The audio only leaves the host when ``base_url`` points somewhere other than
localhost; there is no default remote endpoint to leak to.
"""

import logging
import os
import tempfile
import wave

from aiassistant.voice.asr.asr_backends.base import ASRBackend
from aiassistant.voice.audio import CHANNELS, TARGET_SAMPLE_RATE

logger = logging.getLogger(__name__)

# 16-bit PCM.
_SAMPLE_WIDTH = 2

DEFAULT_MODEL = "whisper-1"
#: Environment variable consulted when no key is in config and the backend
#: needs one. A self-hosted server ignores the key entirely.
DEFAULT_API_KEY_ENV = "ASR_API_KEY"


class WhisperServerBackend(ASRBackend):
    """Transcribe one complete utterance with an OpenAI-compatible endpoint."""

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = "",
                 api_key: str = "", language: str = "",
                 api_key_env: str = DEFAULT_API_KEY_ENV):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.language = language
        self.api_key_env = api_key_env

    def preflight(self) -> str:
        """Require an explicit endpoint; there is no hosted default to fall to."""
        if self.base_url:
            return ""
        return (
            "No voice.asr.base_url set for the OpenAI-compatible ASR endpoint. "
            "Point it at your Whisper server (for example "
            "http://127.0.0.1:8080/v1), or use voice.asr.backend: faster_whisper "
            "for fully offline recognition."
        )

    def transcribe(self, audio_bytes: bytes) -> dict:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai is not installed; run: pip install openai"
            ) from exc

        # A self-hosted server ignores the key. The SDK requires the argument,
        # so use the configured key when present and a placeholder otherwise.
        client = OpenAI(api_key=self.api_key or "not-required", base_url=self.base_url)

        tmp_path = self._write_wav(audio_bytes)
        try:
            with open(tmp_path, "rb") as handle:
                kwargs = {"model": self.model, "file": handle}
                if self.language:
                    kwargs["language"] = self.language
                result = client.audio.transcriptions.create(**kwargs)
        finally:
            os.unlink(tmp_path)

        text = getattr(result, "text", "") or ""
        return {
            "text": text.strip(),
            "confidence": 1.0,
            "language": self.language or "",
        }

    @staticmethod
    def _write_wav(pcm: bytes) -> str:
        """Write PCM to a temp WAV and return its path (caller deletes it).

        The file is removed if the write itself fails, so a microphone WAV is
        never left behind in the temp directory.
        """
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            os.close(fd)
            with wave.open(path, "wb") as handle:
                handle.setnchannels(CHANNELS)
                handle.setsampwidth(_SAMPLE_WIDTH)
                handle.setframerate(TARGET_SAMPLE_RATE)
                handle.writeframes(pcm)
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return path
