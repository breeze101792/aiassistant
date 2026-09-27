"""A harness that satisfies the contract without a model or a subprocess.

Used by tests to prove the agent loop and the event consumers work, and as a
reference for what a minimal conforming implementation looks like.
"""

from collections.abc import AsyncIterator

from aiassistant.agent.harness.base import (
    AgentHarness,
    EventKind,
    HarnessCaps,
    HarnessHealth,
    TurnEvent,
    TurnRequest,
)


class FakeHarness(AgentHarness):
    """Emits a scripted turn. Optionally raises, stalls, or calls a tool."""

    name = "fake"

    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        tool_calls: list[tuple[str, dict]] | None = None,
        fail: Exception | None = None,
        stall: bool = False,
    ):
        self.deltas = deltas if deltas is not None else ["Hello", " there"]
        self.tool_calls = tool_calls or []
        self.fail = fail
        self.stall = stall
        self._cancelled = False

    @property
    def caps(self) -> HarnessCaps:
        return HarnessCaps(streaming=True, cancellable=True)

    async def health(self) -> HarnessHealth:
        return HarnessHealth(ok=True, detail="fake")

    async def cancel(self) -> None:
        self._cancelled = True

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[TurnEvent]:
        self._cancelled = False

        if self.fail is not None:
            yield TurnEvent(
                kind=EventKind.TURN_ERROR,
                text=str(self.fail),
                error_class="harness",
            )
            return

        if self.stall:
            import asyncio
            for _ in range(1000):
                if self._cancelled:
                    yield TurnEvent(kind=EventKind.TURN_DONE, cancelled=True)
                    return
                await asyncio.sleep(0.01)
            yield TurnEvent(kind=EventKind.TURN_ERROR, text="never cancelled")
            return

        for call_id, (name, args) in enumerate(self.tool_calls):
            cid = f"call_{call_id}"
            yield TurnEvent(
                kind=EventKind.TOOL_CALL, call_id=cid, tool_name=name, args=args,
            )
            result = {"result": "ok"}
            if req.execute_tool:
                result = await req.execute_tool(name, args)
            yield TurnEvent(
                kind=EventKind.TOOL_RESULT, call_id=cid, tool_name=name,
                result=result.get("result"), is_error=bool(result.get("error")),
            )

        text = ""
        for delta in self.deltas:
            if self._cancelled:
                yield TurnEvent(kind=EventKind.TURN_DONE, cancelled=True)
                return
            text += delta
            yield TurnEvent(kind=EventKind.TEXT_DELTA, text=delta)

        yield TurnEvent(kind=EventKind.USAGE, usage={"input": 1, "output": 2})
        yield TurnEvent(kind=EventKind.TEXT_FINAL, text=text)
        yield TurnEvent(kind=EventKind.TURN_DONE)
