import os
import uuid
from datetime import datetime, timezone

from brain.perceive import now_iso


class Responder:
    """Stage 7: Formulate and deliver the final response."""

    def __init__(self, conversations_path: str, context_recent_messages: int = 20):
        self.conversations_path = conversations_path
        self.context_recent_messages = context_recent_messages
        self._conversation_id: str | None = None
        os.makedirs(conversations_path, exist_ok=True)

    def respond(self, text: str, thinking: str | None = None,
                tools_used: list[dict] | None = None) -> dict:
        self._conversation_id = self._conversation_id or str(uuid.uuid4())[:8]
        return {
            "text": text,
            "conversation_id": self._conversation_id,
            "thinking": thinking,
            "tools_used": tools_used or [],
        }

    def save_turn(self, speaker: str, content: str, thinking: str | None = None,
                  tools_used: list[dict] | None = None) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = os.path.join(self.conversations_path, f"{today}.md")
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

        header = f"# Conversation — {today}\n\n" if not os.path.exists(filepath) else ""
        lines = [f"## {timestamp} | {speaker}", "", content]

        if tools_used:
            tool_str = ", ".join(
                f"{t['name']}({t.get('request_id', '?')}, {t.get('duration_ms', '?')}ms)"
                for t in tools_used
            )
            lines.append(f"[tools: {tool_str}]")

        if thinking:
            lines.append(f"[thinking: {thinking}]")

        lines.append("")

        with open(filepath, "a") as f:
            if header:
                f.write(header)
            f.write("\n".join(lines))

        return filepath
