"""Chunk-4 spike findings, as executable assertions.

These pin the facts the live pi spike established. Each one was a wrong
assumption in the first adapter draft, and each would have shipped a visible bug:

* ``message_end`` fires once per role, so the system prompt and the echoed user
  message must not be treated as the answer.
* A failed turn arrives as an assistant message with ``stopReason: "error"``
  and ``errorMessage``, not as a separate error event.
* ``turn_end`` repeats the assistant message and also ends the turn.

The spike also confirmed: ``get_state`` answers, ``agent_settled`` arrives,
stdin close exits cleanly, and our ``tool_call`` extension hook vetoes a real
out-of-workspace read. Those are recorded in docs/research/pi-rpc.md.
"""

import json

import pytest

from aiassistant.agent.harness.base import EventKind
from aiassistant.agent.harness.pi import events as pi_events
from aiassistant.agent.harness.pi.protocol import decode


def _msg(obj: dict):
    return decode(json.dumps(obj))


class TestSpikeFindings:
    def test_message_end_for_system_role_is_not_the_answer(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "system",
                "content": "",
                "sections": {"preamble": "You are an expert coding assistant..."},
            },
        }))
        assert events == [], "the system prompt must never become the response"

    def test_message_end_for_user_echo_is_not_the_answer(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "Reply with exactly: PONG"}],
            },
        }))
        assert events == []

    def test_assistant_message_with_stop_reason_error_is_a_turn_error(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": '{"error": {"code": 429, "message": "quota exceeded"}}',
            },
        }))
        assert len(events) == 1
        assert events[0].kind is EventKind.TURN_ERROR
        assert "quota exceeded" in events[0].text
        assert events[0].error_class == "harness"

    def test_nested_error_blob_is_flattened_for_display(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "assistant", "content": [], "stopReason": "error",
                "errorMessage": '{"error": {"message": "line one\\n  line two"}}',
            },
        }))
        assert "\n" not in events[0].text, "an error blob must not span lines"
        assert "line one" in events[0].text

    def test_auth_error_is_classified_as_config(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "assistant", "content": [], "stopReason": "error",
                "errorMessage": "invalid api key",
            },
        }))
        assert events[0].error_class == "config"

    def test_assistant_message_with_usage_emits_both_events(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "PONG"}],
                "usage": {"input": 10, "output": 2, "totalTokens": 12, "cost": 0},
            },
        }))
        kinds = [e.kind for e in events]
        assert EventKind.TEXT_FINAL in kinds
        assert EventKind.USAGE in kinds
        usage = next(e for e in events if e.kind is EventKind.USAGE)
        assert usage.usage["total"] == 12

    def test_turn_end_ends_the_turn(self):
        events = pi_events.map_event(_msg({"type": "turn_end"}))
        assert events[0].kind is EventKind.TURN_DONE

    def test_message_start_is_ignored(self):
        """Verified live: message_start precedes each role's message_end."""
        assert pi_events.map_event(_msg({"type": "message_start"})) == []
