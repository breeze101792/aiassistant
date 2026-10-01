# TUI States

The state contract for the TUI orb. It mirrors [../orb-states.md](../orb-states.md)
exactly: the same states, the same transitions, the same overlay rules. The TUI
does **not** invent states.

The GUI encodes each state on **hue**, **motion**, and **ring form**. The TUI has
only two real channels, because a terminal has no reliable color and this design
has no animation:

1. **Word** — the exact state label. Always present, always unique.
2. **Form** — a three-character glyph whose shape mirrors the GUI ring form.

Attribute and color pair are an **additive** channel only. They never carry a
distinction the word and the glyph do not already carry
([§ Never color-only](#never-color-only)).

Glyphs, attributes, and pairs are tokens from [tokens.md](tokens.md).

## State sources

Identical to [../orb-states.md § State sources](../orb-states.md#state-sources):

| Tier | States | Source | Lifetime |
| --- | --- | --- | --- |
| **Base** | `idle`, `listening`, `transcribing`, `thinking`, `speaking`, `error`, `muted` | `voice.state` | Until the next `voice.state` |
| **Orb-local** | `connecting` | The TUI's own bridge state (unreachable) | Until the first forward arrives, including the `voice.state.request` reply |
| **Overlay** | `backend-down` | `agent.turn.error` with `class: "harness"`, or a failed health probe | Until the next successful turn event or `voice.state` change |
| **Overlay** | `transcript-error` | `agent.turn.error` with `class` ≠ `harness` | Until dismissed or the next turn |

Overlays **layer** on the base state; they do not replace it. The header keeps the
base state's word and glyph, and the overlay is appended (backend-down) or shown
as an error row (transcript-error). Full behavior in
[../interactions.md § Error surfacing](../interactions.md#error-surfacing).

## The state table

The header row is the TUI's orb. It shows, left to right: the form glyph, the
state label, the overlay text if any, and the backend badge.

| State | Exact label | Form glyph (ASCII) | Label attribute | Color pair | Non-color cue (word + form) |
| --- | --- | --- | --- | --- | --- |
| `connecting` | `Connecting...` | `:o:` | `attrEmphasis` | `cpState` (blue) | The word; a dashed, colon-framed glyph |
| `idle` | `Idle` | `(o)` | `attrEmphasis` | `cpState` (cyan) | The word; a soft round frame |
| `muted` | `Muted` | `/o/` | `attrMuted` | `cpState` (grey) | The word; the slash frame; also the status bar reads `^T` to unmute |
| `listening` | `Listening` | `>o<` | `attrEmphasis` | `cpState` (green) | The word; an inward-pointing frame; the meter is live |
| `transcribing` | `Transcribing` | `}o{` | `attrEmphasis` | `cpState` (cyan) | The word; a doubled, opposed frame |
| `thinking` | `Thinking` | `~o~` | `attrEmphasis` | `cpState` (magenta) | The word; a wavy, rotating frame; a `Thinking` transcript row appears |
| `speaking` | `Speaking` | `<o>` | `attrEmphasis` | `cpState` (yellow) | The word; an outward-pointing frame; the meter is live |
| `error` | `Error` | `%o%` | `attrEmphasis` | `cpState` (red) | The word; a jagged frame; an `!Error` row |
| `backend-down` (overlay) | base label + `  ! Backend down` | base glyph (retained) | `attrEmphasis` | `cpWarn` | The words "Backend down"; an `!Error` row with `[harness]` |

The badge (right-aligned in the header) reads `native / qwen3:latest` from
`status.harness`; when `backend-down` is set it gains a trailing ` !` and uses
`cpWarn`. The TUI requests `status.harness` on every connect, so it fills shortly
after the bridge connects rather than waiting for a harness change. The
badge is data, not a state, so it does not change the state label.

### `error` versus `transcript-error`

Two distinct things, deliberately:

- **`error`** is a **base state** from `voice.state: error`. It replaces the
  header glyph with `%o%` and the label with `Error`; the `!Error` transcript row
  carries the message and hint.
- **`transcript-error`** is an **overlay** for `agent.turn.error` where
  `class` ≠ `harness`. The **base state and its glyph are retained**; the failure
  appears as an `!Error` transcript row with a class chip and a `hint:` line.

So a turn can fail with `transcript-error` while the orb still reads `Thinking` or
`Speaking`; the row is where the failure lives. This matches
[../orb-states.md](../orb-states.md#the-full-state-table) and
[../interactions.md](../interactions.md#error-surfacing).

### Level meter per state

`voice.level` carries a `source` (`input` | `output`). A state reacts to **at
most one** source ([../audio-reactivity.md](../audio-reactivity.md#source-routing)).
The meter is the TUI's level channel.

| State | Meter shows | Source | No level seen |
| --- | --- | --- | --- |
| `listening` | Live bar + `%` | `input` | Bar `0%`, dim |
| `speaking` | Live bar + `%` | `output` | Bar `0%`, dim |
| `transcribing`, `thinking`, `idle`, `muted`, `error`, `connecting` | `0%`, dim | ignored | `0%` |
| `backend-down` / `transcript-error` | per the base state | per the base state | per the base state |

When the meter is not live it is still drawn at `0%`: the row never appears and
disappears, which would make the layout jump.

## Never color-only

This is the acceptance gate, the TUI form of
[../orb-states.md § Grayscale check](../orb-states.md#grayscale-check). The TUI
drops hue and motion entirely, so the test is stricter: every state must be
distinguishable with **all color removed and all attributes removed**.

Two checks:

1. **Word alone.** Every state has a unique label (table above). This is
   sufficient by itself: with color gone, the words are unique.
2. **Form alone.** The frame shapes are distinct in ASCII:
   `: :`, `( )`, `/ /`, `> <`, `{ }`, `~ ~`, `< >`, `% %`. No two states
   share a frame. The `listening` (`> <`) and `speaking` (`< >`) pair is the only
   near pair; it is separated by the **direction** of the angle brackets, which is
   readable and is reinforced by the word.

Rules for change:

- Adding a state requires a unique word **and** a unique form. A new state that
  reuses an existing frame and is within a similar perceived brightness of an
  existing state is not allowed.
- The monochrome fallback column in [tokens.md](tokens.md#color-pairs) is the
  authority: if a state is only legible because of its color pair, it fails this
  gate.

## Transitions

Transitions are driven by `voice.state`, the orb-local bridge state, and the
overlays; the TUI renders the result of the shared FSM and never arbitrates
([../orb-states.md § Transitions](../orb-states.md#transitions)). The base-state
diagram is unchanged:

```
IDLE ──> LISTENING ──> TRANSCRIBING ──> THINKING ──> SPEAKING ──> LISTENING
             ^                                |            |
             └──────────── interrupt / error ─┴────────────┘
```

| Trigger | TUI behavior |
| --- | --- |
| Any base transition | The header glyph and label change on the next redraw; there is no crossfade |
| `connecting` → any base | The first forward after (re)subscribe; the TUI requests `voice.state` on every connect, so this does not depend on a live event |
| any → `connecting` | Bridge disconnect; backoff retries are counted in a dim line under the header (see [layout.md](layout.md#connecting)) |
| `backend-down` set | Append `  ! Backend down` to the header and draw the `[harness]` error row |
| `backend-down` cleared | The next `agent.delta`, `agent.final`, or `voice.state` change removes the overlay text |
| `transcript-error` set | Draw the `!Error` row; **do not** change the header |
| `transcript-error` cleared | Dismiss (Esc) or the next `listening`/`thinking` removes the row |

There is no transition animation. The GUI's `durStateFade` has no TUI equivalent;
a state change is one `refresh()`.

## Related

- [tokens.md](tokens.md) — glyph, attribute, and pair definitions.
- [layout.md](layout.md) — where the header, meter, and rows are placed.
- [mockup.txt](mockup.txt) — each state as a literal frame.
- [../orb-states.md](../orb-states.md) — the authoritative state contract.
