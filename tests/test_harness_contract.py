"""Harness contract conformance.

One parametrized suite run against every harness implementation. This is what
makes REQ-HARNESS-002 real: both harnesses emit one event vocabulary and
terminate the same way, so nothing downstream has to branch on which is running.

The pi adapter is added to the parametrization in chunk 4, when it exists.
"""

import asyncio

import pytest

from aiassistant.agent.harness.base import (
    AgentHarness,
    EventKind,
    HarnessCaps,
    TurnEvent,
    TurnRequest,
)
from aiassistant.agent.harness.fake import FakeHarness


def _harnesses() -> list[AgentHarness]:
    """Every harness that can be built without a model or a subprocess.

    The pi harness is exercised in tests/test_pi_adapter.py against recorded
    JSONL and, in the spike, against a live process; it is excluded here because
    it needs a child process to exist.
    """
    return [FakeHarness(), FakeHarness(deltas=["a"]), FakeHarness(tool_calls=[("t", {})])]


@pytest.fixture(params=_harnesses(), ids=lambda h: f"{h.name}-{id(h) % 1000}")
def harness(request):
    return request.param


async def _collect(h: AgentHarness, req: TurnRequest) -> list[TurnEvent]:
    return [event async for event in h.run_turn(req)]


class TestConformance:
    @pytest.mark.asyncio
    async def test_turn_terminates(self, harness):
        events = await asyncio.wait_for(
            _collect(harness, TurnRequest(text="hi", turn_id="t1")), timeout=5,
        )
        assert events, "a turn must emit at least one event"
        assert events[-1].is_terminal(), "the last event must be terminal"

    @pytest.mark.asyncio
    async def test_exactly_one_terminal_event(self, harness):
        events = await _collect(harness, TurnRequest(text="hi", turn_id="t1"))
        terminals = [e for e in events if e.is_terminal()]
        assert len(terminals) == 1, f"expected 1 terminal event, got {len(terminals)}"

    @pytest.mark.asyncio
    async def test_never_emits_after_terminal(self, harness):
        events = await _collect(harness, TurnRequest(text="hi", turn_id="t1"))
        terminal_index = next(i for i, e in enumerate(events) if e.is_terminal())
        assert terminal_index == len(events) - 1

    @pytest.mark.asyncio
    async def test_caps_is_reported(self, harness):
        caps = harness.caps
        assert isinstance(caps, HarnessCaps)
        assert isinstance(caps.owns_tools, bool)
        assert isinstance(caps.streaming, bool)

    @pytest.mark.asyncio
    async def test_health_never_raises(self, harness):
        health = await harness.health()
        assert isinstance(health.ok, bool)
        assert isinstance(health.detail, str)

    @pytest.mark.asyncio
    async def test_cancel_is_safe_with_no_turn(self, harness):
        await harness.cancel()
        await harness.cancel()

    @pytest.mark.asyncio
    async def test_final_text_is_the_concatenated_deltas(self, harness):
        """The authoritative text must match what was streamed, so consumers
        that rendered deltas are not contradicted by the final."""
        events = await _collect(harness, TurnRequest(text="hi", turn_id="t1"))
        deltas = "".join(e.text for e in events if e.kind == EventKind.TEXT_DELTA)
        finals = [e.text for e in events if e.kind == EventKind.TEXT_FINAL]
        if finals:
            assert finals[0] == deltas or not deltas


class TestToolCorrelation:
    @pytest.mark.asyncio
    async def test_every_tool_result_matches_a_call(self):
        h = FakeHarness(tool_calls=[("alpha", {}), ("beta", {})])
        events = await _collect(h, TurnRequest(text="hi", turn_id="t1"))
        calls = {e.call_id for e in events if e.kind == EventKind.TOOL_CALL}
        results = {e.call_id for e in events if e.kind == EventKind.TOOL_RESULT}
        assert results == calls, "every result must correlate to a call in the same turn"

    @pytest.mark.asyncio
    async def test_execute_tool_callback_is_invoked(self):
        seen = []

        async def execute(name, args):
            seen.append(name)
            return {"result": f"{name}-done"}

        h = FakeHarness(tool_calls=[("alpha", {"x": 1})])
        events = await _collect(
            h, TurnRequest(text="hi", turn_id="t1", execute_tool=execute),
        )
        assert seen == ["alpha"]
        results = [e for e in events if e.kind == EventKind.TOOL_RESULT]
        assert results[0].result == "alpha-done"


class TestFailureModes:
    @pytest.mark.asyncio
    async def test_error_turn_is_terminal(self):
        h = FakeHarness(fail=RuntimeError("boom"))
        events = await _collect(h, TurnRequest(text="hi", turn_id="t1"))
        assert events[-1].kind == EventKind.TURN_ERROR
        assert events[-1].is_terminal()

    @pytest.mark.asyncio
    async def test_cancel_ends_turn_as_cancelled(self):
        h = FakeHarness(stall=True)
        task = asyncio.ensure_future(_collect(h, TurnRequest(text="hi", turn_id="t1")))
        await asyncio.sleep(0.05)
        await h.cancel()
        events = await asyncio.wait_for(task, timeout=5)
        assert events[-1].kind == EventKind.TURN_DONE
        assert events[-1].cancelled is True
