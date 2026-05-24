# AI Assistant — High-Level Design

> Design locked: 2026-05-21

## Overview

A modular, human-like AI assistant. The assistant has body parts — ears (listen), mouth (speak), eyes (see), brain (think), hands (act), canvas (display) — plus a scheduler and chat interfaces, all connected by a message bus. Every module communicates only through the bus via well-defined topic contracts. Modules can run locally or remotely. All modules are always loaded; the backend determines behavior (e.g., `stub` for no hardware, `text` for no speakers).

## Architecture

```
                      ┌──────────────────────┐
                      │     Message Bus       │
                      │   (Nervous System)    │
                      │                       │
                      │  Pub/Sub + RPC        │
                      │  Local: direct call   │
                      │  Remote: websocket    │
                      └──┬──┬──┬──┬──┬──┬──┬──┘
                         │  │  │  │  │  │  │
   ┌─────────────────────┘  │  │  │  │  │  └──────────────────┐
   │                        │  │  │  │  │                     │
 ┌──┴───┐ ┌──────┐ ┌────┐┌──┴──┴──┐┌┴──────┐ ┌──────┐ ┌──────┴──┐
 │ Ears │ │Mouth │ │Eyes││ Brain  ││Hands  │ │Sched │ │ Canvas  │
 │(listen│ │(speak│ │(see││ (think ││ (act) │ │(clock│ │ (show)  │
 └──────┘ └──────┘ └────┘└────────┘└───────┘ └──────┘ └─────────┘
  always    always  always  always    always    always    always

 ┌──────────┐  ┌──────────┐
 │   CLI    │  │   Chat   │
 │(terminal)│  │(telegram,│
 └──────────┘  │  whatsapp│
               └──────────┘
               interface modules
```

## Module Status and Optionality

| Module    | Backend determines behavior | Example backends |
|-----------|---------------------------|------------------|
| Brain     | LLM provider              | ollama, openai, rkllama |
| Scheduler | Always active             | — |
| Ears      | ASR engine                | funasr, whisper, stub (no mic) |
| Mouth     | TTS engine                | edge_tts, piper, text (stdout) |
| Eyes      | Camera + vision model     | opencv, ollama_vision, stub (no camera) |
| Canvas    | Display backend           | web, gui, file |
| Hands     | Always active             | — |
| CLI       | Terminal output style     | simple, rich |
| Chat      | Messaging platform        | telegram, whatsapp (future) |

All modules are always loaded. The backend controls what actually happens:
- `stub` backend: returns "not available" — module is present but has no hardware
- `text` backend (Mouth): prints to stdout instead of audio output
- The brain always publishes to `action.speak`, `command.eyes.capture`, etc. — it doesn't check whether the module has real hardware. The module handles its own limitations.

The bus tells the brain which modules are available. The brain adapts:
- **Chat mode** (no ears, no mouth): Text input via `user.input.text` → Brain → `response.text`
- **Voice mode** (ears + mouth): Ears → Brain → Mouth
- **Full mode** (all modules): Full sensory input, action execution, spoken responses

**Crash recovery**: Non-core modules (Ears, Mouth, Eyes, Canvas, Hands, CLI, Chat) that crash are disabled and the bus publishes `bus.module.disconnected`. The brain detects this and adapts — e.g., if Mouth crashes, the brain stops publishing `action.speak` and relies on text responses. A crashed module can be restarted independently. Brain and Bus crashes are fatal — the process exits.

## Topic Naming Convention

All topics follow `<category>.<target>.<action>` with three categories:

| Category  | Direction    | Meaning                                    |
|-----------|-------------|--------------------------------------------|
| `sensory` | Module → Bus | Data flowing in from the world             |
| `action`  | Bus → Module | Command to do something                    |
| `status`  | Module → Bus | Module state, completion, errors           |
| `response`| Brain → Bus  | Brain's output to the user                 |
| `command` | Bus → Module | Control a module's lifecycle               |

## Module Categories

| Category | Contains | Purpose |
|----------|----------|---------|
| **Core** | Brain, Scheduler | Core intelligence and time awareness. |
| **Sensory** | Ears, Eyes | Input from the world into the bus. |
| **Output** | Mouth, Canvas | Output from the bus to the world. |
| **Action** | Hands | Execute commands and tools. |
| **Interface** | CLI, Chat | Bridges between the bus and external communication channels. |

## Module API Contracts

### 1. Bus API

The bus is the only thing every module depends on. It exposes:

```python
class MessageBus:
    # Publishing — fire and forget
    def publish(topic: str, payload: dict) -> None: ...

    # Subscribing — callback invoked on every matching message
    def subscribe(topic: str, callback: Callable[[str, dict], None]) -> str: ...
    def unsubscribe(subscription_id: str) -> None: ...

    # RPC — ask a question, get an answer (with timeout)
    def request(topic: str, payload: dict, timeout: float = 5.0) -> dict: ...

    # Module lifecycle
    def register(module: "BaseModule") -> None: ...
    def unregister(module_name: str) -> None: ...
    def list_modules() -> dict[str, dict]: ...
    # Returns: {"ears": {"status": "ready", "remote": false}, "mouth": {"status": "ready"}, ...}

    # User input (for chat/text mode)
    def user_input(text: str) -> None: ...
    # Shortcut for publishing "user.input.text" — used by CLI, web UI, etc.
```

**Bus internal topics** (modules never publish these directly):

| Topic | Payload | Purpose |
|-------|---------|---------|
| `bus.module.connected` | `{module_name, remote, capabilities}` | Module came online |
| `bus.module.disconnected` | `{module_name, reason}` | Module went offline |
| `bus.module.health` | `{module_name, health_dict}` | Periodic heartbeat |

---

### 2. Ears Module (Listening) — always loaded

Captures audio from microphone, detects wake words, converts speech to text. If no microphone is available, use backend `stub` — the module is present but returns "no mic available" when the brain tries to listen.

**Subscribes to:**

| Topic | Payload | Effect |
|-------|---------|--------|
| `command.ears.start` | `{}` | Start continuous listening |
| `command.ears.stop` | `{}` | Stop listening entirely |
| `command.ears.pause` | `{duration_ms: int \| null}` | Pause listening (null = until told to resume) |
| `command.ears.resume` | `{}` | Resume after pause |

**Publishes:**

| Topic | Payload | When |
|-------|---------|------|
| `sensory.speech.heard` | `{text: str, confidence: float, language: str, timestamp: str}` | Speech recognized |
| `sensory.speech.hotword` | `{hotword: str, timestamp: str}` | Wake word detected |
| `status.ears.ready` | `{sample_rate: int, device: str}` | Module initialized |
| `status.ears.error` | `{error: str, traceback: str}` | Hardware or ASR failure |

**Behavior:**
- On `command.ears.start`: Open mic, start VAD loop, wait for speech → ASR → publish `sensory.speech.heard`
- On `command.ears.pause`: Keep mic open but stop ASR (e.g., while mouth is speaking to avoid self-triggering)
- Hotword mode: if configured with wake words, only ASR after wake word detected

**Variants:**
- `ears.funasr` — Uses FunASR models (current implementation, good for Chinese)
- `ears.whisper` — Uses OpenAI Whisper (better for multilingual)
- `ears.google` — Uses Google Speech Recognition (simpler, cloud-dependent)

---

### 3. Mouth Module (Speaking) — always loaded

Converts text to speech and plays it through speakers. The mouth handles audio playback regardless of who generates the audio (LLM, TTS engine, pre-recorded). If no speaker is available, use backend `text` to print to stdout. The brain always publishes to `action.speak` — Mouth decides how to render it.

**Subscribes to:**

| Topic | Payload | Effect |
|-------|---------|--------|
| `action.speak` | `{text: str, voice: str \| null, speed: float \| null, interrupt: bool}` | Speak this text |

- `voice`: voice profile name (module-specific)
- `speed`: 0.5 to 2.0, default 1.0
- `interrupt`: if true, stop current speech immediately and start this one

