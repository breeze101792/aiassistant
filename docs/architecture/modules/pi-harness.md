# MOD-0003 — `agent/harness/pi`

**Purpose:** Drive the external pi coding agent as an `AgentHarness`, mapping its
JSONL RPC events onto our `TurnEvent` vocabulary.

**Must not do:** interpret pi's tool results, inject pi's own context, or send
pi's RPC `bash` command.

**Dependencies:** `agent/harness` (interface) · the `pi` binary as a child
process · [IF-0003](../../contracts/protocols.md#if-0003-pi-rpc).

**State it owns:** the child process, its stdin/stdout handles, the pending
command futures, and the active-turn state.

See [research/pi-rpc.md](../../research/pi-rpc.md) for the established facts and
source citations.

## Process lifecycle

| Aspect | Design |
| --- | --- |
| Spawn | `pi --mode rpc --no-session --tools <allowlist> --no-extensions -e <guard.ts> --no-approve -nc` |
| Working dir | `cwd` = configured workspace. Sets pi's tool defaults. **Not** a boundary. |
| Environment | Explicit minimal env plus configured entries. Never logged. |
| stdout | One asyncio reader task. `readline()` on the binary pipe; split on `\n` only. |
| stderr | Drained by its own task to the log. **Must** be drained or pi blocks on a full pipe. |
| Health | RPC `get_state` at spawn and before each turn. |
| Restart | On unexpected exit: error the active turn, respawn with backoff `[1,2,4,8,30]s` (PLACEHOLDER — tune), max 3 attempts per 10 min (PLACEHOLDER — tune), then report unhealthy and fail fast. |
| Shutdown | Close stdin, wait 5 s (PLACEHOLDER), then `terminate()`, then `kill()`. |

## PROVIDES

### `run_turn(req) -> AsyncIterator[TurnEvent]`

1. Write `{"id": turn_id, "type": "prompt", "message": req.text}`.
2. Await the response for `turn_id`; its `data.disposition` is `started`,
   `queued`, or `handled`.
3. Yield mapped events from the shared reader until `agent_settled`.
4. Yield `turn_done(cancelled=False)`.

Correlation: commands are correlated by `id`; session events are correlated
**temporally** — every event between the `prompt` response and its
`agent_settled` belongs to that turn.

### `cancel() -> None`

Sends `clear_queue`, then `abort`, and awaits the abort response, which arrives
when pi is idle.

> **Never close stdin to cancel.** Closing stdin is pi's orderly-shutdown signal.

### `health() -> HarnessHealth`

RPC `get_state` with a short timeout.

## Event mapping

| pi event | `TurnEvent` | Note |
| --- | --- | --- |
| `message_update` / `text_delta` | `text_delta` | Live text |
| `message_update` / `thinking_delta` | `thinking_delta` | Never spoken |
| `toolcall_end` | `tool_call` | Args assembled from deltas |
| `tool_execution_start` | `tool_result(status=running)` | Correlated by `toolCallId` |
| `tool_execution_update` | `tool_result(status=partial)` | Display only |
| `tool_execution_end` | `tool_result(result, is_error)` | |
| `message_end` | `text_final` | **Authoritative**; replaces deltas |
| `message_update.usage` | `usage` | |
| `agent_settled` | `turn_done` | End of turn |
| error / `auto_retry_end(success=false)` | `turn_error` | |
| `compaction_*`, `queue_update`, `session_info_changed` | — | Logged, not surfaced |

## Tool ownership

`caps.owns_tools = True`. pi runs its own tools. There is no RPC to register
our tools without writing a pi **TypeScript extension**, which is out of MVP
scope (the mechanism exists and the door is open — see
[ADR-0008](../decisions/ADR-0008-pi-owns-tools.md)).

Consequences: our tools and our sandbox do not apply on pi turns; the tool
audit trail comes from `tool_result` events.

## Memory

`caps.owns_memory = True`. The prompt is the bare user text. The single
exception is a compact recent-conversation prime after a process restart, so a
crash does not erase continuity (REQ-MEM-004).

## Confinement

| Layer | Mechanism | Covers |
| --- | --- | --- |
| Tool allowlist | `--tools read,write,edit,grep,find,ls` (no shell) | Removes arbitrary execution |
| Policy extension | `workspace_guard.ts` `tool_call` hook returning `{block: true}` | Blocks paths outside the workspace |
| Process hygiene | `cwd` pin, scrubbed env, `--no-extensions --no-approve -nc` | Reduces blast radius; prevents in-folder injection |
| RPC shell | **Never sent** by the host | Closes the RPC `bash` bypass |

**Not covered at the coding level:** network access and prompt injection. See
[security/threat-model.md](../../security/threat-model.md) and
[ADR-0012](../decisions/ADR-0012-pi-confinement.md).

## REQUIRES

- `agent/harness` — the interface it implements
- The `pi` binary, pinned and provisioned (REQ-SEC-003)
- The workspace directory, for `cwd`
- The policy extension file, at an absolute path

It requires **nothing** from `tools/`, `reasoning/`, or `agent/memory`: on pi
turns those are deliberately out of the path (ADR-0008).

## INVARIANTS

- Exactly one child process exists while the harness is healthy.
- At most one turn is active.
- The reader task never stops reading; a stalled reader stalls pi.
- Every command response is routed to its pending future by `id`; an unmatched
  response is logged, not raised.
- A session event between a `prompt` response and its `agent_settled` belongs to
  that turn, and to no other.
- `cancel()` never closes stdin.
- The host never sends the RPC `bash` command.

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-PI-SPAWN` | Binary missing or not executable |
| `ERR-PI-DEAD` | Child exited mid-turn |
| `ERR-PI-PROTOCOL` | A stdout line was not JSON, or was JSON of the wrong shape |
| `ERR-PI-ABORT-TIMEOUT` | `abort` did not return within `conversation.turn_timeout_s` |

## CONCURRENCY

- One long-lived child. One active turn.
- The reader task is shared; control-command responses are routed by `id` to
  their pending future.

## RESOURCES

- One child process, two pipes, one reader task, one stderr task.
- Unverified items that must be confirmed by the host spike before this is
  relied on: behavior of `abort` during a running tool; exact `message_end`
  content-block shape; `--no-session` on-disk semantics; behavior of a `prompt`
  arriving mid-stream.

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| Event mapping matches fixtures | host (recorded JSONL) | T-0302 |
| Malformed line does not kill the reader | host (fixture) | T-0306 |
| Cancel ends the turn as cancelled | host (fake pi) | T-0303 |
| Crash mid-turn errors the turn and restarts | host (kill child) | T-0308 |
| Prompt carries no memory prefix except after restart | host | T-0305 |
| Workspace guard blocks out-of-workspace paths | host (fixture) | T-0309 |
| No zombie after quit | host, mac, linux | T-0310 |
