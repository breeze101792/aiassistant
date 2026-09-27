# MOD-0010 — `scheduler`

**Purpose:** Persist and fire timed tasks: reminders and simple recurring jobs.

**Must not do:** decide what a reminder says, or speak. It publishes
`schedule.triggered` and the agent turns that into a turn.

**Dependencies:** `bus` topics, a JSON storage file.

**Kept, not new.** The user asked to keep the scheduler and place it correctly.
It moves from `modules/scheduler/` to the top level with the other modules and is
otherwise frozen internally. See
[ADR-0010](../decisions/ADR-0010-keep-scheduler.md).

## PROVIDES

### `setup() -> bool`

Loads pending tasks from `scheduler.storage_path`.

### `start() / stop() -> None`

Starts the clock loop. `stop()` cancels it.

### `_clock_loop()`

Polls once per second. On a task whose time has passed, publishes
`schedule.triggered`. Recurring tasks advance by their interval; one-shot tasks
are removed.

## REQUIRES

- `bus.publish` / `bus.subscribe`

## OWNS

- The pending task list and its storage file.
- The clock loop task.

## INVARIANTS

- A one-shot task fires at most once.
- A recurring task's next time is always in the future.
- The pending count never exceeds `scheduler.max_pending`.

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-SCHED-FULL` | `max_pending` reached; the add is refused |
| `ERR-SCHED-PARSE` | A stored task has an unparseable time; it is skipped, not crashed on |

## CONCURRENCY

The clock loop is the only writer to storage during normal operation; add and
delete handlers run on the same loop, so no lock is needed.

## RESOURCES

One asyncio task; a JSON file bounded by `max_pending`.

## Known weakness (carried forward, not fixed in MVP)

The clock loop rebuilds the whole task list and rewrites storage on every
trigger (`scheduler.py:106-111`). For a personal reminder count this is fine and
is left as-is; noted here rather than silently accepted.

## VERIFICATION

| Clause | Test |
| --- | --- |
| Add, list, delete round-trip | T-1001 |
| A due task publishes `schedule.triggered` exactly once | T-1002 |
| A recurring task re-arms with a future time | T-1003 |
| `max_pending` refuses further adds | T-1004 |
| Storage survives a reload | T-1005 |
