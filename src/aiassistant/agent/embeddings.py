import json
import math
import sqlite3
from typing import Any


class EmbeddingsEngine:
    """Text → vector via LLM embedding endpoint, cached in SQLite.

    embeddings.db is a cache. It can be rebuilt from markdown files.
    """

    def __init__(self, db_path: str, llm_backend=None):
        self.db_path = db_path
        self.llm = llm_backend
        self._init_db()

    def set_llm(self, llm_backend):
        self.llm = llm_backend

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversation_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    timestamp TEXT,
                    speaker TEXT,
                    chunk TEXT,
                    embedding BLOB,
                    tokens INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS fact_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    fact TEXT,
                    embedding BLOB,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT,
                    chunk_index INTEGER,
                    chunk TEXT,
                    embedding BLOB
                );
                CREATE INDEX IF NOT EXISTS idx_conv_date ON conversation_embeddings(date);
                CREATE INDEX IF NOT EXISTS idx_fact_category ON fact_embeddings(category);
            """)

    # ── Embedding ─────────────────────────────────────────────

    def _embeddings_available(self) -> bool:
        if not self.llm:
            return False
        if getattr(self, "_embeddings_unavailable", False):
            return False
        return True

    def embed(self, text: str) -> list[float]:
        if not self._embeddings_available():
            raise RuntimeError("No LLM backend configured for embeddings")
        try:
            return self.llm.embed(text)
        except Exception:
            self._embeddings_unavailable = True
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._embeddings_available():
            raise RuntimeError("No LLM backend configured for embeddings")
        try:
            return self.llm.embed_batch(texts)
        except Exception:
            self._embeddings_unavailable = True
            raise

    # ── Conversation Embeddings ───────────────────────────────

    def index_conversation_turn(self, date_str: str, timestamp: str,
                                 speaker: str, chunk: str):
        if not self.llm:
            return
        embedding = self.embed(chunk)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversation_embeddings (date, timestamp, speaker, chunk, embedding, tokens) VALUES (?, ?, ?, ?, ?, ?)",
                (date_str, timestamp, speaker, chunk, _serialize(embedding), len(chunk.split()))
            )

    def search_conversations(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.llm:
            return []
        query_vec = self.embed(query)
        return self._search_table("conversation_embeddings", query_vec,
                                  ["date", "timestamp", "speaker", "chunk"], top_k)

    # ── Fact Embeddings ───────────────────────────────────────

    def index_fact(self, category: str, fact: str):
        if not self.llm:
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        embedding = self.embed(fact)
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM fact_embeddings WHERE category=? AND fact=?",
                (category, fact)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE fact_embeddings SET embedding=?, updated_at=? WHERE id=?",
                    (_serialize(embedding), now, existing[0])
                )
            else:
                conn.execute(
                    "INSERT INTO fact_embeddings (category, fact, embedding, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (category, fact, _serialize(embedding), now, now)
                )

    def search_facts(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.llm:
            return []
        query_vec = self.embed(query)
        return self._search_table("fact_embeddings", query_vec,
                                  ["category", "fact"], top_k)

    # ── Knowledge Base Embeddings ─────────────────────────────

    def index_knowledge_chunks(self, source_file: str, chunks: list[str]):
        if not self.llm:
            return
        embeddings = self.embed_batch(chunks)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM knowledge_embeddings WHERE source_file=?",
                (source_file,)
            )
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                conn.execute(
                    "INSERT INTO knowledge_embeddings (source_file, chunk_index, chunk, embedding) VALUES (?, ?, ?, ?)",
                    (source_file, i, chunk, _serialize(emb))
                )

    def search_knowledge(self, query: str, top_k: int = 3) -> list[dict]:
        if not self.llm:
            return []
        query_vec = self.embed(query)
        return self._search_table("knowledge_embeddings", query_vec,
                                  ["source_file", "chunk"], top_k)

    # ── Rebuild ───────────────────────────────────────────────

    def rebuild_index(self, conversations_path: str, facts_path: str,
                      knowledge_path: str):
        """Rebuild all embeddings from markdown source files."""
        import os
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM conversation_embeddings")
            conn.execute("DELETE FROM fact_embeddings")
            conn.execute("DELETE FROM knowledge_embeddings")

        # Rebuild conversation embeddings
        if os.path.isdir(conversations_path):
            for fname in sorted(os.listdir(conversations_path)):
                if not fname.endswith(".md"):
                    continue
                date_str = fname.replace(".md", "")
                filepath = os.path.join(conversations_path, fname)
                with open(filepath) as f:
                    content = f.read()
                import re
                for m in re.finditer(r"## (\d{2}:\d{2}:\d{2}) \| (\w+)\n\n(.+?)(?=\n## |\n\[|\Z)", content, re.DOTALL):
                    self.index_conversation_turn(date_str, m.group(1), m.group(2), m.group(3).strip())

        # Rebuild fact embeddings
        if os.path.isdir(facts_path):
            for fname in os.listdir(facts_path):
                if not fname.endswith(".md"):
                    continue
                category = fname.replace(".md", "")
                filepath = os.path.join(facts_path, fname)
                with open(filepath) as f:
                    for line in f:
                        m = re.match(r"- \[.*?\] (.+)", line)
                        if m:
                            self.index_fact(category, m.group(1).strip())

    # ── Internal ──────────────────────────────────────────────

    def _search_table(self, table: str, query_vec: list[float],
                      columns: list[str], top_k: int) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(f"SELECT {', '.join(columns)}, embedding FROM {table}").fetchall()

        scored = []
        for row in rows:
            *values, emb_blob = row
            emb = _deserialize(emb_blob)
            if emb and len(emb) == len(query_vec):
                score = _cosine_similarity(query_vec, emb)
                scored.append((score, dict(zip(columns, values))))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]


def _serialize(vec: list[float]) -> bytes:
    return json.dumps(vec).encode("utf-8")


def _deserialize(blob: bytes) -> list[float] | None:
    try:
        return json.loads(blob.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
