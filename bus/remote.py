import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class RemoteBus:
    """WebSocket server for remote module connections.

    Remote modules connect via WebSocket and bridge their local bus
    messages to the central bus. Authentication via shared token.
    """

    def __init__(self, bus, port: int = 8765, auth_token: str = ""):
        self.bus = bus
        self.port = port
        self.auth_token = auth_token
        self._server = None
        self._clients: dict[str, any] = {}
        self._client_subscriptions: dict[str, list[str]] = {}

    async def start(self) -> None:
        try:
            import websockets
            self._server = await websockets.serve(
                self._handle_connection, "0.0.0.0", self.port
            )
            logger.info(f"Remote bus listening on ws://0.0.0.0:{self.port}")
        except ImportError:
            logger.warning("websockets package not installed — remote connections disabled")
        except Exception as e:
            logger.error(f"Failed to start remote bus: {e}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(self, websocket, path):
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"Remote connection from {client_id}")

        # Auth
        if self.auth_token:
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(msg)
                if data.get("token") != self.auth_token:
                    await websocket.send(json.dumps({"error": "auth failed"}))
                    await websocket.close()
                    return
            except asyncio.TimeoutError:
                await websocket.close()
                return

        module_name = "unknown"
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    action = data.get("action", "publish")
                    topic = data.get("topic", "")
                    payload = data.get("payload", {})

                    if action == "register":
                        module_name = data.get("module_name", "unknown")
                        self.bus.registry.add(module_name, remote=True)
                        self.bus.publish("bus.module.connected", {
                            "module_name": module_name,
                            "remote": True,
                            "capabilities": data.get("capabilities", {}),
                        })
                        await websocket.send(json.dumps({"status": "registered"}))

                    elif action == "publish":
                        self.bus.publish(topic, payload)

                    elif action == "subscribe":
                        def make_callback(cid, ws):
                            def callback(t, p):
                                asyncio.ensure_future(self._forward(ws, t, p))
                            return callback
                        sub_id = self.bus.subscribe(topic, make_callback(client_id, websocket))
                        self._client_subscriptions.setdefault(client_id, []).append(sub_id)

                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"Remote client disconnected: {client_id} — {e}")
        finally:
            for sub_id in self._client_subscriptions.pop(client_id, []):
                self.bus.unsubscribe(sub_id)
            if module_name != "unknown":
                self.bus.registry.remove(module_name)
                self.bus.publish("bus.module.disconnected", {
                    "module_name": module_name,
                    "reason": "connection closed",
                })

    async def _forward(self, websocket, topic: str, payload: dict) -> None:
        try:
            await websocket.send(json.dumps({"topic": topic, "payload": payload}))
        except Exception:
            pass