**Publishes:**

| Topic | Payload | When |
|-------|---------|------|
| `status.mouth.started` | `{text: str, timestamp: str}` | Speech begins |
| `status.mouth.done` | `{text: str, timestamp: str, interrupted: bool}` | Speech finishes |
| `status.mouth.ready` | `{engines: [str]}` | Module initialized |
| `status.mouth.error` | `{error: str, traceback: str}` | TTS or playback failure |

**Behavior:**
- Queues multiple `action.speak` requests — plays them in order
- On `interrupt: true`: flush queue, stop current playback, start new speech
- Publishes `status.mouth.started` when playback begins, `status.mouth.done` when complete

**Variants:**
- `mouth.tts` — Uses a TTS engine (espeak, piper, edge-tts, etc.) for real audio output
- `mouth.text` — Prints text to stdout (for chat mode where TTS is unwanted)
- `mouth.silent` — Discards all speak requests (for testing)

---

### 4. Eyes Module (Vision) — always loaded

Captures images from camera, optionally runs vision model for analysis. Use backend `stub` if no camera is available.

**Subscribes to:**

| Topic | Payload | Effect |
|-------|---------|--------|
| `command.eyes.capture` | `{analysis: bool}` | Take a single frame, analyze if true |
| `command.eyes.stream.start` | `{fps: float, analysis: bool}` | Continuous capture at fps |
| `command.eyes.stream.stop` | `{}` | Stop streaming |

**Publishes:**

| Topic | Payload | When |
|-------|---------|------|
| `sensory.vision.frame` | `{image_base64: str \| null, description: str, objects: [str], timestamp: str}` | Frame captured (with or without analysis) |
| `status.eyes.ready` | `{camera: str, resolution: str, vision_model: str \| null}` | Module initialized |
| `status.eyes.error` | `{error: str, traceback: str}` | Camera or model failure |

**RPC endpoint:**

| RPC Topic | Request | Response |
|-----------|---------|----------|
| `eyes.analyze` | `{image_base64: str}` | `{description: str, objects: [str], text_in_image: str \| null}` |

**Behavior:**
- `capture` with `analysis: false`: just returns the frame (base64), no vision model
- `capture` with `analysis: true`: runs vision model, returns description + objects
- `stream`: continuous `sensory.vision.frame` messages at the specified fps
- RPC `eyes.analyze`: used by brain to analyze a specific image

**Variants:**
- `eyes.camera` — Real camera capture (OpenCV, PiCamera, etc.)
- `eyes.screenshot` — Takes screenshots instead of camera (for desktop assistant)
- `eyes.stub` — Returns a dummy frame (for testing)

---

### 5. Brain Module (Reasoning) — the Core

This is the central intelligence. It has an internal thinking loop, not just "input → LLM → output."

#### 5a. Internal Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        BRAIN                                  │
│                                                               │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │
│  │ Perceive │ → │  Reason  │ → │   Plan   │ → │   Act    │  │
│  │          │   │          │   │          │   │          │  │
│  │ filter   │   │ internal │   │ break    │   │ execute  │  │
│  │ sensory  │   │ monolog  │   │ into     │   │ tools    │  │
│  │ input    │   │ + recall │   │ steps    │   │          │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘  │
│        │              │              │              │         │
│        │              │              │              ▼         │
│        │              │              │         ┌──────────┐  │
│        │              │              │         │ Reflect  │  │
│        │              │              │         │          │  │
│        │              │              │         │ enough   │  │
│        │              │              │         │ info?    │  │
│        │              │              │         └────┬─────┘  │
│        │              │              │              │         │
│        │              │              │    ┌─────────┘         │
│        │              │              │    │ no                │
│        │              │              │    ▼                   │
│        │              │              │  loop back to Reason   │
│        │              │              │                        │
│        │              │              │    yes                  │
│        │              │              │    ▼                   │
│        │              │              └── ┌──────────┐         │
│        │              │                  │ Respond  │         │
│        │              │                  │          │         │
│        │              │                  │ formulate│         │
│        │              │                  │ response │         │
│        │              │                  └──────────┘         │
│        │              │                                       │
│        ▼              ▼                                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                    MEMORY LAYER                        │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  │    │
│  │  │ Conversation│  │    Facts     │  │  Knowledge  │  │    │
│  │  │ History     │  │  (markdown)  │  │  Base (RAG) │  │    │
│  │  │ (markdown)  │  │              │  │  (markdown) │  │    │
│  │  └─────────────┘  └──────────────┘  └─────────────┘  │    │
│  │                       │                               │    │
│  │              ┌────────┴────────┐                      │    │
│  │              │  embeddings.db  │  ← vector index      │    │
│  │              │    (SQLite)     │     across all memory │    │
│  │              └─────────────────┘                      │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                    PERSONA                             │    │
│  │  System prompt, behavior rules, language preference   │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

#### 5b. Thinking Loop (7 stages)

```
SENSORY INPUT
     │
     ▼
[1. PERCEIVE] — Filter and classify input
     - Is this speech? Text? Vision? A tool result?
     - Is it addressed to me? (hotword check)
     - Is it noise? → ignore
     - Is it a tool result I was waiting for? → fast-track to Reflect
     │
     ▼
[2. UNDERSTAND] — What is the user really asking?
     - Intent classification (question, command, chat, ...)
     - Disambiguation (if vague, ask)
     - Urgency check (is this time-sensitive?)
     │
     ▼
[3. REASON] — Internal chain of thought (LLM call)
     - "Let me think about this step by step..."
     - What do I already know? (check memory)
     - What do I need to find out? (identify gaps)
     - This is an internal monolog — NOT shown to user
     │
     ▼
[4. PLAN] — Break into actions
     - If simple: direct answer (no tools needed) → jump to Respond
     - If complex: identify tool(s) needed, order of execution
     - If multi-step: create a task plan with dependencies
     │
     ▼
[5. ACT] — Execute tools
     - Call tool(s) via action.execute or command.eyes
     - Wait for results
     │
     ▼
[6. REFLECT] — Did I get what I need?
     - Tool result sufficient? → proceed to Respond
     - Need more info? → loop back to Reason (max 3 loops)
     - Tool failed? → decide: retry, fallback, or tell user
     │
     ▼
[7. RESPOND] — Formulate final response
     - Synthesize findings into natural language
     - Match user's language and style
     - Publish response.text (always) + action.speak (if mouth available)
     - Append turn to today's conversation file (data/memory/conversations/YYYY-MM-DD.md)
     - Generate embedding for the turn → store in embeddings.db
     - Extract and persist any new facts to data/memory/facts/
```

#### 5c. Input/Output Topics

**Subscribes to:**

| Topic | Purpose |
|-------|---------|
| `user.input.text` | Direct text input (CLI, web UI, API) |
| `sensory.speech.heard` | Speech transcribed by ears |
| `sensory.speech.hotword` | Wake word detected — brain enters active listening mode |
| `sensory.vision.frame` | Vision data from eyes |
| `sensory.canvas.click` | User clicked on canvas |
| `sensory.canvas.input` | User typed on canvas |
| `sensory.canvas.draw` | User drew on canvas |
| `schedule.triggered` | Scheduled task time arrived |
| `status.hand.done` | Result of a tool execution |
| `status.hand.error` | Tool execution failed |
| `status.eyes.error` | Vision module error |
| `status.canvas.error` | Canvas error |
| `bus.module.connected` | New module came online |
| `bus.module.disconnected` | Module went offline — adapt behavior |

**Publishes:**

