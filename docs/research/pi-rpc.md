# pi RPC — Established Facts

Factual reference on Mario Zechner's "pi" coding agent, as established from its
own documentation and source. Documentation only; no pi binary was installed and
no code was written. Every claim carries a marker: `[V]` verified against the
cited source, `[U]` unverified (not confirmed from a fetchable source).

Project: `https://github.com/earendil-works/pi` (the former `badlogic/pi-mono`
redirects to it). npm package: `@earendil-works/pi-coding-agent` v0.87.1. MIT
license. TypeScript. Node >= 22.19. Distributions: npm global install and a
`curl` installer; standalone binaries for darwin-arm64/x64 and linux-arm64/x64.

## 1. What pi is

| Claim | Value | Source | Flag |
| --- | --- | --- | --- |
| Identity | A minimal, extensible AI **agent for the terminal** (an agent harness) | `README.md` | [V] |
| Author | Mario Zechner | `package.json` `"author": {"name":"Mario Zechner"}` | [V] |
| License | MIT | `README.md`, `package.json` `"license": "MIT"` | [V] |
| Version | 0.87.1 | npm registry `latest` | [V] |
| Language / runtime | TypeScript; `engines.node >= 22.19.0` | `package.json` | [V] |
| npm install | `npm install -g --ignore-scripts @earendil-works/pi-coding-agent` | `README.md` | [V] |
| Installer | `curl -fsSL https://pi.dev/install.sh \| sh` | `README.md` | [V] |
| Standalone binaries | darwin-arm64/x64, linux-arm64/x64 | `install.sh` managed-install paths; `build:binary` produces `dist/pi` | [V] |

**Not** a model provider and **not** an inference engine. pi owns the reasoning
loop (prompts the model, parses and runs tool calls, manages context) and calls
an external provider (Anthropic, OpenAI, or a configured compatible endpoint).
The project's own three-layer model (`docs/README.md`) states this explicitly:
pi is the **harness**, not the provider or the model.

Sources: `packages/coding-agent/README.md`,
`packages/coding-agent/package.json`, npm `registry.npmjs.org` metadata,
`https://pi.dev/install.sh`.

## 2. How pi is driven

pi has three non-interactive interfaces plus the terminal UI.

| Mode | Invocation (quoted) | Behavior | Source | Flag |
| --- | --- | --- | --- | --- |
| One-shot print | `pi --print "Summarize this repository"` | Runs the supplied prompts, writes the final assistant text to stdout, exits | `cli.md` | [V] |
| JSON one-shot | `pi --mode json "Inspect this repository" > events.jsonl` | Runs prompts, writes JSONL events to stdout, exits | `cli.md`, `json.md` | [V] |
| RPC long-lived | `pi --mode rpc --no-session` | Reads JSONL commands from stdin, writes responses and events to stdout until shutdown | `rpc.md` | [V] |
| TUI | `pi` (terminal stdin/stdout) | Opens the terminal UI unless `--print`, `--mode json`, or `--mode rpc` selects another interface | `cli.md` | [V] |

`-p`/`--print` runs once and exits. `--mode text` does not force one-shot when
stdin/stdout are terminals. When either stream is redirected and neither JSON nor
RPC mode is selected, pi uses print mode. JSON and RPC modes reserve stdout for
protocol records.

## 3. RPC framing

From `rpc.md` §Framing and `json.md` §Framing and process I/O:

| Rule | Statement | Flag |
| --- | --- | --- |
| Strict JSONL | One complete JSON object per record, terminated with LF (`\n`) | [V] |
| Split on LF only | Split records only on LF; strip an optional preceding carriage return to accept CRLF input | [V] |
| Do not use a Unicode-aware line reader | Node.js `readline` also splits on `U+2028`/`U+2029`, which are valid inside JSON strings; do not treat them as boundaries | [V] |
| stdout is protocol-only | stdout is reserved for protocol records; diagnostics and application logging go to stderr | [V] |
| Backpressure | Read stdout continuously; pi honors stdout backpressure, but a client that stops reading can stall the process. Honor stdin backpressure when writing | [V] |

The documentation's own warning, quoted: *"Read stdout continuously. Pi honors
stdout backpressure, but a client that stops reading can stall the process."*

## 4. Command/response correlation by `id`

Every command accepts an optional string `id`; the matching response repeats it.
Command handling is asynchronous, so clients must correlate by `id`, not response
order (`rpc.md` §Correlate commands and responses). [V]

