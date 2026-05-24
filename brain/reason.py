from llm.base import LLMBackend


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

    def reset(self):
        self._history = []

    def reason(
        self,
        user_message: str,
        memory_context: str = "",
        tool_schemas: list[dict] | None = None,
    ) -> dict:
        self._history.append({"role": "user", "content": user_message})
        self._check_and_compress()

        messages = [{"role": "system", "content": self.persona}]

        if memory_context:
            messages.append({
                "role": "system",
                "content": f"Relevant context:\n{memory_context}"
            })

        messages.extend(self._history)

        tools = None
        if tool_schemas:
            tools = [{"type": "function", "function": s} for s in tool_schemas]

        response = self.llm.chat(messages, tools=tools)

        content = response.get("content") or ""
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

        self._history = [
            {"role": "system",
             "content": f"Summary of earlier conversation:\n{summary_text}"},
            {"role": "assistant", "content": "Understood. I'll use this context going forward."},
        ] + latest