| Topic | Payload | Purpose |
|-------|---------|---------|
| `response.text` | `{text: str, conversation_id: str, thinking: str \| null}` | Final text response (always published) |
| `action.speak` | `{text: str, voice: str \| null, speed: float \| null, interrupt: bool}` | Speak this (only if mouth available) |
| `action.execute` | `{tool: str, params: dict, request_id: str}` | Execute a tool via hands |
| `action.canvas.show` | `{content_type: str, data: str, title: str, ...}` | Display on canvas |
| `action.canvas.generate` | `{prompt: str, style: str \| null, size: str \| null}` | Generate AI image |
| `action.canvas.draw` | `{elements: [...]}` | Draw on canvas |
| `action.canvas.clear` | `{}` | Clear canvas |
| `action.schedule.add` | `{task, time, repeat, description}` | Schedule a task |
| `command.eyes.capture` | `{analysis: bool}` | Request vision input |
| `command.ears.pause` | `{duration_ms: int \| null}` | Pause listening while speaking |

**RPC endpoint:**

| RPC Topic | Request | Response |
|-----------|---------|----------|
| `brain.ask` | `{question: str, context: dict \| null}` | `{answer: str, thinking: str \| null}` |

`brain.ask` is a stateless one-shot — no session, no history. Used by external systems or scheduled tasks.

#### 5d. Memory System

All memory is stored as **markdown files on disk**. Full conversation history is preserved permanently — nothing is discarded. Embeddings power semantic search across all memory. The brain's memory has three tiers:

- **Embeddings engine**: Converts text to vectors for semantic search. Uses the configured LLM backend's embedding endpoint (Ollama, OpenAI) or a dedicated embedding model. This is a brain-internal capability — not a separate module — because embeddings are only meaningful to the brain's memory system. Embeddings are cached in `data/embeddings.db` (SQLite) so they survive restarts and don't need re-computation.

- **Working memory (context window)**: The subset of memory loaded into the LLM context for the current turn. NOT a ring buffer that discards old messages — the full history is always preserved on disk. Working memory is assembled fresh each turn via:
  1. **Recency**: last K messages always included (configurable, default 20)
  2. **Semantic relevance**: embedding search finds related earlier messages across all time
  3. **Facts**: relevant facts from the facts directory
  4. **Knowledge**: relevant chunks from the knowledge base
  When the assembled context exceeds the token budget, the oldest non-essential items are dropped from context (but NEVER from disk).

- **Permanent memory (conversation history)**: Every conversation turn is saved as markdown, organized by date. Nothing is ever deleted or summarized away. This is the source of truth — working memory is just a retrieval view over this data.
  ```
  data/memory/conversations/
  ├── 2026-05-20.md    # One file per day
  ├── 2026-05-21.md    # All turns from that day
  └── 2026-05-22.md    # Appended in real-time during conversation
  ```
  Each file format:
  ```markdown
  # Conversation — 2026-05-22

  ## 14:30:05 | user
  What's the weather tomorrow?

  ## 14:30:08 | assistant
  Tomorrow (May 23) in Taipei: sunny, around 26°C.
  [tools: datetime(r1, 45ms), weather(r2, 350ms)]
  [thinking: User asked about weather, needed date + location...]

  ## 14:35:12 | user
  And what about Friday?
  ...
  ```
  Each turn includes: timestamp, speaker, content, tool calls made, and optional thinking trace. The brain appends to today's file after every response (step 7: RESPOND). A new file is created at midnight.

- **Facts (extracted knowledge)**: Important facts the brain extracts and persists as organized markdown files. The brain writes facts during the REFLECT stage when it learns something worth remembering. Each file is a category:
  ```
  data/memory/facts/
  ├── user_preferences.md   # "User prefers Celsius", "User works at Acme Corp"
  ├── people.md             # "John is user's manager", "Lisa is user's sister"
  ├── projects.md           # "Working on aiassistant — Python, modular architecture"
  └── locations.md          # "Home: Taipei", "Office: Xinyi District"
  ```
  Each fact is stored with an embedding vector (in embeddings.db). Facts can be updated or deleted — the markdown file is the canonical source, embeddings.db is the search index.

- **Knowledge base (RAG)**: Optional directory of reference documents as markdown files. Indexed at startup and on change. The brain chunks documents, generates embeddings, and caches them in embeddings.db. During REASON, it searches for relevant chunks and injects them into the LLM context.
  ```
  data/memory/knowledge/
  ├── python_tips.md        # User's coding reference
  ├── company_policies.md   # Work-related reference
  └── (any .md files)       # Drop in any markdown file, auto-indexed
  ```

**Embeddings database** (`data/embeddings.db`):

SQLite with these tables:
```sql
CREATE TABLE conversation_embeddings (
    id INTEGER PRIMARY KEY,
    date TEXT,          -- "2026-05-22"
    timestamp TEXT,     -- "14:30:08"
    speaker TEXT,       -- "user" | "assistant"
    chunk TEXT,         -- the text content
    embedding BLOB,     -- serialized vector
    tokens INTEGER      -- token count
);

CREATE TABLE fact_embeddings (
    id INTEGER PRIMARY KEY,
    category TEXT,      -- "user_preferences", "people", etc.
    fact TEXT,          -- the fact text
    embedding BLOB,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE knowledge_embeddings (
    id INTEGER PRIMARY KEY,
    source_file TEXT,   -- "python_tips.md"
    chunk_index INTEGER,
    chunk TEXT,
    embedding BLOB
);

CREATE INDEX idx_conv_date ON conversation_embeddings(date);
CREATE INDEX idx_fact_category ON fact_embeddings(category);
```

**Memory flow during thinking:**

```
[REASON stage]
  1. Generate embedding for current query + recent conversation context
  2. Search previous conversations (semantic + recency via embeddings.db)
  3. Search facts (semantic via embeddings.db → load from markdown files)
  4. Search knowledge base (semantic via embeddings.db → load chunks)
  5. Merge results into LLM context as "Relevant memories: ..."
  6. LLM reasons with full context

[RESPOND stage]
  7. Append turn to today's conversation file (data/memory/conversations/YYYY-MM-DD.md)
  8. Generate embedding for the new turn → store in embeddings.db
  9. If facts were learned: update relevant fact file + re-index in embeddings.db
```

**Key design properties:**
- **Markdown is the source of truth**: embeddings.db is a cache/index — it can be rebuilt from the markdown files
- **Full history preservation**: nothing is ever deleted or summarized away; working memory is a retrieval view, not a replacement
- **Human-readable**: all memory is plain markdown — the user can read, edit, or delete files directly
- **Portable**: copying the `data/memory/` directory moves all memory to another machine
- **Searchable without AI**: `grep` works on conversation files; embeddings add semantic search on top

#### 5e. Persona

Defined in config as a system prompt. The brain injects this at the start of every LLM call:
- Assistant's name, personality, tone
- Language preference (English, Chinese, auto-detect)
- Behavior rules (always use tools when possible, never guess dates, etc.)
- Output format preferences (no markdown, plain text, etc.)

---

### 6. Hands Module (Action) — always loaded

Executes commands, API calls, and file operations. Always active — the assistant must be able to do things.

**Subscribes to:**

| Topic | Payload | Effect |
|-------|---------|--------|
| `action.execute` | `{tool: str, params: dict, request_id: str, sandbox: bool}` | Execute a named tool with parameters |

`sandbox`: if true, run in restricted mode (no network, limited paths, timeout).

**Publishes:**

| Topic | Payload | When |
|-------|---------|------|
| `status.hand.done` | `{request_id: str, result: any, duration_ms: float, tool: str}` | Tool execution succeeded |
| `status.hand.error` | `{request_id: str, error: str, tool: str, traceback: str}` | Tool execution failed |
| `status.hands.ready` | `{tools: [str], remote_targets: [str]}` | Module initialized |

**Built-in tools registered by hands:**

| Tool Name | Parameters | Description |
|-----------|-----------|-------------|
| `shell` | `{command: str, cwd: str \| null}` | Execute shell command |
| `web_search` | `{query: str, max_results: int}` | Search the web |
| `web_fetch` | `{url: str}` | Fetch and extract page content |
| `weather` | `{location: str}` | Get current weather |
| `datetime` | `{}` | Get current date/time/timezone |
| `file.read` | `{path: str}` | Read a file |
| `file.write` | `{path: str, content: str}` | Write to a file |

