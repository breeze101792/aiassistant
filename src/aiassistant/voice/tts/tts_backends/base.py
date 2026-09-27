"""Speech synthesis backends.

A backend **synthesizes and returns audio**; it never plays it. Playback belongs
to the voice module, which owns the output stream and the stop flag. The
pre-refactor backend called ``afplay`` itself, which is why interrupt could not
work: nothing held a handle to stop.
"""


class TTSBackend:
    """Abstract interface for speech synthesis."""

    #: Human-readable name, used in config and errors.
    name = "base"

    async def synthesize(self, text: str, voice: str | None = None,
                         speed: float = 1.0) -> bytes:
        """Return encoded audio for ``text``, or b"" when nothing was produced."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release any resources. Safe to call more than once."""

    @property
    def outputs_audio(self) -> bool:
        """False for backends that only display text."""
        return True
