"""Model provider interface.

Two call styles, both required:

* ``chat`` — one blocking call, returns the whole reply. Used for short,
  non-interactive subtasks (context compression, memory priming).
* ``chat_stream`` — yields deltas as they arrive. This is the path the agent
  uses for a turn, because it is what lets the transcript appear incrementally
  and TTS start speaking before the model has finished.

Both are synchronous by contract: providers are blocking SDKs. Callers run them
off the event loop (see ``agent.module._run_blocking`` and
``reasoning._stream.iter_blocking``).
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamChunk:
    """One step of a streamed completion.

    A stream is a sequence of chunks with ``delta`` / ``thinking`` set, followed
    by exactly one terminal chunk with ``done=True`` carrying the assembled
    ``content``, any ``tool_calls``, and ``usage``.
    """

    delta: str = ""
    thinking: str = ""
    done: bool = False
    content: str | None = None
    tool_calls: list[dict] | None = None
    usage: dict = field(default_factory=dict)


class LLMBackend(ABC):
    """Abstract interface for model providers.

    Every backend supports streaming chat, blocking chat, and embeddings.
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
        """Send a chat request and return the whole reply.

        Returns:
            {
                "content": str | None,   # None when the reply is only tool calls
                "tool_calls": [
                    {"id": str | None, "name": str, "arguments": dict}
                ] | None,
                "usage": {"prompt_tokens": int, "completion_tokens": int},
            }
        """
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Iterator[StreamChunk]:
        """Stream a chat request, yielding :class:`StreamChunk` objects.

        The final chunk has ``done=True`` and carries the authoritative
        ``content``, ``tool_calls``, and ``usage``. Deltas before it are
        incremental: concatenating them must reproduce ``content`` (except for
        provider whitespace normalization, on which the terminal chunk wins).
        """
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert a single text to an embedding vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Convert multiple texts. Backends with a batch endpoint override this."""
        return [self.embed(t) for t in texts]

    def token_count(self, messages: list[dict]) -> int:
        """Estimate the token count of a message list, using tiktoken when available."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            total = 0
            for msg in messages:
                content = msg.get("content") or ""
                total += len(enc.encode(content))
                total += 4  # role and formatting overhead per message
            return total + 2  # priming tokens
        except ImportError:
            return sum(len((m.get("content") or "").split()) * 2 for m in messages)

    async def achat(self, messages: list[dict], **kwargs: Any) -> dict:
        """Await a blocking ``chat`` call off the event loop."""
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.chat(messages, **kwargs))

    async def achat_stream(
        self,
        messages: list[dict],
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Await a streaming ``chat_stream`` call, off the event loop."""
        from aiassistant.reasoning._stream import iter_blocking

        async for chunk in iter_blocking(lambda: self.chat_stream(messages, **kwargs)):
            yield chunk

    def format_tool_arguments(self, arguments: dict) -> Any:
        """How tool-call arguments must be represented in conversation history.

        Providers disagree, and getting this wrong is a request-time validation
        error, not a visible failure: Ollama requires a dict, while OpenAI
        requires a JSON string. The provider owns the answer rather than the
        caller guessing.
        """
        return arguments