**Behavior:**
- Each tool execution gets a unique `request_id` (generated by brain)
- Results include the `request_id` so the brain can match responses to requests
- Tools have configurable timeouts (default 30s)
- `sandbox: true` restricts: no network, paths limited to safe directories, subprocess timeout 10s
- The hands module is tool-agnostic — new tools are registered by adding a function + schema

**RPC endpoint:**

| RPC Topic | Request | Response |
|-----------|---------|----------|
| `hands.list_tools` | `{}` | `{tools: [{name, description, parameters}]}` |

The brain calls this at startup to discover available tools. Tools are defined only in Hands — the brain caches the schemas for LLM function calling.

**Remote hands:**
When a remote hand connects via WebSocket, it registers with a `remote_target` name. The brain can target it:
```json
{"tool": "shell", "params": {"command": "docker ps"}, "remote_target": "lab-server"}
```
The bus routes the message to the correct remote connection.

---

### 7. Scheduler Module (Clock) — always loaded

Manages time-based tasks — reminders, recurring actions, delayed execution. Always active.

**Subscribes to:**

| Topic | Payload | Effect |
|-------|---------|--------|
| `action.schedule.add` | `{task: str, time: str, repeat: str \| null, description: str}` | Add a scheduled task. `time` is ISO8601. `repeat`: "daily" \| "weekly" \| "hourly" \| null |
| `action.schedule.list` | `{}` | List all pending tasks |
| `action.schedule.delete` | `{id: str}` | Remove a task by ID |

**Publishes:**

| Topic | Payload | When |
|-------|---------|------|
| `schedule.triggered` | `{id: str, task: str, time: str, description: str}` | A scheduled time arrives |
| `status.schedule.added` | `{id: str, task: str, time: str}` | Task successfully added |
| `status.schedule.deleted` | `{id: str}` | Task successfully deleted |
| `status.schedule.list` | `{tasks: [{id, task, time, repeat, description}]}` | Response to list request |
| `status.scheduler.ready` | `{pending_count: int}` | Module initialized |
| `status.scheduler.error` | `{error: str, traceback: str}` | Scheduler failure |

**Behavior:**
- Persists tasks to disk (`data/schedules.json`) — survives restart
- Watches clock every second, publishes `schedule.triggered` when a task's time arrives
- Recurring tasks (`repeat` set) are automatically re-scheduled after triggering
- Brain subscribes to `schedule.triggered` and treats it like user input: "Reminder: [task description]"
- Max 100 pending tasks to prevent abuse

**Why separate from Hands:**
- The scheduler has its own persistence and lifecycle
- Scheduled tasks must survive brain restart (brain may restart during a long-running session)
- The clock is a continuous watcher, not a request-response tool
- Separation of concerns: hands execute NOW, scheduler executes LATER

---

### 8. Canvas Module (Visual Display) — always loaded

The visual output counterpart to Eyes (visual input) and Mouth (audio output). Generates images from text prompts, displays content, and accepts user interaction. Use backend `file` for headless setups. This completes the vision modality: Eyes see, Canvas shows.

**Subscribes to:**

| Topic | Payload | Effect |
|-------|---------|--------|
| `action.canvas.show` | `{content_type: str, data: str, title: str \| null, width: int \| null, height: int \| null}` | Display content. `content_type`: "image" \| "text" \| "diagram" \| "url" \| "html" |
| `action.canvas.generate` | `{prompt: str, style: str \| null, size: str \| null}` | Generate an AI image from text prompt |
| `action.canvas.clear` | `{}` | Clear the canvas |
| `action.canvas.draw` | `{elements: [{type, x, y, data, ...}]}` | Programmatic drawing — lines, shapes, text annotations |
| `action.canvas.update` | `{id: str, content_type: str, data: str}` | Update a specific element by ID |

**Publishes:**

| Topic | Payload | When |
|-------|---------|------|
| `sensory.canvas.click` | `{x: float, y: float, target: str \| null, button: str}` | User clicked on canvas |
| `sensory.canvas.input` | `{text: str, position: {x, y}}` | User typed on canvas |
| `sensory.canvas.draw` | `{elements: [{type, points, ...}]}` | User drew on canvas |
| `status.canvas.ready` | `{backend: str, resolution: str}` | Module initialized |
| `status.canvas.generated` | `{prompt: str, image_path: str, duration_ms: float}` | Image generation complete |
| `status.canvas.error` | `{error: str, traceback: str}` | Display or generation failure |

**Behavior:**
- `show`: display images, text blocks, diagrams, URLs, or raw HTML on the canvas surface
- `generate`: use an AI image model (Stable Diffusion, DALL-E, or local model) to create an image from a text prompt, then display it
- `draw`: programmatic drawing — the brain can compose visual layouts
- Interaction events (`sensory.canvas.*`) allow the user to point at things, draw, or type on the canvas. The brain receives these like any other sensory input.
- Elements have persistent IDs — `update` replaces content in-place

**Variants:**
- `canvas.web` — Serves a web page, user opens in browser. Supports HTML, images, interactive drawing.
- `canvas.gui` — Native window (Tkinter, PyQt). Simpler setup, fewer features.
- `canvas.file` — Outputs to image/HTML files. For headless/scripted use.

**RPC endpoint:**

| RPC Topic | Request | Response |
|-----------|---------|----------|
| `canvas.screenshot` | `{}` | `{image_base64: str, resolution: str}` |

Allows the brain (via Eyes or directly) to capture what's currently on the canvas.

---

### 9. Interface Modules

Interface modules bridge the bus to external communication channels. They all follow the same pattern: publish user input to `user.input.text`, subscribe to `response.text` to send responses back. The assistant's output channels (Mouth for audio, Canvas for visual) are separate — interfaces just move text between the user and the bus.

#### 9a. CLI Module (Terminal)

Reads stdin, prints to stdout. The primary local text interface.

**Subscribes to:** `response.text`, `response.thinking` (verbose mode), `status.*.error`

**Publishes:** `user.input.text` — `{text: str, timestamp: str}`

**Behavior:**
- Displays a prompt (configurable, default `> `)
- Reads one line at a time, publishes to `user.input.text`
- When `response.text` arrives, prints it with the assistant name prefix
- In verbose mode, also prints `response.thinking` (internal monolog)
- Special commands: `/exit`, `/agent <name>`, `/verbose`, `/clear`
- Multi-line input: if line ends with `\`, continue reading

**Variants:** `cli.simple` (basic stdin/stdout), `cli.rich` (colored output via `rich` library)

#### 9b. Chat Module

Same pattern as CLI, but over messaging platforms. Multiple backends can be active simultaneously (e.g., Telegram + WhatsApp). Each backend publishes to `user.input.text` and subscribes to `response.text`.

**Subscribes to:** `response.text`

**Publishes:** `user.input.text` — `{text: str, timestamp: str, channel: str, sender: str}`

**Backends:**
- `chat.telegram` — Telegram Bot API
- `chat.whatsapp` — WhatsApp Business API (future)
- `chat.slack` — Slack bot (future)

Deferred to later phase. Same interface pattern as CLI — just a different transport.

---

## Tools System

### Philosophy: LLM Fills the Form, Code Does the Work

Tools follow a strict hybrid pattern:

```
LLM sees:   tool name + JSON schema (parameters with types and descriptions)
LLM does:   selects tool, fills in parameter values → outputs JSON
System does: validates JSON against schema, calls Python function, returns result
```

The LLM NEVER generates execution code. It only fills out a structured form. The execution is deterministic Python code. This avoids:
- LLM hallucinating incorrect function calls
- Prompt injection via tool output
- Inconsistent behavior across different LLM backends
- The "skill menu" problem — every LLM handles instructions differently

This is the OpenAI function-calling standard. Ollama supports it natively. Every tool follows the same contract.

### Tool Definition

```python
class ToolBase:
    name: str           # e.g., "web_search"
    description: str    # e.g., "Search the web for current information"
    parameters: dict    # JSON Schema for parameters
    # Example:
    # {
    #   "type": "object",
    #   "properties": {
    #     "query": {"type": "string", "description": "Search query"},
    #     "max_results": {"type": "integer", "description": "Max results", "default": 5}
    #   },
    #   "required": ["query"]
    # }

    def execute(self, **kwargs) -> Any:
        """Deterministic Python code. No LLM involved."""
        ...
