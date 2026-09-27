class ChatBackend:
    """Abstract interface for messaging platform backends."""

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def send_message(self, text: str) -> None:
        raise NotImplementedError
