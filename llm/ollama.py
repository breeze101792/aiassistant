import ollama

from llm.base import LLMBackend


class OllamaBackend(LLMBackend):
    """Ollama LLM backend — local models via Ollama API."""

    def __init__(self, model: str, url: str = "http://127.0.0.1:11434", api_key: str = ""):
        super().__init__(model=model, url=url, api_key=api_key)
        self._client = ollama.Client(host=self.url)

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
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            kwargs["tools"] = tools

        response = self._client.chat(**kwargs)

        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", None)

        return {
            "content": content.strip() if content else None,
            "tool_calls": _normalize_tool_calls(tool_calls),
            "usage": {
                "prompt_tokens": response.get("prompt_eval_count", 0),
                "completion_tokens": response.get("eval_count", 0),
            },
        }

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings(model=self.model, prompt=text)
        return response.get("embedding", [])

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def _normalize_tool_calls(tool_calls) -> list[dict] | None:
    """Normalize Ollama tool_calls to standard format."""
    if not tool_calls:
        return None
    result = []
    for tc in tool_calls:
        name = tc.get("function", {}).get("name", "")
        arguments = tc.get("function", {}).get("arguments", {})
        if isinstance(arguments, str):
            import json
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        result.append({"name": name, "arguments": arguments})
    return result
