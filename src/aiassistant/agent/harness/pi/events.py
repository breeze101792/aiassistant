"""Map pi's event stream onto our TurnEvent vocabulary.

Pure functions over decoded messages, so the mapping is unit-testable against
recorded JSONL fixtures without a pi process.

pi event shapes (docs/research/pi-rpc.md, IF-0003):

* ``message_update`` carries an ``assistantMessageEvent`` whose ``type`` is one
  of ``text_delta``, ``thinking_delta``, ``toolcall_start``, ``toolcall_delta``,
  ``toolcall_end``, ``text_end``. Deltas are delta-only and must be assembled.
* ``message_end`` carries the authoritative assistant message. It replaces the
  assembled deltas.
* ``tool_execution_start`` / ``_update`` / ``_end`` are correlated by
  ``toolCallId``. These are notifications: pi already ran the tool.
* ``agent_settled`` marks the end of a turn.
* ``usage`` rides on ``message_update`` as
  ``{input, output, cacheRead, cacheWrite, totalTokens, cost}``.
"""

import json
import logging

from aiassistant.agent.harness.base import EventKind, TurnEvent
from aiassistant.agent.harness.pi.protocol import RpcMessage

logger = logging.getLogger(__name__)

# Events we decode but do not surface; logged at debug for diagnosis.
IGNORED_EVENTS = frozenset({
    "agent_start", "turn_start", "agent_end", "message_start",
    "queue_update", "session_info_changed", "compaction_start",
    "compaction_end", "auto_retry_start", "auto_retry_end",
    "extension_error", "bash_execution_update",
})


def map_event(message: RpcMessage):
    """Map one pi event to a list of TurnEvents (usually zero or one).

    Returning a list keeps the caller simple and allows one pi event to yield
    several of ours without a special case.
    """
    event_type = message.type

    if event_type == "message_update":
        return _map_message_update(message)

    if event_type == "message_end":
        return _map_message_end(message)

    if event_type == "tool_execution_start":
        call_id = message.raw.get("toolCallId", "")
        return [TurnEvent(
            kind=EventKind.TOOL_CALL,
            call_id=call_id,
            tool_name=message.raw.get("toolName", ""),
            args=message.raw.get("args") or {},
        )]

    if event_type in ("tool_execution_update", "tool_execution_end"):
        call_id = message.raw.get("toolCallId", "")
        is_end = event_type == "tool_execution_end"
        is_error = bool(message.raw.get("isError", False))
        raw_result = message.raw.get("result")
        if not is_end:
            raw_result = message.raw.get("partialResult")
        return [TurnEvent(
            kind=EventKind.TOOL_RESULT,
            call_id=call_id,
            tool_name=message.raw.get("toolName", ""),
            result=_stringify(raw_result),
            is_error=is_error,
        )]

    if event_type == "turn_end":
        # Verified live: turn_end repeats the assistant message, so it is used
        # only as a completion signal. Agent_settled remains the authoritative
        # end-of-turn marker; whichever arrives first ends the turn.
        return [TurnEvent(kind=EventKind.TURN_DONE)]

    if event_type == "agent_settled":
        return [TurnEvent(kind=EventKind.TURN_DONE)]

    if event_type in IGNORED_EVENTS:
        logger.debug("pi event ignored: %s", event_type)
        return []

    if event_type.endswith("_error") or event_type == "error":
        return [TurnEvent(
            kind=EventKind.TURN_ERROR,
            text=message.error or event_type,
            error_class="harness",
        )]

    logger.debug("pi event unmapped: %s", event_type)
    return []


def _map_message_update(message: RpcMessage) -> list[TurnEvent]:
    inner = message.raw.get("assistantMessageEvent") or {}
    inner_type = inner.get("type", "")
    events: list[TurnEvent] = []

    if inner_type == "text_delta":
        text = inner.get("delta", inner.get("text", "")) or ""
        if text:
            events.append(TurnEvent(kind=EventKind.TEXT_DELTA, text=text))

    elif inner_type == "thinking_delta":
        text = inner.get("delta", inner.get("text", "")) or ""
        if text:
            events.append(TurnEvent(kind=EventKind.THINKING_DELTA, text=text))

    elif inner_type == "toolcall_end":
        call = inner.get("toolCall") or inner.get("call") or {}
        events.append(TurnEvent(
            kind=EventKind.TOOL_CALL,
            call_id=call.get("id", inner.get("toolCallId", "")),
            tool_name=call.get("name", inner.get("name", "")),
            args=call.get("arguments") or {},
        ))

    usage_raw = message.raw.get("usage")
    if isinstance(usage_raw, dict):
        events.append(TurnEvent(kind=EventKind.USAGE, usage=_normalize_usage(usage_raw)))

    return events


def _map_message_end(message: RpcMessage) -> list[TurnEvent]:
    """Map the authoritative assistant message, and only that one.

    Verified against a live pi 0.87.1 session (spike, chunk 4): ``message_end``
    fires once per role — system, then user, then assistant. Only the assistant
    message is a final answer; mapping the others would make the system prompt
    the spoken response.

    A failed turn also arrives here, not as a separate error event: the
    assistant message carries ``stopReason: "error"`` and ``errorMessage``.
    That must surface as a turn error, not an empty success.
    """
    payload = message.raw.get("message") or {}
    if payload.get("role") != "assistant":
        return []

    stop_reason = payload.get("stopReason")
    if stop_reason == "error" or payload.get("errorMessage"):
        return [TurnEvent(
            kind=EventKind.TURN_ERROR,
            text=_clean_error(payload.get("errorMessage") or "pi reported an error"),
            error_class=_classify_error(payload.get("errorMessage") or ""),
        )]

    text = _extract_text(payload)
    events = [TurnEvent(kind=EventKind.TEXT_FINAL, text=text)] if text else []

    usage = payload.get("usage")
    if isinstance(usage, dict):
        events.append(TurnEvent(kind=EventKind.USAGE, usage=_normalize_usage(usage)))
    return events


def _clean_error(raw: str) -> str:
    """Collapse pi's nested JSON error blob into one readable line."""
    text = str(raw)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            inner = parsed.get("error")
            if isinstance(inner, dict):
                text = str(inner.get("message", inner))
            elif inner is not None:
                text = str(inner)
    except (json.JSONDecodeError, TypeError):
        pass
    return " ".join(text.split())[:400]


def _classify_error(text: str) -> str:
    lowered = text.lower()
    if "quota" in lowered or "rate limit" in lowered or "429" in lowered:
        return "harness"
    if "api key" in lowered or "auth" in lowered or "permission" in lowered:
        return "config"
    if "model" in lowered and ("not found" in lowered or "unknown" in lowered):
        return "config"
    return "harness"


def _extract_text(payload: dict) -> str:
    """Pull plain text out of a pi content-block message.

    pi content is a list of blocks; text blocks carry ``type: "text"``. A plain
    string is also accepted so a shape change degrades rather than breaks.
    """
    content = payload.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def _normalize_usage(usage: dict) -> dict:
    """Map pi's usage keys onto ours (input/output/total/cost)."""
    return {
        "input": usage.get("input", 0),
        "output": usage.get("output", 0),
        "total": usage.get("totalTokens", usage.get("total", 0)),
        "cost": usage.get("cost", 0),
    }


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    import json
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)
