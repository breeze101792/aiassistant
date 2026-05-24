from modules.hands.skills.base import SkillBase


class ResearchSkill(SkillBase):
    """Research a topic: search → fetch → summarize → save."""

    name = "research_topic"
    description = "Research a topic thoroughly: search the web, fetch top sources, summarize findings, and optionally save to a file."
    parameters = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic to research"},
            "depth": {"type": "string", "enum": ["brief", "detailed"], "description": "Research depth"},
            "output_file": {"type": "string", "description": "Optional file path to save findings"},
        },
        "required": ["topic"],
    }

    def execute(self, topic: str, depth: str = "brief", output_file: str | None = None) -> str:
        max_results = 5 if depth == "brief" else 10

        # Step 1: Search
        results = self.call_tool("web_search", query=topic, max_results=max_results)
        if not results:
            return f"No search results found for: {topic}"

        # Step 2: Fetch top sources
        sources = []
        for r in results[:3]:
            try:
                content = self.call_tool("web_fetch", url=r["url"])
                sources.append({"title": r["title"], "url": r["url"], "content": content[:2000]})
            except Exception:
                sources.append({"title": r["title"], "url": r["url"], "content": "[fetch failed]"})

        # Step 3: Summarize with LLM
        context_str = "\n\n".join(
            f"Source: {s['title']}\n{s['content']}"
            for s in sources
        )
        summary = self.call_llm(
            f"Summarize the following research about '{topic}'. Be concise and highlight key findings.",
            context=[context_str],
        )

        # Step 4: Save if requested
        if output_file:
            full_report = f"# Research: {topic}\n\n{summary}\n\n## Sources\n"
            for s in sources:
                full_report += f"- [{s['title']}]({s['url']})\n"
            self.call_tool("file.write", path=output_file, content=full_report)

        return summary
