import logging

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class ChatModule(BaseModule):
    """Messaging platform interface — bridges external chats to the bus."""

    module_name = "chat"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        chat_cfg = config.get("chat", {})
        self.backend_names = chat_cfg.get("backends", [])
        self.telegram_token = chat_cfg.get("telegram_token", "")
        self.telegram_allowed = chat_cfg.get("telegram_allowed_users", [])
        self._backends: list = []

    async def setup(self) -> bool:
        for name in self.backend_names:
            if name == "telegram" and self.telegram_token:
                from modules.chat.backends.telegram import TelegramBackend
                backend = TelegramBackend(
                    token=self.telegram_token,
                    allowed_users=self.telegram_allowed,
                    on_message=self._on_chat_message,
                )
                self._backends.append(backend)

        logger.info(f"Chat setup — {len(self._backends)} backends loaded")
        return True

    async def start(self) -> None:
        self.bus.subscribe("response.text", self._handle_response)
        for backend in self._backends:
            backend.start()
        logger.info(f"Chat started — backends: {self.backend_names}")

    async def stop(self) -> None:
        for backend in self._backends:
            backend.stop()
        logger.info("Chat stopped")

    async def health(self) -> dict:
        return {"status": "ok", "details": {"active_backends": self.backend_names}}

    async def _on_chat_message(self, text: str, channel: str, sender: str) -> None:
        self.bus.user_input(text, channel=channel, sender=sender)

    async def _handle_response(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        for backend in self._backends:
            try:
                backend.send_message(text)
            except Exception as e:
                logger.error(f"Chat backend send error: {e}")
