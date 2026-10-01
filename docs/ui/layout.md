# Layout and Window Behavior

Two window modes, one window, one transcript. The window **morphs** between
compact and expanded — it never opens a second window
([orb-ui.md § Window behavior](../requirements/features/orb-ui.md#window-behavior)).

All sizes are **PLACEHOLDER**: tune against a real desktop on both OSes. Ranges
are in brackets.

## Window modes

| Mode | Purpose | Contents | Size | Default |
| --- | --- | --- | --- | --- |
| **Compact ambient** | Glanceable presence; the resting state | Orb + state label + a minimal control reveal | `112 × 112 dp` **PLACEHOLDER** [88–160] | Yes |
| **Expanded panel** | Read the transcript, type, control | Header (orb + badge), transcript, composer, control bar | `420 × 560 dp` **PLACEHOLDER** [360–520 × 420–720] | No |

Both modes are frameless with a transparent background where the compositor
supports it; on Wayland they degrade to an opaque rounded window
([§ Wayland degradation](#wayland-degradation)).

| Property | Compact | Expanded | Token |
| --- | --- | --- | --- |
| Width | `windowCompactSize` | `windowExpandedWidth` | [tokens.md](tokens.md#geometry-and-window-sizing) |
| Height | `windowCompactSize` | `windowExpandedHeight` | |
| Radius | circle (window is square) | `radiusXl` | |
| Padding | `space4` around the orb | `space6` outer, `space4` inner | |
| Min usable size | n/a (fixed) | `360 × 420 dp` | |

### Mode switching

| From | To | Trigger | Motion |
| --- | --- | --- | --- |
| Compact | Expanded | Click orb; `Toggle transcript`; `Ctrl/Cmd+T` | Morph: width/height animate over `Theme.durSlow` = `420 ms`, `easeInOutQuad`; content crossfades `durFast` |
| Expanded | Compact | Click header orb; `Esc`; toggle again | Reverse morph; if the composer has text, `Esc` clears text instead of collapsing (see [interactions.md](interactions.md#escape-resolution-order)) |
| Either | Either | `reduced_motion` | No morph animation; instant resize, content crossfade `80 ms` |

The morph anchors to the **top-left** of the persisted geometry so the window
does not jump. Geometry is persisted per mode (below).

## Compact ambient mode

Zones, back to front:

| Zone | Content | Size |
| --- | --- | --- |
| Z1 — Orb | The full orb, centered | `orbSizeCompact` |
| Z2 — State label | One line of `typeCaption`, `colorTextSecondary`; visible on hover, on keyboard focus, or when `reduced_motion` is on | full width, `space5` from orb |
| Z3 — Control reveal | On hover/focus: mute, stop, and transcript buttons appear as a row below the orb; they fade in `durFast` | `hitIcon` each, `space2` gap |
| Z4 — Drag handle | The orb itself is the drag surface (see [interactions.md](interactions.md#drag)) | — |

The compact window shows **no** transcript. It must remain one glance: an orb and
its label.

## Expanded panel

Zones, top to bottom:

```
┌─────────────────────────────────────────────┐
│ H: Header   [ (orb) jarvis · native·qwen3 ]  │  ← Z1
├─────────────────────────────────────────────┤
│ T: Transcript (scrollable)                   │  ← Z2
│    user / assistant / tool / error rows      │
│                                              │
├─────────────────────────────────────────────┤
│ C: Composer  [ type a message…      ] [→] [🎤]│  ← Z3
├─────────────────────────────────────────────┤
│ B: Control bar  [mute][stop][badge][⚙][⤢][✕] │  ← Z4
└─────────────────────────────────────────────┘
```

| Zone | ID | Height | Contents | Detail |
| --- | --- | --- | --- | --- |
| Header | Z1 | `64 dp` | Orb (`orbSizeExpanded`), identity name, backend badge | [components/controls.md § Backend badge](components/controls.md#backend-badge) |
| Transcript | Z2 | flexible (fills) | Role-labelled rows | [components/transcript.md](components/transcript.md) |
| Composer | Z3 | `hitComposer` + `space4` | Text field, send, mic-hold | [components/composer.md](components/composer.md) |
| Control bar | Z4 | `48 dp` | Mute, stop, settings, transcript toggle, quit | [components/controls.md](components/controls.md) |

Vertical rhythm: `space4` panel inner padding; `space5` between the transcript
and the composer; `space2` between composer and control bar.

### Header

| Element | Position | Token |
| --- | --- | --- |
| Orb | Leading, vertically centered | `orbSizeExpanded` |
| Identity name | After the orb, `space3` gap | `typeTitle` |
| Backend badge | Trailing | `typeLabel`, `radiusSm`, `surfaceRaised` |
| Live state label | Under the identity name | `typeCaption`, `colorTextMuted` |

The header orb is the **same** orb component at a smaller size; state, motion,
and level still apply.

## Transcript behavior

The transcript is an append-only scrolling view backed by a `ListModel` in QML.
Full row spec: [components/transcript.md](components/transcript.md).

| Behavior | Rule |
| --- | --- |
| Role label | Each row has a speaker: `user`, `assistant`, `tool`, `error` |
| Timestamp | Local wall clock `HH:MM:SS`, `typeCaption`, `colorTextMuted`, right-aligned |
| Streaming | `agent.delta {kind:"text", text, index}` appends fragments to the **current assistant row** |
| `thinking` kind | `agent.delta {kind:"thinking"}` renders dimmed/italic in its own collapsed sub-row; never spoken (REQ-ORB-005, [schemas.md](../contracts/schemas.md)) |
| Monotonic index | Fragments are keyed by `index`; an out-of-order fragment triggers a resync request rather than a silent hole ([components/transcript.md](components/transcript.md#deltas-and-resync)) |
| `agent.final` | Replaces the assembled delta text for the turn; usage is shown as a `typeMono` footer |
| Scrollback | Bounded to `Theme.transcriptMaxTurns` = `500` **PLACEHOLDER** [200–2000] rows; oldest evicted. Persistence is the memory store's job (REQ-CONV-004), not the view's |
| Empty state | "No messages yet. Say \"<first hotword>\" or type below." centered, `colorTextMuted`, `typeBody`. The phrase comes from `voice.hotwords`, not a literal |

### Autoscroll

| Condition | Behavior |
| --- | --- |
| **Pinned-bottom** (default) | The view stays scrolled to the newest row as deltas arrive |
| User scrolls up | Unpins; a **jump-to-latest** pill appears at the bottom edge showing the count of new rows |
| New delta while unpinned | Row is appended but the view does not move; pill count increments |
| Click jump-to-latest | Smooth scroll to bottom `durBase`, re-pins |
| User scrolls back to within `24 dp` of the bottom | Re-pins automatically; pill hides |
| Turn starts while unpinned | Does **not** force a scroll; the pill is the only affordance |
| `reduced_motion` | Jump is instant (no smooth scroll) |

The pill is `32 dp` tall, `radiusPill`, `surfaceRaised`, `typeLabel`, and carries
its own accessible name ("Jump to latest, N new messages"). It must be operable
by keyboard (`Tab` reaches it; `Enter` activates).

## Window behavior

| Aspect | Behavior | Config / token |
| --- | --- | --- |
| Frameless | `Qt.FramelessWindowHint`; no title bar, no OS chrome | fixed |
| Transparent | `Qt.WA_TranslucentBackground`; the orb's field fades into the desktop | fixed, degrades (below) |
| Always-on-top | `Qt.WindowStaysOnTopHint` applied only when configured | `display.always_on_top` (REQ-ORB-004) |
| Positioning | On Wayland, compositor-mediated; the orb requests but may not receive | fixed |
| Dragging | Frameless windows cannot use the OS title bar; use `startSystemMove()` on the orb / a header drag | [interactions.md](interactions.md#drag) |
| Geometry persistence | Position, size, mode, and monitor are saved on move/resize (debounced `500 ms` **PLACEHOLDER** [250–1000]) and restored on launch | `display.geometry` (REQ-ORB-004) |
| Multi-monitor | Restore to the saved monitor if present; else center on the primary | — |
| Off-screen guard | If the saved position is entirely off all current screens, recenter on the primary and log it | — |
| Focus steal, idle | Starting in `idle` shows the window **without activating it** — no focus steal (REQ-ORB-004, T-0201) | `Qt.WindowDoesNotAcceptFocus` at idle, or deferred `show()` |
| Focus steal, active | When the user opens the panel or the orb enters `error`, the window may take focus | — |
| Appear | The window appears on `status.assistant.ready`; before that it is hidden | `status.assistant.ready` |
| Close | `✕` / `Cmd-W` hides to tray-or-exit per preference; the **assistant keeps running** — the orb is a client | — |

### Focus policy detail

The idle orb must not steal focus. The pragmatic sequence:

1. Create the window hidden.
2. On `status.assistant.ready`, show it with `show()` and **not** `raise_()` /
   `activateWindow()`.
3. Set `Qt.WindowDoesNotAcceptFocus` while in `idle` with no transcript focus.
4. When the user interacts (click, hotkey, error), clear the flag and allow
   focus.

This is the same intent as `display.always_on_top`: configurable and
non-invasive. Verify on both OSes (T-0201). Note that some window managers
ignore focus hints; the honest caveat is that "no focus steal" is best-effort on
Linux.

## Wayland degradation

Wayland does not let clients reliably set always-on-top, position, or focus, and
frameless transparency depends on the compositor
([ui-stack.md § Platform caveats](../research/ui-stack.md#platform-caveats),
[ADR-0013](../architecture/decisions/ADR-0013-pyside6-orb.md)).

| Capability | X11 / Xwayland | Wayland (native) | Degradation |
| --- | --- | --- | --- |
| Always-on-top | Works | Not guaranteed | If the hint is refused, continue; do not error. Show a first-run note that the window may not stay above others |
| Client positioning | Works | Not guaranteed; getters may return `0,0` | Do not trust saved coordinates; center or let the compositor place the window |
| Frameless transparency | Works | Compositor-dependent | **Fallback: opaque rounded window.** Use `colorBg` as the base with `windowRadiusOpaque`; the orb keeps a `colorBorder` hairline so it reads as an object, not a hole |
| Global hotkeys | Native APIs | `org.freedesktop.portal.GlobalShortcuts` may prompt | A separate scoped item (REQ-WAKE-004 caveat); the orb's own controls always work |
| Focus | Works | Compositor-mediated | Best-effort; never rely on it for correctness |

### Detecting the fallback

| Signal | Action |
| --- | --- |
| `QGuiApplication.platformName()` contains `wayland` | Set `Theme.isWayland` = `true` |
| `Theme.isWayland` and transparency probe fails | `Theme.opaqueFallback` = `true`; use `colorBg` + `radiusXl` + `colorBorder`, no root transparency |
| Transparency works under Wayland | Use transparent mode; still apply the positioning caveat |
| `Theme.opaqueFallback` | The orb's field glow blends into `colorBg` rather than the desktop; the design must look intentional, not clipped |

The mockup shows both the transparent and the opaque-fallback presentation
([mockup.html](mockup.html)).

## Related

- [tokens.md](tokens.md) — every size above.
- [components/transcript.md](components/transcript.md) — transcript rows in detail.
- [components/composer.md](components/composer.md), [components/controls.md](components/controls.md).
- [interactions.md](interactions.md) — drag, focus, Escape, hotkeys.
