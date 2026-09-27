"""Turn policy: retries and fallbacks that actually act.

The pre-refactor ``Reflector`` computed RETRY and FALLBACK verdicts that nothing
ever acted on — the caller only branched on ABORT, so a retry never happened.
This module keeps the vocabulary but is consumed for real by
``NativeHarness``, which retries a failed tool call before giving up.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    """What to do after a tool attempt."""

    PROCEED = "proceed"    # the result is usable
    RETRY = "retry"        # try the same tool again
    ABORT = "abort"        # stop and report the failure


@dataclass
class Decision:
    outcome: Outcome
    summary: str = ""

    @property
    def should_retry(self) -> bool:
        return self.outcome is Outcome.RETRY


class RetryPolicy:
    """Bound the number of attempts per tool call."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def decide(self, *, result: object, error: str | None, attempt: int) -> Decision:
        """Decide what to do after ``attempt`` (0-based) of running a tool.

        A transient failure (timeout, connection) is retried; anything else
        aborts, because retrying a refused path or an unknown tool just wastes
        the user's time.
        """
        if error is None:
            if result is None:
                return Decision(Outcome.ABORT, "The tool returned no result.")
            return Decision(Outcome.PROCEED, "Result available.")

        if _is_transient(error) and attempt < self.max_retries - 1:
            return Decision(
                Outcome.RETRY,
                f"Transient failure, retrying ({attempt + 1}/{self.max_retries}): {error}",
            )
        return Decision(Outcome.ABORT, f"Tool failed: {error}")


_TRANSIENT_MARKERS = (
    "timed out", "timeout", "temporarily", "connection", "refused",
    "unavailable", "try again", "rate limit",
)


def _is_transient(error: str) -> bool:
    lowered = error.lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


def repair_and_parse_json(raw: object) -> dict:
    """Best-effort parse of a tool-call argument payload.

    Models emit malformed JSON often enough to matter: trailing commas, single
    quotes, and unescaped newlines all appear in practice. Returns an empty dict
    when the payload cannot be recovered, so a bad argument blob degrades to
    "tool called with defaults" rather than killing the turn.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}

    text = str(raw).strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    repaired = text
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)      # trailing commas
    repaired = repaired.replace("'", '"')                    # single quotes
    repaired = re.sub(r"(?<!\\)\n", " ", repaired)           # raw newlines
    try:
        parsed = json.loads(repaired)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
