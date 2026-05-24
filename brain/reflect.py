from dataclasses import dataclass
from enum import Enum


class ReflectVerdict(str, Enum):
    PROCEED = "proceed"
    LOOP = "loop"
    RETRY = "retry"
    FALLBACK = "fallback"
    ABORT = "abort"


@dataclass
class ReflectDecision:
    verdict: ReflectVerdict
    summary: str = ""


class Reflector:
    """Stage 6: Evaluate tool results — do we have enough to answer?"""

    def __init__(self, max_loops: int = 3):
        self.max_loops = max_loops
        self._loop_count = 0

    def evaluate(self, tool_result: object, error: str | None = None,
                 goal: str = "") -> ReflectDecision:
        self._loop_count += 1

        if error:
            if self._loop_count <= self.max_loops:
                return ReflectDecision(
                    verdict=ReflectVerdict.RETRY,
                    summary=f"Tool failed: {error}. Will retry ({self._loop_count}/{self.max_loops})."
                )
            return ReflectDecision(
                verdict=ReflectVerdict.ABORT,
                summary=f"Tool failed after {self.max_loops} retries: {error}."
            )

        if tool_result is None:
            return ReflectDecision(
                verdict=ReflectVerdict.FALLBACK,
                summary="No result returned."
            )

        return ReflectDecision(
            verdict=ReflectVerdict.PROCEED,
            summary="Got result, proceeding to respond."
        )

    def reset(self):
        self._loop_count = 0
