# MOD-0009 — `console`

**Purpose:** Terminal interface and headless fallback.

**Must not do:** duplicate agent logic. It drives the same topics the orb does,
and renders the same events.

**Dependencies:** `bus` topics, `readline`.

## PROVIDES

### `start() / stop() -> None`

Reads stdin on an executor, never blocking the loop. Persists readline history.

### Commands

| Command | Action |
| --- | --- |
| `/exit` | Shut down |
| `/help` | Command help |
| `/status` | Module registry and harness health |
| `/mute` | Toggle microphone mute |
| `/stop` | Publish `command.agent.interrupt` |
| `/harness [native\|pi]` | Show or switch the harness |
| `/new` | Start a new session |
| `/log [level]` | Show or set the log level |
| `/thinking` | Toggle thinking display |
| `/clear` | Clear the terminal |

### Rendering

Streaming: `agent.delta` appends in place; `agent.final` settles the line.
Status: `voice.state` renders a one-line state indicator. Errors render inline
and do not block input.

## REQUIRES

- `bus.publish`, `bus.subscribe`, `bus.user_input`
- `command.agent.interrupt`, `command.voice.mute`

## OWNS

Readline history and local display state.

## INVARIANTS

- Console and orb produce identical turn behavior (REQ-CONSOLE-002).
- No console command bypasses the bus.

## ERRORS

Errors render from `agent.turn.error`, `voice.*.error`, and module-disconnected
topics, with a recovery hint (REQ-ERR-001).

| Code | Behavior |
| --- | --- |
| `ERR-CONSOLE-STDIN-CLOSED` | EOF on stdin; shut down cleanly |
| `ERR-CONSOLE-UNKNOWN-COMMAND` | Print help; do not forward to the agent |

## CONCURRENCY

Stdin is read on an executor, so it never blocks the loop. Handlers run on the
loop and print directly; output ordering is best-effort under concurrent events,
which is acceptable for a debugging surface.

## RESOURCES

One executor job at a time, one readline history file bounded to `HISTORY_MAX`.

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| Headless run is usable | mac, linux | T-0901 |
| Same topics as the orb | host | T-0902 |
| Transcript, status, and errors all render | host | T-0903 |
| Console can be forced via config | mac, linux | T-0904 |
| Streaming render works | host | T-0905 |
| `/stop` produces a cancelled turn | host | T-0906 |