```json
{"id":"req-1","type":"get_state"}
{"id":"req-1","type":"response","command":"get_state","success":true,"data":{"...":"..."}}
```

Session events generally carry **no** command id because they describe session
activity. The documented exception is `bash_execution_update`: when the
originating `bash` command has an id, its output events repeat that id. [V]

## 5. Command set

Documented in `rpc-commands.md`. All rows [V].

| Command | Documented behavior |
| --- | --- |
| `prompt` | Send a user prompt. Response returns after the prompt is accepted/queued/handled; events continue asynchronously. Optional `images`. During streaming, `streamingBehavior` (`"steer"` or `"followUp"`) is required or the command errors. |
| `abort` | Abort the current operation and wait for the session to become idle before responding. |
| `clear_queue` | Remove queued steering and follow-up messages and return their text (`{steering, followUp}`). |
| `steer` | Queue a steering message while the agent runs; delivered after the current assistant turn finishes its tool calls, before the next LLM call. |
| `follow_up` | Queue a follow-up message; delivered only when the agent has no more tool calls or steering messages. |
| `get_state` | Current session state: model, thinkingLevel, isStreaming, isCompacting, steeringMode, followUpMode, sessionFile, sessionId, sessionName, autoCompactionEnabled, messageCount, pendingMessageCount. |
| `get_session_stats` | Token usage, cost, and current context-window usage. |
| `get_last_assistant_text` | Text content of the last assistant message; `null` when none. |
| `set_model` | Switch to a specific model by `provider` + `modelId`; response contains the full Model object. |
| `abort_bash` | Abort a **running bash command** (separate from `abort`). |
| `bash` | Execute a shell command; output streams as `bash_execution_update` events; response contains the final result. |
| `get_messages`, `get_entries`, `get_tree` | Conversation / append-order entries / session tree. |
| `get_commands` | Extension commands, prompt templates, and skills. |

### `data.disposition`

The `prompt` response's `data.disposition` is one of:

| Value | Meaning |
| --- | --- |
| `"started"` | Pi accepted the prompt to start a run. |
| `"queued"` | Pi queued it during a run. |
| `"handled"` | An extension command or input handler consumed the prompt. |

A successful prompt response (`success: true`) means the prompt was
accepted/queued/handled **immediately**; it does **not** mean model work
completed. If `disposition` is `"handled"`, no run started, so do not wait for
`agent_settled`. Failures after acceptance are reported through the normal event
and message stream, not as a second response for the same id. [V]

### Interrupt recipe

`rpc-commands.md` documents the interactive-Esc recipe: send `clear_queue`
before `abort`, then restore the returned text in the client editor. `abort`
continues queued messages when they remain in the session. [V]

`abort_bash` is a separate command that cancels only a running bash command. The
implementation confirms it aborts the bash abort-controllers
(`agent-session.ts` `abortBash()` aborts every controller in
`_bashAbortControllers`). [V]

## 6. Event stream

Canonical reference: `json.md`. JSON mode emits one session-header record first;
RPC mode emits the same session-event shapes but no header (use `get_state`). [V]

### Message events

| Event | Fields | Meaning |
| --- | --- | --- |
| `message_start` | `message` | A message started. |
| `message_update` | `usage`, `assistantMessageEvent` | An assistant message emitted a content-block update. |
| `message_end` | `message` | A message completed. **The authoritative final message.** |

`message_update` records on the wire are **delta-only**: they omit the SDK
event's cumulative `message` field and every `assistantMessageEvent.partial`
snapshot. Deltas must be assembled by the client. [V]

`assistantMessageEvent` types (`json.md`):

| Type | Extra fields | Meaning |
| --- | --- | --- |
| `start` | none | Provider stream started (`partial` removed on the wire). |
| `text_start` | `contentIndex` | A text block started. |
| `text_delta` | `contentIndex`, `delta` | Append text. |
| `text_end` | `contentIndex`, `content` | Text block ended with authoritative content. |
| `thinking_start` | `contentIndex` | A thinking block started. |
| `thinking_delta` | `contentIndex`, `delta` | Append thinking text. |
| `thinking_end` | `contentIndex`, `content` | Thinking block ended with authoritative content. |
| `toolcall_start` | `contentIndex`, `id`, `toolName` | A tool-call block started. |
| `toolcall_delta` | `contentIndex`, `delta` | Append serialized argument data. |
| `toolcall_end` | `contentIndex`, `toolCall` | Tool call ended with the complete `ToolCall`. |
| `done` | `reason`, `message` | Provider stream completed. |
| `error` | `reason`, `error` | Provider stream errored / aborted. |

