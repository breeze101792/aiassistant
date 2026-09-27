"""pi adapter tests against recorded JSONL fixtures.

The spike records real pi output; these fixtures pin the mapping so a pi upgrade
that changes the wire format fails here rather than in a live session.

Fixtures are shaped from the documented protocol (docs/research/pi-rpc.md,
IF-0003). Items marked UNVERIFIED there are covered by shape-tolerant tests: a
change in content-block layout degrades instead of crashing.
"""

import json

import pytest

from aiassistant.agent.harness.base import EventKind
from aiassistant.agent.harness.pi import events as pi_events
from aiassistant.agent.harness.pi.process import PiProcess, PiProcessConfig
from aiassistant.agent.harness.pi.protocol import (
    ProtocolError,
    RpcRequest,
    command_request,
    decode,
    encode,
    prompt_request,
)


def _msg(obj: dict):
    return decode(json.dumps(obj))


class TestFraming:
    def test_encode_is_one_json_line(self):
        line = encode(RpcRequest(id="r1", type="prompt", fields={"message": "hi"}))
        assert line.endswith(b"\n")
        assert line.count(b"\n") == 1
        assert json.loads(line) == {"id": "r1", "type": "prompt", "message": "hi"}

    def test_decode_round_trip(self):
        msg = decode('{"id": "r1", "type": "response", "success": true}')
        assert msg.id == "r1"
        assert msg.is_response
        assert msg.success

    def test_events_have_no_id(self):
        assert _msg({"type": "message_update"}).is_event
        assert not _msg({"id": "x", "type": "response"}).is_event

    def test_non_json_raises_protocol_error(self):
        with pytest.raises(ProtocolError):
            decode("this is not json")

    def test_json_array_is_a_protocol_error(self):
        with pytest.raises(ProtocolError):
            decode("[1, 2, 3]")

    def test_empty_line_is_a_protocol_error(self):
        with pytest.raises(ProtocolError):
            decode("   \n")

    def test_unicode_line_separator_inside_a_string_is_not_a_boundary(self):
        """U+2028/U+2029 are legal in JSON strings and must survive decoding."""
        payload = {"id": "r1", "type": "response", "text": "line\u2028break\u2029end"}
        msg = decode(json.dumps(payload))
        assert "line\u2028break\u2029end" == msg.raw["text"]

    def test_prompt_request_shape(self):
        req = prompt_request("tid", "hello")
        assert json.loads(encode(req)) == {"id": "tid", "type": "prompt", "message": "hello"}

    def test_command_request_shape(self):
        req = command_request("cid", "abort")
        assert json.loads(encode(req)) == {"id": "cid", "type": "abort"}


class TestEventMapping:
    def test_text_delta(self):
        events = pi_events.map_event(_msg({
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "delta": "Hel"},
        }))
        assert len(events) == 1
        assert events[0].kind is EventKind.TEXT_DELTA
        assert events[0].text == "Hel"

    def test_thinking_delta_is_separate(self):
        events = pi_events.map_event(_msg({
            "type": "message_update",
            "assistantMessageEvent": {"type": "thinking_delta", "delta": "hmm"},
        }))
        assert events[0].kind is EventKind.THINKING_DELTA

    def test_usage_rides_on_message_update_and_is_normalized(self):
        events = pi_events.map_event(_msg({
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "delta": "x"},
            "usage": {"input": 10, "output": 5, "totalTokens": 15, "cost": 0.01},
        }))
        usage = next(e for e in events if e.kind is EventKind.USAGE)
        assert usage.usage == {"input": 10, "output": 5, "total": 15, "cost": 0.01}

    def test_message_end_is_the_authoritative_final(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": "final answer"}]},
        }))
        assert len(events) == 1
        assert events[0].kind is EventKind.TEXT_FINAL
        assert events[0].text == "final answer"

    def test_message_end_for_non_assistant_roles_is_ignored(self):
        """Verified live: message_end fires per role, so the system prompt and
        the echoed user turn must NOT become the spoken answer."""
        for role in ("system", "user"):
            events = pi_events.map_event(_msg({
                "type": "message_end",
                "message": {"role": role, "content": [{"type": "text", "text": "not the answer"}]},
            }))
            assert events == [], f"{role} message leaked into the response"

    def test_message_end_accepts_a_plain_string_content(self):
        """Shape tolerance: a content layout change must degrade, not crash."""
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {"role": "assistant", "content": "plain text"},
        }))
        assert events[0].text == "plain text"

    def test_assistant_error_message_becomes_a_turn_error(self):
        """Verified live: a failed turn arrives as an assistant message with
        stopReason=error, not as a separate error event."""
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {
                "role": "assistant", "content": [], "stopReason": "error",
                "errorMessage": '{"error": {"code": 429, "message": "quota exceeded"}}',
            },
        }))
        assert len(events) == 1
        assert events[0].kind is EventKind.TURN_ERROR
        assert "quota exceeded" in events[0].text

    def test_message_end_with_no_text_emits_nothing(self):
        events = pi_events.map_event(_msg({
            "type": "message_end",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]},
        }))
        assert events == []

    def test_tool_execution_is_correlated_by_tool_call_id(self):
        call = pi_events.map_event(_msg({
            "type": "tool_execution_start",
            "toolCallId": "c1", "toolName": "read", "args": {"path": "a.txt"},
        }))[0]
        done = pi_events.map_event(_msg({
            "type": "tool_execution_end",
            "toolCallId": "c1", "toolName": "read", "result": "file body", "isError": False,
        }))[0]
        assert call.kind is EventKind.TOOL_CALL
        assert done.kind is EventKind.TOOL_RESULT
        assert call.call_id == done.call_id == "c1"
        assert done.is_error is False
        assert done.result == "file body"

    def test_tool_execution_error_is_flagged(self):
        done = pi_events.map_event(_msg({
            "type": "tool_execution_end",
            "toolCallId": "c2", "toolName": "read",
            "result": "no such file", "isError": True,
        }))[0]
        assert done.is_error is True

    def test_toolcall_end_from_message_update(self):
        events = pi_events.map_event(_msg({
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "toolcall_end",
                "toolCall": {"id": "c9", "name": "grep", "arguments": {"pattern": "x"}},
            },
        }))
        call = next(e for e in events if e.kind is EventKind.TOOL_CALL)
        assert call.call_id == "c9"
        assert call.tool_name == "grep"

    def test_agent_settled_ends_the_turn(self):
        events = pi_events.map_event(_msg({"type": "agent_settled"}))
        assert len(events) == 1
        assert events[0].kind is EventKind.TURN_DONE

    def test_ignored_lifecycle_events_produce_nothing(self):
        for name in ("agent_start", "turn_start", "agent_end",
                     "message_start", "queue_update", "compaction_start"):
            assert pi_events.map_event(_msg({"type": name})) == []

    def test_turn_end_is_a_completion_signal(self):
        """Verified live: turn_end follows the assistant message and ends the
        turn, as does agent_settled."""
        events = pi_events.map_event(_msg({"type": "turn_end"}))
        assert len(events) == 1
        assert events[0].kind is EventKind.TURN_DONE

    def test_unmapped_event_is_not_fatal(self):
        assert pi_events.map_event(_msg({"type": "something_brand_new"})) == []

    def test_error_event_maps_to_turn_error(self):
        events = pi_events.map_event(_msg({"type": "turn_error", "error": "boom"}))
        assert events[0].kind is EventKind.TURN_ERROR


