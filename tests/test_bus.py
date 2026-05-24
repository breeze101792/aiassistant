import asyncio
import pytest
from bus.bus import MessageBus
from bus.errors import NoSubscriberError, TimeoutError


class TestPubSub:
    """Pub/Sub delivery semantics."""

    def test_single_subscriber_receives_message(self):
        bus = MessageBus()
        received = []

        def handler(topic, payload):
            received.append((topic, payload))

        bus.subscribe("test.hello", handler)
        bus.publish("test.hello", {"msg": "world"})

        assert len(received) == 1
        assert received[0] == ("test.hello", {"msg": "world"})

    def test_multiple_subscribers_same_topic(self):
        bus = MessageBus()
        received = []

        def handler1(topic, payload):
            received.append("h1")

        def handler2(topic, payload):
            received.append("h2")

        bus.subscribe("test.multi", handler1)
        bus.subscribe("test.multi", handler2)
        bus.publish("test.multi", {})

        assert len(received) == 2
        assert "h1" in received
        assert "h2" in received

    def test_unsubscribe_stops_delivery(self):
        bus = MessageBus()
        received = []

        def handler(topic, payload):
            received.append(payload)

        sub_id = bus.subscribe("test.stop", handler)
        bus.publish("test.stop", {"count": 1})
        bus.unsubscribe(sub_id)
        bus.publish("test.stop", {"count": 2})

        assert len(received) == 1
        assert received[0] == {"count": 1}

    def test_wrong_topic_not_received(self):
        bus = MessageBus()
        received = []

        def handler(topic, payload):
            received.append(payload)

        bus.subscribe("test.foo", handler)
        bus.publish("test.bar", {"x": 1})

        assert len(received) == 0

    def test_publish_no_subscribers_does_not_crash(self):
        bus = MessageBus()
        bus.publish("test.nosub", {"data": 1})

    def test_subscriber_exception_does_not_affect_others(self):
        bus = MessageBus()
        good_received = []

        def bad_handler(topic, payload):
            raise RuntimeError("boom")

        def good_handler(topic, payload):
            good_received.append(payload)

        bus.subscribe("test.error", bad_handler)
        bus.subscribe("test.error", good_handler)
        bus.publish("test.error", {"val": 42})

        assert len(good_received) == 1
        assert good_received[0] == {"val": 42}

    @pytest.mark.asyncio
    async def test_async_handler_is_scheduled(self):
        bus = MessageBus()
        received = []

        async def async_handler(topic, payload):
            await asyncio.sleep(0.001)
            received.append(payload)

        bus.subscribe("test.async", async_handler)
        bus.publish("test.async", {"key": "value"})

        # Let the async task complete
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0] == {"key": "value"}


class TestRPC:
    """RPC request-response."""

    @pytest.mark.asyncio
    async def test_rpc_gets_response(self):
        bus = MessageBus()

        def responder(topic, payload):
            request_id = payload.get("_request_id")
            if request_id:
                bus.respond_rpc(request_id, {"answer": 42})

        bus.subscribe("brain.ask", responder)
        result = await bus.request("brain.ask", {"question": "life"})
        assert result == {"answer": 42}

    @pytest.mark.asyncio
    async def test_rpc_no_subscriber_raises(self):
        bus = MessageBus()
        with pytest.raises(NoSubscriberError):
            await bus.request("nobody.here", {}, timeout=0.5)

    @pytest.mark.asyncio
    async def test_rpc_timeout_raises(self):
        bus = MessageBus()

        def slow_responder(topic, payload):
            pass  # never responds

        bus.subscribe("slow.service", slow_responder)
        with pytest.raises(TimeoutError):
            await bus.request("slow.service", {}, timeout=0.1)


class TestModuleLifecycle:
    """Module registration."""

    def test_register_module(self):
        bus = MessageBus()

        class FakeMod:
            module_name = "test_mod"

        bus.register(FakeMod())
        modules = bus.list_modules()
        assert "test_mod" in modules
        assert modules["test_mod"]["status"] == "ready"

    def test_unregister_module(self):
        bus = MessageBus()

        class FakeMod:
            module_name = "temp_mod"

        bus.register(FakeMod())
        assert "temp_mod" in bus.list_modules()
        bus.unregister("temp_mod")
        assert "temp_mod" not in bus.list_modules()

    def test_list_modules_initially_empty(self):
        bus = MessageBus()
        assert bus.list_modules() == {}


class TestUserInput:
    """User input shortcut."""

    def test_user_input_publishes_correct_topic(self):
        bus = MessageBus()
        received = []

        def handler(topic, payload):
            received.append((topic, payload))

        bus.subscribe("user.input.text", handler)
        bus.user_input("hello")

        assert len(received) == 1
        topic, payload = received[0]
        assert topic == "user.input.text"
        assert payload["text"] == "hello"
        assert payload["channel"] == "cli"
        assert payload["sender"] == "user"
        assert "timestamp" in payload


class TestHasSubscriber:
    """Subscriber detection."""

    def test_has_subscriber_true(self):
        bus = MessageBus()
        bus.subscribe("test.x", lambda t, p: None)
        assert bus.has_subscriber("test.x")

    def test_has_subscriber_false(self):
        bus = MessageBus()
        assert not bus.has_subscriber("test.nobody")


class TestRemoteBusSubscriptionCleanup:
    """Bug regression: RemoteBus must clean up subscriptions on disconnect."""

    @pytest.mark.asyncio
    async def test_subscriptions_are_removed_on_disconnect(self, message_bus):
        """Subscriptions from remote client should be removed from bus after disconnect."""
        from bus.remote import RemoteBus
        import json
        import asyncio

        initial_sub_count = len(message_bus._subscribers)

        remote = RemoteBus(message_bus, port=18765)
        server_task = asyncio.ensure_future(remote.start())
        await asyncio.sleep(0.1)

        try:
            import websockets
            async with websockets.connect("ws://127.0.0.1:18765") as ws:
                # Register
                await ws.send(json.dumps({
                    "action": "register",
                    "module_name": "test_module",
                    "capabilities": {"type": "test"},
                }))
                await ws.recv()  # "registered"

                # Subscribe to topics
                await ws.send(json.dumps({
                    "action": "subscribe",
                    "topic": "test.topic.one",
                }))
                await ws.send(json.dumps({
                    "action": "subscribe",
                    "topic": "test.topic.two",
                }))

                await asyncio.sleep(0.05)
                assert message_bus.has_subscriber("test.topic.one")
                assert message_bus.has_subscriber("test.topic.two")
        except Exception:
            pass
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

        # After disconnect, subscriptions should be cleaned up
        remaining_count = len(message_bus._subscribers)
        assert remaining_count == initial_sub_count, \
            f"Expected {initial_sub_count} subscribers after cleanup, got {remaining_count}"


class TestRegistry:
    """Module registry operations."""

    def test_add_and_list(self, message_bus):
        message_bus.registry.add("test_mod", remote=False)
        modules = message_bus.registry.list_all()
        assert "test_mod" in modules

    def test_remove(self, message_bus):
        message_bus.registry.add("test_mod")
        assert message_bus.registry.is_registered("test_mod")
        message_bus.registry.remove("test_mod")
        assert not message_bus.registry.is_registered("test_mod")

    def test_module_names_property(self, message_bus):
        message_bus.registry.add("mod_a")
        message_bus.registry.add("mod_b")
        names = message_bus.registry.module_names
        assert "mod_a" in names
        assert "mod_b" in names

    def test_get_nonexistent_returns_none(self, message_bus):
        assert message_bus.registry.get("nonexistent") is None
