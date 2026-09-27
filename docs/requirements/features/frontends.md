# Feature: Frontends (GUI orb, TUI orb, console)

**Status:** draft — product definition for review. Not yet merged into
[requirements.md](../requirements.md) or [trace.md](../../testing/trace.md).
**Requirements (proposed):** REQ-FRONTEND-001..012.
**Related:** REQ-ORB-001..007, REQ-CONSOLE-001..006, REQ-CFG-002.

This file defines **what the frontend selection does and what the TUI orb is**.
It does not choose the transport (separate process vs in-process module) or the
visual layout; those go to `architect` and `ui-designer`.

## Purpose and user goals

| Goal | User |
| --- | --- |
| Show the assistant's ambient state and transcript on a desktop. | Today's GUI user (REQ-ORB-001). |
| Show the same ambient state and transcript when there is no display server (a headless server, an SSH session, Linux without X/Wayland). | [S] user request. |
| Let the user say which frontend to open, or open none. | [S] user request: "we could specify if we want to open a tui/gui". |
| Keep the assistant running when a frontend cannot start. | REQ-CONSOLE-001. |

## 1. Reconciled selection model

Today three names overlap:

| Name | Where | Values | Meaning |
| --- | --- | --- | --- |
| `display.mode` | `config.yaml:122`, `config.py:17-20` | `orb`, `console`, `auto` | Which UI to show. |
| CLI `--mode` | `main.py:282-284` | `console`, `audio`, `ui`, `auto` | Display choice **and** a voice preset. |
| `AIASSISTANT_DISPLAY_OFF` | `config.py:29-31` | set/unset | Force console. |

`--mode audio` only sets voice backends (`main.py:316-318`: `voice.backend=halasr`,
`voice.tts.backend=edge_tts`) and leaves the display unresolved; it is not a
display mode. `--mode ui` maps to `display_choice=orb` (`main.py:320-327`).

### 1.1 One concept: the frontend

**Recommendation.** Name the concept **frontend**. It is the interactive
presentation layer of the assistant. There is one selection, not two.

| Frontend | Interactive UI | Display server | Terminal (tty) | Owner of stdin/stdout |
| --- | --- | --- | --- | --- |
| `gui` | PySide6 orb window (REQ-ORB-001) | required | not used | the GUI process |
| `tui` | full-screen terminal orb | not required | required | the TUI |
| `console` | line-based transcript / REPL | not required | optional (works over a pipe) | the console |
| `none` | none | not required | not used | — |
| `auto` | resolved by rule §1.4 | — | — | — |

Canonical value for the GUI is **`gui`**. `orb` stays accepted as an alias for
`gui` so the as-built requirement clauses (REQ-CONSOLE-004, REQ-CONSOLE-006) and
existing configs keep working.

### 1.2 Config key and CLI flag

- **Config key stays `display.mode`.** Extend its value set to
  `gui | tui | console | none | auto` (`config.py:20` `DISPLAY_MODES`). Do not
  rename the key; REQ-CONSOLE-004/006 name it and are verified.
- **Documented CLI flag becomes `--frontend {gui,tui,console,none,auto}`.**
  Keep `--mode` as a hidden deprecated alias, mirroring the repo's existing
  deprecation style (`main.py:285-286` declares `--audio` a deprecated alias).
  Alias mapping: `ui → gui`, `console → console`, `auto → auto`, and
  `audio →` the `--audio` behavior with **no** frontend choice.
- **`audio` leaves the frontend enum.** It is a voice concern, not a display
  concern. Keep the `--audio` flag (`main.py:285`) for the backend override at
  `main.py:316-318`; recommend documenting the same override as config
  (`voice.backend`, `voice.tts.backend`). `--mode audio` becomes a deprecated
  alias for `--audio`.

### 1.3 Precedence

Follows REQ-CFG-002 (CLI > environment > config > defaults):

| Rank | Source | Wins when |
| --- | --- | --- |
| 1 | `--frontend` / `--mode` | always, when a value other than `auto` is given |
| 2 | `AIASSISTANT_DISPLAY_OFF` (`config.py:29-31`) | no explicit CLI value; forces `console` |
| 3 | `display.mode` (`config.py:127`) | no CLI value and env unset |
| 4 | default `auto` (`config.py:127`, `main.py:283`) | key unset |

