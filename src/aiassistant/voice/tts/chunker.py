"""Sentence chunking for streaming speech.

Splitting on sentence boundaries is what makes streaming useful: the first
sentence reaches the speaker while the model is still writing the second. Wait
for the full response and the whole feature is pointless.

Pure logic with no audio dependency, so it is fully unit-testable.
"""

# Speak on sentence punctuation, or once a run gets long enough that waiting
# for punctuation would be noticeable. Both are placeholders to tune.
MIN_CHUNK_CHARS = 40
MAX_CHUNK_CHARS = 240
FLUSH_ON = ".!?。！？\n"


class SentenceChunker:
    """Accumulate streaming text and emit speakable chunks."""

    def __init__(self, min_chars: int = MIN_CHUNK_CHARS, max_chars: int = MAX_CHUNK_CHARS):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""

    def push(self, delta: str) -> list[str]:
        """Add a delta and return any complete chunks, in order."""
        if not delta:
            return []
        self._buffer += delta
        return self._drain(final=False)

    def flush(self) -> list[str]:
        """Emit whatever remains. Call at the end of a turn."""
        return self._drain(final=True)

    @property
    def pending(self) -> str:
        return self._buffer

    def reset(self) -> None:
        self._buffer = ""

    def _drain(self, *, final: bool) -> list[str]:
        out: list[str] = []
        while True:
            cut = self._find_cut(final=final)
            if cut is None:
                return out
            chunk = self._buffer[:cut].strip()
            self._buffer = self._buffer[cut:]
            if chunk:
                out.append(chunk)

    def _find_cut(self, *, final: bool) -> int | None:
        text = self._buffer

        # 1. A sentence boundary past the minimum length.
        for index in range(len(text)):
            if text[index] in FLUSH_ON and index + 1 >= self.min_chars:
                # Absorb trailing whitespace so the next chunk starts clean.
                end = index + 1
                while end < len(text) and text[end].isspace():
                    end += 1
                return end

        # 2. A run longer than the maximum, with no punctuation in sight.
        if len(text) >= self.max_chars:
            space = text.rfind(" ", 0, self.max_chars)
            return space + 1 if space > 0 else self.max_chars

        # 3. At end of turn, speak whatever is left.
        if final and text.strip():
            return len(text)

        return None
