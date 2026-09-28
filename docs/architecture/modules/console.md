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
| `/harness [native]` | Show or switch the harness |
| `/new` | Start a new session |
| `/log [level]` | Show or set the log level |
| `/thinking` | Toggle thinking display |
| `/clear` | Clear the terminal |

### Rendering

Streaming: the first `agent.delta` erases the prompt and opens a single
`Assistant:` line; later deltas append to it with a plain write. The streamed
text is accumulated so `agent.final` can settle without guessing.

`agent.final` takes one of two paths. If the streamed text equals the final, it
only ends the line, because reprinting it would duplicate the answer. If the
model revised mid-stream, it erases the rows the stream occupied and writes the
final once.

Erasing must cover every **physical row**. A `\r` plus `\x1b[K` clears only the
cursor row, so a wrapped answer kept its earlier rows and appeared twice when
reprinted. `_erase_streamed_rows` moves the cursor up by `_wrapped_rows - 1`
and clears each row; the count uses `_display_width`, which counts a wide (CJK,
emoji) character as two columns and a combining mark as zero, because the
persona matches the user's language and a CJK answer is normal
(REQ-CONSOLE-009).

Status: `voice.state` renders a one-line state indicator. Errors render inline
and do not block input.

Thinking: `agent.delta` with `kind: thinking` and the `agent.final` reasoning
summary never enter the transcript. They are emitted at debug level, and the
summary additionally renders only when `/thinking` is on (REQ-CONSOLE-010).
Input echo: on a tty the terminal echoes the typed line at the prompt, so the
console does not print it again; a piped or redirected run has no terminal
echo, so the transcript keeps `You: ...` there. A voice turn publishes
`voice.transcribed`, which is always shown (REQ-CONSOLE-011).

### Prompt ownership

The console owns the interactive prompt line. On `start()` it registers
`_emit` with `terminal.set_prompt_writer`, and every asynchronous writer — the
handlers above, and `main.PromptAwareHandler` for log records — routes through
`terminal.write_above`. The console erases the prompt, writes the line on its
own, and redraws the prompt, so output never glues itself to `> ` or leaves the
terminal without a prompt (REQ-CONSOLE-008).

`_prompt_shown` is the single source of truth for whether the prompt is on
screen; the read loop uses it instead of a local flag, and the handlers do not
print the prompt themselves. `suspend_terminal()` clears the writer so the TUI
can own the tty (REQ-FRONTEND-009).

Log records keep their stream: with no prompt owner the handler defers to
`logging.StreamHandler`, so a non-interactive run still logs to stderr.

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
