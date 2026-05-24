class CanvasBackend:
    """Abstract interface for canvas display backends."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def show(self, content_type: str, data: str, title: str | None = None,
             width: int | None = None, height: int | None = None) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def draw(self, elements: list[dict]) -> None:
        raise NotImplementedError

    def update(self, element_id: str, content_type: str, data: str) -> None:
        raise NotImplementedError

    def screenshot(self) -> dict:
        raise NotImplementedError
