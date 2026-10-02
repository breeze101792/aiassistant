# Payload and Config Schemas

Field-level schemas for bus payloads, the config file, and the frozen memory
format. Protocol semantics live in [protocols.md](protocols.md); the orb API
sequence lives in [api.md](api.md).

Status legend: `as-built` reflects shipped code · `new` is the target · `unverified`
is a claim no test or source confirms yet.

---

## Bus payloads

### `user.input.text`

**Status:** new fields, as-built base (`bus/bus.py:127-134`).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | str | yes | The user's input |
| `timestamp` | str ISO 8601 UTC | yes | As-built `_now_iso` (`bus/bus.py:137-139`) |
| `channel` | enum `voice` \| `orb` \| `console` \| `schedule` \| `messaging` | yes | As-built default `cli` (`bus/bus.py:127`) is renamed to `console` |
| `sender` | str | yes | As-built default `user`; a messaging backend sets the platform sender |
| `source` | str \| null | no | Origin detail (e.g. a device or backend name). **New field.** |

### `agent.delta`

**Status:** new.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | `"text"` \| `"thinking"` | yes | Maps from `TurnEvent` `text_delta` / `thinking_delta` |
| `text` | str | yes | The **delta fragment only** |
| `index` | int | yes | Monotonic per turn, starts at 0, increments by 1 |

**DELTA-ONLY, with a monotonic `index`.** This payload is **never** the growing
accumulator. Sending the accumulator at 20 Hz makes the byte cost grow
quadratically over a turn. The orb accumulates fragments by `index`; a gap in
`index` is the signal to request a snapshot. `agent.final` is authoritative and
replaces the assembled text (`features/orb-ui.md:48-52`).

### `agent.final`

**Status:** new. Supersedes as-built `response.text` (`brain/brain.py:371`).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | str | yes | Authoritative final text (`text_final`) |
| `session_id` | str | yes | The session this turn belongs to |
| `usage` | object \| null | no | `{input, output, total, cost}` when the harness reports it |

### `agent.turn.error`

**Status:** new.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | str | yes | Human-readable error |
| `class` | enum `config` \| `audio` \| `harness` \| `tool` \| `memory` | yes | Error classification (REQ-ERR-001) |
| `hint` | str | yes | **Actionable recovery hint** (REQ-ERR-001). Never empty; when nothing better exists, use the next step from `flows.md` (g). |
| `code` | str \| null | no | The internal code, e.g. `ERR-HARNESS-DEAD`. Useful for logs; the UI keys off `class`. |

#### Harness code → error class mapping

The harness reports internal codes (`ERR-PROVIDER-*`, `ERR-HARNESS-*`); the orb
keys its overlay off the five-value `class` enum. This table is the single
mapping, so no consumer guesses.

| Internal code | `class` | `hint` |
| --- | --- | --- |
| `ERR-HARNESS-SPAWN` | `harness` | "The harness could not start. Check the log and the `agent.harness` value." |
| `ERR-HARNESS-DEAD` | `harness` | "The harness stopped. It will restart; if this repeats, check the log and switch harness." |
| `ERR-HARNESS-PROTOCOL` | `harness` | "The harness sent an unusable response. Try the turn again." |
| `ERR-HARNESS-TIMEOUT`, `ERR-AGENT-TURN-TIMEOUT` | `harness` | "The harness did not respond in time. Retry, or raise `conversation.turn_timeout_s`." |
| `ERR-PROVIDER-UNAVAILABLE` | `harness` | "The model provider is unreachable. Check that it is running, then retry." |
| `ERR-PROVIDER-AUTH` | `config` | "The provider rejected the credential. Set it in the environment (REQ-CFG-005)." |
| `ERR-PROVIDER-MODEL` | `config` | "The model is not available. Pull it, or set `agent.llm.model`." |
| `ERR-PROVIDER-TIMEOUT` | `harness` | "The model did not respond in time. Retry." |
| `ERR-TOOL-NOT-FOUND`, `ERR-TOOL-DENIED`, `ERR-TOOL-FAILED`, `ERR-AGENT-TOOL-TIMEOUT` | `tool` | "The tool could not run. Retry, or rephrase the request." |
| `ERR-VOICE-NO-INPUT` | `audio` | "No microphone. Plug one in or grant permission, then retry from the UI (REQ-ERR-002)." |
| `ERR-VOICE-NO-OUTPUT` | `audio` | "No output device. Responses will be text-only until one is available." |
| `ERR-VOICE-ASR-FAIL` | `audio` | "Speech recognition failed. Try again, or use text input." |
| `ERR-VOICE-TTS-FAIL`, `ERR-VOICE-DECODE-FAIL` | `audio` | "Speech synthesis failed. The response is shown as text." |
| `ERR-VOICE-OVERFLOW` | `audio` | Not surfaced as an error; a `voice.overflow` warning only. |
| config load/validation errors | `config` | Names the offending key and value (REQ-CFG-003). |
| memory read/write errors | `memory` | "The turn could not be saved. Check disk space and `memory.*` paths." |

