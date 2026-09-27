"""Text-only output: no audio device, no synthesis.

Used when TTS is disabled or no output device exists. It still reports the
assistant's speech so a headless run stays useful (REQ-CONSOLE-001).
"""

import logging

from aiassistant.voice.tts.tts_backends.base import TTSBackend

logger = logging.getLogger(__name__)


class TextTTS(TTSBackend):
    """Prints the text that would have been spoken."""

    name = "text"

    @property
    def outputs_audio(self) -> bool:
        return False

    async def synthesize(self, text: str, voice: str | None = None,
                         speed: float = 1.0) -> bytes:
        if text.strip():
            logger.info("Assistant (spoken text): %s", text)
        return b""