`AIASSISTANT_DISPLAY_OFF` forces `console` but yields to an explicit CLI value,
preserving REQ-CONSOLE-006.

### 1.4 What `auto` resolves to

Rules, extending `resolve_display_mode` (`config.py:112-133`) and
`gui_available` (`config.py:99-109`):

| Host | Display server probe | tty | `auto` resolves to |
| --- | --- | --- | --- |
| Linux desktop | `DISPLAY` or `WAYLAND_DISPLAY` set (`config.py:26`) | yes | `gui` |
| macOS desktop | not probed; treated as present (`config.py:107-109`) | yes | `gui` |
| Headless Linux server | neither set | yes | `console` (default; see Q1) |
| SSH session, no X forwarding | neither set | yes | `console` (default; see Q1) |
| stdout piped / cron / systemd | either | no | `console` (works over a pipe, `console/module.py:156-168`) |
| `AIASSISTANT_DISPLAY_OFF=1` | either | either | `console` |

**Known gap.** `gui_available` returns `True` for every non-Linux platform
(`config.py:107-109`). A macOS **SSH** session therefore resolves to `gui`, and
the orb is spawned and fails three times before giving up
(`main.py:221-240`). An explicit `gui` request that cannot be satisfied must
degrade loudly on the first failure instead of relying on bounded restarts
(REQ-FRONTEND-004). See Q2.

## 2. The TUI orb

### 2.1 What it is

A **full-screen terminal application** that presents the assistant's ambient
state, transcript, and status, and accepts text input. It is the terminal
equivalent of the GUI orb, chosen when a display server is absent but an
interactive terminal is present.

- Renders from the **same, Qt-free view model** the GUI orb uses
  (`orb/model.py:1-8`, `on_voice_state`/`on_delta`/`on_final`/`on_error`/
  `on_harness`/`on_tool_event` at `orb/model.py:42-129`). The GUI orb itself is
  Qt-coupled only in the render layer; the mapping is reusable.
- Consumes the **same bus topics** as the GUI orb (`orb-ui.md:26-44`):
  `voice.state`, `voice.level`, `agent.delta`, `agent.final`,
  `agent.tool.event`, `agent.turn.error`, `status.harness`,
  `status.assistant.ready`.
- Publishes the **same commands**: `user.input.text {channel}`,
  `command.agent.interrupt`, `command.voice.mute` (`orb-ui.md:38-44`).
- Uses the Python standard library (`curses`) only. It adds no runtime
  dependency.

### 2.2 What it shows

The same information the GUI orb shows, not a reduced set:

| Element | Source |
| --- | --- |
| Ambient state: `connecting`, `idle`, `muted`, `listening`, `transcribing`, `thinking`, `speaking`, `error`, `backend-down` | `voice.state`, plus the two overlays in `orb-states.md:16-25`. |
| Live level cue (a text/bar meter) | `voice.level` with `source` (`orb-ui.md:51-54`). |
| Transcript: user, assistant, tool rows; assistant text streams | `agent.delta`, `agent.final`, `agent.tool.event`. |
| Error with recovery hint | `agent.turn.error`; `orb-ui.md:53`, `orb-states.md:21`. |
| Harness / model badge | `status.harness`. |
| Module status, mute state | bus registry, `command.voice.mute`. |

The state set and meaning are those of `orb-states.md`; **the TUI does not
re-invent states**. Because it is non-color and non-animated by nature, it
carries each state as **text plus a distinct form cue** (REQ-ORB-007's
"never color-only" rule applies unchanged).

### 2.3 Controls

Keyboard only:

| Control | Effect |
| --- | --- |
| Type + Enter | Publish `user.input.text`; a leading `/` runs a console command (`console/module.py:176-201`) |
| Stop / interrupt | `command.agent.interrupt` (`orb-ui.md:42`) |
| Mute toggle | `command.voice.mute` |
| Transcript scroll / page | Local |
| Clear | Local |
| Quit | Clean shutdown |

### 2.4 What it is not

