"""Integration tests — full message flow with real Ollama."""
import asyncio
import pytest
from bus.bus import MessageBus
from brain.brain import BrainModule
from modules.hands.hands import HandsModule
from modules.scheduler.scheduler import SchedulerModule
from llm.base import LLMBackend


class MockToolLLM(LLMBackend):
    """Mock LLM that returns tool_calls for testing the full tool pipeline."""

    def __init__(self, model="mock", url=""):
        self.model = model
        self.url = url
        self.api_key = ""
        self.chat_calls: list[dict] = []
        self.embed_calls: list[list[str]] = []

    def chat(self, messages, tools=None, max_tokens=4096, temperature=0.7):
        call = {"messages": [dict(m) for m in messages], "tools": tools}
        self.chat_calls.append(call)

        # If this is the first call and tools are available, return a tool_call
        if tools and len(self.chat_calls) == 1:
            return {
                "content": "Let me look that up.",
                "tool_calls": [{
                    "id": "call_001",
                    "name": "datetime",
                    "arguments": "{}",
                }],
                "usage": {"total_tokens": 30},
            }
        # Second call (after tool results), return a synthesized answer
        return {
            "content": "Today is Monday, May 24, 2026.",
            "tool_calls": None,
            "usage": {"total_tokens": 20},
        }

    def embed(self, text):
        self.embed_calls.append(text if isinstance(text, list) else [text])
        return [0.1, 0.2, 0.3]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

    def token_count(self, messages):
        return 100


@pytest.fixture
def config():
    return {
        "brain": {
            "persona": "You are a helpful assistant. Be concise. Answer in 1-2 sentences.",
            "llm": {
                "provider": "ollama",
                "model": "qwen3:latest",
                "url": "http://127.0.0.1:11434",
                "api_key": "",
                "max_tokens": 256,
                "temperature": 0.7,
            },
            "memory": {
                "conversations_path": ".config/aiassistant/memory/conversations",
                "facts_path": ".config/aiassistant/memory/facts",
                "knowledge_path": ".config/aiassistant/memory/knowledge",
                "embeddings_db": ".config/aiassistant/embeddings.db",
                "context_max_tokens": 4096,
                "context_recent_messages": 20,
            },
            "embeddings": {"provider": "ollama", "model": "qwen3-embedding:0.6b", "url": "", "batch_size": 10},
            "thinking": {"max_reflect_loops": 3},
        },
        "hands": {
            "tool_paths": ["./modules/hands/builtin_tools", "./modules/hands/skills"],
            "sandbox_default": False,
            "command_timeout": 30,
            "safe_paths": ["./workspace", "/tmp/aiassistant"],
        },
        "scheduler": {
            "storage_path": ".config/aiassistant/schedules.json",
            "max_pending": 100,
        },
    }


class TestTextChatFlow:
    """End-to-end text chat with real Ollama."""

    @pytest.mark.asyncio
    async def test_brain_responds_to_text(self, config):
        bus = MessageBus()

        # Setup modules
        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)
        sched = SchedulerModule(bus, config)

        assert await brain.setup()
        assert await hands.setup()
        assert await sched.setup()

        await brain.start()
        await hands.start()
        await sched.start()

        # Collect responses
        responses = []

        def on_response(topic, payload):
            responses.append(payload)

        bus.subscribe("response.text", on_response)

        # Send a message
        bus.user_input("What is 2+2? Answer in one short sentence.")

        # Wait for response
        await asyncio.sleep(10)

        await brain.stop()
        await hands.stop()
        await sched.stop()

        assert len(responses) > 0, "No response received from brain"
        text = responses[0].get("text", "")
        assert len(text) > 0, "Empty response text"
        assert "4" in text or "four" in text.lower(), f"Expected answer containing 4, got: {text}"
        print(f"\nBrain response: {text}")

    @pytest.mark.asyncio
    async def test_brain_with_tool_call(self, config):
        bus = MessageBus()

        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)
        sched = SchedulerModule(bus, config)

        assert await brain.setup()
        assert await hands.setup()
        assert await sched.setup()

        await brain.start()
        await hands.start()
        await sched.start()

        responses = []

        def on_response(topic, payload):
            responses.append(payload)

        bus.subscribe("response.text", on_response)

        # Ask something that should use the datetime tool
        bus.user_input("What day is it today? Use the datetime tool if available.")

        await asyncio.sleep(15)

        await brain.stop()
        await hands.stop()
        await sched.stop()

        assert len(responses) > 0, "No response received"
        text = responses[0].get("text", "")
        print(f"\nBrain response (with tools): {text}")
        print(f"Tools used: {responses[0].get('tools_used', [])}")

    @pytest.mark.asyncio
    async def test_conversation_memory(self, config):
        bus = MessageBus()

        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)
        sched = SchedulerModule(bus, config)

        assert await brain.setup()
        await hands.setup()
        await sched.setup()

        await brain.start()
        await hands.start()
        await sched.start()

        responses = []

        def on_response(topic, payload):
            responses.append(payload)

        bus.subscribe("response.text", on_response)

        # First turn
        bus.user_input("My name is TestUser. Remember that.")
        await asyncio.sleep(8)

        # Second turn
        bus.user_input("What is my name?")
        await asyncio.sleep(8)

        await brain.stop()
        await hands.stop()
        await sched.stop()

        assert len(responses) >= 2, f"Expected at least 2 responses, got {len(responses)}"
        second_response = responses[1].get("text", "")
        print(f"\nResponse 1: {responses[0].get('text', '')}")
        print(f"Response 2: {second_response}")

        # Second response should reference TestUser
        assert "TestUser" in second_response or "testuser" in second_response.lower(), \
            f"Expected brain to remember name 'TestUser', got: {second_response}"


