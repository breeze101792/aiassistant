from modules.eyes.vision_backends.base import VisionBackend


class StubVision(VisionBackend):
    """Returns placeholder — no camera available."""

    def capture(self, analyze: bool = False) -> dict:
        return {
            "description": "No camera available (stub backend)",
            "objects": [],
            "image_base64": None,
            "timestamp": _now_iso(),
        }

    def analyze(self, image_base64: str) -> dict:
        return {"description": "No vision model configured", "objects": [], "text_in_image": None}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
