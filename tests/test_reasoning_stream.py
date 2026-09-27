"""Streaming provider tests.

The streaming path is what makes a live transcript and early TTS possible, so
the shape of the stream — ordered deltas, then exactly one terminal chunk with
the authoritative content — is a contract, not an implementation detail.
"""

import asyncio
from collections.abc import Iterator

import pytest

from aiassistant.reasoning.base import LLMBackend, StreamChunk
from aiassistant.reasoning.factory import (
    ProviderError,
    create_provider,
    resolve_embedding_provider,
)


class ScriptedProvider(LLMBackend):
    """A provider whose stream is a fixed script, including a think block."""

    def __init__(self, chunks: list[StreamChunk]):
        super().__init__(model="scripted")
        self._chunks = chunks
        self.blocked = False

    def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096) -> dict:
        return {"content": "whole", "tool_calls": None, "usage": {}}

    def chat_stream(
        self, messages, tools=None, temperature=0.7, max_tokens=4096,
    ) -> Iterator[StreamChunk]:
        assert not self.blocked, "chat_stream ran on the event loop thread"
        yield from self._chunks

    def embed(self, text: str) -> list[float]:
        return [0.0]


def _deltas(chunks: list[StreamChunk]) -> list[str]:
    return [c.delta for c in chunks if c.delta]


class TestStreamShape:
    @pytest.mark.asyncio
    async def test_deltas_arrive_in_order_then_one_terminal_chunk(self):
        provider = ScriptedProvider([
            StreamChunk(delta="Hel"),
            StreamChunk(delta="lo"),
            StreamChunk(done=True, content="Hello", usage={"completion_tokens": 2}),
        ])
        seen = [c async for c in provider.achat_stream([{"role": "user", "content": "x"}])]

        assert _deltas(seen) == ["Hel", "lo"]
        assert seen[-1].done is True
        assert seen[-1].content == "Hello"
        assert seen[-1].usage == {"completion_tokens": 2}
        assert sum(1 for c in seen if c.done) == 1

    @pytest.mark.asyncio
    async def test_thinking_is_separate_from_text(self):
        provider = ScriptedProvider([
            StreamChunk(thinking="weighing"),
            StreamChunk(delta="answer"),
            StreamChunk(done=True, content="answer"),
        ])
        seen = [c async for c in provider.achat_stream([])]
        assert [c.thinking for c in seen if c.thinking] == ["weighing"]
        assert _deltas(seen) == ["answer"]

    @pytest.mark.asyncio
    async def test_stream_does_not_block_the_event_loop(self):
        """A ticker must keep ticking while the provider is streaming.

        This is the regression guard for the defect where a synchronous provider
        call stalled the whole bus.
        """
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(30):
                ticks += 1
                await asyncio.sleep(0.005)

        provider = ScriptedProvider([
            StreamChunk(delta=str(i)) for i in range(50)
        ] + [StreamChunk(done=True, content="done")])

        async def consume():
            async for _ in provider.achat_stream([]):
                await asyncio.sleep(0.002)

        await asyncio.gather(ticker(), consume())
        assert ticks >= 25, f"loop was starved: only {ticks} ticks"

    @pytest.mark.asyncio
    async def test_consumer_abandoning_the_stream_is_safe(self):
        provider = ScriptedProvider(
            [StreamChunk(delta=str(i)) for i in range(100)] + [StreamChunk(done=True)]
        )
        stream = provider.achat_stream([])
        await stream.__anext__()
        await stream.aclose()  # a cancelled turn does exactly this

    @pytest.mark.asyncio
    async def test_provider_exception_surfaces_to_the_consumer(self):
        class Boom(LLMBackend):
            def __init__(self):
                super().__init__(model="boom")

            def chat(self, *a, **k):
                raise RuntimeError("nope")

            def chat_stream(self, *a, **k):
                raise RuntimeError("stream failed")

            def embed(self, text):
                return []

        with pytest.raises(RuntimeError, match="stream failed"):
            async for _ in Boom().achat_stream([]):
                pass


class TestFactory:
    def test_unknown_provider_names_the_value(self):
        with pytest.raises(ProviderError, match="Unknown .* provider 'gemini'"):
            create_provider({"provider": "gemini", "model": "x"})

    def test_missing_model_is_an_error(self):
        with pytest.raises(ProviderError, match="model"):
            create_provider({"provider": "ollama", "model": ""})

    def test_missing_provider_is_an_error(self):
        with pytest.raises(ProviderError, match="provider"):
            create_provider({})

    def test_ollama_provider_builds(self):
        provider = create_provider({"provider": "ollama", "model": "m"})
        assert provider.model == "m"

    def test_embeddings_same_reuses_the_chat_provider(self):
        chat = create_provider({"provider": "ollama", "model": "m"})
        assert resolve_embedding_provider({"provider": "same"}, chat) is chat

    def test_embeddings_can_use_a_different_provider(self):
        chat = create_provider({"provider": "ollama", "model": "m"})
        other = resolve_embedding_provider({"provider": "ollama", "model": "e"}, chat)
        assert other is not chat
        assert other.model == "e"
