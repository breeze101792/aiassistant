# ADR-0002 — Rename modules to functional names

**Status:** accepted · **Date:** 2026-09-26

## Decision

Replace the body metaphor with functional names.

| Old | New |
| --- | --- |
| `brain/` | `agent/` |
| `ears/` + `mouth/` | `voice/` (merged) |
| `hands/` | `tools/` |
| `eyes/` | `vision/` |
| `canvas/` | deleted |
| `chat/` | `messaging/` |
| `cli/` | `console/` |
| `scheduler/` | `scheduler/` (top-level) |
| `llm/` | `reasoning/` |
| — | `orb/`, `bridge/` (new) |

## Why

The names describe a metaphor rather than a function. The cost is concrete:

- `ears` and `mouth` hid that they were one duplex device, which allowed two
  owners and produced the mute race.
- `hands` does not say "tool registry and executor".
- `llm/` does not say "model provider", which is why the provider and the loop
  owner were initially confused for one thing.

Functional names state the responsibility.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Keep the body metaphor | The rename is an explicit user request; the metaphor also obscures the duplex coupling |
| Namespaced names (`io.audio`, `core.agent`) | A second taxonomy on top of the directory tree |
| Rename only some modules | Leaves the doc and config inconsistent |

## Consequences

- A wide but mechanical change: source paths, `MODULE_SPECS` (`main.py:69-78`),
  config section names, topic strings, test imports, and docs.
- **String-coupled code is the risk.** There is no compiler help for config keys,
  topic strings, or `monkeypatch` target paths (`tests/test_ears.py:46` and five
  more). The rename is one isolated chunk with a full grep sweep and a test fence.
- Config must accept old keys with a deprecation warning rather than break a
  user's existing file (REQ-CFG-004).
