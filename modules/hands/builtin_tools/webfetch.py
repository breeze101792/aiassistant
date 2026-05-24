from modules.hands.builtin_tools.base import ToolBase


class WebFetchTool(ToolBase):
    name = "web_fetch"
    description = "Fetch and extract text content from a URL."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch content from"},
        },
        "required": ["url"],
    }

    def execute(self, url: str) -> str:
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; aiassistant/1.0)"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to fetch {url}: {e}")

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines[:200])
        except ImportError:
            return html[:4000]
