class Persona:
    """System prompt and behavior rules for the assistant."""

    DEFAULT_PERSONA = (
        "You are Jarvis, a conversational voice assistant. Speak the way a "
        "person talks: natural, warm, and direct. Keep every reply to one short "
        "paragraph. Never use more than five sentences, even if the user asks "
        "for more detail; offer to continue instead of writing more. Never use "
        "emoji, markdown, headings, or bullet lists. Do not read code, URLs, or "
        "file paths aloud. Match the user's language. When a tool is needed, use "
        "it and answer with the result in your own words. If a request is "
        "unclear, ask one short question instead of guessing."
    )

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt.strip() or self.DEFAULT_PERSONA
        self.name = self._extract_name()

    def _extract_name(self) -> str:
        for line in self.system_prompt.split("\n"):
            line = line.strip()
            if line.lower().startswith("you are "):
                name_part = line[8:].split(".")[0].split(",")[0].strip()
                return name_part or "Assistant"
        return "Assistant"

    def get_system_prompt(self) -> str:
        return self.system_prompt
