from modules.hands.builtin_tools.base import ToolBase


class BrowserTool(ToolBase):
    name = "browser"
    description = "Open a URL in the default web browser."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to open in the browser"},
        },
        "required": ["url"],
    }

    def execute(self, url: str) -> str:
        import webbrowser
        webbrowser.open(url)
        return f"Opened {url} in browser"