```

### Tool Lifecycle

```
STARTUP
  │
  ▼
[Hands] loads all ToolBase subclasses from builtin_tools/
  │ publishes status.hands.ready {tools: [{name, description, parameters}, ...], remote_targets: []}
  │
  ▼
[Brain] receives tool list → builds LLM function-calling format schemas
  │ stores in internal registry: {tool_name → schema}
  │
  ▼
  READY — brain can now use tools in LLM calls

RUNTIME (per request)
  │
  ▼
[Brain] PLAN stage → decides tools might be needed
  │ includes tool schemas in LLM request (OpenAI function-calling format)
  │
  ▼
[LLM] returns one of:
  - text response (no tool needed) → Brain jumps to RESPOND
  - function_call {name: "web_search", arguments: {query: "..."}}
  │
  ▼
[Brain] validates function_call against tool schema → publishes:
  │ action.execute {tool: "web_search", params: {query: "..."}, request_id: "r1"}
  │
  ▼
[Hands] looks up tool by name → calls tool.execute(**params) → publishes:
  │ status.hand.done {request_id: "r1", result: "...", duration_ms: 350}
  │
  ▼
[Brain] REFLECT → incorporates result into next reasoning step
  │ if more tools needed → loops back to PLAN/ACT
  │ if done → RESPOND
```

Key points:
- **Tools are defined in ONE place**: Hands. Both schema and implementation live together in the same file.
- **Brain discovers tools at startup**: via `status.hands.ready` payload, or by calling RPC `hands.list_tools` if brain starts after hands.
- **Brain never executes tools**: it only passes `{tool, params}` to Hands. Execution is always deterministic Python code.
- **Adding a tool**: create a new file in `builtin_tools/`, define the class, restart. Brain discovers it automatically.

### Tool Organization

Tools live in directories — not a single file. Hands scans directories, finds all `ToolBase` subclasses, loads them.

```
hands/
├── builtin_tools/           # Built-in — always loaded
│   ├── __init__.py
│   ├── base.py              # ToolBase
│   ├── shell.py             # One tool per file
│   ├── websearch.py
│   ├── webfetch.py
│   ├── browser.py
│   ├── weather.py
│   ├── datetime_tool.py
│   ├── file_ops.py
│   ├── email.py             # Send/receive email
│   └── calendar.py          # Google Calendar / CalDAV
│
├── external_tools/          # User-installed tools — loaded if path configured
│   └── (third-party tool packages)
│
└── skills/                  # Composed tool sequences
    ├── __init__.py
    ├── base.py              # SkillBase (extends ToolBase)
    ├── research.py          # web_search → web_fetch → summarize → save
    └── daily_briefing.py    # datetime + weather + calendar.list + news headlines
```

**External tools** — configurable paths. Hands scans all configured directories:

```yaml
hands:
  tool_paths:
    - "./modules/hands/builtin_tools"
    - "./modules/hands/skills"
    - "/home/user/.aiassistant/tools"    # user-installed tools
    - "./external/aiassistant-tools"      # project-specific tools
```

Any directory with `ToolBase` subclasses gets loaded. Third-party tools can be installed via pip, git clone, or symlink — Hands doesn't care how the files got there.

### Skills

A skill is a tool that orchestrates other tools. Same contract as a tool (`name`, `description`, `parameters`, `execute`), but internally it chains multiple tool calls. The LLM sees skills and tools identically — both are just functions it can call.

```
Tool:  "web_search" → single API call, returns results
Skill: "research_topic" → chains web_search + web_fetch + summarize + file.write
```

Example:
```python
class ResearchSkill(SkillBase):
    name = "research_topic"
    description = "Research a topic thoroughly: search, fetch sources, summarize, save findings."
    parameters = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic to research"},
            "depth": {"type": "string", "enum": ["brief", "detailed"], "description": "Research depth"},
            "output_file": {"type": "string", "description": "File to save findings to"}
        },
        "required": ["topic"]
    }

    def execute(self, topic, depth="brief", output_file=None):
        # Step 1: Search
        results = self.call_tool("web_search", query=topic, max_results=5 if depth == "brief" else 10)

        # Step 2: Fetch top sources
        sources = []
        for r in results[:3]:
            content = self.call_tool("web_fetch", url=r["url"])
            sources.append(content)

        # Step 3: Summarize (calls LLM via brain RPC)
        summary = self.call_llm(f"Summarize these sources about {topic}:", context=sources)

        # Step 4: Save if requested
        if output_file:
            self.call_tool("file.write", path=output_file, content=summary)

        return summary
```

Skills differ from tools in that they can call other tools and the LLM internally:
- `self.call_tool(name, **params)` — publishes `action.execute` and waits for `status.hand.done`, returns result
- `self.call_llm(prompt, context)` — calls `brain.ask` RPC for reasoning/subtasks

This means skills are "program + LLM" — the program defines the workflow, the LLM fills in the details where needed. The LLM only sees the skill as a function signature; it never sees the internal implementation.

### Tool Lifecycle

```
STARTUP
  │
  ▼
[Hands] scans tool_paths → finds all ToolBase & SkillBase subclasses
  │ loads them into registry
  │ publishes status.hands.ready {tools: [{name, description, parameters}, ...], remote_targets: []}
  │
  ▼
[Brain] receives tool list → builds LLM function-calling format schemas
  │ stores in internal cache: {tool_name → schema}
  │
  ▼
  READY — brain can now present tools + skills to LLM

RUNTIME (per request)
  │
  ▼
[Brain] PLAN stage → includes tool schemas in LLM request
  │
  ▼
[LLM] returns one of:
  - text response → Brain jumps to RESPOND
  - function_call {name: "web_search", arguments: {query: "..."}}
  - function_call {name: "research_topic", arguments: {topic: "AI agents", depth: "detailed"}}
  │
  ▼
[Brain] validates → publishes action.execute {tool, params, request_id}
  │
  ▼
[Hands] looks up tool/skill → calls execute(**params)
  │ if tool: runs directly, returns result
  │ if skill: runs composed workflow (may call other tools + LLM), returns result
  │ publishes status.hand.done {request_id, result, duration_ms}
  │
  ▼
[Brain] REFLECT → incorporate result → loop or RESPOND
```

Key points:
- **Tools and skills use the same interface** — the LLM can't tell them apart
- **One file per tool/skill** — no monolithic tool registry
- **External tools via config paths** — install anywhere, add the path, restart
- **Skills compose tools + LLM calls** — program defines the workflow, LLM fills details

---

## Data Flow Diagrams

### Flow A: Voice mode (ears + mouth + brain)

```
USER SPEAKS
  │
  ▼
[Ears] wake word "hey assistant" → publish sensory.speech.hotword
  │
  ▼
[Brain] enters active mode → command.ears.start (continuous listening)
  │
  ▼
USER: "What's the weather tomorrow?"
  │
  ▼
[Ears] ASR → publish sensory.speech.heard {text: "what's the weather tomorrow", confidence: 0.95}
  │
  ▼
[Brain] PERCEIVE → UNDERSTAND → REASON (internal: "user wants weather, I need date+location")
  │
  ├─ PLAN: need CurrentDateTimeAPI + WeatherAPI
  │
  ├─ ACT: publish action.execute {tool: "datetime", params: {}, request_id: "r1"}
  │       │
  │       ▼
  │       [Hands] execute → publish status.hand.done {request_id: "r1", result: "2026-05-21T14:30:00+08:00"}
  │       │
  │       ▼
  │       [Brain] REFLECT → have date, still need weather
  │
  ├─ ACT: publish action.execute {tool: "weather", params: {location: "Taipei"}, request_id: "r2"}
  │       │
  │       ▼
  │       [Hands] execute → publish status.hand.done {request_id: "r2", result: "sunny, 26°C"}
  │       │
  │       ▼
  │       [Brain] REFLECT → all info gathered
  │
  └─ RESPOND: "Tomorrow (May 22) in Taipei: sunny, around 26°C."
       │
       ├─ publish response.text {text: "...", conversation_id: "c42"}
       └─ publish action.speak {text: "Tomorrow May 22 in Taipei: sunny, around 26 degrees."}
            │
            ▼
       [Mouth] TTS → audio output → publish status.mouth.done
