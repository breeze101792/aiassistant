from collections.abc import Iterator
import json

from openai import OpenAI

from aiassistant.reasoning.base import LLMBackend, StreamChunk


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend.

    Works with OpenAI, Azure, and any OpenAI-compatible endpoint
    (vLLM, LM Studio, etc.).
    """

    def __init__(self, model: str, url: str = "https://api.openai.com/v1", api_key: str = ""):
        super().__init__(model=model, url=url, api_key=api_key)
        self._client = OpenAI(base_url=self.url, api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        response = self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content
        tool_calls = choice.message.tool_calls

        return {
            "content": content.strip() if content else None,
            "tool_calls": _normalize_openai_tool_calls(tool_calls),
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Iterator[StreamChunk]:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools

        collected: list[str] = []
        # Tool-call arguments arrive as fragments keyed by index, not id.
        tool_fragments: dict[int, dict] = {}
        usage: dict = {}

        for event in self._client.chat.completions.create(**kwargs):
            if getattr(event, "usage", None):
                usage = {
                    "prompt_tokens": event.usage.prompt_tokens or 0,
                    "completion_tokens": event.usage.completion_tokens or 0,
                }
            if not event.choices:
                continue
            delta = event.choices[0].delta
            if delta is None:
                continue

            text = getattr(delta, "content", None)
            if text:
                collected.append(text)
                yield StreamChunk(delta=text)

            # Reasoning models expose a separate channel; keep it out of the
            # spoken text but let the caller surface it as thinking.
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield StreamChunk(thinking=reasoning)

            for tc in getattr(delta, "tool_calls", None) or []:
                entry = tool_fragments.setdefault(
                    tc.index, {"id": tc.id, "name": "", "arguments": ""}
                )
                if tc.id:
                    entry["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

        yield StreamChunk(
            done=True,
            content="".join(collected).strip() or None,
            tool_calls=_finalize_tool_fragments(tool_fragments),
            usage=usage,
        )

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in response.data]

    def format_tool_arguments(self, arguments: dict) -> str:
        """OpenAI requires tool-call arguments as a JSON string."""
        return json.dumps(arguments, ensure_ascii=False)


def _normalize_openai_tool_calls(tool_calls) -> list[dict] | None:
    """Normalize OpenAI tool_calls to the standard shape."""
    if not tool_calls:
        return None
    result = []
    for tc in tool_calls:
        result.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": _parse_arguments(tc.function.arguments),
        })
    return result


def _finalize_tool_fragments(fragments: dict[int, dict]) -> list[dict] | None:
    """Assemble streamed tool-call fragments into complete calls."""
    if not fragments:
        return None
    return [
        {
            "id": entry.get("id"),
            "name": entry["name"],
            "arguments": _parse_arguments(entry["arguments"]),
        }
        for _, entry in sorted(fragments.items())
    ]


def _parse_arguments(arguments) -> dict:
    if isinstance(arguments, dict):
        return arguments
    if not arguments:
        return {}
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return {}
