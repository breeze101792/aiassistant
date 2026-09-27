"""RemoteBus integration tests.

There was no test here, which is exactly why the server shipped broken: its
handler signature did not match the installed ``websockets`` version, so every
connection died immediately and nothing noticed.
"""

import asyncio
import json

import pytest
import pytest_asyncio

from aiassistant.bus.bus import MessageBus
from aiassistant.bus.remote import RemoteBus

websockets = pytest.importorskip("websockets")


def _free_port() -> int:
    """A port the OS says is free, to avoid collisions between test runs."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture
async def bus():
    b = MessageBus()
    b._loop = asyncio.get_running_loop()
    return b


@pytest_asyncio.fixture
async def remote(bus):
    port = _free_port()
    server = RemoteBus(bus, port=port)
    await server.start()
    yield server, port
    await server.stop()


async def _connect(port, token: str = ""):
    ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    if token:
        await ws.send(json.dumps({"token": token}))
    return ws


class TestConnection:
    @pytest.mark.asyncio
    async def test_connect_and_register(self, remote):
        server, port = remote
        async with await _connect(port) as ws:
            await ws.send(json.dumps({"action": "register", "module_name": "t"}))
            reply = json.loads(await ws.recv())
            assert reply == {"status": "registered"}

    @pytest.mark.asyncio
    async def test_subscribe_then_receive_forward(self, remote, bus):
        server, port = remote
        async with await _connect(port) as ws:
            await ws.send(json.dumps({"action": "subscribe", "topic": "test.topic"}))
            await asyncio.sleep(0.1)
            assert bus.has_subscriber("test.topic")

            bus.publish("test.topic", {"n": 1})
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            assert msg == {"topic": "test.topic", "payload": {"n": 1}}

    @pytest.mark.asyncio
    async def test_subscribe_without_register(self, remote, bus):
        """The orb subscribes and never registers; that must be supported."""
        server, port = remote
        async with await _connect(port) as ws:
            await ws.send(json.dumps({"action": "subscribe", "topic": "orb.topic"}))
            await asyncio.sleep(0.1)
            assert bus.has_subscriber("orb.topic")

    @pytest.mark.asyncio
    async def test_publish_reaches_local_subscribers(self, remote, bus):
        server, port = remote
        seen = []
        bus.subscribe("from.remote", lambda t, p: seen.append(p))
        async with await _connect(port) as ws:
            await ws.send(json.dumps({
                "action": "publish", "topic": "from.remote", "payload": {"x": 9},
            }))
            for _ in range(50):
                await asyncio.sleep(0.02)
                if seen:
                    break
        assert seen == [{"x": 9}]

    @pytest.mark.asyncio
    async def test_unsubscribe_action_drops_subscription(self, remote, bus):
        server, port = remote
        async with await _connect(port) as ws:
            await ws.send(json.dumps({"action": "subscribe", "topic": "u.topic"}))
            await asyncio.sleep(0.1)
            assert bus.has_subscriber("u.topic")

            await ws.send(json.dumps({"action": "unsubscribe", "topic": "u.topic"}))
            for _ in range(50):
                await asyncio.sleep(0.02)
                if not bus.has_subscriber("u.topic"):
                    break
            assert not bus.has_subscriber("u.topic")

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_subscriptions(self, remote, bus):
        server, port = remote
        baseline = len(bus._subscribers)
        async with await _connect(port) as ws:
            await ws.send(json.dumps({"action": "subscribe", "topic": "gone.topic"}))
            await asyncio.sleep(0.1)
            assert len(bus._subscribers) > baseline

        for _ in range(100):
            await asyncio.sleep(0.02)
            if len(bus._subscribers) == baseline:
                break
        assert len(bus._subscribers) == baseline

    @pytest.mark.asyncio
    async def test_malformed_frame_does_not_kill_the_server(self, remote, bus):
        server, port = remote
        async with await _connect(port) as ws:
            await ws.send("this is not json")
            await ws.send(json.dumps({"action": "subscribe", "topic": "still.alive"}))
            for _ in range(50):
                await asyncio.sleep(0.02)
                if bus.has_subscriber("still.alive"):
                    break
            assert bus.has_subscriber("still.alive")


class TestSecurity:
    @pytest.mark.asyncio
    async def test_auth_rejects_wrong_token(self, bus):
        port = _free_port()
        server = RemoteBus(bus, port=port, auth_token="right")
        await server.start()
        try:
            import websockets
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"token": "wrong"}))
                reply = json.loads(await ws.recv())
                assert reply.get("error") == "auth failed"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_auth_accepts_correct_token(self, bus):
        port = _free_port()
        server = RemoteBus(bus, port=port, auth_token="right")
        await server.start()
        try:
            async with await _connect(port, token="right") as ws:
                await ws.send(json.dumps({"action": "register", "module_name": "t"}))
                assert json.loads(await ws.recv()) == {"status": "registered"}
        finally:
            await server.stop()

    def test_non_loopback_bind_requires_a_token(self, bus):
        """An unauthenticated LAN-reachable bus plus a pi harness is a remote
        shell (RISK-0001). The server must refuse to start."""
        server = RemoteBus(bus, host="0.0.0.0", auth_token="")
        assert server.requires_token is True
        assert server._validate() is False

    def test_loopback_bind_does_not_require_a_token(self, bus):
        server = RemoteBus(bus, host="127.0.0.1", auth_token="")
        assert server.requires_token is False
        assert server._validate() is True

    @pytest.mark.asyncio
    async def test_non_loopback_without_token_does_not_serve(self, bus):
        port = _free_port()
        server = RemoteBus(bus, host="0.0.0.0", port=port, auth_token="")
        await server.start()  # must no-op, not raise
        assert server._server is None
        await server.stop()
