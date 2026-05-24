from modules.eyes.vision_backends.base import VisionBackend


class OpenCVBackend(VisionBackend):
    """Real camera capture using OpenCV."""

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._cap = None

    def capture(self, analyze: bool = False) -> dict:
        import base64
        import cv2
        import numpy as np

        if self._cap is None:
            self._cap = cv2.VideoCapture(self.camera_index)

        ret, frame = self._cap.read()
        if not ret:
            return {"description": "Camera read failed", "objects": [], "image_base64": None}

        _, buffer = cv2.imencode(".jpg", frame)
        img_b64 = base64.b64encode(buffer).decode("utf-8")

        result = {
            "image_base64": img_b64,
            "description": "Image captured",
            "objects": [],
        }
        return result

    def analyze(self, image_base64: str) -> dict:
        return {"description": "No vision model configured", "objects": [], "text_in_image": None}
