# ADR-0004 — Two axes: agent harness and model provider

**Status:** accepted · **Date:** 2026-09-26

## Decision

Model the "swappable brain" as **two independent configuration axes**:

```yaml
agents:
  jarvis:
    harness: native        # who owns the reasoning loop: native | pi
    llm:                   # which provider, used only by the native harness
      provider: ollama     # ollama | openai
      model: qwen3:latest
    pi:                    # pi's own config, used only by the pi harness
      workspace: ./pi_workspace
```

## Why

There are three distinct layers, and conflating them caused a real
misunderstanding during design — pi was initially treated as a model provider.

| Layer | What it is | Examples |
| --- | --- | --- |
| Model provider | Serves an LLM over an API | Ollama, OpenAI |
| Model | The specific weights | `qwen3:latest` |
| **Agent harness** | Owns the loop: prompts the model, parses and executes tool calls, manages context | our `agent`, **pi**, Claude Code, Codex |

pi is a **harness**. It contains its own agent loop and its own tools
(`read`, `bash`, `edit`, `write`), and it calls its own provider, configured in
its own files (`~/.pi/agent/models.json`, `auth.json`). It is not a provider and
not an inference engine.

Therefore:

- Swapping the provider (ollama ↔ openai) and swapping the harness (native ↔ pi)
  are different operations with different consequences.
- A flat `provider: pi` would be wrong: it would put a harness where a provider
  belongs and imply pi could be selected per-model.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Flat `brain.llm.provider: pi` | Category error; pi is not a provider |
| A single `backend` enum | Cannot express "pi with its own model", and would imply false symmetry |
| Treat pi as a library call | It is an external process with its own loop; that is the whole point |

## Consequences

- Capability differences are real and must be reported, not hidden: `pi` owns
  tools and memory; `native` delegates tools to `tools/` (REQ-HARNESS-005).
- There is **no silent fallback** between harnesses: a switch would silently
  change what the assistant can do (REQ-HARNESS-006).
- Memory injection is harness-dependent (see
  [features/agent-harness.md](../../requirements/features/agent-harness.md#memory-and-double-contexting)
  and [MOD-0003 pi-harness](../modules/pi-harness.md#memory)).
