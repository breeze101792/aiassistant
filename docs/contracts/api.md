# Orb ↔ Assistant Bridge API

The API surface the orb process uses. It is the bus WebSocket protocol
([IF-0001](protocols.md#if-0001-bus-websocket-bridge-protocol)) on the wire, with
the topic set fixed by [IF-0004](protocols.md#if-0004-orb-bridge-api). The orb
depends only on `bridge/`; it never imports `agent/`
([MOD-0008](../architecture/modules/orb.md)).

Status: `new` for the orb contract; `as-built` where it cites `bus/remote.py`.

---

## Connection sequence

| # | Client (orb) | Server (`bus/remote.py`) |
| --- | --- | --- |
| 1 | Open `ws://<bus.bind>:<bus.websocket_port>` | Accepts (`remote.py:31`) |
| 2 | If a token is configured, send `{"token":str}` as the **first** frame | Validates within 5 s (`remote.py:50-60`) |
| 3 | Register: `{"action":"register","module_name":"orb","capabilities":{}}` | Adds to registry, publishes `bus.module.connected`, replies `{"status":"registered"}` (`remote.py:71-79`) |
| 4 | Subscribe to the topic list (below), one frame each | Subscribes, records the subscription id (`remote.py:84-90`) |
| 5 | Receive forwards `{"topic":...,"payload":...}` | Sends on each matching publish (`remote.py:106-110`) |

A token is mandatory for any non-loopback bind (REQ-SEC-002). The orb may
subscribe without registering; a subscribe-only client is supported
([MOD-0005c](../architecture/modules/bus-bridge.md#busremotepy--the-server-mod-0005c)).

### Subscribe list

The orb subscribes to exactly the IF-0004 topics:

```
voice.state
voice.level
agent.delta
agent.final
agent.turn.error
status.assistant.ready
status.harness
```

On connect (and every reconnect) the orb also **publishes** two resync requests,
`voice.state.request` and `status.harness.request`; the `voice.state` and
`status.harness` replies follow. Both are edge-triggered, so without the request
a client that connects after the last event would show `connecting` forever.

---

## Worked example: one voice turn

Actual JSON lines, in order. Client frames are marked `→` (orb → server),
server forwards are marked `←`. Timestamps and text are illustrative.

```
→ {"token":"<token>"}
← {"status":"registered"}
→ {"action":"register","module_name":"orb","capabilities":{}}
→ {"action":"subscribe","topic":"voice.state"}
→ {"action":"subscribe","topic":"voice.level"}
→ {"action":"subscribe","topic":"agent.delta"}
→ {"action":"subscribe","topic":"agent.final"}
→ {"action":"subscribe","topic":"agent.turn.error"}
→ {"action":"subscribe","topic":"status.assistant.ready"}
→ {"action":"subscribe","topic":"status.harness"}
← {"topic":"status.assistant.ready","payload":{}}

# voice detects speech and endpoints the utterance
← {"topic":"voice.state","payload":{"state":"listening"}}
← {"topic":"voice.level","payload":{"level":0.42,"source":"input","ts":1043.51}}

# utterance finalized, ASR runs
← {"topic":"voice.state","payload":{"state":"transcribing"}}
← {"topic":"voice.transcribed","payload":{"text":"what is the weather"}}

# agent takes the gate and dispatches to the harness
← {"topic":"voice.state","payload":{"state":"thinking"}}
← {"topic":"status.harness","payload":{"harness":"native","model":"qwen3:latest"}}
← {"topic":"agent.delta","payload":{"kind":"text","text":"It is ","index":0}}
← {"topic":"agent.delta","payload":{"kind":"text","text":"sunny ","index":1}}
← {"topic":"agent.delta","payload":{"kind":"text","text":"today.","index":2}}

# playback of the TTS chunks
← {"topic":"voice.state","payload":{"state":"speaking"}}
← {"topic":"voice.level","payload":{"level":0.30,"source":"output","ts":1044.02}}

# authoritative final text and end of turn
← {"topic":"agent.final","payload":{"text":"It is sunny today.","session_id":"7f3a91c2","usage":{"input":41,"output":9,"total":50,"cost":0.0}}}
← {"topic":"voice.state","payload":{"state":"idle"}}
```

The orb appends `agent.delta` fragments by `index` and reconciles to
`agent.final`. A user-typed turn is the same trace with the orb publishing:

```
→ {"action":"publish","topic":"user.input.text","payload":{"text":"hello","channel":"orb","sender":"user","timestamp":"2026-09-26T10:00:00+00:00"}}
```

An interrupt is the orb publishing the command:

```
→ {"action":"publish","topic":"command.agent.interrupt","payload":{}}
```

---

## Reconnect and resync

Server subscriptions are cleaned up on disconnect (`bus/remote.py:97-98`), so a
dropped connection leaves the orb with no forwards. The client contract:

| # | Step | Why |
| --- | --- | --- |
| 1 | Reconnect with backoff | `ERR-ORB-BRIDGE-UNREACHABLE`; show `connecting` |
| 2 | Re-send the token if configured, then re-register | A new connection is a new client |
| 3 | Re-subscribe to the full topic list | Subscriptions do not survive the socket |
| 4 | Detect gaps via `agent.delta.index` | `index` is monotonic per turn; any gap is a lost fragment |
| 5 | On a gap, request a snapshot | Rebuild transcript state; do not leave a silent hole |

The resync request topic has **no defined name in any current doc** — it is
**undefined/unverified** and must be added before REQ-ORB-005 resync is
implemented. Until then the orb can settle to `agent.final` when it arrives.

The invariant is in [MOD-0008](../architecture/modules/orb.md): "Delta text is
accumulated with the monotonic `index`; a gap triggers a resync request rather
than a silent hole."

---

## Error frames

| Frame | Direction | Meaning |
| --- | --- | --- |
| `{"error":"auth failed"}` | server → client | Wrong or missing token; server then closes (`remote.py:55`) |

Client-side error states (no wire frame):

| Code | Behavior |
| --- | --- |
| `ERR-ORB-BRIDGE-UNREACHABLE` | `connecting` state; retry with backoff |
| `ERR-ORB-SHADER` | Fall back to the QML state circle |
| `ERR-ORB-NO-DISPLAY` | Exit non-zero; the assistant stays in console mode |

For application-level turn failures the orb reads `agent.turn.error`
(`{message, class}`), not an error frame. The bridge protocol has no
application error envelope beyond `{"error": ...}` for auth.

## Related

- [IF-0001 bus WebSocket bridge](protocols.md#if-0001-bus-websocket-bridge-protocol)
- [IF-0004 orb bridge API](protocols.md#if-0004-orb-bridge-api)
- [schemas.md](schemas.md) — every payload above in full
- [bridge/ client](../architecture/modules/bus-bridge.md#bridge--the-ws-client-mod-0005b)
