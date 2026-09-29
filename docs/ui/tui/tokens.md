# TUI Tokens

The single source of every glyph, attribute, color pair, and spacing value in the
TUI orb. It is the terminal counterpart of the GUI orb's
[tokens.md](../tokens.md).

**No component may hard-code a value.** If a value is not here, add it here first.
Everything below is reachable with `addnstr`/`mvaddstr`, `attron`/`attroff`,
`init_pair`, and `curses` constants.

Units: `cols` and `rows` are terminal cells. `cp` is a `curses` color pair
number. `A_*` are `curses` attributes.

---

## Glyph set

ASCII is the baseline. A glyph is a three-character frame around a one-character
core; the **core** carries the state, the **frame** carries its ring form
(see [states.md](states.md)). Each glyph has a Unicode upgrade that is used only
when the locale is UTF-8 and terminfo advertises the capability; ASCII is never
removed.

### State form glyphs (header)

| State | ASCII | Unicode upgrade | Shape it mirrors |
| --- | --- | --- | --- |
| `connecting` | `:o:` | `∘o∘` | dashed ring |
| `idle` | `(o)` | `(○)` | solid ring, at rest |
| `muted` | `/o/` | `⊘o⊘` | slash chord |
| `listening` | `>o<` | `≻o≺` | ring contracting inward |
| `transcribing` | `}o{` | `⟫o⟪` | two counter-rotating segments |
| `thinking` | `~o~` | `≈o≈` | single rotating arc |
| `speaking` | `<o>` | `≺o≻` | ring expanding outward |
| `error` | `%o%` | `¤o¤` | jagged ring |
| `backend-down` (overlay) | keeps the base glyph | keeps the base glyph | a **bar chord** in the GUI; here it is the appended text `! Backend down` plus the badge `!` |

