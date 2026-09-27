# MOD-0006 — `reasoning`

**Purpose:** Provide model access behind one streaming interface for the native
harness: chat with tool calling, and embeddings.

**Must not do:** own the agent loop, run tools, or manage conversation context.
Those belong to `agent/`.

**Dependencies:** provider SDKs (`ollama`, `openai`).

## PROVIDES

### `ModelProvider.chat_stream(messages, tools, **opts) -> AsyncIterator[StreamChunk]`

| Field | Content |
| --- | --- |
| Purpose | Stream a completion. |
| Parameters | `messages` (OpenAI-style list); `tools` (function schemas, optional); `temperature`, `max_tokens` |
| Returns | An async iterator of chunks: `{delta: str}` text fragments, then a terminal chunk carrying `content`, `tool_calls`, and `usage` |
| Preconditions | The provider is configured |
| Postconditions | The iterator is exhausted exactly once |
| Context | async; the call must not block the event loop |
| Timing | Unbounded; cancellable by abandoning the iterator and closing the underlying client stream |

### `ModelProvider.chat(messages, tools, **opts) -> dict`

Non-streaming convenience, used for compression and short subtasks. Runs off the
event loop.

### `ModelProvider.embed(text: str) -> list[float]`
### `ModelProvider.embed_batch(texts: list[str]) -> list[list[float]]`

Embeddings. Must run off the event loop (REQ-MEM-006).

### `ModelProvider.token_count(messages: list[dict]) -> int`

Unchanged from as-built (`llm/base.py:51`).

### `create_provider(cfg: dict) -> ModelProvider`

Factory selecting `ollama` or `openai`. An unknown provider raises a clear
error (REQ-BACKEND-002).

## REQUIRES

Nothing internal. Provider SDKs and network access.

## OWNS

The provider client objects and the embedding cache of "provider unavailable"
state (`embeddings.py:57`).

## INVARIANTS

- No provider call runs on the event loop. This is the fix for the defect where
  a synchronous call at `brain.py:233` stalled the entire bus.
- A provider error surfaces as a typed error, never as an empty string.

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-PROVIDER-UNAVAILABLE` | Connection refused or host unreachable |
| `ERR-PROVIDER-AUTH` | Missing or rejected credential |
| `ERR-PROVIDER-MODEL` | Model not found or not pulled |
| `ERR-PROVIDER-TIMEOUT` | The provider did not respond in time |

## CONCURRENCY

`chat_stream` calls are independent; multiple may run. Embeds are serialized by
the caller (`embeddings.py`) to avoid hammering the endpoint.

## RESOURCES

Depends on the SDK's own pool. No static budget.

## Behavior preserved from as-built

`_strip_thinking` (`reason.py:8`) handles real observed formats: qwen3's
` thinking` / `</thinking>` and `<response>`, and deepseek's XML. It is kept and
moved into `reasoning/`, because a streaming model still emits these tags and
the display must not show raw thinking.

## Stream mapping into `TurnEvent`

The native harness maps provider chunks to events:

| Provider chunk | `TurnEvent` |
| --- | --- |
| text delta | `text_delta` |
| reasoning/thinking content, when separable | `thinking_delta` |
| assembled tool calls | `tool_call` |
| terminal content | `text_final` |
| usage | `usage` |

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| Streaming yields text deltas then a terminal chunk | host (fake provider) | T-0601 |
| Tool calls are normalized across providers | host | T-0602 |
| Unknown provider raises clearly | host | T-0603 |
| Thinking tags are stripped from final text | host | T-0604 |
| No provider call blocks the loop | host (loop-yield timing) | T-0605 |
| Provider error is typed, not silent | host | T-0606 |
