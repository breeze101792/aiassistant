"""WebSocket server that bridges out-of-process clients onto the bus.

Clients (the orb, and any future remote module) speak a small JSON envelope
protocol: ``register``, ``subscribe``, ``unsubscribe``, ``publish``. Inbound
forwards are ``{"topic": ..., "payload": ...}``.

Security defaults: bind loopback and require a token for any wider bind.
See docs/security/threat-model.md RISK-0001.
"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"

AUTH_TIMEOUT_S = 5.0


class RemoteBus:
    """WebSocket server for remote clients.

    A client may subscribe without registering (the orb does). Registration is
    optional and only records the client in the module registry.
    """

    def __init__(
        self,
        bus,
        port: int = DEFAULT_PORT,
        auth_token: str = "",
        host: str = DEFAULT_HOST,
    ):
        self.bus = bus
        self.port = port
        self.host = host
        self.auth_token = auth_token
        self._server = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client_subscriptions: dict[str, list[str]] = {}

    @property
    def requires_token(self) -> bool:
        """A token is mandatory whenever the bind is not loopback-only."""
        return self.host not in LOOPBACK_HOSTS

    def _validate(self) -> bool:
        if self.requires_token and not self.auth_token:
            logger.error(
                "Refusing to start: bind address %s is not loopback and "
                "remote_auth_token is empty. Set bus.remote_auth_token, or "
                "bind bus.bind to 127.0.0.1.",
                self.host,
            )
            return False
        return True

    async def start(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.warning("websockets not installed — remote connections disabled")
            return

        if not self._validate():
            return

        self._loop = asyncio.get_running_loop()
        try:
            self._server = await websockets.serve(
                self._handle_connection, self.host, self.port,
            )
            logger.info(
                "Remote bus listening on ws://%s:%s%s",
                self.host,
                self.port,
                " (auth required)" if self.auth_token else "",
            )
        except OSError:
            logger.warning("Port %s in use — remote connections disabled", self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_connection(self, websocket) -> None:
        # websockets >= 14 passes a single connection argument.
        client_id = _peer_id(websocket)
        logger.info("Remote connection from %s", client_id)

        if self.auth_token and not await self._authenticate(websocket):
            return

        module_name = "unknown"
        try:
            async for message in websocket:
                await self._dispatch(websocket, client_id, message, module_name)
                data = _try_json(message)
                if data and data.get("action") == "register":
                    module_name = data.get("module_name", "unknown")
        except Exception as e:
            logger.debug("Remote client disconnected: %s — %s", client_id, e)
        finally:
            self._cleanup(client_id, module_name)

    async def _authenticate(self, websocket) -> bool:
        """The token must arrive as the client's first frame."""
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=AUTH_TIMEOUT_S)
        except asyncio.TimeoutError:
            await websocket.close()
            return False

        data = _try_json(msg)
        if not data or data.get("token") != self.auth_token:
            await websocket.send(json.dumps({"error": "auth failed"}))
            await websocket.close()
            return False
        return True

    async def _dispatch(self, websocket, client_id: str, message, module_name: str) -> None:
        data = _try_json(message)
        if data is None:
            logger.debug("Ignoring malformed frame from %s", client_id)
            return

        action = data.get("action", "publish")
        topic = data.get("topic", "")
        payload = data.get("payload", {})

        if action == "register":
            name = data.get("module_name", "unknown")
            self.bus.registry.add(name, remote=True)
            self.bus.publish("bus.module.connected", {
                "module_name": name,
                "remote": True,
                "capabilities": data.get("capabilities", {}),
            })
            await websocket.send(json.dumps({"status": "registered"}))

        elif action == "publish":
            self.bus.publish(topic, payload)

        elif action == "subscribe":
            callback = self._make_forwarder(websocket)
            sub_id = self.bus.subscribe(topic, callback)
            self._client_subscriptions.setdefault(client_id, []).append(sub_id)

        elif action == "unsubscribe":
            self._unsubscribe_all(client_id)

    def _make_forwarder(self, websocket):
        """Forward a bus topic to one client, from whatever thread publishes it.

        ``publish`` is thread-safe and may be called from the audio threads, so
        the send must be scheduled onto the server loop explicitly rather than
        relying on a loop being present in the calling thread.
        """
        def callback(topic: str, payload: dict) -> None:
            coro = self._forward(websocket, topic, payload)
            loop = self._loop
            if loop is None or not loop.is_running():
                coro.close()
                return
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                asyncio.ensure_future(coro)
            else:
                asyncio.run_coroutine_threadsafe(coro, loop)
        return callback

    async def _forward(self, websocket, topic: str, payload: dict) -> None:
        try:
            await websocket.send(json.dumps({"topic": topic, "payload": payload}))
        except Exception:
            # The client is gone; its subscriptions are reclaimed on disconnect.
            pass

    def _unsubscribe_all(self, client_id: str) -> None:
        for sub_id in self._client_subscriptions.pop(client_id, []):
            self.bus.unsubscribe(sub_id)

    def _cleanup(self, client_id: str, module_name: str) -> None:
        self._unsubscribe_all(client_id)
        if module_name != "unknown":
            self.bus.registry.remove(module_name)
            self.bus.publish("bus.module.disconnected", {
                "module_name": module_name,
                "reason": "connection closed",
            })


def _try_json(message) -> dict | None:
    try:
        data = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _peer_id(websocket) -> str:
    try:
        address = websocket.remote_address
    except AttributeError:
        return "unknown"
    if not address:
        return "unknown"
    return f"{address[0]}:{address[1]}"