The frame glyphs are deliberately distinct **in ASCII shape**: `( )`, `> <`,
`{ }`, `~ ~`, `< >`, `% %`, `: :`, `/ /`. Do not choose a Unicode
upgrade that collapses two ASCII-distinct frames into one shape. `backend-down`
has no glyph of its own: it layers on a base state, which keeps its glyph
([states.md](states.md#the-state-table)).

### Transcript and status glyphs

| Purpose | ASCII | Unicode upgrade | Notes |
| --- | --- | --- | --- |
| User row gutter | `You` | `You` | plain text, no glyph |
| Assistant row gutter | identity name (`Jarvis`) | same | from `agents.<id>.identity.name`, never hard-coded |
| Thinking row gutter | `Thinking` | same | rendered dim |
| Tool row gutter | tool name | same | rendered dim |
| Error row gutter | `!Error` | same | leading `!` is the non-color badge |
| Recovery hint indent | 10 spaces | same | aligns under the row body, see [layout.md](layout.md) |
| Streaming cursor | `_` | `▁` | drawn `A_REVERSE` in the real TUI; `_` here so a capture survives |
| Composer prompt | `you> ` | same | 5 cols, fixed |
| Level meter fill | `#` | `█` | `A_REVERSE` or `cpMeter`; text `#` in a capture |
| Level meter empty | `-` | `·` | dim |
| Level meter caps | `[` `]` | same | ASCII only, always |
| Overlay marker | `!` | `!` | prefix on the overlay text in the header |
| Scroll indicators | `^` `v` | `↑` `↓` | shown at the transcript edges when content overflows |
| Pinned marker | `pinned` | same | status-bar right when auto-scrolled to newest |
| Unpinned marker | `N new` | same | status-bar right when scrolled up; `N` = rows arrived since unpinning |

Rule: **ASCII never assumes Unicode.** The Unicode column is optional and is
selected once at startup from `locale.getpreferredencoding()` and
`curses.tigetstr("cup")` succeeding; a failure falls back to ASCII silently.

---

## Attribute set

`curses` attributes are the TUI's equivalent of the GUI's type weight and focus
ring. `A_BOLD` and `A_DIM` are widely supported; `A_REVERSE` is universal and is
the only attribute used for a **functional** cue (focus and cursor). The rest are
enhancement.

| Token | `curses` | Use | Functional? |
| --- | --- | --- | --- |
| `attrPrimary` | `A_NORMAL` | Transcript body, state label | no |
| `attrSecondary` | `A_DIM` | Role gutters, timestamps, hints, meter empty | no |
| `attrEmphasis` | `A_BOLD` | State label, error message, backend badge | no |
| `attrStream` | `A_REVERSE` | Streaming cursor | **yes** |
| `attrFocus` | `A_REVERSE` | Focused element (composer, scrolled transcript) | **yes** |
| `attrMuted` | `A_DIM` | `muted` state label and glyph | no |

There is **no `A_BLINK`** and **no animation**: `A_BLINK` is unsupported on many
terminals and, where supported, is strobe-like. It is forbidden by this design.
There is no `A_UNDERLINE` requirement; it is used nowhere, so minimal terminals
without it are unaffected.

---

## Color pairs

Color pairs are an **enhancement only**. The monochrome fallback column is the
authority: a state must remain fully legible using only the word and the glyph.
Pairs are registered with `init_pair(cp, fg, bg)` when
`curses.has_colors()` is true, and the foreground index is chosen for the
terminal's palette (the terminal's own 0–7/0–15 colors, never RGB). The
background is always the terminal default (`use_default_colors()`), never a
fixed index: a terminal background may be transparent, and a painted black is
unreadable on it.

| Token | cp | fg (256-color index) | Used by | Monochrome fallback |
| --- | --- | --- | --- | --- |
| `cpDefault` | 0 | default | everything | terminal default |
| `cpState` | 1 | per-state, see below | header state label + form glyph | already bold + labelled + glyph |
| `cpDim` | 2 | light grey (250) | gutters, timestamps, hints | `A_DIM` already |
| `cpError` | 3 | red (1 / 203) | error gutter `!Error`, hint | `!Error` text and `!` badge already |
| `cpWarn` | 4 | yellow/orange (3 / 214) | `backend-down` overlay, badge `!` | words "Backend down" already |
| `cpAccent` | 5 | cyan/blue (6 / 39) | streaming cursor, meter fill | `_` cursor and `#` fill already |
| `cpUser` | 6 | green (2 / 78) | `You` gutter | `You` text already |

### `cpState` foreground per state

This is the TUI's approximation of the GUI state hue. It selects an ANSI color
index; it is **not** the GUI hex, because a 16-color terminal cannot show it.
The luminance ordering follows [../orb-states.md § Grayscale check](../orb-states.md#grayscale-check)
so the *brightness* ordering is preserved even without hue.

| State | 8-color fg | 256-color fg | Perceived brightness |
| --- | --- | --- | --- |
| `connecting` | blue (4) | 24 | dim |
| `muted` | white (7) | 245 | dim, grey |
| `idle` | cyan (6) | 67 | dim |
| `backend-down` | yellow (3) | 130 | medium |
| `thinking` | magenta (5) | 141 | medium |
| `error` | red (1) | 203 | bright |
| `transcribing` | cyan (6) | 75 | bright |
| `listening` | green (2) | 79 | bright |
| `speaking` | yellow (3) | 221 | brightest |

If `curses.tigetnum("colors") < 8`, `has_colors()` is false and every pair
collapses to `cpDefault`; the design is unchanged because the word and glyph
already carry the state.

### `NO_COLOR`

`NO_COLOR` set to any value, or `TERM` without color support, disables all
`init_pair` calls. This is not an error; it is the monochrome-safe path the design
is built around.

---

## Spacing and alignment

A character grid has no sub-cell spacing. Alignment is exact column arithmetic.

| Token | Value | Use |
| --- | --- | --- |
| `colGutter` | `10` | Role gutter width including its trailing space |
| `colTime` | `8` | Timestamp width (`HH:MM:SS`) |
| `colBodyMin` | `24` | Minimum body column before a row is considered too narrow |
| `colMeterBar` | `20` in 80-col, `30` in 120-col | Level meter bar cells |
| `colComposerPrompt` | `5` | `you> ` |
| `rowHeader` | `1` | Header row |
| `rowRule` | `1` | Horizontal rule, `-` repeated to width |
| `rowMeter` | `1` | Level meter row |
| `rowComposer` | `1` | Composer row |
| `rowStatus` | `1` | Status-bar row |
| `rowTranscriptMin` | `10` | Minimum transcript rows in the smallest usable terminal (60x16) |

### Row layout arithmetic

Every transcript row is laid out on one line, exactly:

```
gutter(10) | body(cols - 10 - 1 - 8) | space(1) | time(8)
```

- `gutter` is left-aligned in 10 cols: `f"{role:<10}"`. The role is truncated to
  9 chars plus the separating space, so a long tool name is clipped, never
  wrapped.
- `body` is left-aligned and clipped with a trailing `~` when it does not fit.
- `time` is right-aligned in 8 cols: `f"{time:>8}"`.
- A wrapped continuation line (a body longer than one row) is drawn with the
  **gutter blank** and the body indented to `colGutter` (10 spaces). This makes a
  wrapped body visually part of the row above it. The GUI orb wraps freely; the
  TUI wraps at the body column with a blank gutter continuation.

The header is one row:

```
form(3) space(1) label(rest, bold) ... badge(right-aligned, bold)
```

The overlay, when set, is appended after the label: `label  ! Backend down`, so
the base state's word is still the first thing read.

### Rules and separators

- A rule is `-` repeated to the full width. It is drawn only in the ASCII
  baseline; a Unicode upgrade may use `─`, but `-` is always acceptable.
- There is **one** rule under the header and **one** above the composer. No other
  separators: boxes around every region add noise and break on narrow terminals.

---

## Related

- [states.md](states.md) — how these tokens encode state.
- [layout.md](layout.md) — where the tokens are placed.
- [../tokens.md](../tokens.md) — the GUI token set this mirrors.
- [../accessibility.md](../accessibility.md) — the never-color-only rule this file enforces.