Use `contentIndex` to identify the block. Buffer `delta` fields for a live
display, but replace reconstructed data with the completed content in
`text_end`/`thinking_end`/`toolcall_end`, and replace the whole partial message
with `message_end.message` when it arrives. [V]

### Tool execution events

| Event | Fields | Correlation |
| --- | --- | --- |
| `tool_execution_start` | `toolCallId`, `toolName`, `args` | by `toolCallId` |
| `tool_execution_update` | `toolCallId`, `toolName`, `args`, `partialResult` | by `toolCallId` |
| `tool_execution_end` | `toolCallId`, `toolName`, `result`, `isError` | by `toolCallId` |

`partialResult` is the latest partial result supplied by the tool; whether it
replaces or extends an earlier update depends on the tool's result contract. [V]

### Lifecycle events

| Event | Fields | Meaning |
| --- | --- | --- |
| `agent_start` | none | A low-level agent run started. |
| `turn_start` | none | One assistant turn started. |
| `turn_end` | `message`, `toolResults` | One assistant response and its tool calls finished. |
| `agent_end` | `messages`, `willRetry` | That low-level run ended. Retries, overflow recovery, compaction, steering, or follow-up can still follow. |
| `agent_settled` | none | **End-of-turn marker.** Pi will not continue automatically through retries, compaction recovery, or queued messages. |

### Usage

Top-level `usage` on `message_update` is
`{input, output, cacheRead, cacheWrite, totalTokens, cost}`. It is the latest
cumulative provider-reported usage and can remain zero until completion when a
provider does not report usage while streaming. [V]

### Retry and compaction events

| Event | Fields |
| --- | --- |
| `compaction_start` | `reason`: `"manual"` \| `"threshold"` \| `"overflow"` |
| `compaction_end` | `reason`, `result`, `aborted`, `willRetry`, optional `errorMessage` |
| `auto_retry_start` | `attempt`, `maxAttempts`, `delayMs`, `errorMessage` |
| `auto_retry_end` | `success`, `attempt`, and `finalError` on final failure |
| `summarization_retry_scheduled` | `attempt`, `maxAttempts`, `delayMs`, `errorMessage` |
| `summarization_retry_attempt_start` | `source` (`"compaction"` \| `"branchSummary"`), `reason` |
| `summarization_retry_finished` | — |

### RPC-only events

A direct RPC `bash` command emits one `bash_execution_update` per output chunk,
with an optional `id` matching the command id. `extension_error` is emitted when
an extension handler throws. Extension UI records are a separate subprotocol. [V]

## 7. Shutdown

Closing the child's stdin is the **orderly-shutdown** signal: pi disposes the
active runtime before exiting. The docs state clients should still handle
process signals and unexpected exits. [V]

An extension can also request shutdown through its extension context; pi
completes shutdown after the current command or after the active run emits
`agent_settled`. [V]

**Closing stdin is not a cancel.** The documented cancellation path is the
`abort` (and optionally `clear_queue`) command. This is the project's explicit
reading of the source, marked [V] for "stdin close = orderly shutdown"; the
negative claim "stdin close is not a cancel" is [U] until a host spike confirms
it (see §Verified vs unverified).

## 8. Extensions

Extensions are TypeScript modules that run **inside the pi process** with the
same OS permissions (`extensions.md`). [V]

| Fact | Detail | Flag |
| --- | --- | --- |
| Flag | `-e`, `--extension <path>` loads a file or directory; repeatable | [V] |
| Load in RPC | Extensions load in interactive, RPC, JSON, and print modes | [V] |
| Non-interactive UI | RPC can forward supported dialogs/notifications; JSON and print have no UI. Guard terminal-only behavior with `ctx.mode === "tui"` and use `ctx.hasUI` | [V] |

### The `tool_call` hook (veto before execution)

`pi.on("tool_call", handler)` fires before a tool executes and can block it. The
result type, cited from
`packages/coding-agent/src/core/extensions/types.ts`:

