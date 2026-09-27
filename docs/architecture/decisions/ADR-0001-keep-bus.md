# ADR-0001 — Keep the in-process message bus and harden it

**Status:** accepted · **Date:** 2026-09-26

## Decision

Keep `bus/` as the single in-process transport. Add `bus/topics.py` topic
constants and payload schema tests. Fix the identified defects. Do not replace
it with direct imports, an event-loop library, or a network bus.

## Why

The bus already works and is load-bearing for four things:

1. Modules are decoupled and independently testable (stub mode).
2. Out-of-process modules exist (`bus/remote.py`).
3. The orb needs a transport, and the bus WebSocket is already it.
4. The test suite depends on it (`tests/test_bus.py`, `test_integration.py`).

It also enforces the architecture: a module reaches another only by topic, which
is what keeps the dependency graph acyclic.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Direct imports between modules | Removes the acyclic guarantee and the test seam; the whole current design rests on this |
| Replace with `asyncio.Queue` per pair | N^2 queues, no registry, no RPC, no remote |
| A real broker (Redis, NATS) | Adds an external service for a single-user desktop app |
| An event-bus library | Replaces a 139-line file with a dependency; migration risk with no gain |

## Consequences

- Topic strings are the real interface, so they must become constants. Bare
  literals across modules are why a rename could silently break routing: the TTS
  trigger compares `source == "ears"` (`brain/brain.py:211`), a magic string with
  no compiler help.
- The bus must stay off the real-time audio path. `publish` is a synchronous
  dict fan-out (`bus/bus.py:44`) and cannot meet a 20 ms deadline.
