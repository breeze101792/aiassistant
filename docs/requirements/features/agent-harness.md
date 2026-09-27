# Feature: Pluggable Agent Harness

**Requirements:** REQ-HARNESS-001..007, REQ-BACKEND-001..002, REQ-TOOL-001..005, REQ-MEM-004.
**Contract:** [IF-0002 harness interface](../../architecture/modules/agent-harness.md).

## What it does

Lets the **owner of the reasoning loop** be selected by config, without changing
the rest of the system. One harness ships today; the seam exists so more can be
added without touching the callers.

## The three-layer model

The single most common confusion in this project. See
[ADR-0004](../../architecture/decisions/ADR-0004-harness-vs-provider.md).

| Layer | What it is | Here |
| --- | --- | --- |
| Model provider | Serves an LLM over an API | Ollama, OpenAI |
| Model | The weights | `qwen3:latest` |
| **Agent harness** | Owns the loop: prompts the model, parses tool calls, runs them, manages context | `native` (ours) |

A harness is not a provider and not an inference engine. A harness that owned its
own tools would call its own provider, configured in its own files. So provider
and harness are independent axes:

```yaml
agent:
  harness: native            # who owns the loop
  llm:                       # used only when harness: native
    provider: ollama
    model: qwen3:latest
```

## The contract

Every harness implements one interface and emits one event vocabulary, so the
agent module, the orb, and the TTS chunker never branch on which is running:

```python
class AgentHarness(ABC):
    caps: HarnessCaps

    def run_turn(self, req: TurnRequest) -> AsyncIterator[TurnEvent]: ...
    async def cancel(self) -> None: ...
    async def health(self) -> HarnessHealth: ...
```

```python
TurnEvent.kind ∈ {
    text_delta, thinking_delta, tool_call, tool_result,
    text_final, usage, turn_done, turn_error,
}
```

## Capability reporting

`HarnessCaps` exists so a harness reports what it owns instead of a caller
assuming. `native` delegates tools and memory:

| Capability | `native` |
| --- | --- |
| `owns_tools` | `False` (our `tools/` executes) |
| `owns_memory` | `False` (we inject context) |
| `streaming` | `True` |
| `cancellable` | `True` |
| `usage_reporting` | `True` |
| `images` | `False` |

A harness with `owns_tools = True` would change several things, and the caps flag
is how the system knows:

- Our tools — including web search — would not be available on its turns.
- Our sandbox and `safe_paths` would not apply; its confinement would be its own.
- Its tool audit trail would come from its own `tool_result` events.

## Selecting a harness

`create_harness` is the single selection point. It reads `agent.harness`
(default `native`) and fails loudly on an unknown name:

```python
name = (agent_cfg.get("harness") or NATIVE).strip().lower()
if name not in SUPPORTED:
    raise HarnessConfigError(f"Unknown harness {name!r}. Supported: ...")
```

Adding a harness means implementing `AgentHarness` and adding it to `SUPPORTED`;
no caller changes.

## No silent fallback

If the selected harness is unhealthy, the turn fails with a visible error. It
never silently switches to another: harnesses can differ in tool ownership, so a
silent switch would silently change what the assistant can do (REQ-HARNESS-006).

## Memory and contexting

Our harness receives injected memory context. A harness that keeps its own
session context must not also receive ours, or it would be double-contexted:

- **`native` turns:** our memory context is injected, as today.
- **A context-owning harness:** the prompt would be the bare user text.

No such harness ships, so this is a rule for a future implementation, recorded
here so it is not rediscovered.

## Verification

| Clause | Method | Test |
| --- | --- | --- |
| Any harness satisfies the contract | host (parametrized conformance suite) | T-0301 |
| Event vocabulary mapping | host (fixtures) | T-0302 |
| Cancellation ends the turn as cancelled | host (fake harness) | T-0303 |
| Unhealthy harness fails, no fallback | host | T-0304 |
| An unknown harness name is rejected loudly | host | T-0307 |
