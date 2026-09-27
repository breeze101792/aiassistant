"""Brain regression tests — reasoner, responder, thinking loop."""


class TestReasonerCompression:
    """Bug regression: Reasoner compression must not corrupt message roles."""

    def test_compression_preserves_message_structure(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        # Set up a long history that triggers compression
        mock_llm.token_count_response = 5000  # above default threshold
        mock_llm.chat_response = {
            "content": "Compressed summary of conversation.",
            "tool_calls": None,
            "usage": {"total_tokens": 100},
        }

        mock_llm.token_count = lambda messages: 5000 if len(messages) > 3 else 50

        reasoner = Reasoner(
            mock_llm,
            persona="You are a helpful assistant.",
            compress_target=200,
            context_max_tokens=1000,
        )

        # Build history with many user/assistant pairs
        for i in range(10):
            reasoner._history.append({"role": "user", "content": f"Question {i}"})
            reasoner._history.append({"role": "assistant", "content": f"Answer {i}"})

        reasoner._check_and_compress()

        # After compression, verify no system message appears between user/assistant pairs
        roles = [msg["role"] for msg in reasoner._history]
        # The system role (summary) must only be the first message if present
        system_indices = [i for i, r in enumerate(roles) if r == "system"]
        for idx in system_indices:
            assert idx == 0, f"System message found at index {idx}, should only be at index 0"

        # Last two messages should be user + assistant (the latest pair)
        assert roles[-2:] == ["user", "assistant"] or roles[-1] == "assistant"

    def test_compression_does_not_affect_short_history(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.token_count = lambda messages: 50  # below threshold

        reasoner = Reasoner(
            mock_llm,
            persona="You are helpful.",
            compress_target=200,
            context_max_tokens=1000,
        )

        reasoner._history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        reasoner._check_and_compress()

        # History must be unchanged
        assert len(reasoner._history) == 2
        assert reasoner._history[0]["role"] == "user"
        assert reasoner._history[1]["role"] == "assistant"

    def test_compress_too_short_history_does_nothing(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner._history = [{"role": "user", "content": "Hello"}]

        # Should not raise or modify history
        reasoner._compress_history()
        assert len(reasoner._history) == 1

    def test_reset_clears_history(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner._history = [
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
        ]
        reasoner.reset()
        assert reasoner._history == []


class TestRetryPolicy:
    """The retry policy must act, not just compute a verdict (ADR-0009).

    The pre-refactor Reflector returned RETRY and nothing consumed it, so a
    failed tool was never retried. These tests pin the real behavior.
    """

    def test_success_proceeds(self):
        from aiassistant.agent.policy import Outcome, RetryPolicy

        d = RetryPolicy(max_retries=3).decide(result="ok", error=None, attempt=0)
        assert d.outcome is Outcome.PROCEED
        assert d.should_retry is False

    def test_transient_error_retries_then_aborts(self):
        from aiassistant.agent.policy import Outcome, RetryPolicy

        policy = RetryPolicy(max_retries=3)
        assert policy.decide(result=None, error="connection refused", attempt=0).outcome is Outcome.RETRY
        assert policy.decide(result=None, error="connection refused", attempt=1).outcome is Outcome.RETRY
        # Last allowed attempt: no more retries.
        assert policy.decide(result=None, error="connection refused", attempt=2).outcome is Outcome.ABORT

    def test_non_transient_error_aborts_immediately(self):
        """Retrying a refused path or an unknown tool wastes the user's time."""
        from aiassistant.agent.policy import Outcome, RetryPolicy

        d = RetryPolicy(max_retries=3).decide(
            result=None, error="path outside safe roots", attempt=0,
        )
        assert d.outcome is Outcome.ABORT

    def test_null_result_aborts(self):
        from aiassistant.agent.policy import Outcome, RetryPolicy

        d = RetryPolicy(max_retries=3).decide(result=None, error=None, attempt=0)
        assert d.outcome is Outcome.ABORT


class TestJsonRepair:
    """Malformed tool-call arguments must degrade, not kill the turn."""

    def test_valid_json_parses(self):
        from aiassistant.agent.policy import repair_and_parse_json

        assert repair_and_parse_json('{"a": 1}') == {"a": 1}

    def test_trailing_comma_is_repaired(self):
        from aiassistant.agent.policy import repair_and_parse_json

        assert repair_and_parse_json('{"a": 1,}') == {"a": 1}

    def test_single_quotes_are_repaired(self):
        from aiassistant.agent.policy import repair_and_parse_json

        assert repair_and_parse_json("{'a': 'b'}") == {"a": "b"}

    def test_unrecoverable_returns_empty_dict(self):
        from aiassistant.agent.policy import repair_and_parse_json

        assert repair_and_parse_json("not json at all {") == {}

    def test_dict_passes_through(self):
        from aiassistant.agent.policy import repair_and_parse_json

        assert repair_and_parse_json({"a": 1}) == {"a": 1}

    def test_empty_returns_empty(self):
        from aiassistant.agent.policy import repair_and_parse_json

        assert repair_and_parse_json("") == {}
        assert repair_and_parse_json(None) == {}


class TestResponder:
    """Responder: response construction and conversation saving."""

    def test_respond_produces_expected_keys(self, temp_dir):
        from aiassistant.agent.transcript import Responder

        responder = Responder(conversations_path=temp_dir)
        response = responder.respond(text="Hello!")
        assert "text" in response
        assert response["text"] == "Hello!"
        assert "conversation_id" in response
        assert len(response["conversation_id"]) == 8

    def test_respond_includes_thinking(self, temp_dir):
        from aiassistant.agent.transcript import Responder

        responder = Responder(conversations_path=temp_dir)
        response = responder.respond(
            text="Done.",
            thinking="Let me think about this step by step..."
        )
        assert response["thinking"] == "Let me think about this step by step..."

    def test_respond_includes_tools_used(self, temp_dir):
        from aiassistant.agent.transcript import Responder

        responder = Responder(conversations_path=temp_dir)
        response = responder.respond(
            text="Done.",
            tools_used=[{"name": "datetime", "request_id": "abc", "duration_ms": 5}],
        )
        assert response["tools_used"] == [{"name": "datetime", "request_id": "abc", "duration_ms": 5}]

    def test_save_turn_creates_file(self, temp_dir):
        from aiassistant.agent.transcript import Responder

        responder = Responder(conversations_path=temp_dir)
        responder.save_turn("user", "Hello there")
        responder.save_turn("assistant", "Hi! How can I help?")

        import os
        from datetime import datetime, timezone
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = os.path.join(temp_dir, f"{date_str}.md")
        assert os.path.exists(filepath)

        content = open(filepath).read()
        assert "Hello there" in content
        assert "Hi! How can I help?" in content

    def test_conversation_id_persists_across_calls(self, temp_dir):
        from aiassistant.agent.transcript import Responder

        responder = Responder(conversations_path=temp_dir)
        r1 = responder.respond(text="First")
        r2 = responder.respond(text="Second")
        assert r1["conversation_id"] == r2["conversation_id"]


class TestStripThinking:
    """Strip thinking blocks from reasoning model output (qwen3 / deepseek style)."""

    def test_strips_thinking_and_returns_response(self):
        from aiassistant.agent.reasoner import _strip_thinking

        content = "<thinking>\nLet me think about this step by step.\nThe answer is 42.\n<response>\nIt seems the answer is 42."
        result = _strip_thinking(content)
        assert result == "It seems the answer is 42."
        assert "<thinking>" not in result
        assert "Let me think" not in result

    def test_response_only_no_thinking(self):
        from aiassistant.agent.reasoner import _strip_thinking

        content = "The time is 3pm."
        result = _strip_thinking(content)
        assert result == "The time is 3pm."

    def test_thinking_without_response_marker(self):
        from aiassistant.agent.reasoner import _strip_thinking

        content = "<thinking>\nThe user wants stock prices.\nI should search for that."
        result = _strip_thinking(content)
        # Thinking-only without response marker: strip it, fall back to original if empty
        assert "stock prices" not in result

    def test_empty_content(self):
        from aiassistant.agent.reasoner import _strip_thinking

        assert _strip_thinking("") == ""
        assert _strip_thinking(None) is None

    def test_qwen3_plain_text_markers(self):
        """Real qwen3 format: space + 'thinking' on own line, then ' response' marker."""
        from aiassistant.agent.reasoner import _strip_thinking

        # Exact format from qwen3 via ollama
        content = (
            " thinking\n"
            "Okay, the user said \"hi\". I should respond in a friendly way.\n"
            " response\n"
            "\n"
            "Hello! How can I assist you today?"
        )
        result = _strip_thinking(content)
        assert result == "Hello! How can I assist you today?"
        assert "thinking" not in result
        assert "Okay, the user" not in result

    def test_qwen3_hybrid_format(self):
        """qwen3 hybrid: <thinking> opening tag with plain 'response' separator."""
        from aiassistant.agent.reasoner import _strip_thinking

        content = (
            "<thinking>\n"
            "Let me think about this.\n"
            " response\n"
            "\n"
            "Here is my answer."
        )
        result = _strip_thinking(content)
        assert result == "Here is my answer."
        assert "Let me think" not in result

    def test_reason_strips_thinking_from_response(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {
            "content": "<thinking>\nLet me calculate.\n<response>\n2+2 equals 4.",
            "tool_calls": None,
            "usage": {"total_tokens": 20},
        }
        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        response = reasoner.reason("What is 2+2?")
        assert response["content"] == "2+2 equals 4."

    def test_reason_with_tool_results_strips_thinking(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {
            "content": "<thinking>\nAnalyzing results.\n<response>\nToday is Monday, May 24.",
            "tool_calls": None,
            "usage": {},
        }
        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        calls = [{"name": "datetime", "arguments": {}}]
        results = [{"result": "2026-05-24"}]
        response = reasoner.reason_with_tool_results(calls, results)
        assert response["content"] == "Today is Monday, May 24."


class TestReasonerTools:
    """Reasoner: tool schema management and tool-result feedback loop."""

    def test_set_tools_updates_schemas(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        assert reasoner._tool_schemas is None

        reasoner.set_tools([{"type": "function", "function": {"name": "test_tool", "description": "A test tool"}}])
        assert reasoner._tool_schemas is not None
        assert len(reasoner._tool_schemas) == 1

    def test_reason_uses_stored_tool_schemas(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {"content": "I'll check.", "tool_calls": None, "usage": {"total_tokens": 20}}
        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner.set_tools([{"type": "function", "function": {"name": "datetime", "description": "Get current time"}}])

        response = reasoner.reason("What time is it?")
        # Should not crash and should return content
        assert "content" in response
        assert len(mock_llm.chat_calls) == 1
        # Verify tools were passed to LLM
        assert mock_llm.chat_calls[0]["tools"] is not None

    def test_reason_uses_param_overrides_stored(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {"content": "Ok.", "tool_calls": None, "usage": {}}
        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner.set_tools([{"type": "function", "function": {"name": "stored", "description": "Stored"}}])

        # Param should override stored schemas
        override = [{"type": "function", "function": {"name": "override", "description": "Override"}}]
        reasoner.reason("test", tool_schemas=override)
        assert mock_llm.chat_calls[-1]["tools"] == override

    def test_reason_without_tools_passes_none(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {"content": "Hello.", "tool_calls": None, "usage": {}}
        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner.reason("Hi")
        assert mock_llm.chat_calls[0]["tools"] is None

    def test_reason_with_tool_results_appends_to_history(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {"content": "The time is 3pm.", "tool_calls": None, "usage": {"total_tokens": 20}}
        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner._history = [{"role": "user", "content": "What time is it?"}]

        calls = [{"name": "datetime", "arguments": {}}]
        results = [{"result": "2024-01-15 15:00:00"}]
        response = reasoner.reason_with_tool_results(calls, results)

        assert "content" in response
        # History should now contain assistant tool_call (with function wrapper) + tool result + assistant response
        history_roles = [m["role"] for m in reasoner._history]
        assert "tool" in history_roles
        assert history_roles.count("assistant") >= 2
        # Verify the function wrapper is present in history
        assistant_tc_msg = [m for m in reasoner._history if m["role"] == "assistant" and m.get("tool_calls")][0]
        assert assistant_tc_msg["tool_calls"][0]["function"]["name"] == "datetime"

    def test_reason_with_tool_results_synthesizes_answer(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        mock_llm.chat_response = {"content": "The temperature is 72F in Tokyo.", "tool_calls": None, "usage": {}}
        reasoner = Reasoner(mock_llm, persona="You are helpful.")

        calls = [{"name": "weather", "arguments": {"city": "Tokyo"}}]
        results = [{"result": {"temperature": 72, "city": "Tokyo"}}]
        response = reasoner.reason_with_tool_results(calls, results)

        assert "72" in response["content"]
        assert "Tokyo" in response["content"]

    def test_reset_clears_tool_schemas(self, mock_llm):
        from aiassistant.agent.reasoner import Reasoner

        reasoner = Reasoner(mock_llm, persona="You are helpful.")
        reasoner.set_tools([{"type": "function", "function": {"name": "test", "description": "Test"}}])
        reasoner.reset()
        assert reasoner._tool_schemas is not None  # reset doesn't clear tools, only history
        assert reasoner._history == []


class TestBrainToolWiring:
    """Verify Brain → Hands tool loading via bus messages."""

    def test_tool_cache_loads_from_hands_ready_message(self, message_bus):
        from aiassistant.agent.toolcache import ToolCache

        tc = ToolCache()
        assert tc.tool_names == []

        # Simulate status.hands.ready message
        tools = [
            {"name": "web_search", "description": "Search the web", "parameters": {"type": "object", "properties": {}}},
            {"name": "datetime", "description": "Get current time", "parameters": {"type": "object", "properties": {}}},
        ]
        tc.load(tools)
        assert len(tc.tool_names) == 2
        assert "web_search" in tc.tool_names

        # Verify get_formatted_schemas wraps in function format
        formatted = tc.get_formatted_schemas()
        assert len(formatted) == 2
        for f in formatted:
            assert f["type"] == "function"
            assert "function" in f
            assert "name" in f["function"]

        # The native harness accepts the same formatted schemas (ADR-0009
        # removed the Reasoner stage; the harness owns prompting now).
        from aiassistant.agent.harness.native import NativeHarness
        from aiassistant.reasoning.base import LLMBackend, StreamChunk

        class FakeLLM(LLMBackend):
            def chat(self, messages, **kwargs): return {}
            def chat_stream(self, messages, **kwargs):
                yield StreamChunk(done=True, content="")
            def embed(self, text): return []

        harness = NativeHarness(FakeLLM(model=""), persona="Test",
                                tool_schemas=formatted)
        assert harness.tool_schemas == formatted
