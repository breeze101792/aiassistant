"""Wake-phrase detection.

Sits behind an interface so the detection strategy can change without touching
`voice/`. The default matches wake phrases against ASR output, which reuses the
existing hotword path and adds no dependency. A dedicated keyword-spotting
engine runs before ASR at much lower CPU and can replace this later
(REQ-WAKE-003).
"""

import logging
import re

logger = logging.getLogger(__name__)


class WakeDetector:
    """Whether a transcript opens a turn, and what the command part is."""

    def should_wake(self, text: str) -> bool:
        raise NotImplementedError

    def strip_wake(self, text: str) -> str:
        raise NotImplementedError


class AsrHotwordDetector(WakeDetector):
    """Match configured wake phrases against transcribed text.

    Matching is case-insensitive and punctuation-tolerant, because ASR output
    rarely reproduces a phrase exactly. The phrase must appear as a whole word
    so "hey jarvisx" does not wake.
    """

    def __init__(self, phrases: list[str]):
        self.phrases = [p.strip() for p in (phrases or []) if p and p.strip()]
        self._patterns = [self._compile(p) for p in self.phrases]

    @staticmethod
    def _compile(phrase: str) -> re.Pattern:
        words = [re.escape(w) for w in phrase.split()]
        body = r"[\s,.\-!?]*".join(words)  # tolerate ASR punctuation between words
        return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)

    def should_wake(self, text: str) -> bool:
        if not self._patterns:
            # No phrase configured means every utterance is addressed to the
            # assistant, which is what "always listening" should do.
            return True
        return any(p.search(text or "") for p in self._patterns)

    def strip_wake(self, text: str) -> str:
        """Remove the first matching phrase and return the remainder.

        The remainder is the command. An empty remainder means the user said
        only the wake phrase, which opens a capture window instead of a turn.
        """
        for pattern in self._patterns:
            match = pattern.search(text or "")
            if match:
                return (text[:match.start()] + text[match.end():]).strip(" ,.!?-")
        return (text or "").strip()


class AlwaysAwakeDetector(WakeDetector):
    """`open` mode: every segment is addressed to the assistant."""

    def should_wake(self, text: str) -> bool:
        return True

    def strip_wake(self, text: str) -> str:
        return (text or "").strip()


def create_detector(mode: str, phrases: list[str]) -> WakeDetector:
    """`ptt` and `wake` use phrase matching; `open` accepts everything.

    In `ptt` mode the microphone is armed by the user, so a phrase is not
    required even if one is configured.
    """
    if mode == "open":
        return AlwaysAwakeDetector()
    return AsrHotwordDetector(phrases)