- Not the animated GUI orb: no shader, no window, no always-on-top, no
  transparency, no position persistence.
- Not mouse-driven; no theming beyond the terminal's own palette.
- Not a second source of truth: it derives nothing the bus has not published
  (`orb/model.py:5-7`).
- Not a replacement for the console as the **permanent** fallback
  (REQ-CONSOLE-001): it is an alternative terminal frontend, not the floor.

### 2.5 Terminal preconditions and degradation

The TUI takes over the whole terminal, so it starts only when all hold:
stdout **is a tty**; `TERM` is set and is not `dumb`; `curses`/terminfo
initializes. If any fails, the TUI **does not start** and the frontend degrades
to `console` with a message naming the failed precondition. `curses.endwin()`
runs on every exit path, including a crash, so a failed TUI leaves a usable
terminal.

### 2.6 One terminal owner

The console module reads stdin (`console/module.py:100-168`) and writes stdout
(`console/module.py:207-230`). The TUI does the same. **At most one terminal
frontend may own the tty at a time.** When the TUI is active, the console
module's terminal I/O is suppressed (its command handling may be reused); the
TUI wins. This is the functional constraint that separates "TUI" from "orb"
(the GUI orb runs in its own process and does not touch the terminal).

### 2.7 `none`

`none` starts no interactive frontend: no orb, no TUI, and the console's
terminal I/O suppressed. The assistant still runs (voice, bridge, scheduler,
tools). This is the "neither" case of the request.

## 3. Flows

### (k) Headless host opens the TUI orb

**Trigger:** `--frontend tui`, or `display.mode: tui`, on a host with no display
server but an interactive terminal.
**Requirements:** REQ-FRONTEND-003, 005, 006, 007, 008, 009.

| # | Actor | Action |
| --- | --- | --- |
| 1 | app | Resolves the frontend per §1.4; `tui` is selected. |
| 2 | app | Checks terminal preconditions (§2.5). All pass. |
| 3 | app | Suppresses the console's terminal I/O (§2.6). |
| 4 | `tui` | Enters the alternate screen, draws state + transcript from the shared view model. |
| 5 | `tui` | Streams `agent.delta` into the transcript; settles on `agent.final`. |
| 6 | `tui` | Reflects `voice.state` / `voice.level` as text + form cues. |
| 7 | user | Types a turn, or presses stop / mute; the same topics are published as the GUI orb. |
| 8 | app | On quit, `endwin()` restores the terminal. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| No tty, no `TERM`, or `TERM=dumb` | TUI does not start; console runs | Use the console, or attach a real terminal |
| Bridge/module not yet ready | `connecting` state shown | Auto-clears on first forward (`orb-states.md:111-113`) |
| Harness unhealthy | `backend-down` overlay with hint | Flow (g); fix and retry |
| TUI process/module crashes | Terminal restored; console takes over; assistant keeps running | Restart, or continue in console |

### (l) Explicit GUI request with no display server

**Trigger:** `--frontend gui` (or `--mode ui`) on a host where no window can be
shown.
**Requirements:** REQ-FRONTEND-004, 010.

| # | Actor | Action |
| --- | --- | --- |
| 1 | app | CLI value `gui` wins precedence. |
| 2 | app | Probes for a display server (`config.py:99-109`). None found. |
| 3 | app | **Does not start the orb.** Logs a clear message naming the reason (`DISPLAY`/`WAYLAND_DISPLAY` absent). |
| 4 | app | Falls back to the next best frontend: `tui` when a tty is present, else `console`. |
| 5 | app | States the fallback in the chosen frontend, so the degradation is visible, not silent. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| `gui` requested, display present, orb import fails | Message names the missing dependency; fall back per step 4 | `pip install 'aiassistant[ui]'` |
| Orb starts then exits | Bounded restart (3, `main.py:92-93,221-240`); on exhaustion, keep console running | Fix the Qt install, or run `--frontend console` |
| `gui` requested on macOS over SSH | Current probe wrongly reports a GUI (`config.py:107-109`); first failure must degrade per step 3–5 rather than retry 3× | Pass `--frontend tui\|console`, or Q2 |

