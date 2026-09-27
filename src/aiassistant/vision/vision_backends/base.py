class VisionBackend:
    """Abstract interface for computer vision engines."""

    def capture(self, analyze: bool = False) -> dict:
        raise NotImplementedError

    def analyze(self, image_base64: str) -> dict:
        raise NotImplementedError