An internal code with no row here maps to `harness` and logs a warning, so a new
code degrades visibly rather than crashing the mapper.

### `agent.tool.event`

**Status:** new. **This is the tool-activity channel.** Without it, tool rows
cannot render: `agent.delta.kind` covers only text and thinking.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `call_id` | str | yes | Correlates the start and the end. The native harness assigns it. |
| `name` | str | yes | Tool name |
| `status` | enum `running` \| `partial` \| `done` \| `error` | yes | |
| `args` | object \| null | no | Present on `running` |
| `result` | any \| null | no | Present on `done` / `error`; truncated for display |
| `duration_ms` | float \| null | no | Present on `done` |
| `source` | enum `native` | yes | Which harness ran it |

Consumers: the orb transcript (activity row), the console (inline line). The
payload is display-only; nothing is derived from it.

### `voice.overflow`

**Status:** new. A warning, not an error: the segment queue hit its cap and
dropped the oldest segment (IF-0006).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `dropped` | int | yes | Segments dropped since the last report |
| `queue_cap` | int | yes | The configured cap |

### `status.harness`

**Status:** new.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `harness` | `"native"` | yes | The active loop owner |
| `model` | str | yes | Model reported by the harness; empty when the harness has no provider |

### `voice.state`

**Status:** new.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `state` | enum (see [IF-0005](protocols.md#if-0005-voice-events)) | yes | `idle` \| `listening` \| `transcribing` \| `thinking` \| `speaking` \| `error` \| `muted` |
| `muted` | bool | no | Present on `set_mute` and on a request reply; the local toggle desyncs otherwise |
| `previous` | enum | no | Present on a transition; absent from a request reply |

A reply to `voice.state.request` is shape-identical to a transition event and
carries the last state actually published, so a late-connecting client converges
on the same value as a connected one. It is a level read: it does not move the
FSM and does not publish a second time.

### `voice.state.request`

**Status:** new. Empty payload. A late-connecting client (orb, tui) publishes
this once per bridge connect; the voice module replies on `voice.state` with the
current state and mute flag. Fire-and-forget: with no subscriber it is a
harmless no-op, so a frontend can connect to an older assistant.

### `status.harness.request`

**Status:** new. Empty payload. The client asks the agent for the current
`status.harness` badge; the agent replies on `status.harness`. Same
fire-and-forget contract as `voice.state.request`.

### `voice.level`

**Status:** new.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `level` | float `0..1` | yes | RMS |
| `source` | `"input"` \| `"output"` | yes | Mic vs TTS; the orb reacts to both |
| `ts` | float | yes | Monotonic seconds at publish |

Published ≤ 20 Hz, latest-wins. The publisher coalesces; the bridge does not
(`features/orb-ui.md:53-58`).

### `voice.transcribed`

**Status:** new.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `text` | str | yes | ASR output |
| `confidence` | float \| null | no | **Unverified** against current ASR backends |
| `language` | str \| null | no | **Unverified** against current ASR backends |

### `schedule.triggered`

**Status:** as-built (`modules/scheduler/scheduler.py:92-97`).

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | str | yes | 8 hex chars (`scheduler.py:58`) |
| `task` | str | yes | Short title |
| `time` | str ISO 8601 | yes | The task's scheduled time |
| `description` | str | yes | Spoken or shown on trigger |

### Other voice payloads

| Topic | Fields | Status |
| --- | --- | --- |
| `voice.tts.started` | `{text}` | new |
| `voice.tts.done` | `{text, interrupted: bool}` | new |
| `voice.tts.error` | `{error: str}` | new |
| `voice.tts.ready` | `{engines: [str]}` | new |
| `voice.overflow` | `{}` | new |
| `command.voice.mute` | `{muted: bool}` | new |
| `command.agent.interrupt` | `{}` | new |
| `command.assistant.shutdown` | `{}` | new |
| `command.frontend.open` | `{kind: "tui" \| "gui"}` | new |

---

## Config schema

Canonical shape is [data-model.md § Config model](../architecture/data-model.md#config-model);
this section restates it in full and adds the per-module sections and the legacy
migration table.

Precedence (REQ-CFG-002): **CLI override > environment > `config.yaml` > code
defaults**.

Every default lives in code (`config.py` `DEFAULTS`), so the assistant runs with
no config file at all. `config.yaml` is optional and local (git-ignored); it is
deep-merged over the defaults, so it names only the keys that differ.
`config.example.yaml` is the tracked, commented example and mirrors the defaults
key for key.

### `agents:`

An `agents:` map; more than one identity is allowed (REQ-CFG-006). `data-model.md`
shows the canonical block; fields:

| Key | Type | Notes |
| --- | --- | --- |
| `agents.active` | str | **Which agent id is active.** Required when the map has more than one entry; defaults to the only entry otherwise. Resolved once at startup. |
| `agents.<id>.identity.name` | str | Display name |
| `agents.<id>.identity.wake_phrases` | list[str] | Wake phrases for this agent |
| `agents.<id>.persona` | str | System prompt for this agent (was `brain.persona`, `config.yaml:9-11`) |
| `agents.<id>.harness` | `native` | Loop owner (REQ-HARNESS-001) |
| `agents.<id>.llm.provider` | `ollama` \| `openai` | Native only (REQ-BACKEND-001) |
| `agents.<id>.llm.model` | str | e.g. `qwen3:latest` |
| `agents.<id>.llm.url` | str | Provider endpoint |
| `agents.<id>.llm.api_key` | str | Prefer the environment (REQ-CFG-005) |
| `agents.<id>.llm.max_tokens` | int | As-built `config.yaml:17` |
| `agents.<id>.llm.temperature` | float | As-built `config.yaml:18` |

**Active-agent resolution:** exactly one agent is active per process.
`agents.active` names it; if the map has one entry and `agents.active` is unset,
that entry is used. If the map has multiple entries and `agents.active` is
unset or names an unknown id, startup fails with an actionable config error
(REQ-CFG-003). Switching the active agent is a **restart-scoped** change — see
the reload policy below.

### `bus:`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `bus.bind` | str | `127.0.0.1` | Widening requires a token (REQ-SEC-001/002) |
| `bus.websocket_port` | int | `8765` | As-built `config.yaml:5` |
| `bus.remote_auth_token` | str | `""` | Mandatory for non-loopback binds |

### Per-module sections

| Section | Keys | Notes |
| --- | --- | --- |
| `voice` | `listen.mode` (`ptt`\|`open`\|`wake`), `hotwords`, `endpoint_silence_ms` (default 3000: silence before the turn is sent), `wake_window_ms`, `speak_text_turns`, `barge_in.enabled`, `vad.backend`, `vad.energy_threshold`, `vad.aggressiveness`, `segmenter.preroll_ms`, `segmenter.min_utterance_ms`, `segmenter.max_utterance_ms`, `segmenter.onset_ms`, `asr.backend`, `asr.model`, `asr.device`, `asr.compute_type`, `asr.base_url`, `asr.api_key`, `asr.api_key_env`, `asr.language`, `tts.backend`, `tts.voice`, `tts.speed` | ASR backends: faster_whisper (offline, default), whisper_server (self-hosted), whisper, funasr, stub; VAD: energy, webrtc; TTS: edge_tts, text (`features/voice-pipeline.md:79-80`) |
| `tools` | `paths`, `timeout_s`, `sandbox_default`, `safe_paths`, `artifacts_path`, `max_retries` | Was `hands` (`config.yaml:55-61`) |
| `vision` | `backend` (`stub`), `camera_index`, `vision_model` | Was `eyes`; stub only |
| `messaging` | `backends` (`[]`), `telegram.token`, `telegram.allowed_users` | Was `chat`; disabled by default |
| `console` | `prompt` | Was `cli` (`config.yaml:70-72`) |
| `scheduler` | `storage_path`, `max_pending` | As-built (`config.yaml:34-36`) |
| `display` | `mode` (`gui`\|`tui`\|`none`\|`auto`), `always_on_top`, `orb_shader`, `reduced_motion`, `geometry` (`x`, `y`, `w`, `h`) | The frontend: `auto` (the default) shows the GUI orb when a display is available and no visual shell otherwise; `none` is text only (REQ-CONSOLE-004). Legacy `orb`/`ui` alias `gui`, `console` aliases `none`. `AIASSISTANT_DISPLAY_OFF` forces `none` unless the CLI names a frontend (ADR-0017) |
| `memory` | `resume_session`, `semantic`, `conversations_path`, `facts_path`, `knowledge_path`, `embeddings_db`, `context_max_tokens`, `context_recent_messages` | Semantic recall default off (`scope.md:34`); paths as-built (`config.yaml:19-25`) |
| `embeddings` | `provider` (`same`\|`ollama`\|`openai`), `model`, `url`, `batch_size` | As-built (`config.yaml:26-30`); `same` reuses the agent's provider |
| `conversation` | `context_turns`, `busy` (`interrupt`\|`queue`), `turn_timeout_s`, `retry_max` | Turn gating and bounded retries; `turn_timeout_s` is the fallback when a harness-specific timeout is unset |
| `voice.barge_in` | `enabled` (bool, default `false`) | Voice barge-in needs AEC; see [ADR-0011](../architecture/decisions/ADR-0011-half-duplex-first.md) |

### Reload policy

A single rule, so "applies now" versus "needs a restart" is never a guess.

| Scope | Applies |
| --- | --- |
| `display.mode` | **Restart** — it selects which frontend to spawn |
| `display.always_on_top`, `display.orb_shader`, `display.reduced_motion` | **Runtime** — the orb reacts on receipt; the assistant publishes the change |
| `voice.tts.voice`, `voice.tts.speed`, `voice.speak_text_turns` | **Runtime** — read at the next utterance |
| `voice.listen.mode`, mute | **Runtime** — via `command.voice.*` |
| `console.prompt`, log level | **Runtime** |
| `agents.active`, `agents.<id>.harness`, `agents.<id>.llm.*` | **Restart** — the harness is built once at startup (REQ-HARNESS-001) |
| `bus.*`, `tools.paths`, `voice.asr.backend`, `voice.tts.backend`, embedding provider | **Restart** — backends and the process model are fixed at startup |
| Everything else | **Restart** (the safe default) |

There is no config file watcher in the MVP. The console `/harness` command
rebuilds the active harness in place; it is the one exception, and it exists
because it is cheap and useful. All other changes are picked up on the next
launch.

### Legacy key migration

Accepted with a deprecation warning and mapped (REQ-CFG-004). This table covers
**every nested key** in the as-built `config.yaml`, because a top-level-only map
would silently drop most of a user's real config.

#### Section renames

| Legacy section | New section | Notes |
| --- | --- | --- |
| `brain.llm.*` | `agents.<id>.llm.*` | Direct key-for-key |
| `brain.persona` | `agents.<id>.persona` | |
| `brain.memory.*` | `memory.*` | Promoted out of `brain` |
| `brain.embeddings.*` | `embeddings.*` | Promoted out of `brain`; note `provider: same` is preserved |
| `brain.thinking.max_reflect_loops` | `conversation.retry_max` | Renamed concept: retry count, not a "reflect loop" |
| `ears.*` | `voice.asr.*` + `voice.listen.*` + `agents.<id>.identity.wake_phrases` | Split, see below |
| `mouth.*` | `voice.tts.*` | |
| `hands.*` | `tools.*` | Split, see below |
| `eyes.*` | `vision.*` | Direct |
| `canvas.*` | — | **Deleted** (REQ-STRUCT-004, [ADR-0003](../architecture/decisions/ADR-0003-delete-canvas.md)); `web_port` had no implementation |
| `chat.*` | `messaging.*` | `backends` → `backends`; telegram keys → `telegram.*` |
| `cli.*` | `console.*` | |
| `scheduler.*` | `scheduler.*` | Unchanged |
| `bus.*` | `bus.*` | Unchanged, plus the new `bind` key defaulting to `127.0.0.1` |

#### Per-key renames and unit changes

These are the non-1:1 mappings. The unit changes are the traps: a straight value
copy would be wrong by a factor of 1000 or name a different concept.

| Legacy key | New key | Transform |
| --- | --- | --- |
| `brain.llm.provider` | `agents.<id>.llm.provider` | Direct |
| `brain.llm.model` | `agents.<id>.llm.model` | Direct |
| `brain.llm.url` | `agents.<id>.llm.url` | Direct |
| `brain.llm.api_key` | `agents.<id>.llm.api_key` | Direct; warn if non-empty (secrets belong in the env) |
| `brain.llm.max_tokens` | `agents.<id>.llm.max_tokens` | Direct |
| `brain.llm.temperature` | `agents.<id>.llm.temperature` | Direct |
| `brain.memory.context_max_tokens` | `memory.context_max_tokens` | Direct |
| `brain.memory.context_recent_messages` | `memory.context_recent_messages` | Direct |
| `brain.embeddings.provider` | `embeddings.provider` | Direct; `same` stays `same` |
| `brain.embeddings.model` | `embeddings.model` | Direct |
| `brain.embeddings.url` | `embeddings.url` | Direct |
| `brain.embeddings.batch_size` | `embeddings.batch_size` | Direct |
| `ears.backend` | `voice.asr.backend` | Direct |
| `ears.recognizer` | — | **Dropped.** It was meaningful only to the removed pre-ADR fused backend (ADR-0018) |
| `ears.hotwords` | `voice.hotwords` | Direct; the hotword list *is* the wake-phrase list |
| `ears.silence_timeout` | `voice.endpoint_silence_ms` | **Unit change: seconds → milliseconds.** As-built `20` means 20 s; new value `20000` |
| `mouth.backend` | `voice.tts.backend` | Direct |
| `mouth.voice` | `voice.tts.voice` | Direct |
| `mouth.speed` | `voice.tts.speed` | Direct |
| `hands.tool_paths` | `tools.paths` | Renamed key |
| `hands.sandbox_default` | `tools.sandbox_default` | Direct |
| `hands.command_timeout` | `tools.timeout_s` | Renamed key; unit unchanged (seconds) |
| `hands.safe_paths` | `tools.safe_paths` | Direct |
| `cli.backend` | — | **Dropped.** Only `simple` was implemented; `console.prompt` is the surviving key |
| `cli.prompt` | `console.prompt` | Direct |
| `chat.backends` | `messaging.backends` | Direct |
| `chat.telegram_token` | `messaging.telegram.token` | Renested |
| `chat.telegram_allowed_users` | `messaging.telegram.allowed_users` | Renested |
| `eyes.camera_index` | `vision.camera_index` | Direct |
| `eyes.vision_model` | `vision.vision_model` | Direct |
| `eyes.vision_model_url` | `vision.vision_model_url` | Direct |
| `canvas.backend`, `canvas.image_model`, `canvas.image_model_url`, `canvas.default_size`, `canvas.web_port` | — | **Dropped with the module** |

New keys with no legacy source, which get defaults and no warning:
`agents.active`, `agents.<id>.harness` (defaults `native`),
`agents.<id>.identity.name` (defaults `Jarvis`), `bus.bind`
(`127.0.0.1`), `voice.listen.mode` (`ptt`), `voice.barge_in.*`, `display.*`,
`conversation.*`, `memory.resume_session`, `memory.semantic`.

The as-built file (`config.yaml`) uses every legacy section; migration is
implemented in `main.py` in the refactor. REQ-CFG-004 has no proving test yet —
it is listed as `unverified` in [trace.md](../testing/trace.md).

---

## Memory / transcript file format (frozen as-built)

Frozen from `brain/respond.py:27-53`. One markdown file per day, named
`YYYY-MM-DD.md`, under `memory.conversations_path`. The date comes from the
filename; the time is written in UTC.

### File header

Written once, when the file is first created (`brain/respond.py:33-34`):

```
# Conversation — YYYY-MM-DD
```

### Turn block

Each turn appends (`brain/respond.py:34-51`):

```
## HH:MM:SS | <speaker>

<content>
[tools: <name>(<request_id>, <duration_ms>ms), ...]
[thinking: <thinking text>]
```

| Element | Format | Notes |
| --- | --- | --- |
| Header line | `## HH:MM:SS \| speaker` | `speaker` ∈ `user` \| `assistant`; UTC wall clock |
| Blank line | — | After the header |
| `content` | free text | Authoritative text (`text_final` for assistants) |
| `[tools: ...]` | optional | One line; `name(request_id, duration_ms)` comma-joined (`respond.py:36-41`) |
| `[thinking: ...]` | optional | Display only, never spoken (`respond.py:43-44`) |
| Trailing blank line | — | After each block |

Written exactly once per turn (REQ-MEM-002). The as-built code had two writers —
`Responder.save_turn` (`brain/respond.py:27`) and `MemoryManager.save_turn`
(`brain/memory.py:25`) — which this refactor collapses into one
(`data-model.md:37-39`).

The SQLite embeddings cache is a derived index and can be rebuilt from these
markdown files (`data-model.md:22-25`).

## Related

- [protocols.md](protocols.md) — IF-0001..0008 wire contracts.
- [api.md](api.md) — orb connection sequence and trace.
- [data-model.md](../architecture/data-model.md) — entities, storage, lifetime.