class TestProcessCommand:
    """The start command and environment are security-relevant, so pin them."""

    def test_argv_omits_shell_tools_and_ambient_extensions(self):
        p = PiProcess(
            PiProcessConfig(command="pi", tools=["read", "write", "edit", "grep", "find", "ls"]),
            on_message=lambda m: None,
        )
        argv = p.build_argv()
        assert "--mode" in argv and argv[argv.index("--mode") + 1] == "rpc"
        assert "--no-session" in argv
        tools = argv[argv.index("--tools") + 1]
        assert "bash" not in tools and "powershell" not in tools
        assert "read" in tools and "ls" in tools
        assert "--no-extensions" in argv
        assert "--no-approve" in argv
        assert "-nc" in argv

    def test_argv_loads_only_our_extension(self):
        p = PiProcess(
            PiProcessConfig(policy_extension="./pi_extensions/workspace_guard.ts"),
            on_message=lambda m: None,
        )
        argv = p.build_argv()
        assert argv[argv.index("-e") + 1].endswith("workspace_guard.ts")

    def test_no_policy_extension_omits_the_flag(self):
        p = PiProcess(PiProcessConfig(policy_extension=None), on_message=lambda m: None)
        assert "-e" not in p.build_argv()

    def test_env_is_explicit_not_inherited(self):
        p = PiProcess(PiProcessConfig(), on_message=lambda m: None)
        env = p.build_env()
        assert env["AI_AGENT"] == "pi"
        assert env["PI_CODING_AGENT"] == "true"
        # Nothing outside the allowlist leaks in.
        assert set(env) <= set([
            "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR",
            "PI_CODING_AGENT_DIR", "PI_OFFLINE", "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AI_AGENT", "PI_CODING_AGENT",
        ])

    def test_host_never_sends_the_rpc_bash_command(self):
        """The RPC shell surface is closed by never using it (REQ-SEC-005)."""
        import aiassistant.agent.harness.pi.protocol as protocol
        import aiassistant.agent.harness.pi.adapter as adapter

        assert not hasattr(protocol, "BASH")
        source = open(adapter.__file__).read()
        assert 'command_request(.*"bash"' not in source
        assert '"bash"' not in source


class TestHarnessConfig:
    def test_pi_is_disabled_without_explicit_opt_in(self):
        from aiassistant.agent.harness.factory import HarnessConfigError, create_harness

        with pytest.raises(HarnessConfigError, match="disabled"):
            create_harness({"harness": "pi", "pi": {"enabled": False}})

    def test_pi_enabled_builds_the_adapter(self):
        from aiassistant.agent.harness.factory import create_harness
        from aiassistant.agent.harness.pi.adapter import PiHarness

        harness = create_harness({"harness": "pi", "pi": {"enabled": True}})
        assert isinstance(harness, PiHarness)
        assert harness.caps.owns_tools is True
        assert harness.caps.owns_memory is True

    def test_unknown_harness_names_the_value(self):
        from aiassistant.agent.harness.factory import HarnessConfigError, create_harness

        with pytest.raises(HarnessConfigError, match="cortex"):
            create_harness({"harness": "cortex"})
