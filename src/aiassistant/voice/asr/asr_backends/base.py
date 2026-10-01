class ASRBackend:
    """Abstract interface for speech recognition engines."""

    def transcribe(self, audio_bytes: bytes) -> dict:
        raise NotImplementedError

    def preflight(self) -> str:
        """Check the backend can run before capture starts.

        Returns an actionable message when the backend is not usable, or ``""``
        when it is ready. ``VoiceModule.setup`` calls this once, so a missing
        package or endpoint disables voice cleanly instead of failing on every
        utterance. The default is ready: a backend with no external requirement
        does not need to override this.
        """
        return ""

    def close(self) -> None:
        """Release any resources. Safe to call more than once."""
