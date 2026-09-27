# MOD-0012 — `tui`

**Purpose:** The terminal orb. Render the same ambient state, transcript, and
controls the GUI orb does, for a host with no display server.

**Must not do:** import PySide6 or `orb/app.py`, touch audio devices, read the
whole assistant config, reason, or persist state. It speaks the bridge protocol
only.

**Dependencies:** stdlib `curses` · `bridge/` · `orb/model.py` for the Qt-free
view model · [IF-0004](../../contracts/api.md).

**State it owns:** local view state only (transcript model, scroll/pin, composer
buffer, current state). No history file, no geometry.

See [docs/ui/tui/](../../ui/tui/README.md),
[features/frontends.md](../../requirements/features/frontends.md), and
[ADR-0017](../decisions/ADR-0017-frontend-selection-tui.md).

## PROVIDES

### `main() -> int`

Starts the curses application. Returns a process exit code: `0` clean, `3` when
a terminal precondition fails. Spawned by `main.py` as a separate process, or run
directly with `python -m aiassistant.tui`.

### Subscribes

The GUI orb's watch set (`orb/app.py:30-39`), from `bus/topics.py`:
`voice.state`, `voice.level`, `agent.delta`, `agent.final`, `agent.tool.event`,
`agent.turn.error`, `status.harness`, `agent.transcript.snapshot`.

### Publishes

`user.input.text {text, channel: "tui"}` · `command.agent.interrupt` ·
`command.voice.mute` · `agent.transcript.snapshot.request`.

### Internal components

| Component | Responsibility |
| --- | --- |
| `__main__.py` | Entry point; re-checks terminal preconditions, narrow config read |
| `app.py` | Bridge, view model, asyncio loop, stdin, input handling |
| `render.py` | Frame building from the view model; pure curses calls |
| `tokens.py` | Glyphs, attributes, color pairs, key codes |

## REQUIRES

- The assistant's bus WebSocket (the `bridge.Bridge` client).
- An interactive terminal: stdin/out is a tty, `TERM` is set and not `dumb`,
  and terminfo supports cursor addressing. Checked by `config.tui_available()`
  **before** `curses.initscr()`, because a failed `initscr` can exit the
  interpreter.

## INVARIANTS

- No PySide6 import; importing `aiassistant.tui.app` must not pull Qt.
- All curses calls happen on the one asyncio loop thread. curses is not
  thread-safe.
- `curses.endwin()` runs on every exit path, including a crash.
- stdin is read via `loop.add_reader`, never a blocking read.
- The console never reads stdin while the TUI owns the terminal
  (REQ-FRONTEND-009).

## ERRORS

| Condition | Behavior |
| --- | --- |
| Precondition fails (non-tty, `TERM` unset/`dumb`, no curses, no terminfo) | Print the reason to stderr, exit `3`; the parent keeps text mode |
| The child exits within the startup grace | Not retried; text mode continues |
| The child exits cleanly (code 0) after the grace | Treated as the user closing the UI: not restarted, and the console reclaims the tty. This is how `Ctrl+D` quits. |
| The child crashes later | Bounded restart (3), like the orb |
