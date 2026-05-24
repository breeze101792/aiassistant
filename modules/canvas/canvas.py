import logging
import os

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class CanvasModule(BaseModule):
    """Visual display — show content, generate images, accept interaction."""

    module_name = "canvas"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        canvas_cfg = config.get("canvas", {})
        self.backend_name = canvas_cfg.get("backend", "file")
        self.image_model = canvas_cfg.get("image_model")
        self.default_size = canvas_cfg.get("default_size", "1024x1024")
        self._backend = None

    async def setup(self) -> bool:
        if self.backend_name == "file":
            from modules.canvas.backends.file import FileCanvas
            output_dir = os.path.join("data", "canvas_output")
            self._backend = FileCanvas(output_dir=output_dir)
        elif self.backend_name == "web":
            from modules.canvas.backends.web import WebCanvas
            web_port = self.config.get("canvas", {}).get("web_port", 8081)
            self._backend = WebCanvas(port=web_port)
        else:
            logger.warning(f"Unknown canvas backend: {self.backend_name}, using file")
            from modules.canvas.backends.file import FileCanvas
            self._backend = FileCanvas(output_dir=os.path.join("data", "canvas_output"))

        logger.info(f"Canvas setup — backend={self.backend_name}")
        return True

    async def start(self) -> None:
        self.bus.subscribe("action.canvas.show", self._handle_show)
        self.bus.subscribe("action.canvas.generate", self._handle_generate)
        self.bus.subscribe("action.canvas.clear", self._handle_clear)
        self.bus.subscribe("action.canvas.draw", self._handle_draw)
        self.bus.subscribe("action.canvas.update", self._handle_update)
        self.bus.subscribe("canvas.screenshot", self._handle_screenshot_rpc)

        self._backend.start()
        self.bus.publish("status.canvas.ready", {
            "backend": self.backend_name,
            "resolution": self.default_size,
        })
        logger.info("Canvas started")

    async def stop(self) -> None:
        self._backend.stop()
        logger.info("Canvas stopped")

    async def health(self) -> dict:
        return {"status": "ok", "details": {"backend": self.backend_name}}

    async def _handle_show(self, topic: str, payload: dict) -> None:
        try:
            self._backend.show(
                content_type=payload.get("content_type", "text"),
                data=payload.get("data", ""),
                title=payload.get("title"),
                width=payload.get("width"),
                height=payload.get("height"),
            )
        except Exception as e:
            logger.error(f"Canvas show error: {e}")
            self.bus.publish("status.canvas.error", {"error": str(e)})

    async def _handle_generate(self, topic: str, payload: dict) -> None:
        prompt = payload.get("prompt", "")
        if not self.image_model:
            self.bus.publish("status.canvas.error", {"error": "No image model configured"})
            return
        import time
        start = time.monotonic()
        try:
            from modules.canvas.renderer import ImageRenderer
            renderer = ImageRenderer(model=self.image_model)
            image_path = renderer.generate(prompt=prompt, style=payload.get("style"),
                                           size=payload.get("size", self.default_size))
            duration_ms = (time.monotonic() - start) * 1000
            self.bus.publish("status.canvas.generated", {
                "prompt": prompt,
                "image_path": image_path,
                "duration_ms": round(duration_ms, 1),
            })
            self._backend.show(content_type="image", data=image_path, title=prompt[:50])
        except Exception as e:
            logger.error(f"Canvas generate error: {e}")
            self.bus.publish("status.canvas.error", {"error": str(e)})

    async def _handle_clear(self, topic: str, payload: dict) -> None:
        self._backend.clear()

    async def _handle_draw(self, topic: str, payload: dict) -> None:
        self._backend.draw(payload.get("elements", []))

    async def _handle_update(self, topic: str, payload: dict) -> None:
        self._backend.update(
            element_id=payload.get("id", ""),
            content_type=payload.get("content_type", "text"),
            data=payload.get("data", ""),
        )

    async def _handle_screenshot_rpc(self, topic: str, payload: dict) -> None:
        request_id = payload.get("_request_id")
        if request_id:
            result = self._backend.screenshot()
            self.bus.respond_rpc(request_id, result)
