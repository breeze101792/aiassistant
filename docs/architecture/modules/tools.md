# MOD-0007 — `tools`

**Purpose:** Discover, validate, and execute tools for the native harness.

**Must not do:** decide when a tool should be called, or talk to the model. That
is the agent's job.

**Dependencies:** `bus` topics, the filesystem, the network (for web tools).

**State it owns:** the tool registry and the sandbox policy.

> Used only when `harness.caps.owns_tools` is false. The shipped `native`
> harness delegates tools, so every turn consults this module (REQ-HARNESS-005).

## PROVIDES

### `setup() -> bool`

Discovers tools from `tools.paths` by importing modules and finding `ToolBase`
subclasses. Returns `True` with zero tools if no path resolves; a missing path is
logged, not fatal.

### `execute(name: str, params: dict) -> ToolResult`

| Field | Content |
| --- | --- |
| Purpose | Run one tool. |
| Returns | `{result}` or `{error, duration_ms}` |
| Preconditions | `name` is registered |
| Postconditions | Exactly one result or error |
| Side effects | May touch the filesystem or network, bounded by the sandbox |
| Context | Runs in an executor; must not block the event loop |
| Timing | Bounded by `tools.timeout_s` |

### `list_schemas() -> list[dict]`

Function-calling schemas for the model.

### `Sandbox.check_path(path: str) -> bool`

Path policy. **Must** use real path containment, not string prefix matching —
`sandbox.py:58` used `startswith`, so `/tmp/aiassistant-evil` passed as inside
`/tmp/aiassistant`. Fix: resolve with `os.path.realpath` and compare against the
resolved safe roots with a separator boundary (REQ-TOOL-004).

## REQUIRES

- `bus.publish` / `bus.subscribe` / `bus.respond_rpc`
- The filesystem and, for web tools, the network

## OWNS

- The registry: name to tool instance.
- Sandbox policy: safe roots, timeout, network allowance.

## INVARIANTS

- A tool call either returns a result or an error; it never raises to the caller.
- No tool executes outside `tools.timeout_s`.
- With sandboxing on, no path outside the resolved safe roots is touched.

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-TOOL-NOT-FOUND` | No tool registered under that name |
| `ERR-TOOL-TIMEOUT` | Exceeded `tools.timeout_s` |
| `ERR-TOOL-DENIED` | Path or policy violation |
| `ERR-TOOL-FAILED` | The tool raised |

## CONCURRENCY

Tools run in an executor. A tool instance may be shared across calls; tools that
hold state must document it.

## RESOURCES

Depends on the tool. File tools hold one open handle at a time.

## Kept from as-built

The dynamic discovery mechanism (`hands.py:62-110`) is kept. It works and is
what makes `tools.paths` configurable.

## Fixed from as-built

| Defect | Evidence | Fix |
| --- | --- | --- |
| Path prefix escape | `sandbox.py:58` uses `startswith` | Real-path containment |
| Skill LLM call is dead and blocking | `skills/base.py:68` subscribes `brain.ask.response`, which is never published; `:71` calls `run_until_complete` inside a running loop | Use `await bus.request("agent.ask", ...)` |
| Skill tool call blocks the loop | `skills/base.py:49` `run_until_complete` | Await the RPC |

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| Discovery from configured paths | host | T-0701 |
| Tool call round-trip through the agent | host (fake tool) | T-0702 |
| Timeout returns an error | host | T-0703 |
| Path escape is refused | host | T-0704 |
| Skill tool call and LLM call both complete | host | T-0705 |
