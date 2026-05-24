import logging

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class MouthModule(BaseModule):
    """Converts text to speech and plays through speakers. Always loaded."""

    module_name = "mouth"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        mouth_cfg = config.get("mouth", {})
        self.backend_name = mouth_cfg.get("backend", "text")
        self.voice = mouth_cfg.get("voice", "default")
        self.speed = mouth_cfg.get("speed", 1.0)
        self._backend = None
        self._queue: list[dict] = []
        self._processing = False

    async def setup(self) -> bool:
        if self.backend_name == "text":
            from modules.mouth.tts_backends.text import TextTTS
            self._backend = TextTTS()
        elif self.backend_name == "edge_tts":
            from modules.mouth.tts_backends.edge_tts import EdgeTTSBackend
            self._backend = EdgeTTSBackend(voice=self.voice, speed=self.speed)
        else:
            logger.warning(f"Unknown mouth backend: {self.backend_name}, using text")
            from modules.mouth.tts_backends.text import TextTTS
            self._backend = TextTTS()

        logger.info(f"Mouth setup — backend={self.backend_name}")
        return True

    async def start(self) -> None:
        self.bus.subscribe("action.speak", self._handle_speak)
        self.bus.publish("status.mouth.ready", {"engines": [self.backend_name]})
        logger.info("Mouth started")

    async def stop(self) -> None:
        self._queue.clear()
        if self._backend:
            self._backend.stop()
        logger.info("Mouth stopped")

    async def health(self) -> dict:
        return {"status": "ok", "details": {"backend": self.backend_name, "queue_size": len(self._queue)}}

    async def _handle_speak(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        interrupt = payload.get("interrupt", False)
        voice = payload.get("voice") or self.voice
        speed = payload.get("speed", self.speed)

        if interrupt:
            self._queue.clear()
            if self._backend:
                self._backend.stop()

        self._queue.append({"text": text, "voice": voice, "speed": speed})
        if not self._processing:
            await self._process_queue()

    async def _process_queue(self):
        import asyncio
        self._processing = True
        try:
            while self._queue:
                item = self._queue[0]
                self.bus.publish("status.mouth.started", {"text": item["text"], "timestamp": _now_iso()})
                try:
                    result = self._backend.speak(item["text"], voice=item["voice"], speed=item["speed"])
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Mouth speak error: {e}")
                    self.bus.publish("status.mouth.error", {"error": str(e)})
                self.bus.publish("status.mouth.done", {"text": item["text"], "timestamp": _now_iso(), "interrupted": False})
                # Only pop if this item is still at the front (not replaced by interrupt)
                if self._queue and self._queue[0] is item:
                    self._queue.pop(0)
        finally:
            self._processing = False


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
