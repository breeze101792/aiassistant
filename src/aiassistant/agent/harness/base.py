"""The agent harness contract.

A harness owns *how a turn is reasoned*. Two implementations exist:

* ``NativeHarness`` — our loop: we prompt a model provider and run our tools.
* ``PiHarness`` — the external pi coding agent, which owns its own loop, tools,
  and context (see the pi adapter).

Everything downstream of a turn — the transcript, the orb, the TTS chunker —
consumes the single :class:`TurnEvent` vocabulary declared here and never
branches on which harness is running.

The contract is defined in docs/architecture/modules/agent-harness.md.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    """The kinds of event a turn can emit."""

    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT_FINAL = "text_final"
    USAGE = "usage"
    TURN_DONE = "turn_done"
    TURN_ERROR = "turn_error"


TERMINAL_KINDS = frozenset({EventKind.TURN_DONE, EventKind.TURN_ERROR})


@dataclass
class TurnEvent:
    """One event in a turn's stream."""

    kind: EventKind
    text: str = ""
    call_id: str = ""
    tool_name: str = ""
    args: dict | None = None
    result: Any = None
    is_error: bool = False
    usage: dict = field(default_factory=dict)
    cancelled: bool = False
    error_class: str = "harness"

    def is_terminal(self) -> bool:
        return self.kind in TERMINAL_KINDS


@dataclass
class HarnessCaps:
    """What a harness can do. Reported, never silently assumed.

    The two harnesses are genuinely not equivalent: pi owns its tools and its
    memory, our native loop delegates both. Reporting the difference is what
    keeps a swap honest (REQ-HARNESS-005).
    """

    owns_tools: bool = False
    owns_memory: bool = False
    streaming: bool = True
    cancellable: bool = True
    usage_reporting: bool = True
    images: bool = False


@dataclass
class TurnRequest:
    """The input to one turn."""

    text: str
    turn_id: str
    channel: str = "console"
    # Called for each tool the harness wants executed, when it does not own
    # tools itself. Returns a dict with either "result" or "error".
    execute_tool: Callable[[str, dict], Awaitable[dict]] | None = None
    memory_context: str = ""
    tool_schemas: list[dict] | None = None


@dataclass
class HarnessHealth:
    """The result of a health probe."""

    ok: bool
    detail: str = ""


class HarnessError(Exception):
    """A harness-level failure, carrying a class for the UI (REQ-ERR-001)."""

    def __init__(self, message: str, error_class: str = "harness", code: str = ""):
        super().__init__(message)
        self.error_class = error_class
        self.code = code


class AgentHarness(ABC):
    """One implementation per way of running a turn."""

    name = "harness"

    @property
    @abstractmethod
    def caps(self) -> HarnessCaps:
        """Static capability declaration."""

    @abstractmethod
    def run_turn(self, req: TurnRequest) -> AsyncIterator[TurnEvent]:
        """Run one turn and yield its events.

        The iterator always terminates, and its last event is terminal
        (``turn_done`` or ``turn_error``). It is not reentrant: one turn at a
        time per harness instance.
        """
        raise NotImplementedError

    @abstractmethod
    async def cancel(self) -> None:
        """Stop the active turn as promptly as the backend allows.

        Safe to call with no active turn. After it returns, the active iterator
        will end with ``turn_done(cancelled=True)``.
        """
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> HarnessHealth:
        """Report whether a turn can be served. Never raises."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release resources. Default: cancel and do nothing else."""
        await self.cancel()
