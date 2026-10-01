"""Bridge client tests against a real in-process WebSocket server.

The pre-refactor transport had no test at all, which is why a signature
mismatch shipped and every remote connection died. These exercise the real
protocol: connect, register, subscribe, receive a forward, publish, and
reconnect.
"""

import asyncio

import pytest
import pytest_asyncio

from aiassistant.bridge import Bridge, BridgeError
from aiassistant.bus.bus import MessageBus
from aiassistant.bus.remote import RemoteBus

websockets = pytest.importorskip("websockets")


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture
async def server():
    bus = MessageBus()
    bus._loop = asyncio.get_running_loop()
    port = _free_port()
    remote = RemoteBus(bus, port=port)
    await remote.start()
    yield bus, f"ws://127.0.0.1:{port}"
    await remote.stop()


class TestBridgeConnection:
    @pytest.mark.asyncio
    async def test_connect_registers(self, server):
        bus, url = server
        states = []
        bridge = Bridge(url=url, name="orb", on_state=states.append)
        await bridge.connect()
        assert "connected" in states
        assert bus.registry.get("orb") is not None
        await bridge.close()

    @pytest.mark.asyncio
    async def test_subscribe_then_receive_a_forward(self, server):
        bus, url = server
        received = []
        bridge = Bridge(url=url, on_message=lambda t, p: received.append((t, p)))
        await bridge.connect()
        run = asyncio.ensure_future(bridge.run())
        await bridge.subscribe("test.topic")
        await asyncio.sleep(0.1)

        bus.publish("test.topic", {"n": 1})
        for _ in range(50):
            await asyncio.sleep(0.02)
            if received:
                break
        assert received == [("test.topic", {"n": 1})]
        await bridge.close()
        run.cancel()

    @pytest.mark.asyncio
    async def test_publish_reaches_the_bus(self, server):
        bus, url = server
        seen = []
        bus.subscribe("from.orb", lambda t, p: seen.append(p))
        bridge = Bridge(url=url, name="orb")
        await bridge.connect()
        await bridge.publish("from.orb", {"x": 2})
        for _ in range(50):
            await asyncio.sleep(0.02)
            if seen:
                break
        assert seen == [{"x": 2}]
        await bridge.close()

    @pytest.mark.asyncio
    async def test_unreachable_server_raises_a_typed_error(self):
        bridge = Bridge(url=f"ws://127.0.0.1:{_free_port()}")
        with pytest.raises(BridgeError, match="cannot reach"):
            await bridge.connect()
        await bridge.close()

    @pytest.mark.asyncio
    async def test_publish_without_a_connection_raises(self):
        bridge = Bridge(url="ws://127.0.0.1:1")
        with pytest.raises(BridgeError):
            await bridge.publish("x", {})

    @pytest.mark.asyncio
    async def test_subscriptions_are_remembered_for_resubscribe(self, server):
        bus, url = server
        bridge = Bridge(url=url, name="orb")
        await bridge.connect()
        await bridge.subscribe("a.topic")
        await bridge.subscribe("b.topic")
        assert bridge.subscriptions == {"a.topic", "b.topic"}
        await bridge.close()


class TestBridgeReconnect:
    @pytest.mark.asyncio
    async def test_reconnects_and_resubscribes(self, server):
        """A dropped connection must not silently stop the display."""
        bus, url = server
        received = []
        states = []
        bridge = Bridge(
            url=url, name="orb",
            on_message=lambda t, p: received.append(p),
            on_state=states.append,
        )
        await bridge.connect()
        await bridge.subscribe("drop.topic")
        await asyncio.sleep(0.1)
        assert bus.has_subscriber("drop.topic")

        # Force a disconnect; the run loop should reconnect and resubscribe.
        await bridge._ws.close()
        run = asyncio.ensure_future(bridge.run())

        for _ in range(200):
            await asyncio.sleep(0.05)
            if bus.has_subscriber("drop.topic") and any(
                "disconnected" in s for s in states
            ):
                break

        assert any("disconnected" in s for s in states), "no disconnect was reported"
        assert bus.has_subscriber("drop.topic"), "subscription was not restored"

        bus.publish("drop.topic", {"after": "reconnect"})
        for _ in range(50):
            await asyncio.sleep(0.02)
            if received:
                break
        assert received, "no forward arrived after reconnecting"

        await bridge.close()
        run.cancel()


class TestMalformedInput:
    @pytest.mark.asyncio
    async def test_non_json_frame_is_ignored(self, server):
        bus, url = server
        received = []
        bridge = Bridge(url=url, on_message=lambda t, p: received.append(p))
        bridge._handle_message("not json at all")
        assert received == []

    @pytest.mark.asyncio
    async def test_frame_without_a_topic_is_ignored(self, server):
        bus, url = server
        received = []
        bridge = Bridge(url=url, on_message=lambda t, p: received.append(p))
        bridge._handle_message('{"status": "registered"}')
        assert received == []


class TestConnectedMeansSubscribed:
    """"connected" must fire only after the subscription replay.

    A client that reacts to "connected" by publishing a resync request would
    otherwise race forwarder registration on reconnect. The replay must be
    queued on the socket before the connected notification is delivered.
    """

    @pytest.mark.asyncio
    async def test_replay_is_sent_before_connected_is_reported(self, server):
        bus, url = server
        timeline = []
        bridge = Bridge(url=url, name="orb")
        bridge._subscriptions.add("resync.topic")

        real_send = bridge._send
        real_notify = bridge._notify_state

        async def recording_send(frame, require_connection=True):
            if frame.get("action") == "subscribe":
                timeline.append(("subscribe", frame["topic"]))
            return await real_send(frame, require_connection)

        bridge._send = recording_send
        bridge._notify_state = lambda state: timeline.append(("state", state)) or real_notify(state)

        await bridge.connect()

        states = [i for i, item in enumerate(timeline) if item[0] == "state" and item[1] == "connected"]
        replay = [i for i, item in enumerate(timeline) if item == ("subscribe", "resync.topic")]
        assert states, "connected was never reported"
        assert replay, "the subscription was not replayed"
        assert max(replay) < min(states), "connected fired before the replay was sent"
        await bridge.close()
