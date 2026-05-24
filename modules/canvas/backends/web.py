from modules.canvas.backends.base import CanvasBackend


class WebCanvas(CanvasBackend):
    """Web-based canvas — serves a page, user opens in browser."""

    def __init__(self, port: int = 8081):
        self.port = port
        self._server = None

    def start(self) -> None:
        pass  # Web server started in main process

    def stop(self) -> None:
        pass

    def show(self, content_type: str, data: str, title: str | None = None,
             width: int | None = None, height: int | None = None) -> None:
        pass  # Deferred — requires aiohttp web server

    def clear(self) -> None:
        pass

    def draw(self, elements: list[dict]) -> None:
        pass

    def update(self, element_id: str, content_type: str, data: str) -> None:
        pass

    def screenshot(self) -> dict:
        return {"image_base64": None, "resolution": "N/A"}
