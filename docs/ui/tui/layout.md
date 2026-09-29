# TUI Layout

The screen regions, their sizes, and how they behave on resize. Every position is
reachable with `mvaddstr` / `addnstr`; every region is addressable by row and
column.

The GUI orb has two window modes (compact, expanded). The TUI has one full-screen
view and three **width classes**. It takes the whole terminal; there is no compact
TUI.

## Regions

Top to bottom. The header is the orb; the transcript is the body; the meter, the
composer, and the status bar are chrome.

```
 +-------------------------------------------------------------------+
 |  row 0        header   <form> <label>  [overlay]       <badge>     |
 |  row 1        rule     ------------------------------------------  |
 |  row 2..H-5   transcript (scrollable; pinned to newest by default) |
 |  row H-4      meter    mic [#---------]  42%                       |
 |  row H-3      rule     ------------------------------------------  |
 |  row H-2      composer you> <text>_                                |
 |  row H-1      status   Esc stop  ^T mute  ...           pinned      |
 +-------------------------------------------------------------------+
   (H = terminal height in rows)
```

| Region | Rows | Size | Contents | Detail |
| --- | --- | --- | --- | --- |
| Header | `0` | `1` fixed | Form glyph, state label, overlay text, backend badge | [states.md](states.md) |
| Rule | `1` | `1` fixed | `-` to full width | [tokens.md](tokens.md#rules-and-separators) |
| Transcript | `2..H-5` | flexible, **fills** | Role-labelled rows, wrapped | [§ Transcript](#transcript) |
| Meter | `H-4` | `1` fixed | Source label, bar, percent | [§ Level meter](#level-meter) |
| Rule | `H-3` | `1` fixed | `-` to full width | — |
| Composer | `H-2` | `1` fixed | `you> ` prompt + editable text | [§ Composer](#composer) |
| Status bar | `H-1` | `1` fixed | Key hints, pin state | [§ Status bar](#status-bar) |

Fixed chrome is **6 rows** (header, rule, meter, rule, composer, status). The
transcript is `H - 6` rows.

## Baseline wireframe (80x24)

The exact `idle` frame; see [mockup.txt](mockup.txt) for the full set.

```
row 0  (o) Idle                                                   native / qwen3:latest
row 1  --------------------------------------------------------------------------------
row 2  You       What is the weather?                                          10:14:02
row 3  Jarvis    It is sunny today.                                            10:14:05
row 4
..     (transcript scrolls; rows 2..19 = 18 rows)
row 19
row 20 mic [--------------------]   0%
row 21 --------------------------------------------------------------------------------
row 22 you> _Type a message...
row 23 Esc stop  ^T mute  ^L clear  ^D quit  F1 help
```

At 80x24 the transcript gets **18 rows** (rows 2–19), and the chrome is the
remaining 6. The implementation places regions from the bottom up, so no row
count is assumed:

```
row_status   = rows - 1
row_composer = rows - 2
row_rule_low = rows - 3
row_meter    = rows - 4
transcript   = rows 2 .. rows - 5        (height - 6 rows)
```

## Wide wireframe (120x40)

Same regions, wider transcript and a longer meter bar. See
[mockup.txt](mockup.txt) for the literal frame.

```
0 ~o~ Thinking                                                         native / qwen3:latest
1 ------------------------------------------------------------------------------------------------------------------------
2 You       Summarise the meeting notes and list every action item with an owner.        10:30:02
3 Thinking  reading meeting-notes.md, grouping decisions vs tasks...                     10:30:03
...
36 mic [------------------------------]   0%
37 ------------------------------------------------------------------------------------------------------------------------
38 you> _Type a message...
39 Esc stop  ^T mute  ^L clear  ^D quit  PgUp/PgDn scroll  F1 help                    pinned
```

At 120 cols the body column is `120 - 10 - 1 - 8 = 101` cells; at 80 cols it is
`61`. The meter bar grows from 20 to 30 cells (`colMeterBar`).

## Width classes

The layout chooses one class at each resize. They differ only in the meter bar
width and how much the transcript body can show; the regions do not move.

| Class | Width | Meter bar | Notes |
| --- | --- | --- | --- |
| **Narrow** | `60–79` | `20` | Minimum usable. The badge may be clipped from the right; the label is never clipped |
| **Baseline** | `80–119` | `20` | The reference layout |
| **Wide** | `≥120` | `30` | Longer meter; no other change |

The regions are identical in all three classes, so a resize changes no code path
except the meter width and the clipping of long text.

## Resize

`curses` reports the new size after `SIGWINCH`; the TUI re-queries
`os.get_terminal_size()` and redraws. The design's resize rules:

| Event | Behavior |
| --- | --- |
| Terminal grows | Transcript gains rows; it stays pinned to the newest row if it was pinned |
| Terminal shrinks | Transcript loses rows from the **top** (oldest first); the newest row stays visible |
| Width changes | Every row is re-clipped to the new body width; no horizontal scroll |
| Below minimum | Enter the too-small view ([§ Too small](#too-small)); pause drawing the normal layout |
| Back above minimum | Redraw the normal layout; re-pin to newest |

A resize never crashes and never leaves escape sequences unresolved; the redraw
is one `erase()` + full repaint. The TUI does not attempt partial redraws — a
full repaint of a 24-row screen is cheap and avoids state desync.

## Too small

The minimum usable terminal is **60 columns × 16 rows**. Below either, the TUI
shows one centered message and keeps reading the bus (state still updates
internally), so growing the terminal restores the full view with the newest data.

```
Terminal too small: need 60x16, have 50x15.
Resize the window, or press Ctrl+D to quit.
```

| Rule | Value |
| --- | --- |
| Minimum columns | `60` (`colGutter` 10 + `colBodyMin` 24 + time 8 + meter 20 + margins) |
| Minimum rows | `16` (`6` fixed chrome + `10` transcript rows); below this the transcript cannot show a turn plus a response |
| Message | Two lines, centered both ways, `attrPrimary` |
| Controls that still work | `Ctrl+D` closes the TUI; `/exit` shuts the assistant down; `Ctrl+C` is handled by the app, not the TUI |
| State | Still tracked: growing the terminal shows the current state, not the state at the small moment |

This satisfies [frontends.md flow (m)](../../requirements/features/frontends.md#m-tui-cannot-start):
"shows a 'terminal too small' message and pauses, rather than crashing" — and
[frontends.md §2.5](../../requirements/features/frontends.md) for the too-small
threshold.

## Level meter

One row. The source label names which stream the level came from.

```
mic [################----]  42%
spk [#############-------]  63%
```

| Part | Width | Token | Notes |
| --- | --- | --- | --- |
| Source label | `4` | `attrSecondary` | `mic` for `source: input`, `spk` for `source: output`; a 4-char field |
| Space | `1` | — | — |
| Caps + bar | `bar + 2` | fill `cpAccent` / `#`, empty `A_DIM` / `-` | `colMeterBar` cells inside `[` `]` |
| Percent | `4` | `attrSecondary` | `f"{round(level*100):>3}%"`; right-aligned |

The meter is always drawn, at `0%` when the state does not react to level. It
uses the smoothed level from `OrbViewModel.level` (already gated and
attack/decay-shaped in `orb/model.py`), so the bar does not jitter even though
`voice.level` arrives at up to 20 Hz.

When `has_colors()` is false the fill is `#` and the empty is `-`; the percent
text carries the same information, so nothing is lost.

## Composer

One editable line at the bottom of the chrome.

```
you> _Type a message...
you> set a timer for ten minutes_
```

| Property | Value |
| --- | --- |
| Prompt | `you> ` (5 cols), `attrEmphasis` |
| Text | Editable; `attrPrimary`; cursor drawn `A_REVERSE` on the character at the insertion point |
| Placeholder | `Type a message...`, `attrSecondary`, shown only when empty |
| Focus | The composer is the default focus; `attrFocus` (`A_REVERSE`) is on the cursor |
| Input model | Single line in the MVP; a leading `/` is a local console command ([frontends.md §2.3](../../requirements/features/frontends.md)) |
| Overflow | When the text is longer than the field, the **start** is clipped (`<` marker at column 5) so the cursor and the newest typed characters stay visible |
| Enter | Publish `user.input.text {text, channel: "tui"}`; append a `You` row optimistically |
| `Ctrl+C` | Not quit (the app owns it); a no-op or copy, per the app |

The GUI composer is multi-line; the TUI composer is one line by design. Multi-line
paste is accepted and sent as a single turn; the field shows the first line with
the start clipped, and a dim `(+N lines)` marker when the buffer contains
newlines. This keeps the fixed 1-row chrome and avoids a growing composer that
would push the transcript away.

## Transcript

The transcript is the flexible region. Rows are append-only and pinned to the
newest by default.

### Row anatomy

```
gutter(10)  body(body cols)                               time(8)
```

| Element | Layout | Token | Notes |
| --- | --- | --- | --- |
| Gutter | cols 0–9, left-aligned | `attrSecondary` | `You`, identity name, `Thinking`, tool name, `!Error` |
| Body | cols 10..(cols-10) | `attrPrimary` | clipped with `~`; wrapped continuations use a blank gutter |
| Gap | 1 col | — | — |
| Time | last 8 cols, right-aligned | `attrSecondary` | `HH:MM:SS` |

### Roles

| Role | Gutter text | Body attribute | Non-color cue |
| --- | --- | --- | --- |
| `user` | `You` | `attrPrimary` | the word `You` |
| `assistant` | identity (`Jarvis`) | `attrPrimary` | the identity name |
| `thinking` | `Thinking` | `A_DIM` | the word `Thinking`; the row exists only during `thinking` |
| `tool` | tool name | `A_DIM` | the tool name and a `name: status` body |
| `error` | `!Error` | `attrPrimary`, message `attrEmphasis` | the `!` badge and `[class]` chip |
| hint (error sub-row) | blank | `A_DIM` | indented under the error row, prefixed `hint: ` |

The identity name comes from `agents.<id>.identity.name`, never hard-coded
([components/transcript.md](../components/transcript.md)).

### Streaming

An assistant row still receiving deltas ends with a cursor:

```
Jarvis    Yes, light rain in the morning, clearing by_
```

The `_` is drawn `A_REVERSE` over the cell after the last character. On
`agent.final` the cursor is removed and the row is replaced with the authoritative
text. The `thinking` kind in `agent.delta` is rendered as a `Thinking` row, dim,
never spoken — matching [../layout.md § Transcript behavior](../layout.md#transcript-behavior).

### Wrapping

The GUI wraps a body freely. The TUI wraps at the body column with a **blank
gutter** on continuation lines:

```
Jarvis    Three decisions and five action items: Dana owns the schedule,
          Ravi owns the migration, and I will draft the summary_
```

This is one logical row of two display lines. It keeps the time column on the
first line only, which is where the row starts.

### Scroll and pinning

| Behavior | Rule |
| --- | --- |
| Default | Pinned to the newest row; new rows appear at the bottom |
| `PgUp` / `PgDn` | Move one transcript page; unpins |
| `Up` / `Down` | Move one display line; unpins |
| `Home` / `End` | Jump to oldest / newest; `End` re-pins |
| Unpinned | The status bar shows `N new` on the right when new rows arrive |
| Return to bottom | Re-pins automatically |
| Streaming while unpinned | Does not force a scroll; the `N new` count is the affordance |
| `Ctrl+L` | Clear: empties the transcript locally (does not touch the store) |

The pin and new-count logic mirrors [../layout.md § Autoscroll](../layout.md#autoscroll),
with the jump-to-latest pill replaced by the `N new` status-bar marker (there is
no clickable pill in a keyboard-only TUI).

### Empty state

```
No messages yet. Say "hi jarvis" or type below.
```

Centered in the transcript region, `A_DIM`.

## Status bar

One row of key hints on the left and a state marker on the right.

```
Esc stop  ^T mute  ^L clear  ^D quit  F1 help                        pinned
```

| Slot | Content | Changes with state |
| --- | --- | --- |
| Left | Key hints for the controls relevant now | `Esc stop` in active states; `Esc unmute` when muted; `Esc dismiss` when an error row shows |
| Right | `pinned` / `N new` | Pin state and count of rows arrived since unpinning |

`F1` toggles a help overlay that lists every key; it is text, `attrPrimary`, and
dismissed with `Esc` or `F1`. It is the TUI's accessible-names surface: the GUI
gives every control an `Accessible.name`; the TUI states the key and its meaning
in the help overlay and in the status bar.

## Controls (keyboard only)

The full map. It satisfies REQ-FRONTEND-007 (stop/interrupt, mute, scroll, clear,
input, quit).

| Key | Action | Bus effect |
| --- | --- | --- |
| Any printable | Insert into the composer | — |
| `Enter` | Send the composer text | Publish `user.input.text {text, channel: "tui"}` |
| `/` at start | Local console command, not sent to the agent | local |
| `/exit` | Shut down the assistant, then close the TUI | Publish `command.assistant.shutdown {}` |
| `Ctrl+D` | Close the TUI only; the assistant keeps running and the console resumes | — |
| `Esc` | Context-dependent, same order as the GUI ([interactions.md § Escape](../interactions.md#escape-resolution-order)), minus mouse steps | interrupt / dismiss / clear |
| `Ctrl+T` | Toggle mute | Publish `command.voice.mute {muted}` |
| `Ctrl+.` | Stop / interrupt a turn | Publish `command.agent.interrupt {}` |
| `Ctrl+L` | Clear the transcript view | local |
| `PgUp` `PgDn` `Up` `Down` `Home` `End` | Scroll the transcript | local |
| `F1` | Toggle the help overlay | local |

`Esc` resolution order in the TUI (the GUI steps about drag, popover, settings are
removed because those elements do not exist here):

1. Close the help overlay if open.
2. Clear the composer text if it is non-empty.
3. Interrupt the active turn if one is running.
4. Otherwise nothing (do not quit).

Every control is a key; there is no mouse. No control is mouse-only by
construction, so the GUI's "every action is keyboard-reachable" rule
([../accessibility.md](../accessibility.md#keyboard-reachability)) is trivially
met.

## Related

- [states.md](states.md) — what each region renders.
- [tokens.md](tokens.md) — glyphs, attributes, pairs, column arithmetic.
- [mockup.txt](mockup.txt) — literal frames for each state and size.
- [../layout.md](../layout.md) — the GUI layout this adapts.
- [frontends.md §2.3, §2.5](../../requirements/features/frontends.md) — controls and degradation.