```

### Flow B: Chat mode (brain only, no ears/mouth)

```
USER TYPES: "What's 15 * 23?"
  │ (CLI or web UI calls bus.user_input("What's 15 * 23?"))
  │
  ▼
[Bus] publish user.input.text {text: "What's 15 * 23?"}
  │
  ▼
[Brain] PERCEIVE → UNDERSTAND (simple math question) → REASON (no tools needed)
  │
  └─ RESPOND: "15 times 23 equals 345."
       │
       ├─ publish response.text {text: "15 times 23 equals 345.", conversation_id: "c43"}
       └─ action.speak NOT published (no mouth registered)
            │
            ▼
       [CLI/UI] receives response.text → displays to user
```

### Flow C: Vision question (ears + eyes + brain + mouth)

```
USER: "What do you see?"
  │
  [Ears] → sensory.speech.heard
  ▼
[Brain] PERCEIVE → UNDERSTAND (visual question) → REASON ("I need to look")
  │
  ├─ ACT: publish command.eyes.capture {analysis: true}
  │       │
  │       ▼
  │       [Eyes] capture frame → run vision model
  │       │ publish sensory.vision.frame {description: "a person at a desk with a laptop and coffee mug"}
  │       │
  │       ▼
  │       [Brain] REFLECT → have visual context
  │
  └─ RESPOND: "I see you at your desk with a laptop and a coffee mug."
       │
       ├─ publish response.text {...}
       └─ publish action.speak {...}
```

### Flow D: Error — module unavailable

```
[Brain] decides it needs to see something
  │ publish command.eyes.capture {analysis: true}
  │
  ▼
[Bus] no subscriber for command.eyes.capture → wait for timeout (5s)
  │ publish bus.error {topic: "command.eyes.capture", error: "no_subscriber", timeout: 5.0}
  │
  ▼
[Brain] REFLECT → eyes unavailable → adapt
  │
  └─ RESPOND: "I'd like to look, but my vision module isn't connected right now."
```

### Flow E: Scheduled reminder

```
USER: "Remind me to check email at 3pm"
  │
  [Ears or text input] → Brain
  ▼
[Brain] UNDERSTAND → PLAN: need to schedule this
  │
  ├─ ACT: publish action.schedule.add {
  │     task: "Remind user to check email",
  │     time: "2026-05-21T15:00:00",
  │     repeat: null,
  │     description: "User asked to be reminded to check email"
  │   }
  │       │
  │       ▼
  │       [Scheduler] persist → publish status.schedule.added {id: "sched_42", ...}
  │       │
  │       ▼
  │       [Brain] REFLECT → task scheduled
  │
  └─ RESPOND: "I'll remind you to check email at 3pm."
       │
       └─ publish response.text + action.speak

  ... time passes ...

  3:00 PM ── [Scheduler] clock triggers
  │ publish schedule.triggered {id: "sched_42", task: "Remind user to check email", ...}
  │
  ▼
  [Brain] PERCEIVE → this is a scheduled trigger → UNDERSTAND → RESPOND
  │
  └─ "This is your 3pm reminder: check your email."
       │
       ├─ publish response.text {...}
       └─ publish action.speak {text: "This is your 3pm reminder: check your email."}
```

### Flow F: Image generation and interaction

```
USER: "Draw a picture of a cat wearing a spacesuit"
  │
  [Ears or text input] → Brain
  ▼
[Brain] UNDERSTAND → user wants image generation → PLAN: need Canvas
  │
  ├─ ACT: publish action.canvas.generate {prompt: "a cat wearing a spacesuit, digital art", style: null, size: "1024x1024"}
  │       │
  │       ▼
  │       [Canvas] call image model → generate image → publish status.canvas.generated {image_path: "...", duration_ms: 3500}
  │       │
  │       ▼
  │       [Brain] REFLECT → image ready, show it
  │
  └─ RESPOND: "Here's your space cat."
       │
       ├─ publish action.canvas.show {content_type: "image", data: "/output/cat_spacesuit.png", title: "Space Cat"}
       ├─ publish response.text {text: "Here's your space cat."}
       └─ publish action.speak {text: "Here's your space cat."}

  ... user clicks on the canvas ...

  [Canvas] → publish sensory.canvas.click {x: 450, y: 320, target: "cat_spacesuit.png", button: "left"}
  │
  ▼
  [Brain] PERCEIVE → "user clicked on the space cat image" → UNDERSTAND → RESPOND
  │
  └─ "You clicked on the cat's helmet area. Want me to zoom in or add something?"
