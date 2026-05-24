from openai import OpenAI

from llm.base import LLMBackend


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

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in response.data]


def _normalize_openai_tool_calls(tool_calls) -> list[dict] | None:
    """Normalize OpenAI tool_calls to standard format."""
    if not tool_calls:
        return None
    result = []
    for tc in tool_calls:
        arguments = tc.function.arguments
        if isinstance(arguments, str):
            import json
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        result.append({"name": tc.function.name, "arguments": arguments})
    return result
