# MOD-0001 — `agent`

**Purpose:** Own the conversation turn: take input, gate concurrency, dispatch
to the harness, stream events out, and persist the turn.

**Must not do:** touch audio devices, render UI, or import another top-level
module directly. It reaches `voice`, `tools`, `scheduler`, and the orb **only
through bus topics**.

**Dependencies:** `bus` (topics only) · `agent/harness` · `reasoning` (via the
native harness) · `agent/memory`, `agent/embeddings`, `agent/persona`,
`agent/transcript`.

**State it owns:** the active turn task and its handle, the single-turn gate,
conversation context, and the tool-call policy counters.

## PROVIDES

### `setup() -> bool`

| Field | Content |
| --- | --- |
| Purpose | Resolve the harness, load memory, verify the provider. |
| Parameters | none; reads `config["agents"][active]` |
| Returns | `True` ready · `False` the harness or provider could not be resolved |
| Preconditions | Config is loaded and migrated |
| Postconditions | `self.harness` is set and `health()` has been probed once |
| Side effects | Creates memory directories |
| Context | async, called by `main.py` |
| Timing | Bounded by the harness health probe |

### `start() / stop() -> None`

| Field | Content |
| --- | --- |
| Purpose | Subscribe to input and command topics; on stop, cancel the turn and close the harness. |
| Parameters | none |
| Returns | none |
| Preconditions | `setup()` returned `True` |
| Postconditions | Input topics are subscribed; on stop, no turn task remains and the harness is closed |
| Side effects | Subscribes to `user.input.text`, `schedule.triggered`, `command.agent.interrupt`, `status.tools.ready`; publishes nothing on start |
| Context | async, called by `main.py` |
| Timing | `stop()` waits for harness teardown up to `conversation.turn_timeout_s` |

### `on_input(topic: str, payload: dict) -> None`

| Field | Content |
| --- | --- |
| Purpose | Entry point for every user-originated turn. |
| Parameters | `topic`; `payload` carries `text` and `channel` (`voice` \| `orb` \| `console` \| `schedule` \| `messaging`) |
| Returns | none (fire-and-forget; the turn runs as a retained task) |
| Preconditions | `start()` has run |
| Postconditions | Either a turn is now running, or the input was queued, or it was rejected by the gate |
| Side effects | Publishes `agent.delta`, `agent.tool.event`, `agent.final`, `agent.turn.error`; persists the turn |
| Context | async; reentrant-safe via the gate |
| Timing | Returns immediately; the turn is unbounded but cancellable |

### `interrupt() -> None`

The ordered cancel sequence. Cancels the retained task, calls
`harness.cancel()`, publishes state so `voice` stops playback, and ends the turn
with `cancelled` (REQ-CONV-003).

| Field | Content |
| --- | --- |
| Purpose | Stop the active turn as promptly as the harness allows. |
| Parameters | none |
| Returns | none |
| Preconditions | none — safe with no active turn |
| Postconditions | No turn task is running; the turn is terminal with state `cancelled` |
| Side effects | Publishes state so `voice` stops playback and unmutes; ends the iterator |
| Context | async, safe from the bus thread |
| Timing | Returns without waiting for harness teardown; teardown continues in the background |

### `publish_state(state: str) -> None`

| Field | Content |
| --- | --- |
| Purpose | Publish the conversational state the orb and console animate from. |
| Parameters | `state` ∈ `thinking` \| `idle` — the agent's own contribution. The authoritative duplex state is published by `voice`; the agent never publishes `listening`, `speaking`, or `transcribing`. |
| Returns | none |
| Preconditions | `start()` has run |
| Postconditions | The state is on the bus |
| Side effects | Publishes `voice.state` with the agent's phase |
| Context | async |
| Timing | Immediate |

> **Ownership note.** `voice.state` is the shared state topic. `voice` owns the
> audio phases (`listening`, `transcribing`, `speaking`, `muted`) and the idle
> transition; `agent` contributes `thinking`. The `transcribing → thinking`
> handoff is `voice` publishing `thinking` on the agent's behalf when it hands
> off the turn, so there is exactly one publisher per transition and no gap.

## REQUIRES

- `bus.publish` / `bus.subscribe` / `bus.request`
- `harness.run_turn()`, `harness.cancel()`, `harness.health()`
- `memory.get_recent_turns()`, `transcript.write_turn()`
- `reasoning` is reached **only** through the native harness

## OWNS

- `self._turn_task` — the retained handle. Its absence in the old code
  (`brain.py:172` used `ensure_future` without storing the result) is the reason
  interrupt could not work.
- `self._gate` — exactly one in-flight turn (REQ-CONV-002).
- Conversation context and policy retry counters.

## INVARIANTS

- At most one active turn task at any time.
- Every turn ends in exactly one terminal state: `final`, `cancelled`, or
  `error`.
- A user turn is persisted exactly once (REQ-MEM-002).

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-AGENT-HARNESS-UNAVAILABLE` | The harness failed its health probe |
| `ERR-AGENT-TURN-TIMEOUT` | The turn exceeded `conversation.turn_timeout_s` |
| `ERR-AGENT-TOOL-TIMEOUT` | A tool exceeded `tools.timeout_s` |
| `ERR-AGENT-CANCELLED` | The turn was cancelled by the user |

## CONCURRENCY

- `on_input` may be called from the bus callback thread; it schedules the turn
  on the loop.
- `interrupt` is safe from any thread that can schedule on the loop.
- The gate is a single asyncio primitive, not a lock.

## RESOURCES

- Static: two dicts, one task handle. No stack or heap budget concerns beyond the
  conversation context, which is bounded by `conversation.context_turns`.

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| One turn at a time | host | T-0301 |
| Interrupt cancels and terminates the turn | host | T-0303 |
| Every turn has a terminal state | host (fault injection) | T-0401 |
| Turn persisted exactly once | host | T-0402 |
| Harness unavailable fails visibly, no fallback | host | T-0304 |