```ts
export interface ToolCallEventResult {
    /** Block tool execution. To modify arguments, mutate `event.input` in place instead. */
    block?: boolean;
    reason?: string;
    /** Hint that the agent should stop after the current tool batch when this call is blocked. */
    terminate?: boolean;
}
```

The runner applies it in `core/extensions/runner.ts` `emitToolCall()`: it awaits
each registered handler and, as soon as one returns `result.block === true`,
returns that result immediately:

```ts
if (handlerResult) {
    result = handlerResult as ToolCallEventResult;
    if (result.block) {
        return result;
    }
}
```

The agent installs the hook in `core/agent-session.ts` `_installAgentToolHooks()`
as `this.agent.beforeToolCall`. A `tool_call` handler failure blocks the tool as
a fail-safe (`extensions.md`). [V]

### The `user_bash` hook

Fires when the user executes a `!`/`!!` command. A handler that returns
`undefined` passes the command to the next handler and then to local execution if
none handles it; returning `operations` or `result` stops propagation; a handler
failure blocks the command rather than falling through. [V]

### Example extensions

| Example | Purpose | Flag |
| --- | --- | --- |
| `permission-gate.ts` | Prompts before dangerous bash (`rm -rf`, `sudo`, `chmod/chown 777`); returns `{ block: true, reason }` — in non-interactive mode it blocks by default when there is no UI | [V] |
| `tool-override.ts` | Registers a tool with the same name as a built-in (`read`) to replace it; logs access and blocks sensitive paths | [V] |
| `sandbox/index.ts` | OS-level sandboxing of bash via `@anthropic-ai/sandbox-runtime` (`sandbox-exec` on macOS, `bubblewrap` on Linux); overrides `bash` and handles `user_bash` | [V] |

## 9. Tool restriction flags

From `cli.md` §Tools and `settings.md` §Tools. [V]

| Flag | Behavior |
| --- | --- |
| `-t`, `--tools <list>` | Replaces the default selection with a comma-separated allowlist of built-in, extension, or custom tools |
| `-xt`, `--exclude-tools <list>` | Disables comma-separated tool names after all other selection options |
| `-nbt`, `--no-builtin-tools` | Disables default built-in tools, retaining extension and custom tools |
| `-nt`, `--no-tools` | Starts with all built-in, extension, and custom tools disabled |

Built-in tool names: `read`, `bash`, `powershell`, `edit`, `write`, `grep`,
`find`, `ls`. The **default enabled set is `read`, `bash`, `edit`, `write`**
(unless `defaultTools` changes them). [V]

## 9a. Resource and process flags used by this project

