"""One owner for the interactive prompt line.

Async output — a ready banner, a transcript line, a WARNING from any module —
can arrive while the user is sitting at an empty prompt. Printing straight to
stdout then appends to the prompt line and leaves the terminal without a prompt
at all, which is what made the console look broken.

The frontend that draws a prompt registers a writer here. Every other writer
(notably the logging handler) routes through :func:`write_above`, so its output
lands above the prompt and the prompt is redrawn. With no writer registered the
call is a plain stdout write, so a non-interactive run is unchanged.
"""

import sys
from collections.abc import Callable

# The active prompt owner, or None when nothing is drawing a prompt.
_writer: Callable[[str], None] | None = None


def set_prompt_writer(writer: Callable[[str], None] | None) -> None:
    """Register the callback that owns the prompt line. Pass None to clear."""
    global _writer
    _writer = writer


def has_prompt_writer() -> bool:
    """Whether a prompt owner is registered. Used by tests and by callers."""
    return _writer is not None


def write_above(text: str) -> None:
    """Write ``text`` so it does not corrupt an active prompt.

    The owner erases the prompt, writes the text, and redraws the prompt. With
    no owner this is an unbuffered stdout write.
    """
    if _writer is not None:
        _writer(text)
        return
    sys.stdout.write(text)
    sys.stdout.flush()
