"""Microsoft Edge TTS.

Returns MP3 bytes. Decoding to PCM is the voice module's job, so this backend
stays free of any playback concern and is trivially testable.
"""

import logging

from aiassistant.voice.tts.tts_backends.base import TTSBackend

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AriaNeural"


class EdgeTTSBackend(TTSBackend):
    """Cloud-based neural voices via the edge-tts package."""

    name = "edge_tts"

    def __init__(self, voice: str = DEFAULT_VOICE, speed: float = 1.0):
        self.voice = voice
        self.speed = speed

    async def synthesize(self, text: str, voice: str | None = None,
                         speed: float = 1.0) -> bytes:
        if not text.strip():
            return b""
        try:
            import edge_tts
        except ImportError:
            logger.warning("edge-tts is not installed; no audio will be produced")
            return b""

        rate = f"{int(((speed or self.speed) - 1.0) * 100):+d}%"
        communicate = edge_tts.Communicate(text, voice or self.voice, rate=rate)

        # Collect chunks in memory: no temporary file, so nothing can be left
        # behind and no subprocess is needed to play it.
        audio = bytearray()
        try:
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    audio.extend(chunk["data"])
        except Exception as exc:
            logger.error("edge-tts synthesis failed: %s", exc)
            return b""
        return bytes(audio)
