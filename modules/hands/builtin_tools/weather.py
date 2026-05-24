from modules.hands.builtin_tools.base import ToolBase


class WeatherTool(ToolBase):
    name = "weather"
    description = "Get current weather information for a location."
    parameters = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name or location (e.g., 'London', 'Taipei')"},
        },
        "required": ["location"],
    }

    def execute(self, location: str) -> str:
        import urllib.request

        url = f"https://wttr.in/{location}?format=%l:+%c+%t+%h+%w"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "curl/7.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception as e:
            return f"Weather unavailable for {location}: {e}"
