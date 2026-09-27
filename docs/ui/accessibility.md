# Accessibility

Accessibility is a requirement, not polish: REQ-ORB-007 says every control has
an accessible name and is keyboard-operable, reduced motion is honored, and state
is never color-only. This file is the acceptance spec for that requirement.

## Contrast

**Target: WCAG 2.2 Level AA** for all text and essential UI.

| Text kind | Minimum ratio | Token | Measured | Passes |
| --- | --- | --- | --- | --- |
| Body text (< 18.66 px) | `4.5:1` | `colorTextPrimary` on `colorSurface` | 15.2:1 | AA, AAA |
| Secondary text | `4.5:1` | `colorTextSecondary` on `colorSurface` | 7.1:1 | AA, AAA |
| Muted text (timestamps) | `4.5:1` | `colorTextMuted` on `colorSurface` | 5.0:1 | AA |
| Accent on surface | `4.5:1` | `colorAccent` on `colorSurface` | 9.1:1 | AA, AAA |
| Danger on surface | `4.5:1` | `colorDanger` on `colorSurface` | 6.6:1 | AA |
| Warning on surface | `4.5:1` | `colorWarning` on `colorSurface` | 11.0:1 | AA, AAA |
| Success on surface | `4.5:1` | `colorSuccess` on `colorSurface` | 9.5:1 | AA, AAA |

Non-text essential UI (WCAG 2.2 SC 1.4.11, ≥ `3:1`):

| Element | Ratio vs adjacent bg | Passes |
| --- | --- | --- |
| Focus ring `colorFocus` (`#8BD5FF`) on `colorBg` | 12.2:1 | Yes |
| Control icon on `surfaceRaised` (`colorTextPrimary`) | 14.2:1 | Yes |
| Border `colorBorderStrong` on `colorSurface` | 1.7:1 | **Decorative only** — never the sole indicator |
| Backend badge text (`colorTextSecondary`) on `surfaceRaised` | 6.6:1 | Yes |

