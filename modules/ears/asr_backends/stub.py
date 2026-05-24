from modules.ears.asr_backends.base import ASRBackend


class StubASR(ASRBackend):
    """Returns placeholder — no microphone available."""

    def transcribe(self, audio_bytes: bytes) -> dict:
        return {
            "text": "No microphone available (stub backend)",
            "confidence": 0.0,
            "language": "en",
        }
