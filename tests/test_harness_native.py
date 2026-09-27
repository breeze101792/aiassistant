"""Native harness tests, including a real tool round-trip.

The tool round-trip is the case that broke in development: the second request
after a tool call failed provider validation because tool-call arguments were
encoded the wrong way. Ollama requires a dict; OpenAI requires a JSON string.
The provider now owns that encoding, and this pins it.
"""

from collections.abc import Iterator

import pytest

from aiassistant.agent.harness.base import EventKind, TurnRequest
from aiassistant.agent.harness.native import NativeHarness
from aiassistant.reasoning.base import LLMBackend, StreamChunk


class TwoRoundProvider(LLMBackend):
    """Round 1 requests a tool; round 2 returns a final answer.

    Records every message list it is asked to complete, so a test can assert
    what the second request actually contained.
    """

    def __init__(self, arguments_style: str = "dict"):
        super().__init__(model="two-round")
        self.arguments_style = arguments_style
        self.requests: list[list[dict]] = []

    def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096) -> dict:
        return {"content": "x", "tool_calls": None, "usage": {}}

    def chat_stream(self, messages, tools=None, temperature=0.7, max_tokens=4096) -> Iterator[StreamChunk]:
        self.requests.append([dict(m) for m in messages])
        if len(self.requests) == 1:
            yield StreamChunk(done=True, content="Let me check.", tool_calls=[
                {"id": "call_1", "name": "datetime", "arguments": {"timezone": "UTC"}},
            ])
        else:
            yield StreamChunk(delta="Today is ")
            yield StreamChunk(delta="Monday.")
            yield StreamChunk(done=True, content="Today is Monday.")

    def embed(self, text: str) -> list[float]:
        return [0.0]

    def format_tool_arguments(self, arguments: dict):
        return arguments if self.arguments_style == "dict" else __import__("json").dumps(arguments)


async def _run(harness: NativeHarness, execute):
    events = []
    async for event in harness.run_turn(
        TurnRequest(text="what day is it", turn_id="t1", execute_tool=execute)
    ):
        events.append(event)
    return events


class TestToolRoundTrip:
    @pytest.mark.asyncio
    async def test_tool_call_then_final_answer(self):
        provider = TwoRoundProvider()
        harness = NativeHarness(provider, persona="test")
        calls = []

        async def execute(name, args):
            calls.append((name, args))
            return {"result": "2026-09-27"}

        events = await _run(harness, execute)

        assert [c[0] for c in calls] == ["datetime"]
        assert calls[0][1] == {"timezone": "UTC"}
        tool_calls = [e for e in events if e.kind == EventKind.TOOL_CALL]
        tool_results = [e for e in events if e.kind == EventKind.TOOL_RESULT]
        assert tool_calls and tool_results
        assert tool_results[0].result == "2026-09-27"
        assert tool_results[0].is_error is False
        finals = [e for e in events if e.kind == EventKind.TEXT_FINAL]
        assert finals[0].text == "Today is Monday."
        assert events[-1].kind == EventKind.TURN_DONE

    @pytest.mark.asyncio
    async def test_second_request_carries_the_tool_exchange(self):
        """The follow-up request must include the call and its result, or the
        model answers as if no tool had run."""
        provider = TwoRoundProvider()
        harness = NativeHarness(provider, persona="test")

        async def execute(name, args):
            return {"result": "2026-09-27"}

        await _run(harness, execute)
        second = provider.requests[1]
        roles = [m["role"] for m in second]
        assert "tool" in roles, "tool result missing from the follow-up request"
        assistant_msg = next(m for m in second if m["role"] == "assistant" and m.get("tool_calls"))
        assert assistant_msg["tool_calls"][0]["id"] == "call_1"

    @pytest.mark.asyncio
    async def test_tool_arguments_use_the_provider_encoding(self):
        """Ollama wants a dict; a JSON string is a request-time validation error."""
        for style, expected_type in (("dict", dict), ("str", str)):
            provider = TwoRoundProvider(arguments_style=style)
            harness = NativeHarness(provider, persona="test")

            async def execute(name, args):
                return {"result": "ok"}

            await _run(harness, execute)
            second = provider.requests[1]
            assistant_msg = next(m for m in second if m["role"] == "assistant" and m.get("tool_calls"))
            args = assistant_msg["tool_calls"][0]["function"]["arguments"]
            assert isinstance(args, expected_type), f"{style}: got {type(args).__name__}"


class TestRetryBehavior:
    @pytest.mark.asyncio
    async def test_transient_failure_is_retried(self):
        provider = TwoRoundProvider()
        harness = NativeHarness(provider, persona="test")
        attempts = []

        async def execute(name, args):
            attempts.append(1)
            if len(attempts) == 1:
                return {"error": "connection refused"}
            return {"result": "recovered"}

        events = await _run(harness, execute)
        assert len(attempts) == 2, "a transient failure must be retried"
        result = next(e for e in events if e.kind == EventKind.TOOL_RESULT)
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_permanent_failure_is_not_retried(self):
        provider = TwoRoundProvider()
        harness = NativeHarness(provider, persona="test")
        attempts = []

        async def execute(name, args):
            attempts.append(1)
            return {"error": "path outside safe roots"}

        events = await _run(harness, execute)
        assert len(attempts) == 1, "a permanent failure must not be retried"
        result = next(e for e in events if e.kind == EventKind.TOOL_RESULT)
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_tool_exception_becomes_an_error_result(self):
        provider = TwoRoundProvider()
        harness = NativeHarness(provider, persona="test")

        async def execute(name, args):
            raise RuntimeError("tool blew up")

        events = await _run(harness, execute)
        result = next(e for e in events if e.kind == EventKind.TOOL_RESULT)
        assert result.is_error is True
        assert "tool blew up" in str(result.result)


class TestFailureSurfacing:
    @pytest.mark.asyncio
    async def test_provider_error_is_a_terminal_turn_error(self):
        class Boom(LLMBackend):
            def __init__(self):
                super().__init__(model="boom")

            def chat(self, *a, **k):
                raise RuntimeError("nope")

            def chat_stream(self, *a, **k):
                raise RuntimeError("provider exploded")

            def embed(self, text):
                return []

        harness = NativeHarness(Boom(), persona="test")
        events = await _run(harness, None)
        assert events[-1].kind == EventKind.TURN_ERROR
        assert "provider exploded" in events[-1].text
        assert events[-1].is_terminal()

    @pytest.mark.asyncio
    async def test_no_tool_executor_reports_instead_of_crashing(self):
        provider = TwoRoundProvider()
        harness = NativeHarness(provider, persona="test")
        events = await _run(harness, None)
        assert events[-1].is_terminal()