The orb body is **not** text and is **not** a contrast requirement in the WCAG
sense; it is a state indicator, so it is covered by the non-color rule instead.
If the orb sits over a light desktop wallpaper in transparent mode, the field
glow may blend; the opaque fallback
([layout.md](layout.md#wayland-degradation)) is the mitigation, and the state
label is the text fallback.

**Hard rule:** `colorTextMuted` is the dimmest token allowed to carry text.
Nothing dimmer than 5.0:1 is used for any label.

## Reduced motion

Triggered by the OS setting (macOS "Reduce motion", GNOME "Reduce animations")
and by `Theme.reducedMotion`, which the orb reads at startup and on change.

| Motion | Normal | `reduced_motion` |
| --- | --- | --- |
| Orb breath (`idle`) | Scale `1.00→1.03`, 4 s | **Off**; a static solid ring |
| `listening` ring contraction | Level-driven | **Off**; a static ring sized to the mean level |
| `transcribing` counter-rotation | 700 ms | **Off**; ring form `dual` held static |
| `thinking` arc rotation | 1400 ms | **Off**; arc held static |
| `speaking` ripples | Outward ripples | **Off**; body scale still tracks level in a small range (±3 %) **PLACEHOLDER** |
| `error` jagged pulse | 1800 ms | **Off**; jagged ring held static |
| `connecting` dash rotate | 2400 ms | **Off**; dashed ring held |
| Hue crossfades | `320 ms` | `80 ms` opacity cut |
| Panel morph | `420 ms` | Instant resize |
| Autoscroll | Smooth | Instant jump |
| Hover reveals | `durFast` | Instant appearance (no fade), still delayed |
| Toast/banner | Slide/fade | Instant appear; no auto-dismiss motion |

Under `reduced_motion`, state is still fully legible because hue, ring form, and
the state label remain — only the time-varying motion is removed. This is exactly
why the design uses three channels
([README.md](README.md#three-independent-state-channels)).

| Rule | Detail |
| --- | --- |
| Motion is decoration, never information | Anything that moves must also be readable when frozen |
| The level is still exposed as text | The state label reads e.g. "Listening — mic level 42 %" under reduced motion, so audio reactivity is not lost, only animated |
| Detection | `QStyleHints` / the platform's reduced-motion hint where available; otherwise `Theme.reducedMotion` config; **default to respecting the OS** |

## Keyboard reachability

| Rule | Detail |
| --- | --- |
| Every action is keyboard-reachable | No control is mouse-only (REQ-ORB-003) |
| Every control has a shortcut or is in the tab order | See [interactions.md](interactions.md#input-map) |
| Tab order is logical | [interactions.md § Tab order](interactions.md#tab-order) |
| Focus is trapped in the window while expanded | Small modal-ish window; escape to desktop is via `Cmd/Ctrl+W`, not `Tab` |
| `Esc` always resolves | Fixed order, [interactions.md § Escape](interactions.md#escape-resolution-order) |
| No keyboard trap without exit | A trapped tab ring is acceptable because `Esc` and `Cmd/Ctrl+W` always exit; document it |
| Shortcuts are shown | Buttons expose their shortcut in the tooltip and accessible description |
| Global hotkeys are optional | If unavailable (Wayland), the UI is still complete ([interactions.md](interactions.md#keyboard--window--global)) |

## Focus ring

| Property | Value |
| --- | --- |
| Color | `Theme.colorFocus` = `#8BD5FF` |
| Width | `2 dp` |
| Offset | `2 dp` outside the element bounds |
| Shape | Follows the element's radius (pill controls get a pill ring) |
| Visibility | **Always** on keyboard focus; hidden on pointer focus only, and only when the platform convention does so |
| Never removed | `outline: none`-equivalent is forbidden; a custom ring replaces the default, it does not vanish |
| Over the orb | The orb's focus ring is a `colorFocus` ring at `orbSizeCompact / 2 + 4 dp`, drawn above the field |

Focus indication must meet `3:1` against the adjacent background; `colorFocus` on
`colorBg` is 12.2:1.

## Screen-reader labeling

The orb is a frameless window, so it has no title bar and no native window
chrome for a screen reader to announce. Every accessible name is therefore
explicit.

| Element | Accessible name (`Accessible.name`) | Role | Description |
| --- | --- | --- | --- |
| Window | `"jarvis assistant orb"` | Window | `"Ambient assistant status window"` |
| Orb (compact) | `"Assistant status: <state>"` | Image / Indicator | `"Activate to open the transcript panel"` |
| Orb (expanded header) | `"Assistant status: <state>"` | Button | `"Activate to collapse the panel"` |
| State label | the state name | Static text | Live region; announces state changes |
| Mute | `"Mute"` / `"Unmute"` (toggles) | Toggle button | `"Keyboard shortcut Cmd+M"` |
| Stop | `"Stop"` / `"Interrupt"` | Button | Disabled when no turn is active |
| Backend badge | `"Backend: <harness>, model <model>"` | Button | Opens details |
| Settings | `"Settings"` | Button | — |
| Transcript toggle | `"Show transcript"` / `"Hide transcript"` | Toggle button | — |
| Quit | `"Quit orb"` | Button | `"The assistant keeps running"` |
| Composer | `"Message"` | Text field | `"Type a message. Enter to send, Shift+Enter for a new line"` |
| Send | `"Send message"` | Button | Disabled when empty |
| Mic | `"Push-to-talk"` | Button | `"Hold to talk, or tap to toggle"` |
| Transcript list | `"Transcript"` | List | `"N messages"` |
| Transcript row | `"<speaker>, <time>: <text>"` | List item | — |
| Error row | `"Error, <class>: <message>. <hint>"` | List item | Live region, `assertive` |
| Jump-to-latest | `"Jump to latest, N new messages"` | Button | — |

### Live regions

| Event | Politeness | Announcement |
| --- | --- | --- |
| `voice.state` change | `polite` | "Listening", "Thinking", "Speaking", "Idle" |
| Streaming delta | **none** | Announcing every fragment is noise; the final text is announced instead |
| `agent.final` | `polite` | The finalized assistant text |
| Error | `assertive` | The error class and message |
| Backend down / up | `polite` | "Backend unavailable" / "Backend available" |

### The honest caveat

**Qt Quick accessibility coverage is uneven on macOS and Linux.** `Accessible.*`
properties are largely honored on Linux under AT-SPI, but the macOS bridge
(Qt's `QAccessible` → NSAccessibility) does not reliably expose all QML roles,
live regions, or custom hit areas, and screen-reader support for a frameless,
transparent, always-on-top QML window is not fully verified on either platform.
This is stated, not hidden:

| Claim | Status |
| --- | --- |
| Accessible names are set on all controls | Design requirement; implementation-verifiable by inspection |
| AT-SPI (Linux) exposes roles, names, and live regions | Expected; **unverified** until tested with Orca |
| VoiceOver (macOS) reads the QML window and controls | **Unverified**; Qt's macOS QML a11y bridge is partial and known to lag |
| Live-region announcements work on macOS | **Unverified; likely partial** |

Mitigations, given the caveat:

1. **Never rely on a11y alone.** Every state has a visible text label; every
   control is in the tab order; the transcript is a real, selectable list.
2. **Console parity.** The console frontend shows the same transcript, status,
   and errors (REQ-CONSOLE-003), so a user who cannot use the orb has a complete
   text interface.
3. **Test with real screen readers on target** — Orca on Linux, VoiceOver on
   macOS — before claiming conformance. Marked `unverified` in
   [trace.md](../testing/trace.md). Do not claim "accessible" beyond what is
   tested.

## Colorblind-safe cues

Every state carries a non-color cue (REQ-ORB-007). Summary; full table in
[orb-states.md](orb-states.md#the-full-state-table).

| State | Cue when hue is lost |
| --- | --- |
| `idle` | Still/slow breath, solid ring, text "Idle" |
| `connecting` | Dashed rotating ring, text "Connecting…" |
| `muted` | Full slash chord, no motion, muted glyph, text "Muted" |
| `listening` | Ring contracts inward, text "Listening" |
| `transcribing` | Two counter-rotating segments (fastest), text "Transcribing" |
| `thinking` | Single rotating arc + motes, text "Thinking" |
| `speaking` | Ring expands outward, text "Speaking" |
| `error` | Jagged ring, `!` badge, text "Error" |
| `backend-down` | Bar chord, warning badge, text "Backend down" |

The grayscale pairwise check (luminance + form + motion) is in
[orb-states.md § Grayscale check](orb-states.md#grayscale-check). It is the
acceptance gate: a new state that is not distinguishable in grayscale is
rejected.

## Motion safety

| Rule | Value |
| --- | --- |
| No flashing above 3 Hz | **Hard limit.** No orb layer may cycle opacity or brightness faster than `3 Hz` (WCAG 2.3.1 flashing threshold). The fastest designed motion is `transcribing` at `1 / 0.7 s ≈ 1.4 Hz` |
| No full-screen flashes | The orb never fills the window with an alternating bright/dark field |
| Max luminance swing per cycle | The `error` pulse and `speaking` ripples stay well below the flash threshold; verify by inspection against T-0206 |
| Reduced motion removes all periodic animation | See [§ Reduced motion](#reduced-motion) |
| User override | `display.reduced_motion: true` forces it regardless of OS |
| Pause on occlusion | Motion stops when the window is hidden/minimized |
| Level never strobes | Attack/decay smoothing (`τ ≥ 0.045 s`) caps the update rate well under 3 Hz even on a 20 Hz stream ([audio-reactivity.md](audio-reactivity.md#attackdecay-smoothing)) |

If a future state wants a faster pulse, it must stay ≤ 3 Hz **and** be
disable-able by reduced motion, or it is not allowed.

## Minimum hit target size

| Rule | Value | Standard |
| --- | --- | --- |
| Absolute minimum | `24 × 24 dp` | WCAG 2.2 SC 2.5.8 (AA) |
| Icon buttons | `32 × 32 dp` | Comfortable on desktop and touch |
| Primary targets (orb, mic) | `44 × 44 dp` | Large, forgiving |
| Composer field | full width × `40 dp` | — |
| Spacing between targets | ≥ `8 dp` (`space2`) | Prevents mis-taps |
| Compact orb | the whole `112 dp` window is the target | — |

Targets may visually be smaller than their hit area (a `20 dp` icon inside a
`32 dp` button) as long as the **hit area** meets the minimum.

## Related

- [orb-states.md](orb-states.md) — the grayscale check this file enforces.
- [components/controls.md](components/controls.md) — accessible names per control.
- [interactions.md](interactions.md) — keyboard map and Escape order.
- [../testing/TEST_PLAN.md](../testing/TEST_PLAN.md) — T-0206 reduced-motion case.
