# ADR-0010 — Keep the scheduler as a first-class module

**Status:** accepted · **Date:** 2026-09-26

## Decision

Keep the scheduler. Promote it from `modules/scheduler/` to a top-level
`scheduler/` module alongside the others, and give it a documented contract.
Do not delete it and do not leave it orphaned.

## Why

The ratified module-name set covered the body-metaphor modules and left the
scheduler without a home. The options were to delete it, fold it into another
module, or place it properly.

Timed reminders are a real assistant capability — "remind me at 3pm" is a
natural voice request — and the module works: storage, add/list/delete, a clock
loop, and recurring tasks. Deleting working code to satisfy a naming list would
be backwards.

It is also genuinely independent: it needs no tool, no model, and no audio. It
publishes `schedule.triggered` and the agent turns that into a turn, which is
exactly the bus decoupling the architecture is built on.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Delete it | Removes a working feature the user did not ask to remove |
| Fold it into `agent` | The agent would own wall-clock timers, which is a separate concern |
| Move it into `tools` | A reminder is not a tool call; it is a time-based trigger |
| Leave it in `modules/` | Inconsistent with every other top-level module; the orphan is what caused the question |

## Consequences

- `scheduler/` gains a module contract (`architecture/modules/scheduler.md`),
  which it did not have.
- Its tests remain: they are the only test group with no requirement behind them,
  which the trace flags explicitly as a scope question rather than hiding it
  (`testing/trace.md`, T-1001..T-1005).
- Known weakness carried forward and documented rather than silently accepted:
  the clock loop rewrites the whole task list on every trigger
  (`scheduler.py:106-111`).
