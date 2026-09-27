class Persona:
    """System prompt and behavior rules for the assistant."""

    DEFAULT_PERSONA = (
        "You are a smart, detail-oriented assistant. "
        "Always think step by step. Match the user's language. "
        "Be concise. Use tools when available."
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
