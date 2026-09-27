# Data Model

Entities, fields, storage, and lifetime. Every number carries units or a source.

## Storage layout

All paths come from config. Defaults shown; the rest are relative.

| Store | Default path | Format | Lifetime |
| --- | --- | --- | --- |
| Conversations | `.config/aiassistant/memory/conversations/` | Markdown, one file per day | Indefinite |
| Facts | `.config/aiassistant/memory/facts/` | Markdown, one file per category | Indefinite |
| Knowledge | `.config/aiassistant/memory/knowledge/` | Markdown | Indefinite |
| Embeddings cache | `.config/aiassistant/embeddings.db` | SQLite | Rebuildable from markdown |
| Schedules | `.config/aiassistant/schedules.json` | JSON | Until fired or deleted |
| Console history | `.config/aiassistant/history` | readline | Indefinite |
| Artifacts | `tools.artifacts_path` | Files written by tools | Indefinite |

The markdown conversation format is **frozen from as-built**
(`brain/respond.py:41-63`): a `## HH:MM:SS | speaker` header per turn, the
content, and optional `[tools: ...]` / `[thinking: ...]` lines. The SQLite cache
is a derived index and can be rebuilt (`embeddings.py:156`).

## Conversation turn

| Field | Type | Notes |
| --- | --- | --- |
| `timestamp` | str `HH:MM:SS` | Written in UTC; date comes from the filename |
| `speaker` | `user` \| `assistant` | |
| `content` | str | The authoritative text (`text_final` for assistants) |
| `thinking` | str \| null | Display only, never spoken |
| `tools_used` | list | `{name, request_id, duration_ms}` |

Written exactly once per turn (REQ-MEM-002). The as-built code had two writers —
`Responder.save_turn` (`respond.py:27`) and `MemoryManager.save_turn`
(`memory.py:25`) — which this refactor collapses into one.

## Sessions

| Field | Type | Notes |
| --- | --- | --- |
| `session_id` | str | Generated per process start unless resumed |
| `agent_id` | str | The `agents:` key, e.g. `jarvis` |
| `harness` | `native` | Recorded per turn so history is interpretable |
| `resumed_from` | str \| null | Prior session id when `memory.resume_session` is true |

Context passed to the **native** harness is bounded by
`conversation.context_turns`.

## Facts

| Field | Type | Notes |
| --- | --- | --- |
| `category` | str | Becomes the filename |
| `fact` | str | One line, timestamped on write |
| `created_at` / `updated_at` | ISO 8601 | In the embedding table |

## Embedding records

Three tables in `embeddings.db`, all keyed by content and rebuildable:

| Table | Key columns | Payload |
| --- | --- | --- |
| `conversation_embeddings` | date, timestamp, speaker, chunk | embedding blob, token count |
| `fact_embeddings` | category, fact | embedding blob |
| `knowledge_embeddings` | source_file, chunk_index, chunk | embedding blob |

Vectors are serialized as JSON text in a BLOB column, and similarity is cosine
computed in Python (`embeddings.py:221`). Search is a **linear scan** of the
whole table (`embeddings.py:196`). Acceptable for a personal transcript; noted
as a v2 candidate rather than silently accepted.

An embedding dimension mismatch between the query and a stored vector causes
that row to be skipped (`embeddings.py:202`), which is why changing the
embedding model requires a rebuild.

## Schedule task

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | 8 hex chars |
| `task` | str | Short title |
| `time` | ISO 8601 | Triggers when `time <= now` |
| `repeat` | `hourly` \| `daily` \| `weekly` \| null | Next time is always in the future |
| `description` | str | Spoken or shown on trigger |

## Config model

Every default lives in code (`config.py` `DEFAULTS`), so the assistant runs with
no config file. Config is layered YAML with a defined precedence (REQ-CFG-002):
CLI override > environment > `config.yaml` > code defaults.

| Layer | Path | Role |
| --- | --- | --- |
| Local config | `config.yaml` (`-c` overrides) | The user's overrides. Optional and git-ignored. |
| Code defaults | `config.py` `DEFAULTS` | The single source of truth; the app runs on these alone. |
| Example | `config.example.yaml` | Tracked, commented copy of the defaults for the user to copy. |

The local file is deep-merged key by key over the defaults, so it names only
what it changes. A guard test asserts `config.example.yaml` matches `DEFAULTS`
key for key, so the example cannot drift into a lie.

```yaml
agents:
  jarvis:                      # the active agent; more may be defined
    identity:
      name: Jarvis
      wake_phrases: ["hi jarvis"]
    harness: native            # the loop owner
    llm:                       # native only
      provider: ollama         # ollama | openai
      model: qwen3:latest
      url: http://127.0.0.1:11434
      api_key: ""              # prefer the environment

bus:
  bind: "127.0.0.1"            # widening requires a token (REQ-SEC-002)
  websocket_port: 8765
  remote_auth_token: ""
```

Per-module sections (`voice`, `tools`, `vision`, `messaging`, `console`,
`scheduler`, `display`, `memory`) follow the same pattern. Legacy section names
are accepted with a deprecation warning and mapped (REQ-CFG-004).

## Lifetime and retention

| Entity | Retention |
| --- | --- |
| Conversation markdown | Indefinite; user-owned files |
| Embeddings | Derived; safe to delete and rebuild |
| Schedules | Deleted when fired (one-shot) or re-armed (recurring) |
| Transcript shown in the orb or TUI | Session only; scrollback reads from memory on demand. Neither frontend persists state (no TUI history file; the console's readline history is separate) |