class TestModuleLifecycle:
    """Module start/stop integration."""

    @pytest.mark.asyncio
    async def test_all_modules_start_stop(self, config):
        bus = MessageBus()
        modules = []

        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)
        sched = SchedulerModule(bus, config)

        for mod in [brain, hands, sched]:
            assert await mod.setup()
            await mod.start()
            modules.append(mod)

        for mod in reversed(modules):
            await mod.stop()

        assert True  # no crashes


class TestToolCallingWithMockLLM:
    """End-to-end tool calling using a mock LLM (no real Ollama needed)."""

    @pytest.mark.asyncio
    async def test_brain_receives_tool_schemas_from_hands(self, config):
        """Verify Brain subscribes to status.hands.ready and loads tool schemas."""
        bus = MessageBus()
        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)

        await brain.setup()
        await hands.setup()

        # Replace with mock LLM after setup
        mock_llm = MockToolLLM()
        brain.llm = mock_llm
        brain._reasoner.llm = mock_llm

        # Tools should be empty before Hands starts
        assert len(brain.tool_cache.tool_names) == 0

        await brain.start()
        await hands.start()

        # Let scheduled event-loop tasks (like status.hands.ready handler) complete
        await asyncio.sleep(0.01)

        # After Hands starts, Brain should have loaded tools
        assert len(brain.tool_cache.tool_names) > 0
        assert "datetime" in brain.tool_cache.tool_names
        assert brain._reasoner._tool_schemas is not None

        await brain.stop()
        await hands.stop()

    @pytest.mark.asyncio
    async def test_full_tool_call_flow_with_mock_llm(self, config):
        """Full pipeline: user asks question → LLM calls tool → tool executes → LLM synthesizes."""
        bus = MessageBus()
        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)

        await brain.setup()
        await hands.setup()

        mock_llm = MockToolLLM()
        brain.llm = mock_llm
        brain._reasoner.llm = mock_llm

        await brain.start()
        await hands.start()

        # Let scheduled event-loop tasks (like status.hands.ready handler) complete
        await asyncio.sleep(0.01)

        responses = []
        bus.subscribe("response.text", lambda t, p: responses.append(p))

        # Send a question that should trigger tool calling
        bus.user_input("What day is it today?")

        await asyncio.sleep(0.5)

        await brain.stop()
        await hands.stop()

        # Verify response was produced
        assert len(responses) > 0, "No response received"
        text = responses[0].get("text", "")
        assert len(text) > 0

        # Verify tool was used
        tools_used = responses[0].get("tools_used", [])
        assert len(tools_used) > 0, f"No tools were used. Response: {text}"
        assert any(t["name"] == "datetime" for t in tools_used), \
            f"Expected datetime tool to be called, got: {tools_used}"

        # LLM should have been called twice (first with tools, second for synthesis)
        assert len(mock_llm.chat_calls) >= 2, \
            f"Expected at least 2 LLM calls, got {len(mock_llm.chat_calls)}"

    @pytest.mark.asyncio
    async def test_tool_call_response_reflects_tool_result(self, config):
        """The final response should be synthesized from tool results, not the first LLM response."""
        bus = MessageBus()
        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)

        await brain.setup()
        await hands.setup()

        mock_llm = MockToolLLM()
        brain.llm = mock_llm
        brain._reasoner.llm = mock_llm

        await brain.start()
        await hands.start()

        # Let scheduled event-loop tasks (like status.hands.ready handler) complete
        await asyncio.sleep(0.01)

        responses = []
        bus.subscribe("response.text", lambda t, p: responses.append(p))

        bus.user_input("What day is it?")

        await asyncio.sleep(0.5)

        await brain.stop()
        await hands.stop()

        assert len(responses) > 0
        text = responses[0].get("text", "")
        # The mock's second response says "Monday, May 24, 2026" — this
        # proves synthesis happened, not just echoing the first response
        assert "Today is Monday" in text, \
            f"Expected synthesized response, got: {text}"

    @pytest.mark.asyncio
    async def test_direct_answer_without_tools(self, config):
        """When LLM doesn't return tool_calls, flow should work without tools."""
        bus = MessageBus()
        brain = BrainModule(bus, config)
        hands = HandsModule(bus, config)

        await brain.setup()
        await hands.setup()

        mock_llm = MockToolLLM()
        brain.llm = mock_llm
        brain._reasoner.llm = mock_llm
        # Override first response to NOT have tool_calls
        def no_tool_chat(messages, tools=None, **kwargs):
            return {"content": "Hello! How can I help?", "tool_calls": None, "usage": {}}
        mock_llm.chat = no_tool_chat

        await brain.start()
        await hands.start()

        responses = []
        bus.subscribe("response.text", lambda t, p: responses.append(p))

        bus.user_input("Hi there")

        await asyncio.sleep(0.5)

        await brain.stop()
        await hands.stop()

        assert len(responses) > 0
        assert responses[0].get("text") == "Hello! How can I help?"
        assert responses[0].get("tools_used", []) == []
