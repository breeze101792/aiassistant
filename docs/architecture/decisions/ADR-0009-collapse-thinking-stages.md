# ADR-0009 — Collapse the 7-stage thinking loop

**Status:** accepted · **Date:** 2026-09-26

## Decision

Reduce the 7-stage loop to three real stages, and make the retry policy actually
retry.

| Old stage | Fate |
| --- | --- |
| `perceive` | **Kept** — topic classification and noise filtering are real work (`perceive.py:21-72`) |
| `understand` | **Deleted** — English keyword intent classification |
| `reason` | **Kept**, moved to streaming |
| `plan` | **Merged** — keep `ToolCall` and the JSON repair helper; drop the `Planner` class |
| `act` | **Kept** — tool execution |
| `reflect` | **Rewritten** as a policy that retries |
| `respond` | **Merged** into transcript persistence |

## Why

The stages were not dead — they were wired (`brain.py:220`, `:250`, `:278`). But
they add ceremony without adding capability:

**`understand.py`** is an English keyword classifier (`understand.py:15-17`) that
asks "starts with a question word?", yet the persona instructs the model to
"match the user's language". A keyword list cannot classify intent in a language
it does not know, and the only consumer is a clarification branch.

**`plan.py`** is a three-branch conditional (`plan.py:42-60`): if the model
returned tool calls, call tools; else if intent is unknown, ask to clarify; else
answer directly. The model already decided. The one valuable part is
`_repair_and_parse_json` (`plan.py:74`), which fixes malformed tool-call JSON —
that is kept.

**`reflect.py`** is the more serious case: it computes `RETRY` and `FALLBACK`
verdicts, but the caller only ever branches on `ABORT`
(`brain.py:272-286`). The retry never happens.
`tests/test_brain.py:91` asserts "RETRY verdict must trigger actual retry in
thinking loop" — a test for behavior that does not exist. That is a bug, not a
simplification.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Keep all seven stages, wire them properly | Preserves ceremony whose only consumer is a fallback branch; more code to keep green |
| Replace `understand` with an LLM classifier | An extra model call per turn to decide something the reasoning call already handles |
| Keep `Planner` as a class | It has three branches over data the model produced; a function is enough |

## Consequences

- Perceived behavior is preserved: the tool-call path, the clarify path, and the
  direct-answer path all still exist — with less indirection.
- The retry policy becomes real, and its test becomes meaningful.
- The `Responder` merge removes a duplicate writer: `Responder.save_turn`
  (`respond.py:27`) and `MemoryManager.save_turn` (`memory.py:25`) were nearly
  identical, and only one was called.
- Deleted tests: the `Understander` and `Planner` suites in
  `tests/test_brain_core.py`.
