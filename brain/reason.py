import logging
from llm.base import LLMBackend
import re

logger = logging.getLogger(__name__)


def _strip_thinking(content: str) -> str:
    """Remove thinking blocks from model output, keeping only the final response."""
    if not content:
        return content

    original = content

    # Strategy: find the LAST response delimiter and take everything after it.
    #
    # Known qwen3/deepseek formats observed in the wild:
    #   qwen3 (ollama):   "<think>\n...\n</think>\n\nactual response"
    #   qwen3 1.7b:       "<thinking>\n...\n</thinking>\n\nactual response"
    #   qwen3 plain-text: " thinking\n...\n response\n\nactual response"
    #   deepseek XML:     "<thinking>...</thinking>\n<response>actual</response>"
    #
    # The delimiter is a line containing a closing think tag (</think> or </thinking>),
    # a <response> tag, or the plain-text word "response".

    # 1. Find the LAST delimiter line and take everything after it
    delimiter = (
        r'^[ \t]*'
        r'(?:'
        r'</think>'            # qwen3 closing think tag (no "ing")
        r'|</thinking>'        # qwen3 closing thinking tag
        r'|<response>'         # deepseek XML response tag
        r'|response'           # plain text response marker
        r')'
        r'[ \t]*$'
    )
    last_end = None
    for m in re.finditer(delimiter, content, flags=re.MULTILINE):
        last_end = m.end()
    if last_end is not None:
        after = content[last_end:].strip()
        if after:
            after = re.sub(r'\s*</response>\s*$', '', after)
            logger.debug("Stripped thinking via delimiter line (%d → %d chars)",
                         len(original), len(after))
            return after

    # 2. split on <response> tag (not necessarily on its own line)
    if '<response>' in content:
        parts = content.split('<response>', 1)
        text = parts[1].strip()
        text = re.sub(r'\s*</response>\s*$', '', text)
        if text:
            logger.debug("Stripped thinking via <response> split (%d → %d chars)",
                         len(original), len(text))
            return text

    # 3. no response marker — try to strip thinking-only blocks
    if '<thinking>' in content:
        cleaned = re.sub(r'^\s*<thinking>[\s\S]*?</thinking>\s*', '', content, count=1)
        if cleaned != content:
            logger.debug("Stripped <thinking>...</thinking> block (%d → %d chars)",
                         len(original), len(cleaned.strip()))
            return cleaned.strip()
        cleaned = re.sub(r'^\s*<thinking>[\s\S]*', '', content, count=1)
        logger.debug("Stripped <thinking> (no closing tag) (%d → %d chars)",
                     len(original), len(cleaned.strip()))
        return cleaned.strip()

    logger.debug("No thinking pattern found in content (%d chars), returning as-is", len(original))
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
        if raw_content:
            logger.debug("reason raw_content (%d chars): %s", len(raw_content), repr(raw_content[:200]))
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
        if raw_content:
            logger.debug("reason_with_tool_results raw_content (%d chars): %s", len(raw_content), repr(raw_content[:200]))
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
