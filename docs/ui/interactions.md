# Interactions

Every input path, the interrupt sequence, and how errors surface without
blocking. Requirement: every control has an accessible name and a keyboard path
(REQ-ORB-003, REQ-ORB-007). No interaction is mouse-only.

Modifier shorthand: `Cmd` on macOS, `Ctrl` on Linux; written `Cmd/Ctrl`.

## Input map

### Mouse / pointer

| Gesture | Target | Action | Notes |
| --- | --- | --- | --- |
| **Hover** | Compact orb | Reveal the state label (Z2) and the control row (Z3) after `Theme.hoverDelay` = `120 ms` **PLACEHOLDER** [0–250] | Reveal fades in `durFast` |
| **Hover** | Expanded orb | Slightly raise field glow (+0.05); no layout change | — |
| **Left click** | Compact orb | Toggle expanded panel | Primary affordance from compact |
| **Left click** | Expanded header orb | Collapse to compact | — |
| **Left click** | Control button | The button's action | See [components/controls.md](components/controls.md) |
| **Double-click** | Compact orb | Toggle expanded **and** focus the composer | Fast path to typing; focus lands in the text field |
| **Right click** | Anywhere on the orb/window | Context menu: `Push-to-talk`, `Mute`/`Unmute`, `Stop`, `New session`, `Settings`, `Quit` | Same items as the control bar; accessible via the keyboard menu key too |
| **Drag** | Compact orb; expanded header | Move the window via `startSystemMove()` | See [§ Drag](#drag) |
| **Click** | Transcript row | Select the row's text (native selection); no action | Rows are read-only |
| **Click** | Jump-to-latest pill | Scroll to newest and re-pin | [layout.md](layout.md#autoscroll) |
| **Click** | Send button | Submit composer text | Disabled when empty (see [components/composer.md](components/composer.md)) |
| **Press-and-hold** | Mic button | Push-to-talk: capture while held, release to endpoint | See [§ Hold-to-talk](#hold-to-talk) |
| **Click** | Backend badge | Expand a popover listing `harness` + `model`; a "Retry" if backend-down | Non-modal; `Esc` closes |

### Keyboard — window / global

| Shortcut | Action | Scope | Notes |
| --- | --- | --- | --- |
| `Cmd/Ctrl+Shift+J` **PLACEHOLDER** [pick a collision-free chord] | Show/hide the orb | Global | **Needs a native backend** (macOS Event Tap / X11 grab / Wayland portal); REQ-WAKE-004 caveat. Falls back to app-local when unavailable |
| `Cmd/Ctrl+Shift+Space` **PLACEHOLDER** | Push-to-talk toggle (start/stop) | Global, app-focus optional | Same backend caveat |
| `Cmd/Ctrl+M` | Toggle mute | App | Publishes `command.voice.mute {muted}` |
| `Esc` | Context-dependent: cancel drag; close popover/menu; clear composer; collapse panel | App | Order in [§ Escape](#escape-resolution-order) |
| `Cmd/Ctrl+T` | Toggle transcript (compact ↔ expanded) | App | Same as clicking the orb |
| `Cmd/Ctrl+,` | Open settings | App | Opens the settings panel, not the config file |
| `Cmd/Ctrl+Q` (mac) / `Ctrl+Q` | Quit the orb process | App | Does **not** stop the assistant; the orb is a client |
| `Enter` | Send composer text | Composer focused | — |
| `Shift+Enter` | Insert a newline | Composer focused | Multi-line input |
| `Tab` / `Shift+Tab` | Move focus forward / backward | App | Order in [§ Tab order](#tab-order) |
| `Space` / `Enter` | Activate the focused control | App | Standard button behavior |
| `Cmd/Ctrl+W` | Hide the window (orb keeps running) | App | — |
| `Menu` key / `Shift+F10` | Open the context menu on the focused element | App | — |

The global hotkeys are **explicitly scoped and may be unavailable** on Wayland
([ui-stack.md](../research/ui-stack.md#platform-caveats)). The orb must work
fully without them; they are an accelerator, never the only path
([README.md § Concept](README.md#concept)).

### Keyboard — interrupt and stop

| Shortcut | Action |
| --- | --- |
| `Esc` while a turn is active and the composer is not focused | Interrupt the turn |
| `Esc` while a turn is active and the composer is focused, with text | Clear the text (do not interrupt) |
| `Esc` while a turn is active and the composer is focused, empty | Interrupt the turn |
| `Cmd/Ctrl+.` | Interrupt the turn (the platform-standard "stop") |
| `Cmd/Ctrl+Shift+.` | New session |

`Esc` is overloaded by design; the resolution order is fixed in
[§ Escape](#escape-resolution-order). Interrupt is always reachable by `Cmd/Ctrl+.` regardless of
focus, so the overload never traps the user.

## Escape resolution order

`Esc` does the **first** applicable thing, top to bottom:

1. Abort an in-progress window drag.
2. Close an open popover, menu, or badge details.
3. Close the settings panel.
4. Clear the composer text if it is non-empty and focused.
5. Interrupt the active turn if one is running (`voice.state` ∈
   `transcribing`, `thinking`, `speaking`).
6. Collapse the expanded panel to compact.
7. If already compact and idle: nothing (do not quit).

This order is a contract; changing it changes muscle memory.

## Drag

Frameless windows have no title bar, so dragging uses the platform move loop.

| Target | Behavior |
| --- | --- |
| Compact orb body | `press` → `window.startSystemMove()` on the first movement past `4 dp` (a slop threshold, so a click still toggles) |
| Expanded header | Same move; the rest of the window is not a drag surface (so the transcript stays scrollable) |
| Drag on a control or the composer | **Not** a drag; the control receives the event |
| Wayland | `startSystemMove()` may be compositor-mediated; if it fails, fall back to manually setting `window.x/y` from the pointer delta (works on X11; may be ignored on Wayland) |
| Persist | On `x/y` change, save geometry after a `500 ms` debounce |

## Hold-to-talk

Two modes exist for PTT (REQ-WAKE-004); the orb exposes both.

| Mode | Gesture | Start | End |
| --- | --- | --- | --- |
| **Hold** | Press and hold the mic button, or hold `Cmd/Ctrl+Shift+Space` | On press | On release — capture endpoints and the turn proceeds |
| **Toggle** | Tap the mic button, or tap `Cmd/Ctrl+Shift+Space` | First tap | Second tap |

| Condition | Behavior |
| --- | --- |
| `voice.listen.mode: ptt` | The mic button is the sole start affordance; state stays `idle` until armed |
| `voice.listen.mode: open` or `wake` | The mic button becomes a *mute* convenience; PTT still works as a temporary override |
| Muted | PTT is disabled; the button shows the muted state and its accessible name says "Push-to-talk, unavailable while muted" |
| No microphone | PTT disabled with the tooltip "No microphone" ([flows (h)](../requirements/flows.md#h-mic-or-speaker-unavailable)) |
| PTT start/end over the bus | **Undefined**: no topic exists yet ([IF-0007 gap](../contracts/protocols.md#if-0007-topic-registry)). The orb must not invent a topic. Until one lands, PTT drives the orb's local voice control surface or a documented local command; the UI is designed for the eventual bus path |

That last row is the single place this design is blocked on an upstream
contract. The UI is specified now; the wiring is marked here rather than
guessed.

## Interrupt semantics

Interrupt stops playback and cancels the in-flight turn. The **ordered** cancel
sequence is fixed by [IF-0008](../contracts/protocols.md#if-0008-voice-speak-and-interrupt-semantics)
and [flows (c)](../requirements/flows.md#c-interrupt); the orb's part is step 0
below.

| # | Actor | Action |
| --- | --- | --- |
| **0** | **orb** | **Publishes `command.agent.interrupt {}`** |
| 1 | `agent` | Receives the command |
| 2 | `agent` | Cancels the retained turn task |
| 3 | `agent` | Calls `harness.cancel()` — native: cancel the provider stream |
| 4 | `voice` | Stops playback; sets the stop flag |
| 5 | `voice` | Clears the TTS queue; unmutes the mic |
| 6 | `agent` | Ends the turn with `turn_done(cancelled=true)`; **no** `agent.final` |
| 7 | — | `voice.state: idle` |

The orb does **not** optimistically clear the transcript or the orb state on
click. It shows an immediate local acknowledgment (**the orb's stop affordance
presses; a subtle "stopping…" appears**) and then follows the bus: the state
returns to `idle` when `voice.state: idle` arrives. This is deliberate — the orb
displays what it receives ([MOD-0008 § OWNS](../architecture/modules/orb.md#owns))
and does not pretend a cancel succeeded before the assistant confirms it.

| Condition | Orb behavior |
| --- | --- |
| Interrupt with no active turn | The command is still published; the orb treats the result as a no-op and returns to `idle` |
| Interrupt while `speaking` | Playback stops within `voice.barge_in.stop_ms` (REQ-WAKE-005); the orb's `speaking` motion ends on the next state event |
| Interrupt during `listening` | Ends listening; back to `idle` |
| Double-interrupt | The second publish is a no-op; the orb debounces identical interrupts within `250 ms` **PLACEHOLDER** [150–400] |
| Stop pressed while `connecting` | Disabled; no turn can be active |
| Cancelled turn | The assistant row is marked "(cancelled)"; no `agent.final` arrives, so the delta text stays as streamed ([components/transcript.md](components/transcript.md)) |

## Error surfacing

Errors are **non-modal state plus an actionable line**. They never block input
(REQ-ORB-006): the composer stays typable and the transcript stays scrollable
during any error.

| Error source | Orb presentation | Dismiss | Recovery affordance |
| --- | --- | --- | --- |
| `agent.turn.error {class: "harness"}` | Orb overlay `backend-down`; header badge turns `colorWarning`; one transcript error row | Next successful turn event | Badge popover offers **Retry**; text still works |
| `agent.turn.error {class: "tool"}` | `transcript-error` row at the failing turn; orb ring jagged, hue retained | Next turn | Row names the tool and the error; input remains usable |
| `agent.turn.error {class: "config" \| "memory"}` | `transcript-error` row, `colorDanger` | Next turn | Row carries the recovery hint from the classified error (REQ-ERR-001) |
| Bridge unreachable (`ERR-ORB-BRIDGE-UNREACHABLE`) | Orb → `connecting` (`dashed` ring); a caption "Reconnecting…" | First forward received | Automatic retry with backoff; no user action required |
| Auth failure (`{"error":"auth failed"}`) | `connecting` + a caption "Auth failed — check token"; **does not** retry blindly | Manual | Caption names the config key `bus.remote_auth_token` |
| `voice.state: error` | Orb → `error` (`jagged`) | `voice.state` change | One-line message from the last classified error, if any |
| No display (`ERR-ORB-NO-DISPLAY`) | The orb exits; the assistant runs in console mode | — | Console message ([console fallback](../requirements/flows.md#i-first-run-setup)) |
| Shader unavailable (`ERR-ORB-SHADER`) | Silent fallback to the QML circle; **no** error UI | — | The orb looks simpler, it does not complain ([components/orb.md](components/orb.md#fallback)) |

### Error row anatomy

| Element | Style |
| --- | --- |
| Leading icon | `!` in `colorDanger`, `16 dp` |
| Class chip | `typeLabel`, `radiusSm`, background `surfaceRaised`, text names the class |
| Message | `typeBody`, `colorTextPrimary`; the human-readable `message` |
| Recovery hint | `typeCaption`, `colorTextSecondary`; only when the classified error carries one (REQ-ERR-001) |
| Timestamp | `typeCaption`, `colorTextMuted` |

Errors are announced to assistive tech via a live region
([accessibility.md](accessibility.md#screen-reader-labeling)).

## Tab order

Forward order in the expanded panel; compact has no tabbable content except the
orb itself and the revealed controls.

| # | Element | Notes |
| --- | --- | --- |
| 1 | Header orb | Acts as the collapse button; `Space`/`Enter` collapses |
| 2 | Backend badge | `Enter` opens the details popover |
| 3 | Transcript | A single focus stop; arrow keys scroll, `Home`/`End` jump |
| 4 | Jump-to-latest pill | Only present when unpinned; inserted here |
| 5 | Composer text field | — |
| 6 | Send button | — |
| 7 | Mic-hold button | — |
| 8 | Mute | — |
| 9 | Stop | — |
| 10 | Settings | — |
| 11 | Transcript toggle | — |
| 12 | Quit | Last, as the most destructive |

Rules:

- The tab ring is **trapped inside the window** while expanded; `Tab` from the
  last element wraps to the first. This is a small, modal-ish window, so trapping
  is kinder than letting focus escape into the desktop.
- In compact mode, `Tab` cycles only the orb and the revealed controls, then
  wraps.
- `Shift+Tab` reverses.
- Focus is visible at all times (`colorFocus`, 2 dp — [accessibility.md](accessibility.md#focus-ring)).
- Opening the panel moves focus to the transcript, not the composer, so the user
  can read first. Double-click on the orb is the fast path to the composer.

## Related

- [components/controls.md](components/controls.md) — each control and its shortcut.
- [components/composer.md](components/composer.md) — input validation and states.
- [accessibility.md](accessibility.md) — focus, labels, reduced motion.
- [layout.md](layout.md) — window behavior and autoscroll.
