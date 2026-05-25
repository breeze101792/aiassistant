from llm.base import LLMBackend
import re


def _strip_thinking(content: str) -> str:
    """Remove thinking blocks from model output, keeping only the final response."""
    if not content:
        return content
    # qwen3 plain-text: "thinking" and "response" as standalone words on their own lines
    cleaned = re.sub(
        r'(?m)^\s*thinking\s*$[\s\S]*?^\s*response\s*$',
        '', content, count=1,
    )
    if cleaned != content:
        return cleaned.strip()
    # qwen3 / deepseek XML format: <response> marker
    parts = re.split(r'\s*<response>\s*', content, maxsplit=1)
    if len(parts) > 1:
        text = parts[1].strip()
        text = re.sub(r'\s*</response>\s*$', '', text)
        return text
    # If only a thinking block exists with no response marker
    if '<thinking>' in content:
        # Try stripping <thinking>...</thinking> block, leaving any trailing content
        cleaned = re.sub(
            r'^\s*<thinking>[\s\S]*?</thinking>\s*', '', content, count=1,
        )
        if cleaned != content:
            return cleaned.strip()
        # No closing tag — strip everything (all thinking, no response)
        cleaned = re.sub(r'^\s*<thinking>[\s\S]*', '', content, count=1)
        return cleaned.strip()
    return content.strip()


class Reasoner:
    """Stage 3: Internal chain of thought via LLM.

    Maintains conversation history with automatic compression when
    token limits are exceeded.
    """

    def __init__(self, llm: LLMBackend, persona: str,
                 compress_target: int = 600,
                 context_max_tokens: int = 4096):
        self.llm = llm
        self.persona = persona
        self.compress_target = compress_target
        self.context_max_tokens = context_max_tokens
        self._history: list[dict] = []
        self._compressed_summary: str | None = None
        self._tool_schemas: list[dict] | None = None

    def reset(self):
        self._history = []
        self._compressed_summary = None

    def set_tools(self, formatted_schemas: list[dict] | None) -> None:
        """Update available tool schemas (called when tools are loaded after startup)."""
        self._tool_schemas = formatted_schemas

    def reason(
        self,
        user_message: str,
        memory_context: str = "",
        tool_schemas: list[dict] | None = None,
    ) -> dict:
        self._history.append({"role": "user", "content": user_message})
        self._check_and_compress()

        messages = [{"role": "system", "content": self.persona}]

        if self._compressed_summary:
            messages.append({
                "role": "system",
                "content": f"Summary of earlier conversation:\n{self._compressed_summary}"
            })

        if memory_context:
            messages.append({
                "role": "system",
                "content": f"Relevant context:\n{memory_context}"
            })

        messages.extend(self._history)

        tools = tool_schemas or self._tool_schemas

        response = self.llm.chat(messages, tools=tools)

        raw_content = response.get("content") or ""
        content = _strip_thinking(raw_content)
        response["content"] = content
        self._history.append({"role": "assistant", "content": content})

        return response

    def reason_with_tool_results(
        self,
        tool_calls: list[dict],
        tool_results: list[dict],
    ) -> dict:
        """Second reasoning pass: send tool call + results back to LLM for synthesis."""
        for tc, result in zip(tool_calls, tool_results):
            self._history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", {}),
                    }
                }],
            })
            result_data = result.get("result", "")
            if not isinstance(result_data, str):
                import json
                result_data = json.dumps(result_data, ensure_ascii=False)
            self._history.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "unknown"),
                "content": result_data,
            })

        messages = [{"role": "system", "content": self.persona}]
        messages.extend(self._history)

        response = self.llm.chat(messages)
        raw_content = response.get("content") or ""
        content = _strip_thinking(raw_content)
        response["content"] = content
        self._history.append({"role": "assistant", "content": content})

        return response

    def _check_and_compress(self):
        token_cnt = self.llm.token_count(self._history)
        limit = self.context_max_tokens - self.compress_target
        if token_cnt > limit:
            self._compress_history()

    def _compress_history(self):
        if len(self._history) < 3:
            return

        latest = self._history[-2:]  # last user + assistant pair
        to_compress = self._history[:-2]
        tokens_per = max(int(self.compress_target / 3), 50)

        compress_prompt = (
            f"Summarize the previous conversation concisely:\n"
            f"- User's main questions, goals, and requests (use ~{tokens_per} words)\n"
            f"- Your key responses, explanations, and suggestions (use ~{tokens_per} words)\n"
            f"- Any important decisions or conclusions (use ~{tokens_per} words)\n"
            "Keep the summary brief and focused on what's still relevant."
        )

        compress_messages = to_compress + [{"role": "user", "content": compress_prompt}]
        summary = self.llm.chat(compress_messages, max_tokens=self.compress_target)
        summary_text = summary.get("content", "") or "Previous conversation summarized."

        self._compressed_summary = summary_text
        self._history = latest
