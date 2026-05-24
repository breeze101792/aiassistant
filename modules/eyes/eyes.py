import logging

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class EyesModule(BaseModule):
    """Captures images from camera, optionally runs vision model."""

    module_name = "eyes"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        eyes_cfg = config.get("eyes", {})
        self.backend_name = eyes_cfg.get("backend", "stub")
        self.vision_model = eyes_cfg.get("vision_model")
        self.camera_index = eyes_cfg.get("camera_index", 0)
        self._backend = None
        self._streaming = False

    async def setup(self) -> bool:
        if self.backend_name == "stub":
            from modules.eyes.vision_backends.stub import StubVision
            self._backend = StubVision()
        elif self.backend_name == "opencv":
            from modules.eyes.vision_backends.opencv import OpenCVBackend
            self._backend = OpenCVBackend(camera_index=self.camera_index)
        else:
            logger.warning(f"Unknown eyes backend: {self.backend_name}, using stub")
            from modules.eyes.vision_backends.stub import StubVision
            self._backend = StubVision()

        logger.info(f"Eyes setup — backend={self.backend_name}")
        return True

    async def start(self) -> None:
        self.bus.subscribe("command.eyes.capture", self._handle_capture)
        self.bus.subscribe("command.eyes.stream.start", self._handle_stream_start)
        self.bus.subscribe("command.eyes.stream.stop", self._handle_stream_stop)
        self.bus.subscribe("eyes.analyze", self._handle_rpc_analyze)
        self.bus.publish("status.eyes.ready", {
            "camera": self.backend_name,
            "resolution": "unknown",
            "vision_model": self.vision_model,
        })
        logger.info("Eyes started")

    async def stop(self) -> None:
        self._streaming = False
        logger.info("Eyes stopped")

    async def health(self) -> dict:
        return {"status": "ok", "details": {"backend": self.backend_name, "streaming": self._streaming}}

    async def _handle_capture(self, topic: str, payload: dict) -> None:
        analysis = payload.get("analysis", False)
        try:
            result = self._backend.capture(analyze=analysis)
            self.bus.publish("sensory.vision.frame", result)
        except Exception as e:
            logger.error(f"Eyes capture error: {e}")
            self.bus.publish("status.eyes.error", {"error": str(e)})

    async def _handle_stream_start(self, topic: str, payload: dict) -> None:
        self._streaming = True
        logger.debug("Eyes: stream started")

    async def _handle_stream_stop(self, topic: str, payload: dict) -> None:
        self._streaming = False
        logger.debug("Eyes: stream stopped")

    async def _handle_rpc_analyze(self, topic: str, payload: dict) -> None:
        request_id = payload.get("_request_id")
        if request_id and self._backend:
            result = self._backend.analyze(payload.get("image_base64", ""))
            self.bus.respond_rpc(request_id, result)
