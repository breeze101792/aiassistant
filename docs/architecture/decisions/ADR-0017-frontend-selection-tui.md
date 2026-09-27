# ADR-0017 — One frontend selection; the TUI is a separate process

**Status:** accepted · **Date:** 2026-09-27

## Decision

1. **One selection concept — the frontend — with values `gui | tui | none | auto`.**
   `mode` selects only the visual shell. Text (the console REPL) and audio are
   always-available capabilities, not modes. `console` stops being a value and
   becomes an alias for `none`; `orb` and `ui` become aliases for `gui`;
   `audio` leaves the enum entirely (it is a voice-backend preset, kept as
   `--audio`). Default `auto` resolves to `gui` when a display is available,
   else `none`. `auto` never resolves to `tui`; the TUI is explicit
   ([S] directive: "mode would only be gui/tui, text/audio will be always
   available").
2. **The TUI orb is a separate process**, spawned and supervised by `main.py`
   exactly like the GUI orb, talking to the assistant only over the bus
   WebSocket via the existing `bridge.Bridge` client. It is stdlib `curses`
   only, registers as module `tui`, reuses `OrbViewModel` from
   `orb/model.py` (Qt-free), and adds the `tui` input channel.
3. **The console module gains a terminal-ownership gate.** At most one of
   the console (main process) and the TUI process owns the tty. When the TUI
   is active the console subscribes but neither reads stdin nor prints; when
   the TUI exits or gives up, the console resumes the terminal.

## Why

- **`curses.initscr()` can exit the interpreter** on a bad terminal — it is a
  C-level `exit()`, not a Python exception
  (docs.python.org, `curses.initscr`; established in
  [research/tui-options.md §3.1](../../research/tui-options.md)). An
  in-process TUI module cannot survive that: one bad `TERM` kills the whole
  assistant and violates REQ-CONSOLE-001/REQ-FRONTEND-010. A child process
  turns that failure into "the TUI exited; fall back."
- **curses is not thread-safe** and bus callbacks run on the asyncio loop;
  the console already owns stdin via `loop.add_reader`
  (`console/module.py:122-127`). An in-process TUI would contend for stdin
  and serialize every draw against the loop (CLAUDE.md trap 4). A separate
  process runs one loop where the only thread that touches curses is the
  loop thread — thread-safety by construction, and no tty contention.
- **The pattern already exists and is proven.** The GUI orb is a separate
  bridge client spawned and bounded-restarted by `main.py`
  (`main.py:190-240`, [ADR-0013](ADR-0013-pyside6-orb.md), orb module
  invariants "no asyncio in this process / can crash and restart"). The TUI
  is the same shape with an asyncio loop instead of a Qt loop, so
  supervision, shutdown, and the failure story are shared, not invented.
- **The state mapping is already shared.** `OrbViewModel`
  (`orb/model.py:23-148`) is Qt-free by design and is the single place bus
  events become display state. The TUI imports it; no second mapping layer.

## Ruled out

| Option | Why rejected |
| --- | --- |
| **In-process TUI bus module** (frontends.md Q4's recommendation) | Cannot contain `initscr()`'s C-level `exit()`; fights the console for stdin; forces curses calls to be serialized against the bus loop. The recommendation predates weighing the `initscr` fact. |
| **`textual`** | 9 pip distributions; still writes escape sequences to `sys.__stderr__` on a non-tty unless explicitly gated; renders poorly in macOS Terminal.app per its own FAQ (research §2, §3.3). |
| **`rich`** | Degrades safely but is a rendering library, not an application framework; adds 3 distributions for what curses gives for free here (research §2). |
| **TUI in the GUI orb process** | The orb holds the display server; a headless host has neither Qt nor a reason to install it. |
| **`console` as a frontend value** | The user's directive: text is always available; a "console mode" that is really "no visual shell" is `none`. Keeping both `console` and `none` re-creates the three-overlapping-names defect this ADR removes. |
| **`auto` → `tui` on headless** | The user chose text-only/`none` on a headless host; `tui` is explicit. Also changes no verified requirement (REQ-CONSOLE-006 behavior is unchanged: headless auto yields the console REPL on the tty). |

## Consequences

- `display.mode` value set becomes `gui | tui | none | auto` with aliases
  (`orb`, `ui` → `gui`; `console` → `none`); `AIASSISTANT_DISPLAY_OFF` forces
  `none`; CLI `--frontend` becomes documented and `--mode` a deprecated
  alias. Precedence is unchanged: CLI > env > config > default
  (REQ-CFG-002).
- `gui_available()` gains an SSH probe (`SSH_CONNECTION`/`SSH_TTY`), closing
  the macOS-over-SSH gap where every non-Linux host reported a GUI
  (`config.py:107-109`).
- Terminal preconditions are checked **before** entering curses:
  `tui_available()` (stdin+stdout tty, `TERM` not unset/`dumb`/`unknown`,
  `setupterm()` ok, cursor addressing present). `setupterm` raises
  `curses.error` and never exits, so the parent can probe safely;
  `initscr()` runs only in the child.
- Frontend start failures degrade loudly instead of retrying: a first child
  exit within a quick-fail window degrades `gui → tui → none` / `tui → none`
  with a message; later crashes use the existing bounded restarts.
  Runtime reload of `display.mode` becomes restart-scoped (it selects what to
  spawn).
- The console subscribes to the live topics (`voice.state`,
  `voice.transcribed`, `agent.delta`, `agent.final`, `agent.turn.error`) per
  its own module contract; the dead `status.ears.*` / `status.mouth.error`
  subscriptions are removed. `response.text` stays published for the frozen
  messaging module only.
- New input channel constant `CHANNEL_TUI`; pi users must add `tui` to
  `allow_channels` to drive pi from the TUI.
- One residual, accepted risk: if `initscr()` hard-exits, `endwin()` cannot
  run and the terminal may be left on the alternate screen. The parent
  prints the reason after the child dies; the user runs `reset`. This is the
  one failure mode a child process cannot fully clean up.