```

---

## Directory Structure

```
aiassistant/
├── bus/                        # Message bus — the nervous system
│   ├── __init__.py
│   ├── bus.py                  # MessageBus class — pub/sub + RPC router
│   ├── registry.py             # Module registry — tracks connected modules
│   ├── remote.py               # WebSocket server for remote module connections
│   └── errors.py               # Bus-level error types
│
├── modules/                    # Body parts — each is a plugin
│   ├── __init__.py
│   ├── base.py                 # BaseModule — lifecycle interface
│   │
│   ├── ears/                   # Listening
│   │   ├── __init__.py
│   │   ├── ears.py             # EarsModule(BaseModule) — mic + VAD + ASR
│   │   └── asr_backends/       # Pluggable ASR engines
│   │       ├── __init__.py
│   │       ├── base.py         # ASRBackend interface
│   │       ├── funasr.py
│   │       └── whisper.py
│   │
│   ├── mouth/                  # Speaking
│   │   ├── __init__.py
│   │   ├── mouth.py            # MouthModule(BaseModule) — TTS + playback
│   │   └── tts_backends/       # Pluggable TTS engines
│   │       ├── __init__.py
│   │       ├── base.py         # TTSBackend interface
│   │       ├── edge_tts.py
│   │       ├── piper.py
│   │       └── text.py         # Text-only output (no audio)
│   │
│   ├── eyes/                   # Vision
│   │   ├── __init__.py
│   │   ├── eyes.py             # EyesModule(BaseModule) — camera + vision model
│   │   └── vision_backends/    # Pluggable vision engines
│   │       ├── __init__.py
│   │       ├── base.py         # VisionBackend interface
│   │       ├── ollama_vision.py
│   │       └── opencv.py       # Raw camera capture, no ML
│   │
│   ├── brain/                  # Reasoning
│   │   ├── __init__.py
│   │   ├── brain.py            # BrainModule(BaseModule) — the thinking loop
│   │   ├── perceive.py         # Input filter + classifier
│   │   ├── understand.py       # Intent + disambiguation
│   │   ├── reason.py           # Internal chain-of-thought
│   │   ├── plan.py             # Task decomposition
│   │   ├── reflect.py          # Evaluate tool results
│   │   ├── respond.py          # Final response formulation
│   │   ├── memory.py           # Memory: conversation history, long-term facts, RAG
│   │   ├── embeddings.py       # Text → vector via LLM embedding endpoint
│   │   ├── persona.py          # System prompt + behavior rules
│   │   └── tools.py            # Tool schema cache — discovered from Hands at startup
│   │
│   ├── hands/                  # Action (immediate execution)
│   │   ├── __init__.py
│   │   ├── hands.py            # HandsModule(BaseModule) — tool executor
│   │   ├── sandbox.py          # Restricted execution environment
│   │   ├── builtin_tools/      # Built-in tools — one file per tool
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # ToolBase interface
│   │   │   ├── shell.py
│   │   │   ├── websearch.py
│   │   │   ├── webfetch.py
│   │   │   ├── browser.py      # Playwright-based browser automation
│   │   │   ├── weather.py
│   │   │   ├── datetime_tool.py
│   │   │   ├── file_ops.py
│   │   │   ├── email.py        # Email send/receive
│   │   │   └── calendar.py     # Calendar integration
│   │   ├── external_tools/     # User-installed tools (gitignored)
│   │   └── skills/             # Composed tool sequences
│   │       ├── __init__.py
│   │       ├── base.py         # SkillBase (extends ToolBase, adds call_tool + call_llm)
│   │       ├── research.py
│   │       └── daily_briefing.py
│   │
│   ├── scheduler/              # Time-based task scheduler (REQUIRED)
│   │   ├── __init__.py
│   │   ├── scheduler.py        # SchedulerModule(BaseModule) — clock watcher
│   │   └── storage.py          # Persist schedules to disk
│   │
│   ├── canvas/                 # Visual display and image generation
│   │   ├── __init__.py
│   │   ├── canvas.py           # CanvasModule(BaseModule) — display + interaction
│   │   ├── renderer.py         # Image generation (Stable Diffusion, DALL-E, etc.)
│   │   └── backends/           # Display backends
│   │       ├── __init__.py
│   │       ├── base.py         # CanvasBackend interface
│   │       ├── web.py          # Web-based canvas (browser)
│   │       ├── gui.py          # Native GUI window
│   │       └── file.py         # File output (headless)
│   │
│   ├── cli/                    # Terminal interface
│   │   ├── __init__.py
│   │   └── cli.py              # CLIModule(BaseModule) — stdin/stdout bridge
│   │
│   └── chat/                   # Messaging platform interfaces (future)
│       ├── __init__.py
│       ├── chat.py             # ChatModule(BaseModule) — same pattern as CLI
│       └── backends/
│           ├── __init__.py
│           ├── base.py
│           └── telegram.py
│
├── llm/                        # LLM backends (any OpenAI-compatible API)
│   ├── __init__.py
│   ├── base.py                 # LLMBackend interface
│   ├── ollama.py               # Ollama backend
│   ├── openai.py               # OpenAI / compatible API backend
│   └── rkllama.py              # Rockchip NPU backend
│
├── config.yaml                 # Single config: modules, LLM, bus, persona
├── main.py                     # Entry point: start bus, load config, start modules
├── main_remote.py              # Entry point for remote modules (connect to remote bus)
├── requirements.txt
├── .gitignore
│
├── data/                       # Runtime data — created on first run, gitignored
│   ├── memory/
│   │   ├── conversations/      # Full chat history by date (YYYY-MM-DD.md)
│   │   ├── facts/              # Extracted facts (user_preferences.md, people.md, ...)
│   │   └── knowledge/          # Reference documents for RAG (any .md files)
│   ├── embeddings.db           # SQLite vector index across all memory
│   ├── schedules.json          # Persisted scheduled tasks
│   └── workspace/              # Default safe path for file operations
```

---

## Configuration

### config.yaml

```yaml
# Bus settings
bus:
  websocket_port: 8765
  remote_auth_token: ""  # empty = no auth for remote connections

# Brain
brain:
  persona: |
    You are a smart, detail-oriented assistant. Always think step by step.
    Match the user's language. Be concise. Use tools when available.
  llm:
    provider: ollama        # ollama | openai | rkllama
    model: qwen3:1.7b
    url: http://127.0.0.1:11434
    api_key: ""             # only needed for openai
    max_tokens: 4096
    temperature: 0.7
  memory:
    conversations_path: "./data/memory/conversations"
    facts_path: "./data/memory/facts"
    knowledge_path: "./data/memory/knowledge"
    embeddings_db: "./data/embeddings.db"
    context_max_tokens: 4096      # max tokens for working memory context window
    context_recent_messages: 20   # last K messages always included
  embeddings:
    provider: same          # same | ollama | openai
    model: ""               # empty = provider default
    url: ""                 # empty = same as brain's llm url
    batch_size: 10          # messages per embedding batch
  thinking:
    max_reflect_loops: 3

# Scheduler
scheduler:
  storage_path: "./data/schedules.json"
  max_pending: 100

# All modules are always loaded — backend controls behavior
ears:
  backend: stub             # funasr | whisper | stub
  device_index: 5
  sample_rate: 48000
  hotwords: ["hey assistant", "hello"]
  silence_timeout: 20

mouth:
  backend: text             # edge_tts | piper | text
  voice: "en-US-AriaNeural"
  speed: 1.0

eyes:
  backend: stub             # opencv | ollama_vision | stub
  camera_index: 0
  vision_model: null        # null = no analysis, "ollama_vision" = use LLM vision
  vision_model_url: ""

hands:
  tool_paths:
    - "./modules/hands/builtin_tools"
    - "./modules/hands/skills"
    # - "/path/to/external/tools"   # add external tool paths here
  sandbox_default: false
  command_timeout: 30
  safe_paths: ["./workspace", "/tmp/aiassistant"]

canvas:
  backend: file             # web | gui | file
  web_port: 8081
  image_model: null         # null = no generation, "sd_local" | "dalle"
  image_model_url: ""
  default_size: "1024x1024"

# Interface modules
cli:
  backend: simple           # simple | rich
  prompt: "> "
  verbose: false

chat:
  backends: []              # ["telegram"] — empty = no chat backends active
  telegram_token: ""
  telegram_allowed_users: []
