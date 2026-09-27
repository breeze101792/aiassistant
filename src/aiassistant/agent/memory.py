import os
import re
from datetime import datetime, timezone


class MemoryManager:
    """Manages all persistent memory: conversations, facts, and knowledge base.

    Memory is stored as markdown files. Embeddings.db is the search index.
    """

    def __init__(self, conversations_path: str, facts_path: str,
                 knowledge_path: str, embeddings_db_path: str = ""):
        self.conversations_path = conversations_path
        self.facts_path = facts_path
        self.knowledge_path = knowledge_path
        self.embeddings_db_path = embeddings_db_path

        os.makedirs(conversations_path, exist_ok=True)
        os.makedirs(facts_path, exist_ok=True)
        os.makedirs(knowledge_path, exist_ok=True)

    # ── Conversation History ──────────────────────────────────

    def save_turn(self, date_str: str, timestamp: str, speaker: str,
                  content: str, thinking: str | None = None,
                  tools_used: list[dict] | None = None) -> str:
        filepath = os.path.join(self.conversations_path, f"{date_str}.md")
        header = f"# Conversation — {date_str}\n\n" if not os.path.exists(filepath) else ""

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

    def get_turns(self, date_str: str) -> list[dict]:
        filepath = os.path.join(self.conversations_path, f"{date_str}.md")
        if not os.path.exists(filepath):
            return []
        return self._parse_conversation_file(filepath)

    def get_recent_turns(self, count: int = 20) -> list[dict]:
        """Get the most recent N turns across all conversation files."""
        all_turns = []
        try:
            for fname in sorted(os.listdir(self.conversations_path), reverse=True):
                if not fname.endswith(".md"):
                    continue
                filepath = os.path.join(self.conversations_path, fname)
                turns = self._parse_conversation_file(filepath)
                all_turns = turns + all_turns
                if len(all_turns) >= count:
                    break
        except FileNotFoundError:
            pass
        return all_turns[-count:]

    def search_conversations(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """Stub — requires embeddings.db to be populated. Returns empty until Phase 5."""
        return []

    # ── Facts ─────────────────────────────────────────────────

    def save_fact(self, category: str, fact: str) -> str:
        filepath = os.path.join(self.facts_path, f"{category}.md")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        header = f"# {category.replace('_', ' ').title()}\n\n" if not os.path.exists(filepath) else ""
        line = f"- [{timestamp}] {fact}\n"

        with open(filepath, "a") as f:
            if header:
                f.write(header)
            f.write(line)
        return filepath

    def get_facts(self, category: str) -> list[str]:
        filepath = os.path.join(self.facts_path, f"{category}.md")
        if not os.path.exists(filepath):
            return []
        facts = []
        with open(filepath) as f:
            for line in f:
                match = re.match(r"- \[.*?\] (.+)", line)
                if match:
                    facts.append(match.group(1).strip())
        return facts

    def all_fact_categories(self) -> list[str]:
        try:
            files = os.listdir(self.facts_path)
        except FileNotFoundError:
            return []
        return [f.replace(".md", "") for f in files if f.endswith(".md")]

    # ── Knowledge Base ────────────────────────────────────────

    def load_knowledge_chunks(self, query_embedding: list[float], top_k: int = 3) -> list[str]:
        """Stub — returns empty until embeddings.db is populated."""
        return []

    def list_knowledge_files(self) -> list[str]:
        try:
            return [f for f in os.listdir(self.knowledge_path) if f.endswith(".md")]
        except FileNotFoundError:
            return []

    # ── Helpers ───────────────────────────────────────────────

    def _parse_conversation_file(self, filepath: str) -> list[dict]:
        turns = []
        with open(filepath) as f:
            content = f.read()

        pattern = r"## (\d{2}:\d{2}:\d{2}) \| (\w+)\n\n(.+?)(?=\n## |\n\[tools:|\n\[thinking:|\Z)"
        for match in re.finditer(pattern, content, re.DOTALL):
            timestamp, speaker, text = match.groups()
            turns.append({
                "timestamp": timestamp,
                "speaker": speaker,
                "content": text.strip(),
            })
        return turns
