"""The native harness: our own turn loop.

Owns prompting a model provider, streaming the reply, running our tools, and
synthesizing a final answer from tool results. It does **not** own conversation
context (the agent passes a memory context in) or persistence.

Streaming is the point of this implementation: text is emitted as it arrives so
the transcript fills in live and TTS can start before the model finishes.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from aiassistant.agent.harness.base import (
    AgentHarness,
    EventKind,
    HarnessCaps,
    HarnessError,
    HarnessHealth,
    TurnEvent,
    TurnRequest,
)
from aiassistant.agent.reasoner import _strip_thinking
from aiassistant.agent.policy import RetryPolicy
from aiassistant.reasoning.base import LLMBackend
from aiassistant.reasoning.factory import ProviderError

logger = logging.getLogger(__name__)

# A turn may call tools, then re-prompt for a synthesis. This bounds that loop
# so a model that keeps requesting tools cannot spin forever.
MAX_TOOL_ROUNDS = 4


class NativeHarness(AgentHarness):
    """Our loop: model provider plus our tool registry."""

    name = "native"

    def __init__(
        self,
        provider: LLMBackend,
        persona: str,
        *,
        tool_schemas: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_retries: int = 3,
    ):
        self.provider = provider
        self.persona = persona
        self.tool_schemas = tool_schemas
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_policy = RetryPolicy(max_retries)
        self._cancelled = False

    @property
    def caps(self) -> HarnessCaps:
        # We run our own tools, and the agent passes context in.
        return HarnessCaps(
            owns_tools=False,
            owns_memory=False,
            streaming=True,
            cancellable=True,
            usage_reporting=True,
        )

    async def health(self) -> HarnessHealth:
        """Report readiness. A short probe keeps a dead provider from hanging setup."""
        try:
            await self.provider.achat(
                [{"role": "user", "content": "ping"}], max_tokens=1,
            )
            return HarnessHealth(ok=True, detail=f"{self.provider.model} reachable")
        except Exception as exc:
            return HarnessHealth(ok=False, detail=f"{type(exc).__name__}: {exc}")

    async def cancel(self) -> None:
        self._cancelled = True

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[TurnEvent]:
        self._cancelled = False
        messages = self._build_messages(req)
        tool_schemas = req.tool_schemas if req.tool_schemas is not None else self.tool_schemas
        usage_total: dict = {}
        seen_thinking = False

        for round_index in range(MAX_TOOL_ROUNDS):
            if self._cancelled:
                yield TurnEvent(kind=EventKind.TURN_DONE, cancelled=True)
                return

            content_parts: list[str] = []
            tool_calls: list[dict] | None = None
            usage: dict = {}

            try:
                async for chunk in self.provider.achat_stream(
                    messages,
                    tools=tool_schemas if tool_schemas else None,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                ):
                    if self._cancelled:
                        yield TurnEvent(kind=EventKind.TURN_DONE, cancelled=True)
                        return
                    if chunk.thinking:
                        seen_thinking = True
                        yield TurnEvent(kind=EventKind.THINKING_DELTA, text=chunk.thinking)
                    if chunk.delta:
                        content_parts.append(chunk.delta)
                        yield TurnEvent(kind=EventKind.TEXT_DELTA, text=chunk.delta)
                    if chunk.done:
                        tool_calls = chunk.tool_calls
                        usage = chunk.usage or {}
            except Exception as exc:
                yield TurnEvent(
                    kind=EventKind.TURN_ERROR,
                    text=f"{type(exc).__name__}: {exc}",
                    error_class=_classify(exc),
                )
                return

            _accumulate(usage_total, usage)
            if usage:
                yield TurnEvent(kind=EventKind.USAGE, usage=dict(usage))

            # No tools requested: this is the answer.
            if not tool_calls:
                final_text = _strip_thinking("".join(content_parts))
                yield TurnEvent(kind=EventKind.TEXT_FINAL, text=final_text)
                yield TurnEvent(kind=EventKind.TURN_DONE)
                return

            # Tools requested but none can run: report the model's own text.
            if not req.execute_tool:
                final_text = _strip_thinking("".join(content_parts)) or (
                    "I wanted to use a tool, but tools are unavailable."
                )
                yield TurnEvent(kind=EventKind.TEXT_FINAL, text=final_text)
                yield TurnEvent(kind=EventKind.TURN_DONE)
                return

            # Announce and run each call, then feed results back.
            for call in tool_calls:
                call_id = call.get("id") or f"call_{round_index}_{call.get('name', 'tool')}"
                name = call.get("name", "")
                args = call.get("arguments") or {}
                yield TurnEvent(
                    kind=EventKind.TOOL_CALL, call_id=call_id,
                    tool_name=name, args=args,
                )

                result = await self._run_tool_with_retry(req, name, args)

                is_error = bool(result.get("error"))
                yield TurnEvent(
                    kind=EventKind.TOOL_RESULT, call_id=call_id, tool_name=name,
                    result=result.get("result") if not is_error else result.get("error"),
                    is_error=is_error,
                )
                messages.extend(self._tool_messages(call_id, call, result))

        # Tool loop did not converge.
        yield TurnEvent(
            kind=EventKind.TURN_ERROR,
            text=f"Tool loop exceeded {MAX_TOOL_ROUNDS} rounds",
            error_class="tool",
        )

    async def _run_tool_with_retry(self, req: TurnRequest, name: str, args: dict) -> dict:
        """Execute a tool, retrying only transient failures.

        The retry decision is real: a timeout or a refused connection is tried
        again up to ``max_retries``; anything else aborts immediately. The old
        code computed a RETRY verdict and then ignored it (ADR-0009).
        """
        execute = req.execute_tool
        if execute is None:
            return {"error": "no tool executor is configured"}
        last: dict = {"error": "tool was never invoked"}
        for attempt in range(self.max_retries):
            try:
                result = await execute(name, args)
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}

            decision = self.retry_policy.decide(
                result=result.get("result"),
                error=result.get("error"),
                attempt=attempt,
            )
            if not decision.should_retry:
                return result
            logger.debug(decision.summary)
            last = result
        return last

    # ── Internals ────────────────────────────────────────────

    def _build_messages(self, req: TurnRequest) -> list[dict]:
        messages = [{"role": "system", "content": self.persona}]
        if req.memory_context:
            messages.append({
                "role": "system",
                "content": f"Relevant context:\n{req.memory_context}",
            })
        messages.append({"role": "user", "content": req.text})
        return messages

    def _tool_messages(self, call_id: str, call: dict, result: dict) -> list[dict]:
        """The assistant tool-call turn plus the tool result turn.

        Providers expect the call echoed back before the result so the model can
        correlate them. The argument encoding is provider-specific — Ollama
        requires a dict, OpenAI a JSON string — so it is delegated rather than
        hardcoded (getting it wrong is a request-time validation error).
        """
        arguments = call.get("arguments") or {}
        assistant_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call.get("name", ""),
                    "arguments": self.provider.format_tool_arguments(arguments),
                },
            }],
        }
        payload = result.get("result") if "error" not in result else {"error": result["error"]}
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False, default=str)
        return [
            assistant_msg,
            {"role": "tool", "tool_call_id": call_id, "content": payload},
        ]


def _accumulate(total: dict, usage: dict) -> None:
    for key, value in (usage or {}).items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value


def _classify(exc: Exception) -> str:
    """Map a provider exception to an error class for the UI (REQ-ERR-001)."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "auth" in name or "auth" in text or "api key" in text:
        return "config"
    if "not found" in text or "model" in text and "unavailable" in text:
        return "config"
    if "connect" in name or "connection" in text or "refused" in text:
        return "harness"
    return "harness"


def harness_error_from(exc: Exception) -> HarnessError:
    return HarnessError(str(exc), error_class=_classify(exc))


__all__ = ["NativeHarness", "ProviderError", "Any"]
