import json
import os
from datetime import datetime, timezone

from modules.canvas.backends.base import CanvasBackend


class FileCanvas(CanvasBackend):
    """Outputs canvas content to files — headless mode."""

    def __init__(self, output_dir: str = "./data/canvas_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._elements: dict[str, dict] = {}

    def show(self, content_type: str, data: str, title: str | None = None,
             width: int | None = None, height: int | None = None) -> None:
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        if content_type == "text":
            path = os.path.join(self.output_dir, f"text_{ts}.txt")
            with open(path, "w") as f:
                f.write(data)
            self._elements[path] = {"type": "text", "data": data}
        elif content_type == "html":
            path = os.path.join(self.output_dir, f"page_{ts}.html")
            with open(path, "w") as f:
                f.write(f"<html><head><title>{title or 'Canvas'}</title></head><body>{data}</body></html>")
            self._elements[path] = {"type": "html", "data": data}
        else:
            path = os.path.join(self.output_dir, f"output_{ts}.json")
            with open(path, "w") as f:
                json.dump({"type": content_type, "title": title, "data": str(data)}, f, indent=2)
            self._elements[path] = {"type": content_type, "data": str(data)}

    def clear(self) -> None:
        for path in list(self._elements.keys()):
            if os.path.exists(path):
                os.remove(path)
        self._elements.clear()

    def draw(self, elements: list[dict]) -> None:
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        path = os.path.join(self.output_dir, f"draw_{ts}.json")
        with open(path, "w") as f:
            json.dump(elements, f, indent=2)

    def update(self, element_id: str, content_type: str, data: str) -> None:
        if element_id in self._elements:
            self._elements[element_id] = {"type": content_type, "data": data}

    def screenshot(self) -> dict:
        return {
            "image_base64": None,
            "resolution": "N/A",
            "message": "File backend does not support screenshots",
        }
