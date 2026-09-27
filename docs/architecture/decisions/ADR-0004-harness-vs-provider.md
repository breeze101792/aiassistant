# ADR-0004 — Two axes: agent harness and model provider

**Status:** accepted · **Date:** 2026-09-26 · **Amended:** 2026-09-27 (harness is now open-ended; one implementation ships)

## Decision

Model the "swappable brain" as **two independent configuration axes**:

```yaml
agent:
  harness: native        # who owns the reasoning loop
  llm:                   # which provider, used only by the native harness
    provider: ollama     # ollama | openai
    model: qwen3:latest
```

## Why

There are three distinct layers, and conflating them caused a real
misunderstanding during design — an external agent was initially treated as a
model provider.

| Layer | What it is | Examples |
| --- | --- | --- |
| Model provider | Serves an LLM over an API | Ollama, OpenAI |
| Model | The specific weights | `qwen3:latest` |
| **Agent harness** | Owns the loop: prompts the model, parses and executes tool calls, manages context | our `agent` (`native`), and, in principle, any external agent |

A harness is not a provider and not an inference engine. An external harness
would contain its own agent loop, its own tools, and its own provider files. So:

- Swapping the provider (ollama ↔ openai) and swapping the harness are different
  operations with different consequences.
- A flat `provider: <harness name>` would be wrong: it would put a harness where
  a provider belongs and imply a harness could be selected per-model.

## Current state

One harness ships: **`native`**, our own loop. It prompts a model provider and
delegates tools to `tools/` and memory to `agent/memory`.

The interface is deliberately kept open rather than collapsed into a direct
call:

- `AgentHarness` (`agent/harness/base.py`) is the contract, with one
  `TurnEvent` vocabulary.
- `create_harness` (`agent/harness/factory.py`) is the single selection point;
  an unknown name fails loudly rather than falling back.
- `HarnessCaps` reports what a harness owns, so a future loop that owns its tools
  or memory does not have to pretend otherwise.

A second harness is added by implementing the contract and registering it in the
factory. Nothing downstream — the transcript, the orb, the TUI, the TTS chunker —
changes, because they consume `TurnEvent` and never branch on the harness name.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Collapse the harness seam into a direct call to the native loop | Re-adding any harness would mean rebuilding the seam and re-teaching every caller; the cost of keeping it is one indirection |
| A flat `llm.provider: <harness>` | Category error; a harness is not a provider |
| A single `backend` enum mixing provider and harness | Cannot express "a harness with its own model", and implies false symmetry |

## Consequences

- Capability differences are real and must be reported, not hidden
  (REQ-HARNESS-005).
- There is **no silent fallback** between harnesses: a switch would silently
  change what the assistant can do (REQ-HARNESS-006).
- Memory injection is harness-dependent in principle (see
  [features/agent-harness.md](../../requirements/features/agent-harness.md)).