The assistant **never exits** because a GUI is unavailable (REQ-CONSOLE-001).

### (m) TUI cannot start

**Trigger:** `tui` selected, but a terminal precondition fails.
**Requirements:** REQ-FRONTEND-008, 010.

| # | Actor | Action |
| --- | --- | --- |
| 1 | app | Precondition check fails (non-tty, missing/`dumb` `TERM`, or `curses` error). |
| 2 | app | Calls `endwin()` if the screen was entered. |
| 3 | app | Prints the reason to stderr. |
| 4 | app | Starts the console on the same terminal, per REQ-FRONTEND-009. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| stdout redirected to a file | Console's non-tty poll path runs (`console/module.py:156-168`) | Attach a tty and rerun with `--frontend tui` |
| `curses.setupterm` raises | Degrade to console | Check `terminfo` / `TERM` |
| Terminal resized below the minimum | TUI shows a "terminal too small" message and pauses, rather than crashing | Resize |

## 4. Requirements (proposed for requirements.md)

Verification methods as in `requirements.md:6-8`.

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-FRONTEND-001 | One frontend concept. | A single `frontend` selection with values `{gui,tui,console,none,auto}` chooses the interactive UI; no second overlapping selector exists. `orb` is accepted as an alias for `gui`. | [S] | inspection, host |
| REQ-FRONTEND-002 | Deterministic frontend precedence. | CLI `--frontend` beats `AIASSISTANT_DISPLAY_OFF`, which beats `display.mode`, which beats the `auto` default; each layer wins over the next. | [A] | host |
| REQ-FRONTEND-003 | `auto` resolves by host and terminal. | On a Linux desktop (display var set) or macOS it resolves to `gui`; on a headless host with a tty to `console`; with no tty to `console`. | [A] | host, mac, linux |
| REQ-FRONTEND-004 | Explicit `gui` without a display degrades loudly. | `--frontend gui` with no display server selects no orb, logs the reason, and starts `tui` when a tty exists else `console`, stating the fallback. | [S] | mac, linux |
| REQ-FRONTEND-005 | TUI is a terminal frontend, stdlib only. | The TUI runs with no display server and no browser, using only the standard library; no new runtime dependency is added. | [S] | linux, inspection |
| REQ-FRONTEND-006 | TUI shows the same state and transcript as the GUI. | State (`idle`/`listening`/`transcribing`/`thinking`/`speaking`/`error`/`muted`/`connecting`/`backend-down`), transcript rows, streaming text, and the harness badge match the GUI orb for the same bus event sequence. | [S] | host, mac, linux |
| REQ-FRONTEND-007 | TUI controls exist. | Stop/interrupt, mute toggle, transcript scroll/clear, text input, and quit are keyboard-operable and publish the same bus topics as the GUI orb. | [S] | host, mac, linux |
| REQ-FRONTEND-008 | TUI preconditions degrade, never crash. | With non-tty stdout, unset or `dumb` `TERM`, or a `curses` init failure, the TUI does not start and the console runs instead; the terminal is left usable. | [A] | host, linux |
| REQ-FRONTEND-009 | One tty owner. | The TUI and console never both read stdin; when the TUI is active the console's terminal I/O is suppressed. | [A] | host, inspection |
| REQ-FRONTEND-010 | No frontend failure stops the assistant. | Orb, TUI, or console startup failure leaves the assistant running in the next available frontend (extends REQ-CONSOLE-001). | [A] | mac, linux |
| REQ-FRONTEND-011 | `none` runs without an interactive frontend. | `--frontend none` starts no orb, no TUI, and no console terminal I/O, and the assistant remains operational (voice/bridge/scheduler). | [S] | host, linux |
| REQ-FRONTEND-012 | `audio` is not a frontend. | `audio` is absent from the frontend value set; audio backends are selected by `--audio` or config, and no frontend selection changes the voice backends. | [A] | host, inspection |

Proposed test block **T-1201..T-1210** (next free range after `T-1102`; final
numbers belong to `tester`). Each case traces to one REQ-FRONTEND row; merge the
REQ rows into [requirements.md](../requirements.md) and the rows into
[trace.md](../../testing/trace.md) on review.

