"""Agent turn control: one turn at a time, and interrupt that actually works.

Regression context: the turn used to be started with ``asyncio.ensure_future``
and the handle was dropped, so nothing could cancel it. ``command.agent.interrupt``
had no subscriber. Both are fixed in chunk 1.
"""

import asyncio

import pytest

from aiassistant.bus import topics
from aiassistant.bus.bus import MessageBus
from aiassistant.agent.module import AgentModule


class SlowLLM:
    """Blocks in chat until released, so a turn can be cancelled mid-flight."""

    def __init__(self, delay: float = 5.0):
        self.delay = delay
        self.started = asyncio.Event() if False else None
        self.calls = 0
        self.cancelled = False

    def chat(self, messages, tools=None, max_tokens=4096, temperature=0.7):
        import time
        self.calls += 1
        time.sleep(self.delay)
        return {"content": "late answer", "tool_calls": None, "usage": {}}

    def embed(self, text):
        return [0.0]

    def embed_batch(self, texts):
        return [[0.0] for _ in texts]

    def token_count(self, messages):
        return 10


def _config():
    return {
        "agent": {
            "llm": {"provider": "ollama", "model": "test"},
            "memory": {
                "conversations_path": "/tmp/aiassistant_test/memory",
            },
            "embeddings": {"provider": "same", "model": ""},
            "thinking": {"max_reflect_loops": 3},
        },
        "conversation": {"busy": "interrupt"},
    }


@pytest.fixture
def brain():
    bus = MessageBus()
    mod = AgentModule(bus, _config())
    return bus, mod


class TestTurnLifecycle:
    def test_turn_handle_is_retained(self, brain):
        bus, mod = brain
        assert mod._turn_task is None
        mod.perceiver = mod.perceiver  # no-op, keeps intent explicit

    def test_new_input_supersedes_in_flight_turn(self, brain):
        """The supersede policy must leave exactly one live task."""
        bus, mod = brain
        from aiassistant.agent.perceive import PerceivedInput

        perceived = PerceivedInput(
            input_type="text", raw_payload={"text": "hi", "channel": "console"},
        )

        async def scenario():
            mod._turn_task = asyncio.ensure_future(asyncio.sleep(10))
            first = mod._turn_task
            mod._start_turn(perceived, "user.input.text")
            await asyncio.sleep(0)
            assert first.cancelled() or first.done()
            assert mod._turn_task is not first
            mod._turn_task.cancel()

        asyncio.run(scenario())

    @pytest.mark.xfail(strict=True,
                       reason="BUG-4: conversation.busy: queue is documented "
                              "(schemas.md:246, REQ-CONV-002) but _start_turn "
                              "always cancels; it never queues")
    def test_queue_policy_does_not_cancel_the_first_turn(self):
        """REQ-CONV-002: with ``busy: queue`` the first turn must survive."""
        from aiassistant.agent.harness.fake import FakeHarness
        from aiassistant.agent.perceive import PerceivedInput

        bus = MessageBus()
        mod = AgentModule(bus, {
            "agent": {
                "llm": {"provider": "ollama", "model": "test"},
                "memory": {"conversations_path": "/tmp/aiassistant_test/memory_q"},
            },
            "conversation": {"busy": "queue"},
        })
        mod.harness = FakeHarness(stall=True)

        async def scenario():
            mod._turn_task = asyncio.ensure_future(asyncio.sleep(10))
            first = mod._turn_task
            mod._start_turn(
                PerceivedInput(input_type="text",
                               raw_payload={"text": "second", "channel": "console"}),
                "user.input.text",
            )
            await asyncio.sleep(0.05)
            queued = not first.cancelled() and not first.done()
            if mod._turn_task is not first and not mod._turn_task.done():
                mod._turn_task.cancel()
            first.cancel()
            try:
                await first
            except asyncio.CancelledError:
                pass
            return queued

        assert asyncio.run(scenario()) is True


