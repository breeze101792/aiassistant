from abc import ABC, abstractmethod
from typing import Any


class LLMBackend(ABC):
    """Abstract interface for LLM providers.

    Every backend supports chat (with function-calling tools)
    and embeddings (text -> vector).
    """

    def __init__(self, model: str, url: str = "", api_key: str = ""):
        self.model = model
        self.url = url
        self.api_key = api_key

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a chat request. Returns OpenAI-compatible response dict.

        Returns:
            {
                "content": str | None,          # text response (None if tool call)
                "tool_calls": [                 # present if LLM wants to call tools
                    {"name": "web_search", "arguments": {"query": "..."}}
                ] | None,
                "usage": {"prompt_tokens": int, "completion_tokens": int},
            }
        """
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert a single text to an embedding vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Convert multiple texts to embedding vectors.

        Default implementation loops over embed(). Backends with batch
        endpoints should override for efficiency.
        """
        return [self.embed(t) for t in texts]

    def token_count(self, messages: list[dict]) -> int:
        """Estimate token count for a list of messages using tiktoken."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            total = 0
            for msg in messages:
                total += len(enc.encode(msg.get("content", "")))
                total += 4  # role + formatting overhead per message
            return total + 2  # priming tokens
        except ImportError:
            return sum(len(m.get("content", "").split()) * 2 for m in messages)
