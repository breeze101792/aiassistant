# Component — Composer

The text input row: field, send, and mic-hold. Implements flow (d) from
[flows.md](../../requirements/flows.md#d-text-turn-from-the-orb) and publishes
`user.input.text {channel: "orb"}`.

File: `orb/Composer.qml`.

## Layout

```
┌───────────────────────────────────────┬──────┬──────┐
│  type a message…                      │  →   │  🎤  │
└───────────────────────────────────────┴──────┴──────┘
   field (flexible)                     send   mic
```

| Element | Size | Token |
| --- | --- | --- |
| Container height | `hitComposer` = `40 dp` + `space4` total row padding | [tokens.md](../tokens.md#hit-targets) |
| Field | flexible width, `40 dp` tall, `radiusPill` | — |
| Field background | `colorSurfaceRaised`; on focus `colorSurface` with a `colorBorderStrong` outline | — |
| Field text | `typeBody`, `colorTextPrimary`; placeholder `colorTextMuted` | — |
| Send button | `40 × 40 dp`, `radiusMd`, `colorAccent` icon | `hitComposer` |
| Mic button | `40 × 40 dp`, `radiusMd`; toggles PTT | `hitComposer` |
| Gaps | `space2` between field and buttons, `space2` between buttons | — |

The field grows vertically (up to `5` lines **PLACEHOLDER** [3–8]) then scrolls
internally, so a multi-line message is comfortable without pushing the transcript
off-screen.

## Text field

| Behavior | Rule |
| --- | --- |
| Placeholder | "Type a message…" |
| Multi-line | `Shift+Enter` inserts a newline; `Enter` sends ([interactions.md](../interactions.md#keyboard--window--global)) |
| Auto-grow | Up to `5` lines, then internal scroll |
| Paste | Accepted; newlines preserve; size limits apply |
| IME | Standard Qt input method; composition text is not sent mid-composition |
| Selection | Standard; `Cmd/Ctrl+A`, `Cmd/Ctrl+C/V/X` work |
| Undo | Native field undo; not persisted across window mode switches |

## Send

| State | Trigger | Look |
| --- | --- | --- |
| Disabled | Field is empty or whitespace-only | Icon `colorTextMuted`, no hover |
| Enabled | Non-empty, valid | Icon `colorAccent`, hover `colorAccentHover`, press `colorAccentPressed` |
| Sending | Momentarily after Enter, before the field clears | Brief press state `durInstant` |
| Disabled (backend down) | `backend-down` overlay | Enabled anyway — text still queues to the agent once the backend recovers. **Do not disable input on backend-down** (REQ-ORB-006, flow (d)) |

On send:

1. Trim leading/trailing whitespace.
2. If empty after trimming → ignore, no publish (flow (d) branch).
3. If it starts with `/` → treat as a **local console command**; do not publish to
   the agent ([flows (d)](../../requirements/flows.md#d-text-turn-from-the-orb)).
4. Otherwise publish `user.input.text {text, channel: "orb"}`.
5. Append a `user` row to the transcript immediately (optimistic local echo).
6. Clear the field; keep focus in the field.
7. Keep the send button disabled until text is entered again.

The user row is rendered locally before the assistant echoes; this is the one
optimistic render in the UI, and it is exact — the text that was sent is what is
shown.

## Mic-hold

| Interaction | Behavior |
| --- | --- |
| Press and hold | Push-to-talk: capture while held; release endpoints and proceeds |
| Tap | Toggle PTT on/off ([interactions.md](../interactions.md#hold-to-talk)) |
| Disabled: muted | Button shows `muted` styling; accessible name "Push-to-talk, unavailable while muted" |
| Disabled: no microphone | Button disabled; tooltip "No microphone"; the rest of the composer works |
| While speaking | If half-duplex, PTT is the way to interrupt-by-voice is deferred; the button still works for arming but capture is gated ([scope.md](../../requirements/scope.md#mvp-limitations--stated-plainly)) |
| PTT bus wiring | **Undefined upstream**; the UI is specified, the topic is not invented ([interactions.md](../interactions.md#hold-to-talk)) |

## Validation

| Input | Behavior |
| --- | --- |
| Empty / whitespace | Send disabled; Enter does nothing |
| Starts with `/` | Local command path; a `typeCaption` hint under the field names it; not sent to the agent |
| Exceeds a size cap | `Theme.composerMaxChars` = `8000` **PLACEHOLDER** [2000–32000]; the field rejects further input and shows a `colorWarning` counter |
| Only control characters | Treated as empty |
| Very long single line without spaces | Accepted; wraps in the transcript; no client-side wrapping change |

The size cap exists to protect the bus and the model, not the UI; the exact value
is a config concern and the UI reads it rather than fixing it.

## Disabled and error states

| Condition | Field | Send | Mic | Notes |
| --- | --- | --- | --- | --- |
| Normal | Enabled | Enabled when non-empty | Enabled | — |
| Backend down | Enabled | Enabled | Enabled | Input is **never** blocked by an error (REQ-ORB-006) |
| Bridge unreachable (`connecting`) | Enabled | **Disabled** | Disabled | No transport; a caption "Reconnecting — input queued locally" explains |
| Muted | Enabled | Enabled | Disabled | Text still works while muted |
| No microphone | Enabled | Enabled | Disabled | Text is the fallback ([flows (h)](../../requirements/flows.md#h-mic-or-speaker-unavailable)) |
| Turn in flight, `conversation.busy: interrupt` | Enabled | Enabled | Enabled | New input interrupts the current turn ([REQ-CONV-002](../../requirements/requirements.md)) |
| Turn in flight, `conversation.busy: queue` | Enabled | Enabled | Enabled | New input queues |
| Error row present | Enabled | Enabled | Enabled | Non-modal |

Rules:

- **The composer is never disabled by an application error.** The only thing that
  disables sending is no transport (`connecting`) or no text.
- Disabled controls keep their accessible name and say **why** in the
  description ([accessibility.md](../accessibility.md#screen-reader-labeling)).
- The placeholder changes to name the blocking reason when disabled
  ("Reconnecting…").

## Keyboard

| Key | Action |
| --- | --- |
| Any printable | Insert |
| `Enter` | Send (or accept an IME candidate) |
| `Shift+Enter` | Newline |
| `Esc` | First clears text if present; otherwise follows the global Escape order ([interactions.md](../interactions.md#escape-resolution-order)) |
| `Tab` | Move to send, then mic |
| `Cmd/Ctrl+Enter` | Also sends (harmless convenience for users who expect it) |

## Accessible names

| Element | Name | Role |
| --- | --- | --- |
| Field | "Message" | Text field; description includes Enter/Shift+Enter behavior |
| Send | "Send message" | Button |
| Mic | "Push-to-talk" | Button; description "Hold to talk, or tap to toggle" |

Full table: [accessibility.md](../accessibility.md#screen-reader-labeling).

## Related

- [layout.md](../layout.md#expanded-panel) — zone Z3.
- [interactions.md](../interactions.md) — Enter/Shift+Enter, Escape, hold-to-talk.
- [components/controls.md](controls.md) — mute and the control bar.
- [accessibility.md](../accessibility.md) — labels and focus.
