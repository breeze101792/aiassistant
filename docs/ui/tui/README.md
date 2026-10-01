# TUI Orb Design

The design of the terminal orb: a full-screen `curses` interface that presents the
same ambient state and transcript as the GUI orb, adapted to text. It is the
terminal counterpart of [docs/ui/](../README.md).

Read this file → [tokens.md](tokens.md) → [states.md](states.md) →
[layout.md](layout.md). A `curses` implementer can build from these alone.
[mockup.txt](mockup.txt) holds literal captured frames.

Status legend, as in [docs/ui/README.md](../README.md): `draft` written, not yet
reviewed · `reviewed` passed `challenger` · `as-built` reflects shipped code ·
`unverified` no test or source confirms it.

## Files

| File | Subject | Status |
| --- | --- | --- |
| [README.md](README.md) | Index, concept, information model, non-goals | draft |
| [tokens.md](tokens.md) | Glyphs, attributes, color pairs + monochrome fallback, spacing | draft |
| [states.md](states.md) | Every state's label, form glyph, attribute, cue | draft |
| [layout.md](layout.md) | Regions, 80x24 and 120x40 wireframes, resize, too-small | draft |
| [mockup.txt](mockup.txt) | Literal captured frames (the TUI counterpart of `mockup.html`) | draft |

## What this designs against

| Fact | Value | Source |
| --- | --- | --- |
| Identity | default `jarvis` | [scope.md](../../requirements/scope.md) |
| Implementation | Python stdlib `curses` only; no `rich`, no `textual` | [ADR-0017](../../architecture/decisions/ADR-0017-frontend-selection-tui.md), [frontends.md §2.1](../../requirements/features/frontends.md) |
| Process | separate process, bus WebSocket client, `bridge.Bridge` | [ADR-0017](../../architecture/decisions/ADR-0017-frontend-selection-tui.md) |
| View model | reuses `OrbViewModel` (`orb/model.py`), Qt-free | [frontends.md §2.1](../../requirements/features/frontends.md) |
| Orb states | `connecting\|idle\|muted\|listening\|transcribing\|thinking\|speaking\|error` + `backend-down` and `transcript-error` overlays | [orb-states.md](../orb-states.md) |
| Topic surface | same subscribe/publish set as the GUI orb | [orb-ui.md §Data flow](../../requirements/features/orb-ui.md), [protocols.md IF-0004](../../contracts/protocols.md) |
| Constraints | keyboard-first, mouse optional, no animation, monochrome-safe, ASCII-first | [frontends.md §2.3–2.5, §5](../../requirements/features/frontends.md) |

## Concept

The GUI orb is a **presence indicator**: light that answers "is it listening,
thinking, speaking, or stuck?". The TUI orb is the same indicator rendered as
**text and form**. It is not the animated orb with the animation removed; it is a
different medium that carries the same information on channels a terminal
actually has: a word, a glyph, and a character-level form cue.

Three facts force the whole design:

1. **The TUI is non-color and non-animated by nature.** The GUI's hue channel and
   motion channel do not exist here. So the TUI carries state on the two
   remaining channels — **word** (the exact state label) and **form** (a
   three-character glyph whose shape encodes the same distinction the GUI ring
   form does). Color is added only as an enhancement.
