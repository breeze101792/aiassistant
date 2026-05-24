import pytest

from modules.mouth.mouth import MouthModule
from modules.mouth.tts_backends.text import TextTTS
from modules.mouth.tts_backends.base import TTSBackend
from bus.bus import MessageBus


class TestTextTTS:
    def test_speak_prints_to_stdout(self, capsys):
        tts = TextTTS()
        tts.speak('Hello world')
        captured = capsys.readouterr()
        assert 'Hello world' in captured.out

    def test_is_instance_of_base(self):
        assert isinstance(TextTTS(), TTSBackend)


class TestMouthModule:
    def test_module_name(self):
        bus = MessageBus()
        mouth = MouthModule(bus, {'backend': 'text'})
        assert mouth.module_name == 'mouth'

    def test_text_backend_selected(self):
        bus = MessageBus()
        mouth = MouthModule(bus, {'backend': 'text'})
        assert mouth.backend_name == 'text'

    @pytest.mark.asyncio
    async def test_interrupt_clears_pending_items(self, message_bus, capsys):
        """Bug regression: interrupt clears queue but the active item may still finish."""
        mouth = MouthModule(message_bus, {'backend': 'text'})
        await mouth.setup()
        await mouth.start()

        # Enqueue first item — it starts processing immediately
        message_bus.publish("action.speak", {"text": "first", "interrupt": False})
        # Queue has one item, wait briefly for it to start
        import asyncio
        await asyncio.sleep(0.05)

        # Interrupt should clear remaining queue items
        message_bus.publish("action.speak", {"text": "replace", "interrupt": True})

        # Add another item
        message_bus.publish("action.speak", {"text": "after", "interrupt": False})

        # Wait for queue to drain
        await asyncio.sleep(0.3)

        captured = capsys.readouterr()
        # "replace" should appear (the interrupt item)
        assert "replace" in captured.out
        # "after" should appear (added after interrupt)
        assert "after" in captured.out

    @pytest.mark.asyncio
    async def test_queue_sequential_processing(self, message_bus, capsys):
        """Multiple items are processed in order."""
        mouth = MouthModule(message_bus, {'backend': 'text'})
        await mouth.setup()
        await mouth.start()

        message_bus.publish("action.speak", {"text": "one"})
        message_bus.publish("action.speak", {"text": "two"})

        import asyncio
        await asyncio.sleep(0.2)

        captured = capsys.readouterr()
        pos_one = captured.out.index("one")
        pos_two = captured.out.index("two")
        assert pos_one < pos_two