## 5. Scope

### Must-have

| Item | Why |
| --- | --- |
| Frontend enum and precedence (§1) | The request: "specify if we want to open a tui/gui". |
| `--frontend` + `display.mode` alias reconciliation | One concept instead of three. |
| TUI orb: state, transcript, status, input, interrupt, mute, quit | The request: a fallback when there is no display server. |
| Terminal-precondition degradation to console | Keeps REQ-CONSOLE-001 true. |
| `none` | The request: "or neither". |

### Should-have

| Item | Note |
| --- | --- |
| `--mode` deprecated alias with a warning | Smooths scripts; mirrors `--audio` (`main.py:285-286`). |
| Level meter in the TUI | Optional; state text is the must-have. |
| `SSH_CONNECTION`/`SSH_TTY` probe | Closes the macOS-SSH gap (§1.4, Q2). |

### Out of scope

| Item | Why |
| --- | --- |
| Mouse input, pane resizing, mouse-driven scrolling | Keyboard-only this round; not requested. |
| Theming, color schemes, configurable layouts | `ui-designer` territory; not a functional need. |
| Animating the TUI (braille/block orb) | The GUI shader is the animated frontend; the TUI is textual. |
| Windows support | Project targets macOS and Linux (`scope.md:46`, REQ-PLAT-001). |
| A second GUI toolchain | `scope.md:47`. |
| Remote/multi-client TUI over the WebSocket bridge | Transport is `architect`'s call; not needed for the local fallback. |

## 6. Open questions

**Q1 — Should `auto` pick `tui` on a headless host with a tty?**
Current verified behavior: `auto` picks `console` on a headless host
(REQ-CONSOLE-006, T-0907). The request describes the TUI as the fallback when
there is no display server.
- *Recommended default:* **No — keep `auto` → `console` on headless; `tui` is
  explicit (`--frontend tui` or `display.mode: tui`).** Least surprise over SSH,
  and it changes no verified requirement. The TUI still serves headless hosts on
  request.
- *Alternative:* `auto` → `gui` (display) → `tui` (headless, tty) → `console`
  (no tty). This matches the fallback reading but **amends REQ-CONSOLE-006 and
  T-0907**; the user must approve changing a verified requirement.

**Q2 — How should macOS-over-SSH resolve?**
`gui_available` treats every non-Linux platform as having a GUI
(`config.py:107-109`), so an SSH session into a Mac resolves to `gui` and fails.
- *Recommended default:* add `SSH_CONNECTION`/`SSH_TTY` as an extra headless
  signal, and document `--frontend tui|console` as the explicit override.

**Q3 — Is `none` this round or deferred?**
The request names "or neither", so it is included above.
- *Recommended default:* **in scope as `none`**, because it is the only way to
  run without an interactive frontend on a shared terminal. If deferred, drop
  REQ-FRONTEND-011 and move `none` to out-of-scope.

**Q4 — Transport for the TUI: in-process module or separate process?**
The GUI orb is a separate process over the WebSocket bridge (`main.py:208-219`,
`orb-ui.md:13-22`). The TUI has no display server to isolate it from and cannot
own the tty alongside the in-process console, so a separate process adds a
failure mode and a bridge dependency for little gain.
- *Recommended default:* **in-process bus module** (like the console), with the
  transport confirmed by `architect`. This is a technical decision and is marked
  as such; the functional spec holds either way.

**Q5 — Is `--frontend` the right flag name, or keep `--mode`?**
- *Recommended default:* document `--frontend`; keep `--mode` as a hidden
  deprecated alias (`ui → gui`). If minimizing churn matters more, keep `--mode`
  with the narrowed value set and no alias.

## 7. Assumptions

- The user runs this on their own machines as their own user (`scope.md:73-75`).
- "No display server" means the Linux probe finds neither `DISPLAY` nor
  `WAYLAND_DISPLAY` (`config.py:26`), or the orb cannot be shown for another
  stated reason; macOS is treated as having a GUI unless Q2 changes it.
- The TUI presents the same information as the GUI orb; no new states are
  introduced. Any new state requires the grayscale/cue check in
  `orb-states.md:165-170`.
