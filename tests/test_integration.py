"""Integration tests — full message flow with real Ollama."""
import asyncio
import pytest
from bus.bus import MessageBus
from brain.brain import BrainModule
from modules.hands.hands import HandsModule
from modules.scheduler.scheduler import SchedulerModule


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
                "conversations_path": "./data/memory/conversations",
                "facts_path": "./data/memory/facts",
                "knowledge_path": "./data/memory/knowledge",
                "embeddings_db": "./data/embeddings.db",
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
            "storage_path": "./data/schedules.json",
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
