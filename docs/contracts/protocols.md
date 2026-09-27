# Wire Protocols

The external wire contracts. A **contract** is a boundary where the other side
is not ours: the orb process, a future out-of-process harness, or the OS audio
stack ([architecture/overview.md § Boundaries](../architecture/overview.md#boundaries)).

Status legend: `as-built` reflects shipped code · `new` is the target, not yet
implemented · `unverified` is a claim no test or source confirms yet.

| ID | Contract | Status |
| --- | --- | --- |
| [IF-0001](#if-0001-bus-websocket-bridge-protocol) | Bus WebSocket bridge | as-built + target changes |
| [IF-0002](#if-0002-agent-harness-event-contract) | Agent harness event contract | new |
| IF-0003 | pi RPC (our subset) | withdrawn 2026-09-27 (external harness removed) |
| [IF-0004](#if-0004-orb-bridge-api) | Orb bridge API | new |
| [IF-0005](#if-0005-voice-events) | Voice events | new |
| [IF-0006](#if-0006-audio-plane) | Audio plane | new |
| [IF-0007](#if-0007-topic-registry) | Topic registry | new + as-built |
| [IF-0008](#if-0008-voice-speak-and-interrupt-semantics) | Voice speak / interrupt | new |

Payload and config field tables live in [schemas.md](schemas.md). The orb-side
prose and a worked trace live in [api.md](api.md).

---

<a id="if-0001-bus-websocket-bridge-protocol"></a>
## IF-0001 Bus WebSocket bridge protocol

**Purpose:** Let an out-of-process client — the orb, or a future module — publish
onto the in-process bus and receive forwards from it.

**Participants:** the main process `RemoteBus` server (`bus/remote.py:8`) ↔
out-of-process clients; the client library is `bridge/`
([MOD-0005b](../architecture/modules/bus-bridge.md#bridge--the-ws-client-mod-0005b)).

**Status:** as-built, with target changes listed below.

### Framing

| Aspect | Rule |
| --- | --- |
| Transport | WebSocket text frames (`websockets.serve`, `bus/remote.py:31`) |
| Encoding | One JSON object per frame, `json.loads` on receive (`bus/remote.py:66`) |
| Malformed frame | Ignored, not fatal (`bus/remote.py:92-93`; MOD-0005c invariant) |
| Forward direction | Server → client, `{"topic": str, "payload": {}}` (`bus/remote.py:108`) |

### Envelopes

| Direction | Action | Shape |
| --- | --- | --- |
| client → server | register | `{"action":"register","module_name":str,"capabilities":{}}` |
| client → server | publish | `{"action":"publish","topic":str,"payload":{}}` |
| client → server | subscribe | `{"action":"subscribe","topic":str}` |
| client → server | unsubscribe | `{"action":"unsubscribe","topic":str}` (new; not in as-built) |
| server → client | forward | `{"topic":str,"payload":{}}` |
| server → client | register ack | `{"status":"registered"}` (`bus/remote.py:79`) |
| server → client | auth failure | `{"error":"auth failed"}` (`bus/remote.py:55`) |

### Auth

| Condition | Behavior |
| --- | --- |
| `remote_auth_token` non-empty | First inbound frame **must** be `{"token":str}` (`bus/remote.py:50-57`) |
| Token mismatch | Server sends `{"error":"auth failed"}` then closes |
| No first frame within 5 s | Server closes (`bus/remote.py:52,58`) |
| Token empty | No auth at all (as-built defect, `bus/remote.py:50`) |

### As-built defects

| Defect | Evidence | Target fix |
| --- | --- | --- |
| Handler signature breaks every connection on `websockets` 16 | `bus/remote.py:45` is `(self, websocket, path)`; websockets 16 passes one argument (fails `ConnectionClosedError 1011`) | `async def _handle_connection(self, websocket)` |
| Binds all interfaces, auth optional | `bus/remote.py:32` binds `0.0.0.0`; default token is `""` (`config.yaml:6`) | Default `127.0.0.1`; a non-empty token is mandatory for any non-loopback bind (REQ-SEC-001, REQ-SEC-002) |
| `_forward` schedules from a foreign thread | `bus/remote.py:87` calls `asyncio.ensure_future` inside a publish callback, which may run on the audio thread | Schedule on the loop as `bus.publish` does (`bus/bus.py:51-53`) |
| No unsubscribe over WS | `bus/remote.py:97-98` only cleans up on disconnect | Accept an `unsubscribe` action |
| No resync after reconnect | Subscriptions die with the connection; the client has no snapshot | Client re-subscribes and requests a snapshot (see [api.md](api.md)) |

---

<a id="if-0002-agent-harness-event-contract"></a>
## IF-0002 Agent harness event contract

**Purpose:** The one event vocabulary every harness emits and every consumer
reads, so the orb, TTS chunker, and `agent/` never branch on which harness is
running.

**Participants:** `agent/harness` implementations (`native`) → `agent/ →
orb / voice` via bus topics.

**Contract owner:** [MOD-0002 `agent/harness`](../architecture/modules/agent-harness.md#turnevent--the-vocabulary).

**Status:** new.

### `TurnEvent` kinds

| Kind | Payload fields | Consumer |
| --- | --- | --- |
| `text_delta` | `text` | orb transcript, TTS chunker |
| `thinking_delta` | `text` | orb thinking state; never spoken |
| `tool_call` | `call_id`, `name`, `args` | orb activity line |
| `tool_result` | `call_id`, `status`, `result`, `is_error` | orb activity line |
| `text_final` | `text` | **Authoritative**; replaces assembled deltas |
| `usage` | `input`, `output`, `total`, `cost` | status line |
| `turn_done` | `cancelled: bool` | end of turn, persist |
| `turn_error` | `message`, `class` | error state |

### Invariants

- Exactly one terminal event per turn: `turn_done` or `turn_error`
  (`agent-harness.md:78-79`).
- `text_final`, when emitted, is authoritative; delta consumers reconcile to it.
- `tool_result.call_id` matches an earlier `tool_call.call_id` within the same
  turn (`agent-harness.md:80-81`).
- Adding a kind is a contract change and must be reflected here and in the orb
  (`agent-harness.md:71-73`).

> **IF-0003 was withdrawn 2026-09-27**, when the external `pi` harness was
> removed. IF-0003 described the JSONL RPC contract with the upstream `pi` binary;
> no harness is out-of-process today. The number is retired, not reused.

---

<a id="if-0004-orb-bridge-api"></a>
## IF-0004 Orb bridge API

**Purpose:** The topic surface the orb process consumes and produces. The orb
speaks the bus WebSocket protocol ([IF-0001](#if-0001-bus-websocket-bridge-protocol));
this section fixes which topics and payloads it uses.

**Participants:** assistant modules (publishers) ↔ orb process (`bridge/`).
**Module:** [MOD-0008 `orb`](../architecture/modules/orb.md).
**Prose and a worked trace:** [api.md](api.md).

**Status:** new.

### Subscribes

| Topic | Payload | Rate | Drives |
| --- | --- | --- | --- |
| `voice.state` | `state` enum | On change | Base state and color |
| `voice.level` | `{level, source, ts}` | ≤ 20 Hz, latest-wins | Pulse amplitude |
| `agent.delta` | `{kind, text, index}` | Stream rate, coalesced ≤ 20 Hz | Streaming transcript |
| `agent.tool.event` | `{call_id, name, status, args, result, duration_ms, source}` | Per tool lifecycle step | Tool activity rows |
| `agent.final` | final text, session_id, usage | Once per turn | Transcript settle |
| `agent.turn.error` | `{message, class, hint, code}` | Once per failed turn | Error state |
| `voice.overflow` | `{dropped, queue_cap}` | On overflow | Warning badge |
| `status.assistant.ready` | `{}` | Once at startup | Window appears |
| `status.harness` | `{harness, model}` | On change | Backend badge |

`agent.tool.event` exists because tool activity needs its own channel:
`agent.delta.kind` covers only `text` and `thinking`, so without this topic tool
rows could not render. It is display-only.

### Publishes

| Topic | Payload | Rate |
| --- | --- | --- |
| `user.input.text` | `{text, channel:"orb"}` | Per submission |
| `command.agent.interrupt` | `{}` | Per user interrupt |
| `command.voice.mute` | `{muted: bool}` | Per toggle |

All payloads are defined in [schemas.md](schemas.md). Both `voice.level` and
`agent.delta` are coalesced **at the publisher**, not in the bridge
(`features/orb-ui.md:56-58`).

---

<a id="if-0005-voice-events"></a>
## IF-0005 Voice events

**Purpose:** Publish the duplex state, input levels, transcripts, and TTS
lifecycle without ever putting PCM on the bus.

**Participants:** `voice` (publisher) ↔ orb, agent, console.
**Module:** [MOD-0004 `voice`](../architecture/modules/voice.md).

**Status:** new.

### `voice.state`

| Value | Meaning |
| --- | --- |
| `idle` | Not listening, not speaking |
| `listening` | Capture live, awaiting speech |
| `transcribing` | Segment captured, ASR running |
| `thinking` | Turn dispatched, awaiting the harness |
| `speaking` | Playback active |
| `error` | A classified error is showing |
| `muted` | Capture stopped by the user |

Allowed transitions (`features/voice-pipeline.md:65-69`):

```
IDLE ──> LISTENING ──> TRANSCRIBING ──> THINKING ──> SPEAKING ──> LISTENING
             ^                                │            │
             └──────────── interrupt / error ─┴────────────┘
```

Impossible combinations (e.g. listening while speaking) are rejected by the
single state machine (`features/voice-pipeline.md:71-74`).

### Other voice topics

| Topic | Payload | Rate | Notes |
| --- | --- | --- | --- |
| `voice.level` | `{level: float 0..1, source: "input"\|"output", ts: float}` | ≤ 20 Hz, latest-wins | RMS; `source` lets the orb react to mic and to TTS |
| `voice.transcribed` | `{text, confidence?, language?}` | Per finalized segment | Replaces as-built `status.ears.transcribed` (`modules/ears/ears.py:100`) |
| `voice.tts.started` | `{text}` | Per synthesis | Replaces `status.mouth.started` (`modules/mouth/mouth.py:73`) |
| `voice.tts.done` | `{text, interrupted}` | Per utterance | Replaces `status.mouth.done` (`modules/mouth/mouth.py:81`) |
| `voice.tts.error` | `{error}` | On failure | Replaces `status.mouth.error` (`modules/mouth/mouth.py:80`) |
| `voice.overflow` | `{}` | On queue drop | Segment queue cap 2, drop-oldest (`voice.md:74-75`) |

`confidence` and `language` are target fields and **unverified** against the
current ASR backends.

---

<a id="if-0006-audio-plane"></a>
## IF-0006 Audio plane

**Purpose:** Fix the real-time audio constraints so nobody routes PCM through
the bus.

**Participants:** `voice` audio threads ↔ the OS audio stack. The bus is **not**
a participant.

**Status:** new.

| Aspect | Value | Source |
| --- | --- | --- |
| Frame size | 20 ms | `features/voice-pipeline.md:37` |
| Target sample rate | 16 kHz mono | `features/voice-pipeline.md:33` |
| Raw PCM on the bus | **Never**. Events only | `features/voice-pipeline.md:30-33`, REQ-VOICE-006 |
| Why not the bus | `bus.publish` is a synchronous dict fan-out with no bounded latency (`bus/bus.py:44`) | `architecture/overview.md:138-139` |
| Segment queue | Bounded, cap 2, drop-**oldest** on overflow; publish `voice.overflow` | `voice.md:74-75`, `voice.md:104` |
| PCM (playback) queue | Bounded; **exact cap unverified** | `voice.md:104` |
| RMS publish cadence | ≤ 20 Hz, latest-wins | `features/voice-pipeline.md:45` |
| VAD verdicts | Audio plane only | `architecture/overview.md:135-136` |
| Playback interrupt | Stop flag checked in the audio callback, drains silence at the next buffer | `voice.md:45-49` |

Raw PCM crosses only the capture/playback callback boundary; the bus carries
state, transcripts, and level samples.

---

<a id="if-0007-topic-registry"></a>
## IF-0007 Topic registry

**Purpose:** One place for topic string constants, so a rename cannot silently
disable speech. The constants file is **`bus/topics.py`**
([MOD-0005a](../architecture/modules/bus-bridge.md#bus--the-spine-mod-0005a)).

**Status:** new + as-built.

### MVP freeze rule

The rename below is applied **transitively** — publisher and subscriber move
together — and is covered by tests (REQ-STRUCT-003, T-0507). For the MVP, topic
**values are frozen only where renaming a value would break a frozen module**
(`vision`, `messaging`; see
[frozen-modules.md](../architecture/modules/frozen-modules.md)). The frozen
topics are `sensory.vision.frame` (`eyes.py:60`), `eyes.analyze` (`eyes.py:41`),
`status.eyes.ready` (`eyes.py:42`), and `sensory.speech.*`; they keep their
as-built strings for now. Every other listed rename adopts its new value.

### Renames (old → new)

| Old (as-built) | New constant | New value | Notes |
| --- | --- | --- | --- |
| `brain.ask` | `AGENT_ASK` | `agent.ask` | As-built `skills/base.py:70` |
| `action.execute` | `TOOL_EXECUTE` | `tool.execute` | As-built `brain/brain.py:357`, `modules/hands/hands.py:38` |
| `status.hand.done` | `STATUS_TOOL_DONE` | `status.tool.done` | As-built `modules/hands/hands.py:146` |
| `status.hand.error` | `STATUS_TOOL_ERROR` | `status.tool.error` | As-built `modules/hands/hands.py:132,154` |
| `status.hands.ready` | `STATUS_TOOLS_READY` | `status.tools.ready` | As-built `modules/hands/hands.py:42` |
| `status.ears.*` | `VOICE_STATE` / `VOICE_TRANSCRIBED` | `voice.state` / `voice.transcribed` | `status.ears.listening` (`ears.py:109`), `.processing` (`:113`) → `voice.state`; `.transcribed` (`:100`) → `voice.transcribed` |
| `status.mouth.*` | `VOICE_TTS_*` | `voice.tts.*` | `status.mouth.started/done/error/ready` (`mouth.py:73,81,80,40`) |
| `action.speak` | `VOICE_SPEAK` | `voice.speak` | As-built `brain/brain.py:379`, `mouth.py:39` |
| `response.text` | `AGENT_FINAL` (replacement, not a rename) | `agent.final` | As-built `brain/brain.py:371`; superseded by `agent.final` |

### New topics (new constants, no as-built value)

| Constant | Value | Publisher |
| --- | --- | --- |
| `AGENT_DELTA` | `agent.delta` | `agent` |
| `AGENT_TOOL_EVENT` | `agent.tool.event` | `agent` |
| `AGENT_FINAL` | `agent.final` | `agent` |
| `AGENT_TURN_ERROR` | `agent.turn.error` | `agent` |
| `AGENT_TRANSCRIPT_SNAPSHOT` | `agent.transcript.snapshot` | `agent` — **resync on reconnect**; the orb requests it when it detects an `agent.delta` index gap |
| `COMMAND_AGENT_INTERRUPT` | `command.agent.interrupt` | orb, console, hotkey |
| `COMMAND_VOICE_MUTE` | `command.voice.mute` | orb |
| `COMMAND_VOICE_PTT_START` | `command.voice.ptt.start` | orb, hotkey |
| `COMMAND_VOICE_PTT_END` | `command.voice.ptt.end` | orb, hotkey |
| `STATUS_HARNESS` | `status.harness` | `agent` |

### Complete constant list

| Group | Constants (values as-built unless noted) |
| --- | --- |
| Input | `user.input.text` (`bus/bus.py:129`) |
| Agent out | `AGENT_DELTA`=`agent.delta`, `AGENT_FINAL`=`agent.final`, `AGENT_TURN_ERROR`=`agent.turn.error` (new) |
| Agent RPC | `AGENT_ASK`=`agent.ask` (renamed from `brain.ask`) |
| Tools | `TOOL_EXECUTE`=`tool.execute`, `STATUS_TOOL_DONE`=`status.tool.done`, `STATUS_TOOL_ERROR`=`status.tool.error`, `STATUS_TOOLS_READY`=`status.tools.ready` |
| Voice | `VOICE_STATE`=`voice.state`, `VOICE_LEVEL`=`voice.level`, `VOICE_TRANSCRIBED`=`voice.transcribed`, `VOICE_SPEAK`=`voice.speak`, `VOICE_TTS_STARTED`/`VOICE_TTS_DONE`/`VOICE_TTS_ERROR`/`VOICE_TTS_READY`=`voice.tts.*`, `VOICE_OVERFLOW`=`voice.overflow` |
| Commands | `COMMAND_AGENT_INTERRUPT`=`command.agent.interrupt`, `COMMAND_VOICE_MUTE`=`command.voice.mute` (new) |
| Status | `status.assistant.ready` (`main.py:167`), `STATUS_HARNESS`=`status.harness` (new) |
| Schedule | `schedule.triggered` (`scheduler.py:92`), `action.schedule.add/list/delete` (`scheduler.py:33-35`), `status.schedule.added/list/deleted` (`scheduler.py:65-74`), `status.scheduler.error` (`scheduler.py:54`) |
| Module lifecycle | `bus.module.connected` (`remote.py:74`), `bus.module.disconnected` (`remote.py:101`, `main.py:160`) |
| Frozen (vision/messaging) | `sensory.vision.frame` (`eyes.py:60`), `eyes.analyze` (`eyes.py:41`), `status.eyes.ready` (`eyes.py:42`), `sensory.speech.*` superseded by voice topics; values frozen |

**Undefined gap:** push-to-talk start/end over the bus has no topic in any
current doc. It is **unverified/undefined** and must be added before REQ-WAKE-004
is implemented. Do not assume a name.

---

<a id="if-0008-voice-speak-and-interrupt-semantics"></a>
## IF-0008 Voice speak and interrupt semantics

**Purpose:** Fix the shape of spoken output and the exact order of a cancel, so
playback always stops and the mic always comes back.

**Participants:** `agent` → `voice` (via `voice.speak` and
`command.agent.interrupt`) → the OS audio stack.
**Module:** [MOD-0004 `voice`](../architecture/modules/voice.md).

**Status:** new.

### Speak

| Aspect | Rule |
| --- | --- |
| Input | `voice.speak` payload: `{text, voice?, speed?, interrupt?}` |
| Chunking | Text is split into sentences; each sentence is one speak event. The chunker flushes at a sentence boundary (`voice.md:113`, T-0103) |
| End of utterance | The final chunk is followed by an end-of-utterance marker: `voice.tts.done` with `{text, interrupted}` |
| Queueing | Chunks play in order; `interrupt: true` clears the queue and stops current playback first (`voice.md:32-43`) |
| State | Publishes `voice.state: speaking`, then `voice.state: idle` when the queue drains |
| Text turns | A text-originated turn speaks only when `voice.speak_text_turns` is true (REQ-CONV-005) |

### Stop / interrupt

The ordered cancel sequence; **order matters**
([flows.md (c)](../requirements/flows.md#c-interrupt)):

| # | Actor | Action |
| --- | --- | --- |
| 1 | `agent` | Receives `command.agent.interrupt` |
| 2 | `agent` | Cancels the **retained** turn task |
| 3 | `agent` | Calls `harness.cancel()` — native: cancel the provider stream |
| 4 | `voice` | Stops playback; sets the stop flag so the callback drains silence |
| 5 | `voice` | Clears the TTS queue; unmutes the mic |
| 6 | `agent` | Ends the turn with `turn_done(cancelled=true)`; **no** `agent.final` |
| 7 | — | `voice.state: idle` |

| Condition | Behavior |
| --- | --- |
| Interrupt with no active turn | No-op; state returns to idle |
| Harness ignores cancel | Local task still cancelled; error logged |
| Audio device wedged | Stop flag set regardless; device reopened next turn |

## Related

- [schemas.md](schemas.md) — payload and config field tables.
- [api.md](api.md) — orb connection sequence and a worked trace.
- [MOD-0005 `bus`/`bridge`](../architecture/modules/bus-bridge.md) — the server and client.
