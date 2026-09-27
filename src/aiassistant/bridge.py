"""WebSocket client for out-of-process consumers of the bus.

The orb uses this; so can any other out-of-process module. It implements the
client half of IF-0001: authenticate if required, register, subscribe, publish,
and reconnect.

No asyncio in the orb process: this client is the only piece that speaks to the
network, and the orb consumes its callbacks as Qt signals.
"""

import asyncio
import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

DEFAULT_URL = "ws://127.0.0.1:8765"
AUTH_TIMEOUT_S = 5.0
RECONNECT_BACKOFF_S = (1, 2, 5, 10, 30)


class BridgeError(RuntimeError):
    """A typed transport failure, so callers do not swallow silent stops."""


class Bridge:
    """A reconnecting client for the bus WebSocket."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        token: str = "",
        name: str = "orb",
        on_message: Callable[[str, dict], None] | None = None,
        on_state: Callable[[str], None] | None = None,
    ):
        self.url = url
        self.token = token
        self.name = name
        self.on_message = on_message
        self.on_state = on_state

        self._ws = None
        self._subscriptions: set[str] = set()
        self._task: asyncio.Task | None = None
        self._closed = False

    # ── Connection ───────────────────────────────────────────

    async def connect(self) -> None:
        """Connect, authenticate, and send the registration frame."""
        import websockets

        try:
            self._ws = await websockets.connect(self.url)
        except Exception as exc:
            raise BridgeError(f"cannot reach the assistant at {self.url}: {exc}") from exc

        if self.token:
            await self._ws.send(json.dumps({"token": self.token}))
        await self._ws.send(json.dumps({
            "action": "register",
            "module_name": self.name,
            "capabilities": {"type": "client"},
        }))
        # Consume the registration reply before the run loop starts, so it is
        # not mistaken for a topic forward and does not race the first message.
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=AUTH_TIMEOUT_S)
            if self.token:
                # With auth the first frame is the token result, then register.
                raw = await asyncio.wait_for(self._ws.recv(), timeout=AUTH_TIMEOUT_S)
            self._last_handshake = raw
        except asyncio.TimeoutError:
            logger.debug("no register reply within %.0fs; continuing", AUTH_TIMEOUT_S)

        self._notify_state("connected")
        logger.info("bridge connected to %s as %s", self.url, self.name)

    async def subscribe(self, topic: str) -> None:
        """Subscribe, remembering it so a reconnect can restore it."""
        self._subscriptions.add(topic)
        await self._send({"action": "subscribe", "topic": topic})

    async def unsubscribe(self, topic: str) -> None:
        self._subscriptions.discard(topic)
        await self._send({"action": "unsubscribe", "topic": topic})

    async def publish(self, topic: str, payload: dict | None = None) -> None:
        await self._send({"action": "publish", "topic": topic, "payload": payload or {}})

    async def close(self) -> None:
        self._closed = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("closing the bridge raised", exc_info=True)
            self._ws = None
        self._notify_state("closed")

    # ── Run loop ─────────────────────────────────────────────

    async def run(self) -> None:
        """Receive until closed, reconnecting on failure.

        A dropped connection is a typed state change, never a silent stop: the
        orb shows "reconnecting" and resubscribes when it returns.
        """
        attempt = 0
        while not self._closed:
            try:
                if self._ws is None:
                    await self.connect()
                    for topic in list(self._subscriptions):
                        await self._send({"action": "subscribe", "topic": topic},
                                         require_connection=False)
                    attempt = 0

                message = await self._ws.recv()
                self._handle_message(message)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._closed:
                    return
                self._notify_state(f"disconnected: {exc}")
                self._ws = None
                delay = RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)]
                attempt += 1
                logger.warning("bridge disconnected (%s); retrying in %ss", exc, delay)
                await asyncio.sleep(delay)

    def _handle_message(self, raw) -> None:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.debug("bridge received a non-JSON frame")
            return
        if not isinstance(data, dict):
            return
        if "topic" in data:
            if self.on_message:
                self.on_message(data["topic"], data.get("payload") or {})
            return
        if "error" in data:
            logger.warning("bridge reported an error: %s", data["error"])

    # ── Internals ────────────────────────────────────────────

    async def _send(self, frame: dict, require_connection: bool = True) -> None:
        if self._ws is None:
            if require_connection:
                raise BridgeError("bridge is not connected")
            return
        try:
            await self._ws.send(json.dumps(frame))
        except Exception as exc:
            raise BridgeError(f"send failed: {exc}") from exc

    def _notify_state(self, state: str) -> None:
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                logger.debug("bridge state handler raised", exc_info=True)

    @property
    def connected(self) -> bool:
        return self._ws is not None and getattr(self._ws, "state", None) is not None

    @property
    def subscriptions(self) -> set[str]:
        return set(self._subscriptions)
