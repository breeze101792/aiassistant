import asyncio
import logging
import uuid
from collections import defaultdict
from typing import Any, Callable

from bus.errors import NoSubscriberError, TimeoutError, ModuleNotFoundError
from bus.registry import ModuleRegistry

logger = logging.getLogger(__name__)


class MessageBus:
    """Central nervous system. All module communication goes through this.

    Pub/Sub for fire-and-forget messages.
    RPC for request-response with timeout.
    """

    def __init__(self):
        self._subscribers: dict[str, dict[str, Callable]] = defaultdict(dict)
        self._pending_rpc: dict[str, asyncio.Future] = {}
        self.registry = ModuleRegistry()
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        return self._loop

    # ── Pub/Sub ─────────────────────────────────────────────

    def publish(self, topic: str, payload: dict | None = None) -> None:
        """Fire and forget. Deliver to every callback subscribed to this topic.

        Thread-safe: can be called from any thread. Async callbacks are scheduled
        on the main event loop via run_coroutine_threadsafe when called from
        a non-asyncio thread (e.g. HalASR daemon thread).
        """
        payload = payload or {}
        for sub_id, callback in list(self._subscribers.get(topic, {}).items()):
            try:
                result = callback(topic, payload)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.ensure_future(result)
                    except RuntimeError:
                        # Not in an asyncio thread — schedule on main loop
                        asyncio.run_coroutine_threadsafe(result, self._get_loop())
            except Exception:
                # One misbehaving subscriber must not affect others
                logger.debug("Subscriber error on topic %s", topic, exc_info=True)

    def subscribe(self, topic: str, callback: Callable[[str, dict], None]) -> str:
        """Register a callback for a topic. Returns a subscription ID for unsubscribe."""
        sub_id = str(uuid.uuid4())[:8]
        self._subscribers[topic][sub_id] = callback
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription by ID."""
        for topic, subs in list(self._subscribers.items()):
            if subscription_id in subs:
                del subs[subscription_id]
                if not subs:
                    del self._subscribers[topic]
                return

    # ── RPC ──────────────────────────────────────────────────

    async def request(self, topic: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
        """Publish a request and wait for a single response.

        The responding module must call `respond_rpc(request_id, response_payload)`.
        Raises NoSubscriberError if nothing is listening.
        Raises TimeoutError if no response within `timeout` seconds.
        """
        if topic not in self._subscribers or not self._subscribers[topic]:
            raise NoSubscriberError(topic)

        request_id = str(uuid.uuid4())
        payload = payload or {}
        payload["_request_id"] = request_id

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_rpc[request_id] = future

        try:
            self.publish(topic, payload)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_rpc.pop(request_id, None)
            raise TimeoutError(topic, timeout)

    def respond_rpc(self, request_id: str, response: dict) -> None:
        """Called by a module to fulfill an RPC request."""
        future = self._pending_rpc.pop(request_id, None)
        if future and not future.done():
            future.set_result(response)

    # ── Module Lifecycle ─────────────────────────────────────

    def register(self, module) -> None:
        """Register a module with the bus. Module must have a module_name attribute."""
        name = module.module_name
        self.registry.add(name)
        self.registry.update_status(name, "ready")

    def unregister(self, module_name: str) -> None:
        """Remove a module from the registry."""
        self.registry.remove(module_name)

    def list_modules(self) -> dict[str, dict]:
        """Return all registered modules and their status."""
        return self.registry.list_all()

    def has_subscriber(self, topic: str) -> bool:
        """Check if any module is listening on a topic."""
        return topic in self._subscribers and bool(self._subscribers[topic])

    # ── User Input Shortcut ──────────────────────────────────

    def user_input(self, text: str, channel: str = "cli", sender: str = "user") -> None:
        """Shortcut for publishing user input. Used by CLI, Chat, etc."""
        self.publish("user.input.text", {
            "text": text,
            "timestamp": _now_iso(),
            "channel": channel,
            "sender": sender,
        })


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