2. **It must be usable with no color at all.** `TERM` may have no color, `NO_COLOR`
   may be set, or the user may be colorblind. Every state is separated by its
   label and glyph form; the attribute and color pair are decoration
   ([states.md § Never color-only](states.md#never-color-only)).
3. **It must be reachable with `curses`.** Every visual decision in this set maps
   to `addnstr`/`mvaddstr`, `attron`/`attroff`, `init_pair`, and `A_*`
   attributes. Nothing depends on RGB, Unicode box-drawing, or animation.

The GUI's fourth channel, **text**, is not a fallback here — it is the primary
channel. That is the point of the TUI.

## Information model — GUI orb to TUI orb

The TUI presents the same information as the GUI orb, not a reduced set
(REQ-FRONTEND-006). This table is the mapping an implementer should hold in mind;
the GUI column names the source doc.

| GUI orb element | TUI element | GUI source |
| --- | --- | --- |
| Orb body hue (state identity) | State label + form glyph in the header | [orb-states.md](../orb-states.md) |
| Orb ring form (solid / arc / dual / dashed / slash / bar / jagged) | Three-character form glyph | [states.md](states.md) |
| Orb motion (breath / rotate / ripple / pulse) | **Dropped.** No animation. The form glyph stands for it | this file, non-goals |
| Orb level reactivity (`voice.level`) | Text/bar meter, source-labelled, percent text | [layout.md § Level meter](layout.md#level-meter) |
| State label under the orb | State label in the header (always visible, not hover-gated) | [orb-states.md](../orb-states.md) |
| Transcript rows (user/assistant/tool/error/thinking) | Transcript rows, same roles and gutters | [components/transcript.md](../components/transcript.md) |
| Streaming cursor on the assistant row | `_` at the end of the streaming row | [mockup.txt](mockup.txt) |
| Backend badge (`status.harness`) | Header badge, text only | [components/controls.md § Backend badge](../components/controls.md#backend-badge) |
| Error row with recovery hint | Error row with `!` badge and `hint:` line | [interactions.md § Error row anatomy](../interactions.md#error-row-anatomy) |
| Composer (field, send, mic) | One `you>` composer line | [components/composer.md](../components/composer.md) |
| Control bar (mute/stop/scroll/clear/quit) | Status-bar key hints | [frontends.md §2.3](../../requirements/features/frontends.md) |
| Focus ring (`colorFocus`) | `A_REVERSE` on the focused element | [accessibility.md § Focus ring](../accessibility.md#focus-ring) |

The state set is exactly [orb-states.md](../orb-states.md); the TUI invents no
states. The overlay rules hold: `backend-down` and `transcript-error` layer on a
base state rather than replacing it.

## The layer model, restated for text

The GUI paints five concentric layers. The TUI has three flat channels. Each has
one job, and none repeats another.

```
  word  ── the exact state label ("Listening", "Backend down")
   form ── a 3-char glyph whose shape mirrors the GUI ring form
   meter ── the numeric level, as text and a character bar
```

| Channel | What varies | Carries | Always present |
| --- | --- | --- | --- |
| **Word** | One exact label per state | State identity, unambiguous to a screen reader and a human | Yes |
| **Form** | Three-character glyph shape | Fast visual read; the analogue of the GUI ring form | Yes |
| **Meter** | Character bar + percent text | `voice.level`, source-routed | In states that react to level; shown as 0 % elsewhere |

Color pair and `A_*` attributes are a fourth, strictly **additive** channel. They
never carry a distinction that word or form does not already carry.

## Non-goals

| Non-goal | Why |
| --- | --- |
| Mouse input, pane resizing, mouse scrolling | Keyboard only this round ([frontends.md §5](../../requirements/features/frontends.md)) |
| A braille/block animated orb | The GUI shader is the animated frontend; the TUI is textual ([frontends.md §5](../../requirements/features/frontends.md)) |
| Theming or configurable color schemes | The terminal's own palette is the base; color pairs are a fixed enhancement |
| Unicode box-drawing or emoji as required glyphs | They fail on minimal terminals and some SSH clients; ASCII is the baseline |
| A second source of truth | It renders `OrbViewModel`, which renders bus events; it derives nothing ([orb/model.py](../../../src/aiassistant/orb/model.py)) |
| A settings panel or config editor | The GUI orb owns that; the TUI is state, transcript, input, and controls |
| Persisting transcript history | The memory store owns persistence; the view is read-and-scroll |

## Implementation notes (handoff)

A `curses` implementer needs no guessing. The mapping from this design to the API:

| This design | `curses` call |
| --- | --- |
| Draw the header, a row, the meter | `mvaddstr(row, col, text)` / `addnstr` for a clipped body |
| State label `A_BOLD`, gutters `A_DIM` | `attron(A_BOLD)` / `attroff(A_BOLD)`, same for `A_DIM` |
| Streaming cursor, focus, selected row | `attron(A_REVERSE)` around the target cell(s) |
| Color pairs | `init_pair(cp, fg, bg)` at startup when `curses.has_colors()` |
| Repaint after a redraw or resize | `erase()` then draw then `refresh()` |
| Alternate screen | `curses.initscr()` / `endwin()` (in the TUI **child** process, per ADR-0017) |

Order of construction, top to bottom: read size → choose width class → register
color pairs (or not) → draw header, rule, transcript, meter, rule, composer,
status → `refresh()`.

What to avoid, explicitly:

- **Do not animate.** No `A_BLINK`, no periodic repaint for effect, no
  braille/block orb. Repaint only on a bus event, a key, or a resize.
- **Do not make color load-bearing.** Run the whole screen with `init_pair`
  removed and confirm every state is still readable; the word and the glyph must
  carry it. The monochrome fallback column in [tokens.md](tokens.md#color-pairs)
  is the checklist.
- **Do not assume Unicode.** Select the ASCII glyphs unless the locale is UTF-8
  and terminfo supports the glyphs; `-` rules are always valid.
- **Do not invent states or topics.** States come from `voice.state` and the two
  overlays; topics come from `bus.topics`, never a string literal.
- **Do not derive state.** Render `OrbViewModel` only; it already maps,
  smooths, and detects delta gaps.
- **Do not block the bus on drawing.** The TUI is a separate process (ADR-0017);
  it must never open audio devices and must never touch `agent/`.

Accessibility checklist for the handoff:

1. Every state is readable with color and all attributes stripped.
2. Every control is a key; `F1` lists them all.
3. `Esc` always resolves; it never quits.
4. `Ctrl+D` closes the TUI only; `/exit` shuts the assistant down.
   `endwin()` runs on every exit path, including a crash.
5. The too-small view still tracks state, so resizing back restores the newest
   data.
6. The streaming cursor and the focused element are `A_REVERSE`, the one
   functional attribute; nothing functional relies on a color pair.

## Related

- [tokens.md](tokens.md) — every glyph, attribute, and color pair used above.
- [states.md](states.md) — the state contract in full.
- [layout.md](layout.md) — regions and responsive behavior.
- [mockup.txt](mockup.txt) — literal frames.
- [../README.md](../README.md) — the GUI orb this mirrors.
