from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PerceivedInput:
    input_type: str          # "text" | "speech" | "vision" | "tool_result" | "schedule" | "canvas"
    raw_payload: dict
    is_noise: bool = False
    is_addressed_to_assistant: bool = True
    is_tool_result: bool = False
    tool_request_id: str | None = None


class Perceiver:
    """Stage 1: Filter and classify incoming sensory data."""

    def __init__(self, hotwords: list[str] | None = None):
        self.hotwords = hotwords or ["hey assistant", "hello"]

    def classify(self, topic: str, payload: dict) -> PerceivedInput:
        input_type = self._map_topic_to_type(topic)
        is_tool_result = topic in ("status.hand.done", "status.hand.error")
        tool_request_id = None
        is_addressed = True

        if is_tool_result:
            tool_request_id = payload.get("request_id")
        elif input_type == "speech":
            is_addressed = self._check_hotword(payload)
        elif input_type == "vision":
            is_addressed = True  # always assume vision is for assistant

        is_noise = self._is_noise(input_type, payload)

        return PerceivedInput(
            input_type=input_type,
            raw_payload=payload,
            is_noise=is_noise,
            is_addressed_to_assistant=is_addressed,
            is_tool_result=is_tool_result,
            tool_request_id=tool_request_id,
        )

    def _map_topic_to_type(self, topic: str) -> str:
        mapping = {
            "user.input.text": "text",
            "sensory.speech.heard": "speech",
            "sensory.speech.hotword": "speech",
            "sensory.vision.frame": "vision",
            "status.hand.done": "tool_result",
            "status.hand.error": "tool_result",
            "schedule.triggered": "schedule",
            "sensory.canvas.click": "canvas",
            "sensory.canvas.input": "canvas",
            "sensory.canvas.draw": "canvas",
        }
        return mapping.get(topic, "unknown")

    def _check_hotword(self, payload: dict) -> bool:
        text = payload.get("text", "").lower()
        return any(hw.lower() in text for hw in self.hotwords)

    def _is_noise(self, input_type: str, payload: dict) -> bool:
        if input_type == "speech":
            text = payload.get("text", "").strip()
            confidence = payload.get("confidence", 1.0)
            return len(text) < 1 or confidence < 0.3
        if input_type == "text":
            text = payload.get("text", "").strip()
            return len(text) == 0
        return False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
