# Feature: Pluggable Agent Harness

**Requirements:** REQ-HARNESS-001..007, REQ-BACKEND-001..002, REQ-TOOL-001..005, REQ-MEM-004.
**Contract:** [IF-0002 harness interface](../../architecture/modules/agent-harness.md), [IF-0003 pi RPC](../../contracts/protocols.md#if-0003-pi-rpc).

## What it does

Lets the **owner of the reasoning loop** be swapped by config, without changing
the rest of the system.

## The three-layer model

The single most common confusion in this project. See
[ADR-0004](../../architecture/decisions/ADR-0004-harness-vs-provider.md).

| Layer | What it is | Here |
| --- | --- | --- |
| Model provider | Serves an LLM over an API | Ollama, OpenAI |
| Model | The weights | `qwen3:latest` |
| **Agent harness** | Owns the loop: prompts the model, parses tool calls, runs them, manages context | `native`, `pi` |

pi is a **harness**, not a provider and not an inference engine. It calls its
own provider, configured in pi's own files. So there are two independent axes:

```yaml
agents:
  jarvis:
    harness: native            # who owns the loop
    llm:                       # used only when harness: native
      provider: ollama
      model: qwen3:latest
    pi:                        # used only when harness: pi
      workspace: ~/.config/aiassistant/pi_workspace
```

## The contract

Both harnesses implement one interface and emit one event vocabulary, so
`agent/loop.py`, the orb, and the TTS chunker never branch on which is running:

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

## Capability differences

`HarnessCaps` exists because the two harnesses are genuinely not equivalent.
Reporting the difference is what keeps it honest.

| Capability | `native` | `pi` |
| --- | --- | --- |
| `owns_tools` | `False` (our `tools/` executes) | `True` (pi executes its own) |
| `owns_memory` | `False` (we inject context) | `True` (pi holds session context) |
| `streaming` | `True` | `True` |
| `cancellable` | `True` | `True` (`clear_queue` + `abort`) |
| `usage_reporting` | `True` | `True` (`message_update.usage`) |
| `images` | `False` | `True` (not used in MVP) |

Consequences of `owns_tools = True` for pi turns:

- Our tools — including web search — are **not** available on pi turns.
- Our sandbox and `safe_paths` do **not** apply on pi turns; pi's confinement is
  its own (see [security/threat-model.md](../../security/threat-model.md)).
- The tool audit trail comes from pi's `tool_result` events.

## No silent fallback

If the selected harness is unhealthy, the turn fails with a visible error. It
never silently switches to the other harness: they differ in tool ownership, so
a silent switch would silently change what the assistant can do
(REQ-HARNESS-006).

## Memory and double-contexting

pi keeps its own session context. Injecting our memory context into a pi prompt
would double-context it. Rule:

- **Native turns:** our memory context is injected, as today.
- **pi turns:** the prompt is the bare user text; pi already has context.
- **Exception:** after a pi process restart, the first prompt may carry a compact
  recent-conversation summary so a crash does not erase continuity.

A contract test asserts pi prompts contain no memory prefix except that prime.

## Verification

| Clause | Method | Test |
| --- | --- | --- |
| Both harnesses satisfy the contract | host (parametrized conformance suite) | T-0301 |
| Event vocabulary mapping | host (fixtures) | T-0302 |
| Cancellation ends the turn as cancelled | host (fake harness) | T-0303 |
| Unhealthy harness fails, no fallback | host | T-0304 |
| pi prompt has no memory prefix except after restart | host | T-0305 |
| malformed pi stdout line does not kill the reader | host (fixture) | T-0306 |
