# Component — Controls

The control bar (expanded) and control reveal (compact): mute, stop/interrupt,
backend badge, settings, transcript toggle, quit. Every control has an accessible
name, a keyboard shortcut, and state variants (REQ-ORB-003, REQ-ORB-007).

File: `orb/Controls.qml`. Badge data comes from `status.harness`
([schemas.md](../../contracts/schemas.md)).

## Control bar layout

Expanded, zone Z4, `48 dp` tall:

```
[ 🔇 Mute ] [ ■ Stop ]      [ native · qwen3 ]   [ ⚙ ] [ ⤢ ] [ ✕ ]
   left group                    center badge      right group
```

| Region | Contents | Spacing |
| --- | --- | --- |
| Left | Mute, Stop | `space2` |
| Center | Backend badge | centered |
| Right | Settings, Transcript toggle, Quit | `space2` |

Compact: a reveal row under the orb with Mute, Stop, Transcript toggle only
([layout.md](../layout.md#compact-ambient-mode)).

All controls are `hitIcon` = `32 dp`, `radiusMd`, icon `20 dp`, label
`typeLabel`. Hover raises the surface to `colorSurfaceHover`; press
`colorSurfaceActive`; focus draws the `colorFocus` ring.

## Mute

| Variant | Icon | Accessible name | Visual | Behavior |
| --- | --- | --- | --- | --- |
| Unmuted | microphone | "Mute" | `colorTextPrimary` icon, `colorSurfaceRaised` bg | Publishes `command.voice.mute {muted: true}` |
| Muted | microphone-slash | "Unmute" | `stateMuted` icon/bg tint, `muted` text | Publishes `command.voice.mute {muted: false}`; returns to the configured listen mode |
| Hover | — | — | `colorSurfaceHover` | — |
| Focus | — | — | `colorFocus` ring | — |
| Disabled | — | "Mute, unavailable while the bridge is unreachable" | 40 % opacity | Bridge down |

| Property | Value |
| --- | --- |
| Shortcut | `Cmd/Ctrl+M` |
| Publish topic | `command.voice.mute` with `{muted: bool}` |
| State sync | The button reflects `voice.state: muted` from the bus; it does not toggle its own appearance beyond press feedback |
| Effect | Capture stops immediately (REQ-WAKE-007); the orb shows `muted` |
| Non-color cue | The slash icon and the "Muted" text; never color alone |

## Stop / Interrupt

One control, labelled by context.

| Variant | Icon | Label | Accessible name | Enabled when |
| --- | --- | --- | --- | --- |
| Idle | stop (square) | "Stop" | "Stop" | A turn is active (`transcribing`/`thinking`/`speaking`) |
| Active | stop (square) | "Stop" | "Interrupt" | — |
| Busy press | spinner | "Stopping…" | "Stopping" | Within `250 ms` of the press, until the bus confirms |
| Disabled | stop, 40 % | "Stop" | "Stop, no active turn" | No turn |
| Hover / focus | — | — | — | standard |

| Property | Value |
| --- | --- |
| Shortcut | `Cmd/Ctrl+.` (global-ish, always reachable) |
| Action | Publish `command.agent.interrupt {}` |
| Optimistic feedback | Presses, shows "Stopping…" |
| Settle | Clears on `voice.state` change; the orb follows the bus, not the click ([interactions.md](../interactions.md#interrupt-semantics)) |
| Debounce | `250 ms` **PLACEHOLDER** [150–400] between publishes |
| Colors | `colorDanger` when active; `colorTextSecondary` when idle |

The control is **single-purpose**: stop cancels a turn and playback. "New session"
is a separate action in the context menu and `Cmd/Ctrl+Shift+.`, so a mis-click
never silently discards the context.

## Backend badge

Shows the active harness and model from `status.harness {harness, model}`
([schemas.md](../../contracts/schemas.md)). It is the answer to "which brain am I
talking to", and it is the recovery affordance for a dead backend.

| State | Appearance | Accessible name |
| --- | --- | --- |
| Healthy | `typeLabel` text "native · qwen3:latest", `colorTextSecondary`, `radiusSm`, `colorSurfaceRaised` | "Backend: native, model qwen3:latest" |
| Healthy + click | Opens a details popover: harness, model, capability note, and a **Switch harness** entry (restart-scoped, per flow (e)) | — |
| Backend down | `colorWarning` tint, `!` glyph, text "backend down" | "Backend unavailable. Activate for details" |
| Probing | subtle pulsing dot `1200 ms`, text "probing…" | "Probing backend" |
| Unknown / not yet reported | text "backend: —" | "Backend unknown" |

| Property | Value |
| --- | --- |
| Data source | `status.harness` only; the orb never queries the harness itself ([MOD-0008](../../architecture/modules/orb.md)) |
| Popover | Non-modal; `Esc` closes ([interactions.md](../interactions.md#escape-resolution-order)) |
| Retry | The popover offers **Retry** when down (REQ-ERR-002) |
| Harness switch | Opens the settings panel; the switch is restart-scoped and the badge notes that |
| Color cue | `colorWarning` for down; text + `!` for non-color |
| Tooltip | "Active agent harness and model" |

There is **no silent fallback**; a down backend stays down and is named
(REQ-HARNESS-006). The badge never shows a harness other than the one the bus
last reported.

## Settings

| Property | Value |
| --- | --- |
| Icon | gear |
| Accessible name | "Settings" |
| Shortcut | `Cmd/Ctrl+,` |
| Action | Opens the settings panel (modal-ish, trapped focus, `Esc` closes) |
| Settings scope | A **small** panel: listen mode, mute, always-on-top, reduced motion, transcript size, orb shader toggle, identity, quit. The full config stays a file ([README.md § Non-goals](../README.md#non-goals)) |
| Changes | Take effect where possible without restart; items that require a restart say so |
| Disabled | Never (settings must always be reachable, including when the bridge is down) |

The settings panel is deliberately not designed in detail here; it is a small
list of toggles using the same tokens and controls. It must not become a config
editor.

## Transcript toggle

| Variant | Icon | Accessible name | Action |
| --- | --- | --- | --- |
| Collapsed | expand / panel | "Show transcript" | Morph compact → expanded |
| Expanded | collapse / chevron | "Hide transcript" | Morph expanded → compact |
| Hover / focus | — | — | standard |
| Disabled | — | — | never |

| Property | Value |
| --- | --- |
| Shortcut | `Cmd/Ctrl+T` |
| Same action as | Clicking the orb ([layout.md](../layout.md#mode-switching)) |
| State | Reflects the current window mode |

## Quit

| Property | Value |
| --- | --- |
| Icon | close / power |
| Accessible name | "Quit orb" |
| Shortcut | `Cmd/Ctrl+Q` (mac) / `Ctrl+Q` |
| Action | Quits the **orb process**; the assistant keeps running |
| Confirmation | **None.** Quit is reversible (relaunch), so a confirm dialog would be noise |
| Destructive styling | `colorDanger` text on hover only; never a filled red button in the resting bar |
| Last in tab order | Yes ([interactions.md](../interactions.md#tab-order)) |
| Non-color cue | Accessible name and tooltip both say "the assistant keeps running" |

A separate **Hide window** action (`Cmd/Ctrl+W`) hides without quitting, for
users who want the orb gone but the assistant alive. Hide is not a control-bar
button; it is a shortcut and a menu item.

## Context menu

Right-click, or `Menu`/`Shift+F10`, opens the same actions plus the two that do
not earn a bar slot:

| Item | Shortcut | Notes |
| --- | --- | --- |
| Push-to-talk | `Cmd/Ctrl+Shift+Space` | Start/stop |
| Mute / Unmute | `Cmd/Ctrl+M` | Mirrors the button |
| Stop | `Cmd/Ctrl+.` | Mirrors the button |
| New session | `Cmd/Ctrl+Shift+.` | Starts a fresh context; destructive, so menu-only |
| Hide window | `Cmd/Ctrl+W` | — |
| Settings | `Cmd/Ctrl+,` | — |
| Quit | `Cmd/Ctrl+Q` | — |

Menu items are keyboard-navigable; the menu is `radiusMd`, `elevOverlay`,
`typeBody`, with focus rings.

## Shortcut summary

| Action | Shortcut | Global? | Notes |
| --- | --- | --- | --- |
| Show/hide orb | `Cmd/Ctrl+Shift+J` **PLACEHOLDER** | Global (native backend) | Fallback: app-local only |
| Push-to-talk | `Cmd/Ctrl+Shift+Space` **PLACEHOLDER** | Global (native backend) | — |
| Mute | `Cmd/Ctrl+M` | App | — |
| Stop / interrupt | `Cmd/Ctrl+.` | App | Works from any focus |
| New session | `Cmd/Ctrl+Shift+.` | App | Menu-only otherwise |
| Transcript toggle | `Cmd/Ctrl+T` | App | — |
| Settings | `Cmd/Ctrl+,` | App | — |
| Hide | `Cmd/Ctrl+W` | App | — |
| Quit | `Cmd/Ctrl+Q` / `Ctrl+Q` | App | — |
| Escape | `Esc` | App | Resolves per [interactions.md](../interactions.md#escape-resolution-order) |

Global shortcuts are accelerators, not requirements; every one has an
app-local keyboard path and a visible control
([README.md § Concept](../README.md#concept)).

## Accessible names, all controls

| Control | Name | Role | Shortcut in description |
| --- | --- | --- | --- |
| Mute | "Mute" / "Unmute" | Toggle | yes |
| Stop | "Stop" / "Interrupt" | Button | yes |
| Backend badge | "Backend: <harness>, model <model>" | Button | no |
| Settings | "Settings" | Button | yes |
| Transcript toggle | "Show transcript" / "Hide transcript" | Toggle | yes |
| Quit | "Quit orb" | Button | yes |
| PTT (context) | "Push-to-talk" | Button | yes |
| New session (context) | "New session" | Button | yes |
| Hide (context) | "Hide window" | Button | yes |

Full labeling and live-region table: [accessibility.md](../accessibility.md#screen-reader-labeling).

## Related

- [layout.md](../layout.md) — zones and the header.
- [interactions.md](../interactions.md) — full input map and interrupt.
- [components/composer.md](composer.md) — the send and mic controls.
- [accessibility.md](../accessibility.md) — names and focus rings.