```

### Example configs for different modes

**Chat mode** (terminal text only):
```yaml
ears: {backend: stub}
mouth: {backend: text}
eyes: {backend: stub}
canvas: {backend: file}
cli: {backend: simple}
```

**Voice mode** (speech in/out):
```yaml
ears: {backend: funasr}
mouth: {backend: edge_tts}
eyes: {backend: stub}
canvas: {backend: file}
cli: {backend: simple}
```

**Full mode** (all hardware active):
```yaml
ears: {backend: funasr}
mouth: {backend: edge_tts}
eyes: {backend: opencv, vision_model: ollama_vision}
canvas: {backend: web, image_model: sd_local}
cli: {backend: rich, verbose: true}
chat: {backends: ["telegram"]}
```

---

## Design Decisions

- **Decision**: Message bus as central spine vs. direct module-to-module calls
  - **Why**: Direct calls mean modules must know about each other. A bus means modules only know about the bus. Adding a new module requires zero changes to existing modules. Remote becomes transparent — the bus handles routing, modules don't care if a peer is local or remote.
  - **Alternatives considered**: Direct imports (tight coupling, no remote), FastAPI endpoints per module (each module needs a server, complex discovery).

- **Decision**: Pub/sub topics as dot-separated strings vs. typed message objects
  - **Why**: String topics are simple, debuggable, and language-agnostic. Remote modules in any language can participate. No serialization magic.
  - **Alternatives considered**: Python dataclass objects with type hints (not cross-language), gRPC protobufs (heavy for internal messaging).

- **Decision**: Brain has internal thinking loop (Perceive → Understand → Reason → Plan → Act → Reflect → Respond) vs. single LLM call
  - **Why**: A single LLM call works for simple Q&A but fails on multi-step tasks. An explicit loop lets the brain: (a) break complex tasks into steps, (b) verify tool results, (c) retry on failure, (d) show reasoning for transparency. This is the ReAct/chain-of-thought pattern proven in agent research.
  - **Alternatives considered**: Single LLM call with function calling (works for simple cases but can't self-correct), hardcoded if-else decision tree (brittle, can't handle novel situations).

- **Decision**: LLM function-calling format for tool definitions vs. custom tool schema
  - **Why**: OpenAI function-calling format is the de facto standard. Ollama supports it. Adding a new tool means defining a JSON schema — zero brain code changes.
  - **Alternatives considered**: Regex parsing of LLM output (brittle, the current approach), custom tool schema (reinventing the wheel).

- **Decision**: Modules are independent processes vs. threads in one process
  - **Why**: Processes can run on different machines, restart independently, no GIL contention, can be written in different languages. A remote hand on a Raspberry Pi is the same code as a local hand.
  - **Alternatives considered**: Threads (simpler but no remote, GIL-bound), multiprocessing (complex state sharing).

- **Decision**: WebSocket for remote modules vs. gRPC vs. plain TCP
  - **Why**: Simple, firewall-friendly, browser-compatible (future web UI), good Python library support. JSON over WebSocket is trivial to debug.
  - **Alternatives considered**: gRPC (protobuf overhead, harder to debug), plain TCP (reinventing framing), Redis pub/sub (extra dependency).

- **Decision**: Every module publishes health/status, errors are explicit topics vs. exception propagation
  - **Why**: In a distributed system, exceptions can't cross process boundaries. Explicit error topics mean the brain can react to failures gracefully (retry, fallback, inform user).
  - **Alternatives considered**: Exception propagation (only works in-process), heartbeat-only (too coarse — knows module is alive but not why something failed).

- **Decision**: Module variants via backend plugins (e.g., `ears.funasr` vs `ears.whisper`) vs. separate modules
  - **Why**: Same module role, different implementation. The bus contract is identical — only the internal processing differs. This keeps the topic namespace clean and the brain doesn't care which ASR backend is used.
  - **Alternatives considered**: Separate modules for each variant (explodes the topic namespace, brain needs to know about specific modules).

- **Decision**: Scheduler is a separate module vs. a hand tool
  - **Why**: The scheduler has its own persistence and independent lifecycle. Scheduled tasks must survive brain restart — if the brain restarts during a session, "remind me at 3pm" should still fire. Separating schedule from hands also separates two concerns: immediate execution (hands) vs. delayed execution (scheduler).
  - **Alternatives considered**: Schedule as a hand tool (tight coupling, schedule lost on brain restart), schedule inside the brain (violates single-responsibility, brain shouldn't manage a clock).

- **Decision**: Embeddings engine inside the brain vs. separate embedding module
  - **Why**: Embeddings are only meaningful to the brain's memory system — they power semantic search for conversation history, long-term facts, and knowledge base retrieval. The embedding model is typically the same LLM provider already configured. A separate module would add bus overhead for a pure function call (text → vector). If other modules need embeddings later, the brain can expose it as an RPC endpoint.
  - **Alternatives considered**: Separate embedding module (unnecessary bus overhead, no independent lifecycle benefit), dedicated vector database (premature optimization — JSON files with in-memory vector index are sufficient for personal assistant scale).

- **Decision**: Canvas as a separate visual output module vs. merging into Eyes (bidirectional)
  - **Why**: Eyes and Canvas have opposite data flows and different hardware requirements. Eyes reads from camera, Canvas writes to display. Merging them creates a confusing "do everything vision" module that violates single-responsibility. Canvas is to Eyes what Mouth is to Ears — output vs. input for the same modality. This also means each module is simpler and independently deployable.
  - **Alternatives considered**: Merge into Eyes (confusing API, mixed concerns), no Canvas at all (no visual output — can't generate images or display content), add show/generate as tools in Hands (wrong — Hands executes, doesn't display).

- **Decision**: Scheduler is required, not optional
  - **Why**: An assistant without the ability to remind, schedule, or handle time-based tasks is not a real assistant. Even in minimal chat mode, users expect "remind me in 5 minutes" to work. The scheduler has lightweight runtime cost (a clock watcher thread) and minimal disk footprint.
  - **Alternatives considered**: Scheduler as optional (led to confusing UX where scheduling commands silently fail).

- **Decision**: Skills are tools that compose other tools (same interface) vs. prompt-based "skill menu" system
  - **Why**: In a prompt-based skill system, the LLM receives a text description of a workflow and must interpret it — every LLM backend behaves differently. With the tool-interface approach, a skill is just another function with a JSON Schema. The LLM picks it and fills parameters, same as any tool. The skill's `execute()` method runs a deterministic workflow internally (chaining tool calls and LLM sub-tasks). The LLM never sees the workflow — it just sees "research_topic" as an available function. This means skills work identically across all LLM backends.
  - **Alternatives considered**: Prompt-based skills (the "menu" problem — every LLM interprets instructions differently, brittle), LLM-generated workflows (unpredictable, can't guarantee correctness), separate skill registry in the brain (duplication — skills should be defined alongside tools in Hands).

- **Decision**: All modules always loaded, backend controls behavior vs. enable/disable in config
  - **Why**: The brain should always be able to publish `action.speak`, `command.eyes.capture`, etc. without checking if a module is "enabled." The module handles its own limitations — Mouth with `backend: text` prints to stdout instead of audio, Eyes with `backend: stub` returns "no camera." This means the brain has a consistent mental model: "I can always speak, listen, see, show, and act — the modules handle the details." It also eliminates the config complexity of toggling modules on/off.
  - **Alternatives considered**: Enable/disable flags per module (brain must check availability before every action, config gets complicated, inconsistent UX when a module is missing vs. present but limited).

- **Decision**: Chat module with pluggable backends vs. separate Telegram/WhatsApp/Slack modules
  - **Why**: All messaging platforms do the same thing — publish `user.input.text`, subscribe to `response.text`. The transport differs but the bus contract is identical. A single Chat module with backends means adding WhatsApp is 100 lines, not a new module.
  - **Alternatives considered**: Separate module per platform (code duplication, topic namespace pollution), dedicated "notifier" module (wrong abstraction — notification is just response.text over a different transport).

- **Decision**: Markdown files as the memory storage format vs. JSON/document database
  - **Why**: Markdown is human-readable, editable with any text editor, and grep-friendly. The user can browse, edit, or delete memories directly. Full conversation history in markdown means no data is locked inside a binary format or database. Embeddings.db (SQLite) is a search cache that can be rebuilt from the markdown files at any time — markdown is the source of truth, SQLite is the index. This also makes memory portable: copy the `data/memory/` directory to migrate everything.
  - **Alternatives considered**: JSON files (harder to read/edit manually, diff-unfriendly), document DB like MongoDB (extra dependency, not human-browsable), pure SQLite for all memory (can't open in a text editor, harder to inspect).

- **Decision**: Non-core modules crash in isolation, Brain and Bus crashes are fatal
  - **Why**: Ears, Mouth, Eyes, Canvas, Hands, CLI, Chat are non-critical — if one crashes, the assistant can continue with reduced capabilities. The bus detects module disconnection, publishes `bus.module.disconnected`, and the brain adapts (e.g., Mouth crashed → stop publishing `action.speak`, respond text-only). The crashed module can be restarted independently. If Brain or Bus crashes, the assistant cannot function — these are fatal and the process exits. This follows the "always loaded, backend varies" philosophy: a crashed module behaves like a `stub` backend until restarted.
  - **Alternatives considered**: Restart everything on any crash (unnecessary — a camera glitch shouldn't kill the whole assistant), silently ignore crashes (user doesn't know capabilities are degraded).

---

## Module Base Interface

```python
from abc import ABC, abstractmethod

class BaseModule(ABC):
    module_name: str          # "ears" | "mouth" | "eyes" | "brain" | "hands" | "scheduler" | "canvas" | "cli" | "chat"

    def __init__(self, bus: "MessageBus", config: dict):
        self.bus = bus
        self.config = config

    @abstractmethod
    async def setup(self) -> bool:
        """Initialize hardware, load models, validate config.
        Return True if ready, False if setup failed."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Begin operation. Subscribe to bus topics, start loops."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown. Unsubscribe, close hardware, flush buffers."""
        ...

    @abstractmethod
    async def health(self) -> dict:
        """Return health status. Called periodically by bus.
        Format: {"status": "ok"|"degraded"|"error", "details": {...}}"""
        ...

    async def register(self) -> None:
        """Register with the bus. Called by main after setup().
        Default implementation — override if needed."""
        self.bus.register(self)
```

Modules never import each other. The bus is the only shared dependency.
