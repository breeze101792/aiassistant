# ADR-0015 — Design docs are the gate before implementation

**Status:** accepted · **Date:** 2026-09-26

## Decision

Write the full `docs/` set **before** implementing. This doc set is chunk 0 of
the work; no source refactor starts until it exists. Implementation then updates
the docs to as-built as it lands.

## Why

Two reasons, one procedural and one concrete.

**Procedural:** the project design playbook this repo follows states it directly:
"Write design BEFORE code. The doc set is the gate: implementation starts only
after it exists."

**Concrete:** this refactor touches 73 Python files, renames every module,
replaces the audio stack, adds a Qt process, and adds a harness seam. The
first plan tried to write the docs last, as chunk 7, and an adversarial review
found three blocking problems that were only visible because the design was
written down:

1. **The bridge the orb depends on is already broken.** `bus/remote.py:45` has
   the wrong handler signature for the installed `websockets` 16.0; every remote
   connection dies. The plan had called that file "frozen".
2. **An open bus plus a capable agent is a remote-control path.** `remote.py:32`
   binds `0.0.0.0` and `config.yaml:6` has an empty token, so auth is skipped,
   and any client that reaches the port can drive the agent.
3. **Interrupt is not implementable as drawn.** `brain.py:172` fires the turn
   with `ensure_future` and stores no handle, so it cannot be cancelled.

All three are cheap to fix now and expensive to discover after a rename sweep has
invalidated the test suite. That is the argument for the gate.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Code first, docs last | The first plan did this; it is what produced the three findings above as late surprises |
| Partial docs, implement, then complete | Leaves the gate half-open; the pieces written last are the ones nobody re-checks |
| Docs in parallel with code | Sounds efficient, and means the doc describes a moving target rather than setting it |

## Consequences

- Chunk 0 is this doc set plus `PLAN.md`.
- Contracts that depend on unverified external behavior say so explicitly and
  list the evidence that must resolve them.
- "Unverified" is an allowed and explicit state. Silently unverified is not.
- After each implementation chunk, the relevant docs are updated to as-built, so
  the set never drifts far from the code.