class TestTerminalTurnFallback:
    """REQ-CONV-006: a harness that ends without a terminal event must not
    leave the turn dangling — the agent publishes a visible error instead."""

    def test_harness_without_a_terminal_event_ends_in_an_error(self):
        from aiassistant.agent.harness.base import (
            AgentHarness, EventKind, HarnessCaps, HarnessHealth, TurnEvent,
        )
        from aiassistant.agent.perceive import PerceivedInput

        class NoTerminal(AgentHarness):
            name = "no-terminal"

            @property
            def caps(self):
                return HarnessCaps()

            async def health(self):
                return HarnessHealth(ok=True)

            async def cancel(self):
                pass

            async def run_turn(self, req):
                yield TurnEvent(kind=EventKind.TEXT_DELTA, text="partial")

        bus = MessageBus()
        mod = AgentModule(bus, {
            "agent": {
                "llm": {"provider": "ollama", "model": "test"},
                "memory": {"conversations_path": "/tmp/aiassistant_test/memory_nt"},
            },
        })
        errors, finals = [], []
        bus.subscribe(topics.AGENT_TURN_ERROR, lambda t, p: errors.append(p))
        bus.subscribe(topics.AGENT_FINAL, lambda t, p: finals.append(p))

        async def scenario():
            mod.harness = NoTerminal()
            await mod._thinking_loop(
                PerceivedInput(input_type="text",
                               raw_payload={"text": "hi", "channel": "console"}),
                topics.USER_INPUT_TEXT,
            )

        asyncio.run(scenario())
        assert len(errors) == 1, "a missing terminal event must surface as an error"
        assert errors[0]["class"] == "harness"
        assert finals == [], "no final response is fabricated for a broken turn"


class TestInterrupt:
    def test_interrupt_is_subscribed(self, brain):
        bus, mod = brain
        assert bus.has_subscriber(topics.COMMAND_AGENT_INTERRUPT) is False
        asyncio.run(mod.start())
        assert bus.has_subscriber(topics.COMMAND_AGENT_INTERRUPT) is True
        asyncio.run(mod.stop())

    def test_interrupt_cancels_the_running_turn(self, brain):
        """This is the whole point: interrupt must stop work in flight."""
        bus, mod = brain
        from aiassistant.agent.harness.fake import FakeHarness

        harness = FakeHarness(stall=True)

        async def scenario():
            await mod.setup()
            # Inject a stalling harness so the turn is cancellable without a model.
            mod.harness = harness
            await mod.start()
            from aiassistant.agent.perceive import PerceivedInput
            perceived = PerceivedInput(
                input_type="text", raw_payload={"text": "slow", "channel": "console"},
            )
            mod._start_turn(perceived, topics.USER_INPUT_TEXT)
            await asyncio.sleep(0.2)
            assert mod._turn_task is not None and not mod._turn_task.done()

            await mod.interrupt()
            assert mod._turn_task is None
            assert harness._cancelled is True
            await mod.stop()

        asyncio.run(scenario())

    def test_interrupt_is_safe_with_no_turn(self, brain):
        bus, mod = brain

        async def scenario():
            await mod.start()
            await mod.interrupt()
            await mod.interrupt()
            await mod.stop()

        asyncio.run(scenario())


class TestSpeechRouting:
    def test_voice_channel_triggers_speech(self):
        assert topics.should_speak("voice") is True

    def test_console_channel_does_not_speak(self):
        assert topics.should_speak("console") is False

    def test_deliver_response_publishes_speak_only_when_asked(self, brain):
        bus, mod = brain
        spoken = []
        bus.subscribe(topics.VOICE_SPEAK, lambda t, p: spoken.append(p))

        response = {"text": "hello", "conversation_id": "x", "thinking": None}
        mod._deliver_response(response, should_speak=False)
        assert spoken == []

        mod._deliver_response(response, should_speak=True)
        assert len(spoken) == 1
        assert spoken[0]["text"] == "hello"
