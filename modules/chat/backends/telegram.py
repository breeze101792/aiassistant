import logging

from modules.chat.backends.base import ChatBackend

logger = logging.getLogger(__name__)


class TelegramBackend(ChatBackend):
    """Telegram Bot API backend."""

    def __init__(self, token: str, allowed_users: list[str] | None = None,
                 on_message: callable = None):
        self.token = token
        self.allowed_users = allowed_users or []
        self.on_message = on_message
        self._running = False

    def start(self) -> None:
        self._running = True
        logger.info(f"Telegram backend started (token configured: {bool(self.token)})")

    def stop(self) -> None:
        self._running = False

    def send_message(self, text: str) -> None:
        """Stub — full Telegram Bot API integration deferred."""
        pass
