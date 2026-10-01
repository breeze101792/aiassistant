# Component — Transcript

The scrollable, streaming conversation view in the expanded panel. Implements
the data semantics of [IF-0004](../../contracts/protocols.md#if-0004-orb-bridge-api)
and the layout of [layout.md § Transcript behavior](../layout.md#transcript-behavior).

File: `orb/Transcript.qml`, backed by a QML `ListModel` populated from the
`bridge_client` signals.

## Data model

One `ListModel` of turn entries. Each entry is one row; assistant rows mutate as
deltas arrive.

| Role | Type | Meaning |
| --- | --- | --- |
| `role` | enum | `user` \| `assistant` \| `tool` \| `error` \| `thinking` |
| `text` | str | Current assembled text (for assistant rows, the delta accumulator) |
| `thinking` | str | Latest `thinking` delta text; collapsed by default |
| `time` | str | Local wall clock `HH:MM:SS`, captured when the row is created |
| `turnId` | int | Local monotonic turn counter |
| `streaming` | bool | True while deltas are still arriving |
| `cancelled` | bool | True if the turn ended `turn_done(cancelled=true)` |
| `errorClass` | str | For `error` rows: the `class` from `agent.turn.error` |
| `hint` | str | Recovery hint, when the classified error carries one |
| `usage` | var | `{input, output, total, cost}` from `agent.final`, optional |
| `toolName` | str | For `tool` rows |
| `toolStatus` | enum | `running` \| `ok` \| `error` |

Invariant: **at most one** row has `streaming: true` at a time. A new turn
clears it on the previous row.

## Row layout

```
┌─ role gutter ─┬──────────── content ────────────────┬─ time ─┐
│  avatar/label │ text                                  │ 10:14  │
└───────────────┴───────────────────────────────────────┴────────┘
```

| Element | Token | Notes |
| --- | --- | --- |
| Row padding | `space4` vertical, `space3` horizontal | — |
| Row radius | `radiusLg` | Only on hover/selected; otherwise flat |
| Role gutter width | `72 dp` **PLACEHOLDER** [56–88] | Right-aligned label |
| Role label | `typeLabel` | `user` / `assistant` / `tool` / `error` |
| Body text | `typeBody` | Selectable; wraps at panel width |
| Timestamp | `typeCaption`, `colorTextMuted` | Right-aligned, `space3` from text |
| Row gap | `space2` | — |

### Role presentation

| Role | Gutter label | Color cue | Non-color cue |
| --- | --- | --- | --- |
| `user` | "You" | `colorTextSecondary` | Quote bar on the left, `2 dp`, `colorBorderStrong` |
| `assistant` | "Jarvis" (identity) | `colorTextPrimary` | None needed; the default |
| `thinking` | "Thinking" | `colorTextMuted` | Collapsible sub-row, italic, `colorSurfaceRaised` background |
| `tool` | tool name | `colorTextSecondary`, `typeMono` body | Gear glyph; status chip `running`/`ok`/`error` |
| `error` | "Error" | `colorDanger` gutter | `!` badge; `colorDanger` left bar; class chip |

The identity label is "Jarvis" by default and comes from `agents.<id>.identity.name`
([schemas.md](../../contracts/schemas.md)). It is never hard-coded in the view.

## Streaming deltas

`agent.delta {kind: "text", text, index}` appends **fragments only** — never the
accumulator ([schemas.md](../../contracts/schemas.md)). The view keeps a per-turn
buffer keyed by `index`.

| Event | Behavior |
| --- | --- |
| First `text` delta of a turn | Create an assistant row, `streaming: true`, `time` = now |
| Subsequent delta with `index == expected` | Append `text` to the row; `expected += 1` |
| `kind: "thinking"` delta | Append to the row's `thinking` field, rendered collapsed; never spoken |
| `agent.final` | Replace the row `text` with the authoritative `text`; set `streaming: false`; attach `usage` |
| Turn with no `agent.final` (cancelled) | Keep the accumulated delta text; set `cancelled: true`, render "(cancelled)" in `colorTextMuted` |

### Deltas and resync

`index` is monotonic per turn, starting at 0, incrementing by 1
([schemas.md](../../contracts/schemas.md)). A gap is a lost fragment.

| Condition | Behavior |
| --- | --- |
| `index == expected` | Append; advance |
| `index > expected` | **Gap detected.** Mark the row `streaming` with a "resync pending" indicator; request a snapshot |
| `index <= expected` (duplicate/replay) | **Ignore**; never append twice. This is what makes reconnect safe ([api.md § Reconnect and resync](../../contracts/api.md#reconnect-and-resync)) |
| First delta after (re)connect has `index > 0` | Treat as a gap; resync rather than rendering a partial sentence |
| `agent.final` arrives | Always wins; replaces the buffer regardless of gap state. Clears the resync indicator |

**Resync request status:** the request topic has **no defined name** in any
current doc ([api.md § Reconnect and resync](../../contracts/api.md#reconnect-and-resync)).
The view must not invent one. Until a topic lands:

1. Show a subtle inline "…" gap indicator in the row.
2. Continue accepting deltas; if the stream recovers to `index == expected`,
   clear the indicator.
3. Settle to `agent.final` when it arrives.

The invariant from [MOD-0008](../../architecture/modules/orb.md) — "a gap triggers
a resync request rather than a silent hole" — is satisfied by the **visible**
gap indicator even before the request topic exists; a silent hole is never
acceptable.

## Timestamps

| Property | Value |
| --- | --- |
| Format | `HH:MM:SS` local wall clock |
| Source | Client clock at row creation (not `voice.level.ts`, which is monotonic) |
| Token | `typeCaption`, `colorTextMuted` |
| Day boundary | A centered date chip `Today` / `Yesterday` / `YYYY-MM-DD` when the date changes between rows, `typeCaption`, `colorTextMuted` |
| Persistence | The view's timestamps are display-only; the store's format is the frozen markdown one ([schemas.md](../../contracts/schemas.md#memory--transcript-file-format-frozen-as-built)) |

## Tool-call rows

`tool_call` / `tool_result` from the harness event vocabulary
([IF-0002](../../contracts/protocols.md#if-0002-agent-harness-event-contract)) arrive
as `agent.delta` activity. With `native`, our `tools/` executes and the host
observes the result ([flows (f)](../../requirements/flows.md#f-tool-use)).

| Field | Presentation |
| --- | --- |
| Tool name | `typeMono`, `colorTextSecondary` in the gutter |
| Args summary | `typeMono`, one line, truncated with an ellipsis; expandable |
| Status chip | `running` = `colorAccent` spinner + text; `ok` = `colorSuccess`; `error` = `colorDanger` |
| Duration | From the `tool_result`, `typeCaption`, shown after completion |
| Expansion | Click or `Enter` on the row expands the full args/result; a `DisclosureIndicator` glyph is the non-color cue |
| Errors | A failed tool renders an `error` sub-row under the tool row, with `is_error` content |

Tool rows are **collapsed by default**. They are noise in a conversation unless
the user is debugging.

## Error rows

Rendered from `agent.turn.error {message, class}`
([schemas.md](../../contracts/schemas.md)). Anatomy matches
[interactions.md § Error row anatomy](../interactions.md#error-row-anatomy).

| Field | Presentation |
| --- | --- |
| Class chip | `config` \| `audio` \| `harness` \| `tool` \| `memory`; `typeLabel`, `radiusSm`, `surfaceRaised`, `colorDanger` text |
| Message | `typeBody`, `colorTextPrimary` |
| Hint | `typeCaption`, `colorTextSecondary`; present when the classifier provides one (REQ-ERR-001) |
| Action | For `harness`: an inline **Retry** button; for others, the hint names the fix |
| Announcement | `assertive` live region ([accessibility.md](../accessibility.md#live-regions)) |

Errors **do not** block the composer, the transcript, or the orb
(REQ-ORB-006). The row is informational and actionable.

## Scrollback

| Property | Value |
| --- | --- |
| Bound | `Theme.transcriptMaxTurns` = `500` **PLACEHOLDER** [200–2000] rows in the view |
| Eviction | Oldest row evicted from the `ListModel` when the bound is exceeded |
| Persistence | **Not the view's job.** Turns are persisted by the memory store (REQ-MEM-001, REQ-CONV-004); to read older history the user opens the store or the console |
| Initial load | On start, the view loads the current session's recent turns from the snapshot, not the whole history |
| Reconnect | Re-subscribe, then rebuild from the snapshot; deltas with `index <= expected` are ignored so no duplicate row appears (T-0205) |
| Memory bound | `ListModel` row text is replaced, never appended as a new row, so a long turn does not grow the row count |

Autoscroll, pinned-bottom, and jump-to-latest behavior live in
[layout.md § Autoscroll](../layout.md#autoscroll). The view owns the pin state;
the transcript component exposes `pinned: bool` and `newCount: int` for the pill.

## Empty and boundary states

| State | Presentation |
| --- | --- |
| No messages | Centered "No messages yet. Say *<first hotword>* or type below." `typeBody`, `colorTextMuted`. The phrase comes from `voice.hotwords` |
| Only thinking, no text yet | The thinking sub-row is visible; the assistant row shows a subtle typing indicator (three dots, `typeMuted`) until the first `text` delta |
| Very long single turn | Text wraps; the row grows; the view stays pinned to the bottom while `streaming` |
| Rapid turns | New rows append; the previous row's `streaming` clears first |

## Related

- [layout.md](../layout.md) — zones and autoscroll.
- [interactions.md](../interactions.md) — Escape, click, keyboard.
- [accessibility.md](../accessibility.md) — labels, live regions.
- [schemas.md](../../contracts/schemas.md) — `agent.delta` / `agent.final` fields.
- [api.md](../../contracts/api.md) — reconnect and resync sequence.
