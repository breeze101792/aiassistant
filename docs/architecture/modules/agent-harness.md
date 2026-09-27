# MOD-0002 — `agent/harness` (interface)

**Purpose:** Define the one contract a harness implements, and the one event
vocabulary the rest of the system consumes. One harness ships — `native` — and
the seam is open so a future harness can be added without touching the callers
(REQ-HARNESS-008).

**Must not do:** contain provider-specific or process-specific logic. Those live
in the implementation (`harness/native.py`).

**Dependencies:** none beyond the standard library and `bus` topic constants.

## PROVIDES

### `AgentHarness.run_turn(req: TurnRequest) -> AsyncIterator[TurnEvent]`

| Field | Content |
| --- | --- |
| Purpose | Run one conversational turn and stream its events. |
| Parameters | `req.text` (str, the user text); `req.turn_id` (str, uuid); `req.execute_tool` (callback, used only when `caps.owns_tools` is false); `req.images` (optional, unused in MVP). Caller owns the memory; the iterator does not retain it. |
| Returns | An async iterator. Always terminates. The last event is `turn_done` or `turn_error`. |
| Preconditions | `health()` previously returned healthy; no other turn is active on this harness. |
| Postconditions | The iterator is exhausted; no background work remains for this turn. |
| Side effects | Publishes nothing directly. The caller maps events to topics. |
| Context | async; single-consumer; **not** reentrant — one turn at a time. |
| Timing | Unbounded; cancellable through `cancel()`. |

### `AgentHarness.cancel() -> None`

| Field | Content |
| --- | --- |
| Purpose | Stop the active turn as promptly as the backend allows. |
| Parameters | none |
| Returns | none |
| Preconditions | none; safe with no active turn |
| Postconditions | The active iterator will end with `turn_done(cancelled=True)` |
| Side effects | Backend-specific: native cancels the provider stream |
| Context | async; safe to call concurrently with an in-flight `run_turn` |
| Timing | Bounded by the backend's own abort latency; **not** guaranteed instant |

### `AgentHarness.health() -> HarnessHealth`

Returns `{ok: bool, detail: str}`. Called at startup and before a turn
(REQ-HARNESS-007).

| Field | Content |
| --- | --- |
| Purpose | Report whether the harness can serve a turn. |
| Parameters | none |
| Returns | `ok` plus a human-readable `detail`; never raises |
| Preconditions | none; callable before any turn |
| Postconditions | A truthful readiness answer |
| Side effects | native performs a cheap provider probe |
| Context | async |
| Timing | Short timeout; a slow probe reports unhealthy rather than hanging |

### `AgentHarness.caps -> HarnessCaps`

Static capability declaration:

| Field | Type | Meaning |
| --- | --- | --- |
| `owns_tools` | bool | If true, the harness executes tools and our `tools/` is not invoked |
| `owns_memory` | bool | If true, the harness holds session context and we do not inject ours |
| `streaming` | bool | Emits partial deltas |
| `cancellable` | bool | `cancel()` is meaningful |
| `usage_reporting` | bool | Emits `usage` events |
| `images` | bool | Accepts image input |

### `AgentHarness.provider -> LLMBackend | None`

The provider this harness drives, or `None`. A class-level default, so a minimal
implementation ignores it. Callers that need a provider — embeddings resolution
and skill subtasks — read it here rather than probing the implementation.

### `AgentHarness.ensure_started() -> None`

Start any external resource the harness needs. Called once during setup, before
the first health probe. The default does nothing; a harness that spawns a
process overrides it and raises if it cannot start.

### `AgentHarness.close() -> None`

Release resources. The default calls `cancel()`.

### `TurnEvent` — the vocabulary

| Kind | Payload | Consumer |
| --- | --- | --- |
| `text_delta` | `text` | orb transcript, TTS chunker |
| `thinking_delta` | `text` | orb thinking state; never spoken |
| `tool_call` | `call_id`, `name`, `args` | orb activity line |
| `tool_result` | `call_id`, `status`, `result`, `is_error` | orb activity line |
| `text_final` | `text` | **Authoritative**. Replaces assembled deltas. |
| `usage` | `input`, `output`, `total`, `cost` | status line |
| `turn_done` | `cancelled: bool` | end of turn, persist |
| `turn_error` | `message`, `class` | error state |

## REQUIRES

Nothing. An implementation may require `reasoning/` (as `native` does) or a
subprocess, should a future harness need one.

## OWNS

The vocabulary itself. Adding a kind is a contract change and must be reflected
in `contracts/protocols.md` and in the orb.

## INVARIANTS

- Exactly one terminal event per turn (`turn_done` or `turn_error`).
- `text_final`, when emitted, is the authoritative text; consumers that used
  deltas must reconcile to it.
- `tool_result.call_id` always matches an earlier `tool_call.call_id` **within
  the same turn**.

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-HARNESS-TIMEOUT` | The harness exceeded the turn timeout |
| `ERR-HARNESS-DEAD` | The harness failed mid-turn |
| `ERR-HARNESS-PROTOCOL` | The harness produced output the contract cannot express |

## CONCURRENCY

One active turn per harness instance. Concurrent `run_turn` calls are a
programming error and raise.

## RESOURCES

None. Implementations declare their own.

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| The harness satisfies this contract | host (fake + native conformance) | T-0301 |
| Event vocabulary mapping | host (fixtures) | T-0302 |
| Terminal event exactly once | host | T-0301 |
| `call_id` correlation | host | T-0307 |
