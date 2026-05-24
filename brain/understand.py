from dataclasses import dataclass


@dataclass
class Intent:
    type: str           # "question" | "command" | "chat" | "scheduled_reminder" | "unknown"
    urgency: str        # "high" | "normal" | "low"
    needs_clarification: bool = False
    clarification_question: str | None = None


class Understander:
    """Stage 2: Determine what the user really wants."""

    QUESTION_KEYWORDS = ["what", "how", "why", "when", "where", "who", "which", "can you", "do you", "is it", "tell me", "explain", "describe", "find", "search"]
    COMMAND_KEYWORDS = ["do", "run", "execute", "create", "make", "set", "add", "remove", "delete", "start", "stop", "open", "close", "draw", "show", "generate", "remind", "schedule", "send", "email", "write", "save", "download", "search", "lookup", "fetch", "get", "play", "check", "read", "list", "tell"]
    URGENT_KEYWORDS = ["urgent", "asap", "emergency", "now", "immediately", "right now", "quick"]

    def classify(self, text: str) -> Intent:
        text_lower = text.strip().lower()

        if not text_lower:
            return Intent(type="unknown", urgency="normal", needs_clarification=True,
                          clarification_question="I didn't catch that. Could you repeat?")

        urgency = "high" if any(w in text_lower for w in self.URGENT_KEYWORDS) else "normal"

        first_word = text_lower.split()[0] if text_lower else ""
        is_question = text_lower.endswith("?")
        starts_question = first_word in self.QUESTION_KEYWORDS
        starts_command = first_word in self.COMMAND_KEYWORDS

        if starts_command or first_word in ["please"]:
            return Intent(type="command", urgency=urgency)
        elif is_question or starts_question:
            return Intent(type="question", urgency=urgency)
        else:
            return Intent(type="chat", urgency=urgency)
