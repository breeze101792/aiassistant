# Feature: Orb UI

**Requirements:** REQ-ORB-001..007, REQ-WAKE-005, REQ-WAKE-006, REQ-CONSOLE-002.
**Design:** [docs/ui/](../../ui/README.md).
**Contract:** [IF-0004 orb bridge](../../contracts/api.md), [IF-0005 voice events](../../contracts/protocols.md#if-0005-voice-events).

## What it does

A native desktop window showing an ambient, audio-reactive orb that expresses
the assistant's state, plus a transcript panel and text input.

## Why it is a separate process

| Option | Verdict |
| --- | --- |
| **Separate process, connecting as a client to the bus WebSocket** | **Chosen.** A Qt crash cannot take the assistant down; the Qt loop never touches asyncio; identical on macOS and Linux. |
| qasync (asyncio inside the Qt loop, one process) | Rejected. Couples two event loops, adds a dependency, and is unnecessary because `QWebSocket` is already async from Qt's side. |
| Qt on a thread inside the main process | Rejected. `QApplication` must own its thread; cross-thread signal plumbing plus GIL contention with the ASR thread is the worst of both. |

The orb runs **only the Qt event loop**. `QWebSocket` delivers messages as Qt
signals, so there is no asyncio and no qasync in the orb process. The main
process keeps its asyncio loop untouched.

## Data flow

Subscribes:

| Topic | Payload | Drives |
| --- | --- | --- |
| `voice.state` | `idle\|listening\|transcribing\|thinking\|speaking` | Base state and color |
| `voice.level` | RMS 0..1 with `source` | Pulse amplitude |
| `agent.delta` | `{kind, text, index}` | Streaming transcript, speaking shimmer |
| `agent.final` | final text | Transcript settle |
| `agent.turn.error` | message | Error state |
| `status.assistant.ready` | — | Window appears |
| `status.harness` | `{harness, model}` | Backend badge |

Publishes:

| Topic | Payload |
| --- | --- |
| `user.input.text` | `{text, channel: "orb"}` |
| `command.agent.interrupt` | `{}` |
| `command.voice.mute` | `{muted: bool}` |

## Topic value formats

`agent.delta` is **delta-only with a monotonic index**, never the growing
transcript. Sending the accumulator at 20 Hz would make the byte cost grow
quadratically over a turn. `agent.final` is authoritative and replaces the
assembled text.

`voice.level` carries a `source` field (`input` | `output`) so the orb reacts to
the microphone while listening and to the synthesized audio while speaking.
Without it the orb would sit still during playback.

Both streams are coalesced **at the publisher** (<= 20 Hz), not in
`bus/remote.py`, so the bridge stays unchanged.

## Controls

Push-to-talk (hold or toggle), mute, stop, new session, harness switch,
settings, transcript toggle, quit. Every control has a keyboard shortcut.

## Window behavior

Frameless, always-on-top, transparent background. Configurable via
`display.always_on_top`. Position and size persist. The idle window does not
steal focus. Compact (orb only) and expanded (orb plus panel) modes; the window
morphs rather than opening a second one.

## Platform caveats

- **Wayland** does not let clients set always-on-top or position reliably, and
  transparency depends on the compositor. The design degrades to an opaque
  rounded window; this is tested on the actual target session, not assumed.
- **Global hotkeys** cannot be registered portably from Qt Quick and need native
  APIs per platform. They are a separate, explicitly scoped item.
- **Packaging** via `pyside6-deploy` on both OSes. macOS notarization is its own
  task and is not on the MVP path.

## Failure behavior

| Condition | Behavior |
| --- | --- |
| Bridge unreachable | `connecting` state; retries with backoff |
| Bridge drops mid-session | Reconnect and re-subscribe; transcript resynced from a snapshot |
| Orb process crashes | The assistant keeps running; the orb is restarted |
| Shader unavailable (GPU) | Falls back to the QML state circle |

## Verification

| Clause | Method | Test |
| --- | --- | --- |
| Window opens with no browser | manual, both OSes | T-0201 |
| State changes follow bus events | host (fake bridge) | T-0202 |
| Delta text appends incrementally | host | T-0203 |
| Interrupt publishes the command | host | T-0204 |
| Reconnect resyncs without duplicates | host | T-0205 |
| Reduced motion disables animation | manual, inspection | T-0206 |
