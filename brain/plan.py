import json
import re
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class PlanResult:
    action: str  # "direct_answer" | "call_tool" | "multi_step" | "ask_clarification"
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str | None = None
    clarification_question: str | None = None

    @property
    def tool_name(self) -> str | None:
        return self.tool_calls[0].name if self.tool_calls else None

    @property
    def tool_params(self) -> dict | None:
        return self.tool_calls[0].arguments if self.tool_calls else None


class Planner:
    """Stage 4: Decide what action to take based on LLM reasoning."""

    MAX_TOOL_STEPS = 5

    def decide(
        self,
        intent_type: str,
        llm_response: dict,
        has_tools: bool,
    ) -> PlanResult:
        content = llm_response.get("content") or ""
        tool_calls_raw = llm_response.get("tool_calls")

        if tool_calls_raw and has_tools:
            parsed = self._parse_tool_calls(tool_calls_raw)
            return PlanResult(
                action="call_tool",
                tool_calls=parsed,
                reasoning=content,
            )

        if intent_type == "unknown":
            return PlanResult(
                action="ask_clarification",
                clarification_question="I'm not sure what you mean. Could you rephrase that?",
                reasoning=content,
            )

        return PlanResult(
            action="direct_answer",
            reasoning=content,
        )

    def _parse_tool_calls(self, tool_calls_raw: list) -> list[ToolCall]:
        parsed = []
        for tc in tool_calls_raw:
            name = tc.get("name", "")
            arguments = tc.get("arguments", {})
            if isinstance(arguments, str):
                arguments = _repair_and_parse_json(arguments)
            if name:
                parsed.append(ToolCall(name=name, arguments=arguments))
        return parsed


def _repair_and_parse_json(raw: str) -> dict:
    """Fix common LLM JSON errors and parse."""
    fixed = raw.strip()
    fixed = fixed.replace("'", '"')
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return {}
