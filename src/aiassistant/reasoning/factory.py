"""Provider factory.

Selects a model provider from config. An unknown provider is a hard error
naming the value, never a silent fallback to a default (REQ-BACKEND-002).
"""

import logging

from aiassistant.reasoning.base import LLMBackend

logger = logging.getLogger(__name__)

_OLLAMA_DEFAULT_URL = "http://127.0.0.1:11434"
_OPENAI_DEFAULT_URL = "https://api.openai.com/v1"


class ProviderError(ValueError):
    """Raised when the configured provider cannot be constructed."""


def create_provider(cfg: dict, *, role: str = "chat") -> LLMBackend:
    """Build a provider from an ``llm``-shaped config section.

    ``cfg`` keys: ``provider``, ``model``, ``url``, ``api_key``.
    ``role`` only appears in error messages ("chat" or "embeddings").
    """
    provider = (cfg.get("provider") or "").strip().lower()
    model = cfg.get("model") or ""

    if not provider:
        raise ProviderError(
            f"No {role} provider configured. Set agents.<id>.llm.provider "
            f"to 'ollama' or 'openai'."
        )
    if not model:
        raise ProviderError(
            f"No {role} model configured for provider {provider!r}. "
            f"Set agents.<id>.llm.model."
        )

    if provider == "ollama":
        from aiassistant.reasoning.ollama import OllamaBackend

        return OllamaBackend(
            model=model,
            url=cfg.get("url") or _OLLAMA_DEFAULT_URL,
            api_key=cfg.get("api_key", ""),
        )

    if provider in ("openai", "openai-compatible"):
        from aiassistant.reasoning.openai import OpenAIBackend

        return OpenAIBackend(
            model=model,
            url=cfg.get("url") or _OPENAI_DEFAULT_URL,
            api_key=cfg.get("api_key", ""),
        )

    raise ProviderError(
        f"Unknown {role} provider {provider!r}. "
        f"Supported: 'ollama', 'openai'."
    )


def resolve_embedding_provider(cfg: dict, chat_provider: LLMBackend) -> LLMBackend:
    """Resolve the embeddings provider.

    ``provider: same`` reuses the chat provider, which is the common local case
    and avoids configuring the same endpoint twice.
    """
    provider = (cfg.get("provider") or "same").strip().lower()
    if provider == "same":
        return chat_provider
    return create_provider(cfg, role="embeddings")
