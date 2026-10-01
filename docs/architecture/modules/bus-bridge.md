# MOD-0005 — `bus` and `bridge`

Two related pieces: the in-process spine, and the out-of-process client library.

## `bus/` — the spine (MOD-0005a)

**Purpose:** Pub/sub and request/response between modules in the main process.

**Must not do:** carry raw audio, or grow routing logic. Topic matching stays
exact-string; there are no wildcards.

**Dependencies:** the standard library only.

### PROVIDES

| Function | Signature | Notes |
| --- | --- | --- |
| `publish` | `(topic: str, payload: dict \| None) -> None` | Fire and forget; thread-safe |
| `subscribe` | `(topic, callback) -> str` | Returns a subscription id |
| `unsubscribe` | `(subscription_id: str) -> None` | |
| `request` | `async (topic, payload, timeout) -> dict` | RPC; raises `NoSubscriberError`, `TimeoutError` |
| `respond_rpc` | `(request_id: str, response: dict) -> None` | |
| `user_input` | `(text, channel, sender) -> None` | Publishes `user.input.text` |
| `register` / `list_modules` | | Registry access |

### Changes from as-built

| Change | Reason |
| --- | --- |
| `asyncio.get_event_loop()` → `get_running_loop()` at `bus.py:89` | `get_event_loop` is deprecated and wrong off the loop thread |
| Add `bus/topics.py` constants | Topic strings were bare literals scattered across modules, which is why a rename could silently disable speech |
| Keep `publish` thread-safe | The audio plane publishes from a thread |

### INVARIANTS

- A subscriber exception never affects other subscribers (`bus.py:54`).
- Async callbacks are scheduled on the loop, including when published from a
  non-asyncio thread (`bus.py:44-53`).
- Exact topic match only. No wildcard.

### ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-BUS-NO-SUBSCRIBER` | RPC found no listener (`NoSubscriberError`) |
| `ERR-BUS-RPC-TIMEOUT` | No response within the RPC timeout |
| `ERR-BRIDGE-AUTH` | Token rejected at the handshake |
| `ERR-BRIDGE-GONE` | The connection dropped |

### CONCURRENCY

| Context | May call |
| --- | --- |
| asyncio loop | Everything |
| Any other thread | `publish` only; it schedules coroutines on the loop |

`subscribe`, `unsubscribe`, and `request` are loop-affine. The in-process
subscriber dict is mutated without a lock, so subscription changes must come
from the loop.

### RESOURCES

One dict of subscribers, one dict of pending RPC futures, one server socket, and
one task per client connection. No stack budget concerns.

### VERIFICATION

| Clause | Test |
| --- | --- |
| Pub/sub delivery | T-0501 |
| One bad subscriber does not break others | T-0502 |
| Publish from a non-loop thread is scheduled safely | T-0503 |
| RPC timeout raises | T-0504 |

## `bridge/` — the WS client (MOD-0005b)

**Purpose:** One implementation of the bus WebSocket protocol, used by the orb
process and any future out-of-process module.

**Must not do:** contain UI logic, or subscribe to topics on its own initiative.

**Dependencies:** `websockets` client.

### PROVIDES

| Function | Signature | Notes |
| --- | --- | --- |
| `connect` | `async (url, token: str, name: str) -> Bridge` | Authenticates, registers, returns a handle |
| `Bridge.subscribe` | `async (topic: str, handler) -> None` | |
| `Bridge.publish` | `async (topic: str, payload: dict) -> None` | |
| `Bridge.close` | `async () -> None` | |

### INVARIANTS

- Reconnect re-registers and re-subscribes.
- A dropped connection surfaces as a typed error, not a silent stop.

### REQUIRES

- `websockets` client
- The server accepting the connection (IF-0001)

### OWNS

- The connection, its subscriptions, and the reconnect state.

### CONNECTED STATE

`on_state("connected")` is reported only after the subscription replay has been
queued on the socket, on both the first connect and a reconnect. A client may
therefore publish a request from its connected handler (for example a
`voice.state.request` resync) without racing the forwarder registration.

### ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-BRIDGE-UNREACHABLE` | The server is not listening |
| `ERR-BRIDGE-AUTH` | The token was rejected |
| `ERR-BRIDGE-PROTOCOL` | A frame was not the expected shape |

### CONCURRENCY

Single connection, single receive loop. Handlers are invoked in arrival order.

### RESOURCES

One socket and one receive task per bridge instance.

### VERIFICATION

| Clause | Test |
| --- | --- |
| Connect, register, subscribe, receive | T-0505 |
| Reconnect resubscribes | T-0506 |

## `bus/remote.py` — the server (MOD-0005c)

**Purpose:** Accept out-of-process clients and bridge their messages onto the
in-process bus.

**This file is currently broken and must be fixed** (chunk 1). Evidence and the
required changes:

| Defect | Evidence | Fix |
| --- | --- | --- |
| Handler signature mismatch kills every connection | `remote.py:45` is `(self, websocket, path)`; the installed `websockets` is 16.0, whose handler takes one argument. Verified failing with `ConnectionClosedError 1011`. | `async def _handle_connection(self, websocket)` |
| Binds all interfaces with no auth by default | `remote.py:32` binds `0.0.0.0`; `config.yaml:6` token is `""`; `remote.py:50` only enforces auth when the token is non-empty | Default `127.0.0.1`; require a non-empty token for any non-loopback bind (REQ-SEC-001, REQ-SEC-002) |
| `_forward` schedules from a foreign thread | `remote.py:87` calls `asyncio.ensure_future` inside a publish callback, which may run on the audio thread | Schedule on the loop like `bus.publish` does |
| No unsubscribe over WS | `remote.py:97-98` only cleans up on disconnect | Accept an `unsubscribe` action |
| No resync after reconnect | Subscriptions die with the connection and the client has no snapshot | Document the client-side contract: re-subscribe and request a snapshot |

### INVARIANTS

- A client that only subscribes, and never registers, is supported (the orb).
- A malformed JSON line from a client is ignored, not fatal.
- Client subscriptions are cleaned up on disconnect.

### REQUIRES

- The in-process bus (`publish`, `subscribe`, `unsubscribe`)
- The registry, to record connected modules

### OWNS

- The client table and each client's subscription list.
- The bind address and port.

### ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-REMOTE-PORT-IN-USE` | The port is taken; remote connections are disabled, the app continues |
| `ERR-REMOTE-AUTH` | A client failed the handshake and was closed |
| `ERR-REMOTE-NONLOOPBACK-NO-TOKEN` | Startup refused: a non-loopback bind without a token (REQ-SEC-002) |

### CONCURRENCY

One task per client. The forwarding callback may be invoked from any publisher's
thread, so it must schedule onto the loop rather than assume it is on it — this
is the `_forward` fix.

### RESOURCES

One task and one subscription list per connected client. The client count is
unbounded by default; the loopback default keeps the realistic count at one or
two (the orb, the console).

### VERIFICATION

| Clause | Test |
| --- | --- |
| Connect and register | T-0505 |
| Subscribe then receive a published message | T-0507 |
| Auth rejected with a wrong token | T-0508 |
| Non-loopback bind without a token refuses to start | T-0509 |
| Malformed frame does not kill the server | T-0510 |
| Disconnect cleans up subscriptions | T-0511 |
