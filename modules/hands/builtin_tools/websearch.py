from modules.hands.builtin_tools.base import ToolBase


class WebSearchTool(ToolBase):
    name = "web_search"
    description = "Search the web for current information and return results with titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 5},
        },
        "required": ["query"],
    }

    def execute(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })
            return results
        except ImportError:
            raise ImportError("duckduckgo-search package not installed. Run: pip install duckduckgo-search")
