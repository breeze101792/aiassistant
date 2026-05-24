class TTSBackend:
    """Abstract interface for text-to-speech engines."""

    def speak(self, text: str, voice: str | None = None, speed: float = 1.0) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass
