class ToolCache:
    """Cached tool schemas discovered from Hands at startup.

    Converts internal tool definitions to OpenAI function-calling format.
    """

    def __init__(self):
        self._tools: dict[str, dict] = {}         # name → {name, description, parameters}
        self._schemas: list[dict] = []            # OpenAI format

    def load(self, tools: list[dict]) -> None:
        """Load tools from status.hands.ready payload."""
        self._tools = {t["name"]: t for t in tools}
        self._build_schemas()

    def get_schemas(self) -> list[dict]:
        return self._schemas

    def get_formatted_schemas(self) -> list[dict]:
        """Return schemas in OpenAI function-calling format."""
        return [{"type": "function", "function": s} for s in self._schemas]

    def get_tool_list(self) -> list[dict]:
        """Return raw tool dicts (name, description, parameters)."""
        return list(self._tools.values())

    def lookup(self, name: str) -> dict | None:
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def _build_schemas(self):
        self._schemas = []
        for name, tool in self._tools.items():
            schema = {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}, "required": []}),
            }
            # Ensure parameters has type=object at minimum
            if "type" not in schema["parameters"]:
                schema["parameters"]["type"] = "object"
            self._schemas.append(schema)
