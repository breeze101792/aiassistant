class ASRBackend:
    """Abstract interface for speech recognition engines."""

    def transcribe(self, audio_bytes: bytes) -> dict:
        raise NotImplementedError