From `cli.md` §Resources and §Prompts and process. These are the flags in the
[IF-0003](../contracts/protocols.md#if-0003-pi-rpc) start command. Each is
verified against `cli.md`; the citation is to that file unless noted. [V]

| Flag | Behavior | Why we use it |
| --- | --- | --- |
| `-e`, `--extension <path>` | Loads an extension file or directory; repeatable | Loads the packaged `workspace_guard.ts` (absolute path, [ADR-0016](../architecture/decisions/ADR-0016-pi-paths-cwd-independent.md)) |
| `-ne`, `--no-extensions` | Disables discovered and configured extensions. **Explicit `-e` paths still load** | Stops the workspace folder injecting its own extension, while still loading ours |
| `-nc`, `--no-context-files` | Disables `AGENTS.md` and `CLAUDE.md` discovery | Prevents in-folder instruction injection |
| `-na`, `--no-approve` | Ignores trust-gated project-local configuration and resources for this process | Same; the non-interactive counterpart of `--approve` |

The combination `-ne -e <guard.ts>` is the documented behavior: `-ne` disables
*discovered* extensions, while an explicit `-e` path still loads. That is
exactly what confinement needs — our guard loads, ambient ones do not. [V]

Two more flags exist and are **not** used, noted for completeness:
`-ns`/`--no-skills` and `-np`/`--no-prompt-templates`. They disable discovered
skills and templates but still honor explicit paths. [V]

Also relevant: `--offline` disables automatic network activity such as model
catalog refresh, and is equivalent to `PI_OFFLINE=1`. It **does not** disable
provider API calls. It is not on our start command, because pi must reach its
model provider. [V]

## 10. Security posture

Quoted from `security.md` and `README.md`:

| Claim | Statement | Flag |
| --- | --- | --- |
| No built-in permission system | Pi "does not ask for approval before every tool call"; safety comes from isolating what pi can access, not from a gate | [V] |
| Runs with the launcher's permissions | Pi can read, change, and execute files "with the permissions of the account that started it" | [V] |
| Working folder does not confine paths | "The working folder controls resource discovery and the default location for tools, but it does not prevent commands from accessing other paths available to the Pi process." | [V] |
| No `--sandbox` flag | There is no built-in `--sandbox`; sandboxing is an example extension, a container, or a VM | [V] |
| Recommended posture | Whole-process container / VM / sandbox is "usually the strongest practical option" (`security.md`, `containerization.md`) | [V] |

## 11. Environment variables

From `environment-variables.md`. [V]

| Variable | Meaning |
| --- | --- |
| `PI_CODING_AGENT_DIR` | Override the config directory; default `~/.pi/agent` |
| `PI_CODING_AGENT_SESSION_DIR` | Override session storage; overridden by `--session-dir` |
| `PI_OFFLINE` | Disable automatic network activity, including model catalog refreshes |

Process markers set by the CLI and RPC entry points: `AI_AGENT=pi` (generic
marker) and `PI_CODING_AGENT=true` (pi-specific). Child processes inherit both.
They are not session-specific and are **not** set automatically when pi is
embedded through the SDK. Shell tools (`bash`, `powershell`) additionally receive
`PI_SESSION_ID`, `PI_SESSION_FILE`, `PI_PROVIDER`, `PI_MODEL`, and
`PI_REASONING_LEVEL`; user-entered `!`/`!!` commands do not receive these. [V]

## 12. Config

From `configuration.md`, `settings.md`, `models.md`. [V]

| Path | Responsibility |
| --- | --- |
| `~/.pi/agent/settings.json` | User-level settings: preferences, defaults, resource paths, Pi package declarations |
| `~/.pi/agent/models.json` | Compatible endpoints, models, and model overrides |
| `~/.pi/agent/auth.json` | Saved API keys and OAuth credentials |
| `~/.pi/agent/keybindings.json` | TUI and application keybindings |
| `~/.pi/agent/extensions/`, `skills/`, `prompts/`, `themes/` | User resources |

The agent directory is relocated with `PI_CODING_AGENT_DIR` (or the SDK
`agentDir` option). API keys can come from environment variables (e.g.
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) or from `auth.json`. Local /
OpenAI-compatible endpoints are configured through `models.json`
("Configure a compatible endpoint"); model commands return a Model object with
`api`, `provider`, `baseUrl`, `contextWindow`, `maxTokens`, and `cost`. [V]

Provider API-key variables are documented separately in `providers.md`. The
project must point pi at its local Ollama or OpenAI-compatible endpoint via
`models.json`.

## Verified vs unverified

| Claim | Flag | Source |
| --- | --- | --- |
| pi is a harness, not a provider/inference engine | [V] | `README.md`, project `docs/README.md`; npm metadata |
| Author, license, version, Node engine, distributions | [V] | npm registry, `package.json`, `README.md`, `install.sh` |
| CLI / JSON / RPC invocation strings | [V] | `cli.md`, `rpc.md`, `json.md` |
| JSONL framing, LF-only split, stdout purity, stall warning | [V] | `rpc.md` §Framing, `json.md` §Framing |
| Response `id` correlation; events have no id | [V] | `rpc.md` §Correlate |
| Command set and `data.disposition` values | [V] | `rpc-commands.md` |
| `clear_queue`-then-`abort` recipe; separate `abort_bash` | [V] | `rpc-commands.md`; `agent-session.ts#abortBash` |
| Event shapes, delta-only updates, usage fields | [V] | `json.md` |
| `message_end` is the authoritative message | [V] | `json.md` §Message events |
| `agent_settled` is the end-of-turn marker | [V] | `json.md`, `rpc.md` §Run lifecycle |
| Retry / compaction events | [V] | `json.md` |
| stdin close = orderly shutdown | [V] | `rpc.md` §Shutdown |
| stdin close is **not** a cancel | [U] | not stated in docs; to confirm by spike |
| `tool_call` result type and runner early-return | [V] | `extensions/types.ts`, `runner.ts#emitToolCall`, `agent-session.ts#_installAgentToolHooks` |
| `user_bash` propagation rules | [V] | `extensions.md`, `runner.ts` |
| Example extensions exist (permission-gate, tool-override, sandbox) | [V] | repo `examples/extensions/` |
| Tool flags and built-in names / default set | [V] | `cli.md` §Tools, `settings.md` §Tools |
| Security posture quotes | [V] | `security.md`, `containerization.md`, `README.md` |
| Env vars and process markers | [V] | `environment-variables.md` |
| Config paths, API keys, compatible endpoints | [V] | `configuration.md`, `settings.md`, `models.md` |

### Items a host spike must confirm before the adapter relies on them

**Resolved 2026-09-27** against a live pi 0.87.1 (managed install under
`~/.pi/agent`, macOS arm64, Node v26.9.0). Results below; the adapter and its
tests pin each finding.

| # | Item to confirm | Spike result | Flag |
| --- | --- | --- | --- |
| 1 | `abort` during a **running tool** | **Still open.** The spike did not exercise a long-running tool. Cancellation is implemented (`clear_queue` then `abort`) but a running shell tool is untested; the adapter falls back to process-level teardown if `abort` does not return within 10 s. | [U] |
| 2 | Exact `message_end` content-block shape | **Resolved.** `message_end` fires **once per role** — `system`, `user`, then `assistant` — and the assistant payload is `{"role":"assistant","content":[{"type":"text","text":...}],"usage":{...}}`. Mapping the system prompt as the answer would have been a visible bug. `content` may also be a plain string. | [V] |
| 3 | `--no-session` on-disk semantics | **Resolved in effect.** `get_state` answers and no session file is referenced for the turn. Not independently audited on disk. | [V] partial |
| 4 | A prompt arriving **mid-stream** | **Not exercised.** The adapter refuses a second concurrent turn at the harness level, so this path cannot occur through us. | [U] |
| 5 | stdout purity in practice | **Resolved.** Every stdout line decoded as a JSON object across `get_state` and a full prompt turn; no non-JSON bytes appeared. | [V] |
| 6 | Binary install path after `install.sh` | **Resolved.** Managed install at `~/.pi/agent/`, launcher at `~/.pi/agent/bin/pi`. It is **not on the default PATH**; `setup_pi.sh` reports this and the app requires an explicit `pi.command` or a PATH entry. | [V] |
| 7 | Whether a cwd flag exists | **Resolved.** No `--cwd`; the child's working directory is the process cwd, which the adapter sets. Confirms cwd is not a boundary. | [V] |

#### Additional findings from the live spike

These were not on the original list but changed the adapter:

| Finding | Consequence |
| --- | --- |
| A failed turn is an **assistant message with `stopReason: "error"` and `errorMessage`**, not a separate error event. `errorMessage` is a nested JSON blob. | `message_end` maps to `TURN_ERROR` when `stopReason == "error"`, and the blob is flattened for display. Without this a 429 reads as an empty successful turn. |
| `turn_end` repeats the assistant message; `agent_settled` follows it. | `turn_end` is treated as a completion signal; `agent_settled` remains the primary end-of-turn marker. |
| `message_start` precedes each `message_end`; `message_start`, `turn_start`, `agent_start`, `agent_end` carry no content. | Ignored. |
| A `tool_call` extension hook **does** veto a real call: an out-of-workspace `read` was blocked with our reason string and `isError: true`, while the same call inside the workspace succeeded. | Confirms the guard is real enforcement for file tools (ADR-0012). |
| pi's default model (a hosted Google model) returned HTTP 429 on first use. | A local model is configured under `models.json` (`api: openai-completions` against Ollama) for testing. Model choice is pi's own, not ours. |

## Sources

- `https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/rpc.md`
- `.../docs/rpc-commands.md`
- `.../docs/json.md`
- `.../docs/cli.md`
- `.../docs/extensions.md`
- `.../docs/settings.md`
- `.../docs/configuration.md`
- `.../docs/security.md`
- `.../docs/containerization.md`
- `.../docs/environment-variables.md`
- `.../README.md`
- `.../src/core/extensions/types.ts`
- `.../src/core/extensions/runner.ts`
- `.../src/core/agent-session.ts`
- `.../examples/extensions/permission-gate.ts`
- `.../examples/extensions/tool-override.ts`
- `.../examples/extensions/sandbox/index.ts`
- `https://registry.npmjs.org/@earendil-works/pi-coding-agent/latest`
- `https://pi.dev/install.sh`
- Mirror checked: `https://pi.dev/docs/latest/rpc` and `https://pi.dev/docs/latest/cli` serve the same text as the repository `main` docs.
