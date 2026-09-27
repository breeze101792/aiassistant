# PLAN — AI Assistant Refactor

The execution plan. Design lives in [`docs/`](docs/README.md); this file is the
work order and the record of what was built.

> **Status (2026-09-27): all seven chunks are implemented.** The assistant runs,
> the suite is green (341 passed, 1 skipped), and the harness swap and pi
> confinement were verified against a live pi 0.87.1 process. Ctrl+C and
> `/exit` both terminate cleanly, verified through a real terminal.

## Goal

Refactor the existing bus-modular Python assistant into a **voice-first
assistant** with a **native orb UI** and a **config-swappable agent harness**
(`native` or `pi`), running on **macOS and Linux**, with a console fallback.

## What the implementation changed in the design

Two findings from building it changed the design. Both are recorded because a
plan that never corrects itself is not a plan.

| Finding | Where | Consequence |
| --- | --- | --- |
| **pi's `message_end` fires once per role** — system, user, then assistant. | Live spike, chunk 4 | Mapping every `message_end` as the answer would have made the system prompt the spoken response. Only `role: assistant` is a final now. |
| **A failed pi turn is an assistant message with `stopReason: "error"`**, not a separate error event, and `errorMessage` is a nested JSON blob. | Live spike, chunk 4 | Without this a 429 read as an empty successful turn. It now maps to `turn_error` with the blob flattened and classified. |
| **Ctrl+C did not terminate the assistant.** The console read a line with `await loop.run_in_executor(None, input, prompt)`. `input()` blocks until a line arrives, and `asyncio.run` waits for the default executor at shutdown, so SIGINT set the shutdown flag and then hung forever. | Reported by the user after the refactor | The read loop is now cancellable: a loop reader on a tty, a short non-blocking poll otherwise, and `stop()` cancels the reader instead of waiting on it. Verified against a real pty sending `\x03`. Pinned by `tests/test_console.py::TestShutdownSafety`. |
| **Opening the audio device inside a unit test segfaults the host audio stack.** | Chunk 5 tests | `VoiceModule.disable_audio()` exists so tests and headless runs never touch a real device. |
| **Ollama requires tool-call arguments as a dict; OpenAI requires a JSON string.** | Chunk 3 tool round-trip | Argument encoding moved behind `provider.format_tool_arguments`; hardcoding either form fails the other provider at request time. |

## Additions beyond the original plan

Implemented because the design required them once the code existed:

| Item | Why it was needed |
| --- | --- |
| `agent.transcript.snapshot` topic and its handler | The orb detects a delta gap and asks for a resync; without a server side, the gap could not be repaired. |
| `agent.tool.event` topic | Tool activity needed its own channel; `agent.delta.kind` covers only text and thinking. |
| `agent.policy.RetryPolicy` | The old `Reflector` computed RETRY and nothing consumed it. The retry is now real and bounded, with non-transient failures aborting immediately. |
| `pi_extensions/workspace_guard.ts` | Verified live: an out-of-workspace `read` is blocked with our reason string and `is_error: true`, while an in-workspace read succeeds. |
| `scripts/setup_pi.sh` | Pins pi 0.87.1 and reports that the managed install is not on PATH by default. |

## Ground rules

- The design doc set in `docs/` is the gate. It exists before code changes.
- Keep the pytest suite green at each fence where possible.
- Every claim about current behavior cites `file:line`.
- "Unverified" is an allowed and explicit state.

## Three findings that reshaped this plan

Discovered by adversarial review of the first draft. Each is cheap to fix now
and expensive later.

| # | Finding | Evidence | Consequence |
| --- | --- | --- | --- |
| 1 | **The bridge the orb depends on is already broken.** | `bus/remote.py:45` is `_handle_connection(self, websocket, path)`; installed `websockets` is 16.0, whose handler takes one argument. Every remote connection dies with a `TypeError`. No test covers `RemoteBus`. | The "frozen bridge" was a false premise. Fixing it is chunk 1, before anything depends on it. |
| 2 | **pi plus the current bus is a remote shell.** | `remote.py:32` binds `0.0.0.0`; `config.yaml:6` token is `""`; `remote.py:50` enforces auth only when the token is non-empty. pi runs `read`/`bash`/`edit`/`write` as the user with no permission system. | Loopback bind plus a required token are mandatory, not optional (REQ-SEC-001/002). |
| 3 | **Interrupt cannot work as drawn.** | `brain.py:172` calls `asyncio.ensure_future(self._thinking_loop(...))` and stores no handle. | The turn task must be retained, and `command.agent.interrupt` must be subscribed and acted on. |

Two smaller confirmed defects, fixed in passing:

- `sandbox.py:58` uses `startswith`, so `/tmp/aiassistant-evil` passes as inside
  `/tmp/aiassistant`.
- `skills/base.py:68` subscribes `brain.ask.response`, which is never published
  (the brain answers via `respond_rpc` at `brain.py:194`), and `:71` calls
  `run_until_complete` inside a running loop.

## Corrections to earlier claims

Recorded so the record is honest.

| Claim | Truth |
| --- | --- |
| "There is a web frontend to drop" | There is no frontend. `canvas/backends/web.py:7-21` is an all-`pass` stub whose `start()` claims a server that does not exist. Dropping it is a deletion. |
| "`understand.py` / `plan.py` are dead code" | Not dead — wired at `brain.py:220` and `:250`. They are thin ceremony, which is a simplification decision (ADR-0009), not dead-code removal. |
| "`reflect.py` is the retry policy" | `RETRY` and `FALLBACK` are computed but never acted on; only `ABORT` is branched on (`brain.py:272-286`). The retry never happens. `tests/test_brain.py:91` tests behavior that does not exist. |
| "`respond.py` is a pipeline stage" | It duplicates `memory.save_turn`. Only one of the two was ever called. |

## Module map

| Old | New | Action |
| --- | --- | --- |
| `brain/` | `agent/` | Split and rewrite |
| `llm/` | `reasoning/` | Rewrite with streaming |
| `ears/` + `mouth/` | `voice/` | Merge |
| `hands/` | `tools/` | Move, fix sandbox |
| `eyes/` | `vision/` | Move, frozen |
| `chat/` | `messaging/` | Move, frozen |
| `cli/` | `console/` | Rewrite with streaming |
| `canvas/` | — | **Delete** |
| `modules/scheduler/` | `scheduler/` | Promote to top level |
| `main_remote.py` | — | **Delete** |
| — | `agent/harness/{native,pi}/` | New |
| — | `orb/`, `bridge/`, `pi_extensions/`, `scripts/` | New |

Full per-file dispositions are in the design docs; the module contracts are in
[`docs/architecture/modules/`](docs/architecture/modules/).

## Work breakdown

Ordered by what unblocks what. All chunks are in scope; the order is dependency,
not deferral.

### Chunk 0 — Design docs ✅

**Deliverable:** the `docs/` tree and this plan.

| Output | Status |
| --- | --- |
| `docs/README.md` entry point | done |
| `requirements/` — 80 requirements, scope, flows, features | done |
| `architecture/` — overview, 11 module contracts, data model, 15 ADRs | done |
| `contracts/` — protocols (IF-0001..0008), schemas, orb API | done |
| `testing/` — TEST_PLAN, 60 cases, trace matrix | done |
| `operations/` — build, deploy, repo pinning | done |
| `security/` — threat model, 6 risks | done |
| `research/` — pi RPC facts, UI stack comparison | done |
| `ui/` — 12 design docs plus a mockup | done |

**Verify:** doc set is well formed, every REQ appears in `trace.md`, cross-links
resolve. Docs-only, so no tests.

### Chunk 1 — Bus truth and safety

**Unblocks:** the orb (chunk 6) and everything downstream.
**Risk:** high value, low mechanical risk.
**Gate (must all pass before chunk 2):** T-0501, T-0502, T-0503, T-0504, T-0505,
T-0507, T-0508, T-0509, T-0510, T-0511, plus a live connect/subscribe/publish
check and a non-loopback-bind refusal.

| Task | Detail |
| --- | --- |
| Fix the handler | `bus/remote.py:45` → `async def _handle_connection(self, websocket)` |
| Bind loopback | `127.0.0.1` by default, configurable (REQ-SEC-001) |
| Require a token off-loopback | Refuse to start otherwise (REQ-SEC-002) |
| Fix `_forward` thread safety | Schedule on the loop (`remote.py:87`) |
| Add `unsubscribe` over WS | Currently only cleaned up on disconnect |
| `bus/topics.py` | Constants plus payload schema tests |
| Off-loop calls | LLM *and* embeddings (`brain.py:343`, `embeddings.py:65`) |
| Retain the turn task | And subscribe `command.agent.interrupt` with the ordered cancel sequence |
| Tests | A `RemoteBus` integration test — there is none today, which is why the bug shipped |

**Verify:** `pytest`; a live connect/subscribe/publish check; a non-loopback
bind without a token must refuse to start.

### Chunk 2 — Rename sweep and deletions

**Risk:** wide but mechanical. Run it alone; it touches everything.
**Gate:** the full suite passes under the new layout, a grep for every old name
returns nothing (REQ-STRUCT-001), the config-migration test passes, and the
before/after test counts are reported (REQ-STRUCT-002).

| Task | Detail |
| --- | --- |
| Rename modules | Per ADR-0002; include `MODULE_SPECS` (`main.py:69-78`) and `NON_CRITICAL` (`:81`) |
| Delete | `canvas/`, `main_remote.py`, `.gitmodules`, `aiohttp` |
| Config migration | Dual-read legacy keys with a deprecation warning (REQ-CFG-004) |
| Codemod the string-coupled code | Test `monkeypatch` paths such as `tests/test_ears.py:46` |
| **Do not rename frozen topic values yet** | Values consumed by frozen modules stay; the rest rename with tests (IF-0007) |

**Verify:** grep for every old name (REQ-STRUCT-001); full `pytest` fence;
before/after test counts reported (REQ-STRUCT-002).

> **Watch item:** `brain.py:211` decides whether to speak by comparing
> `payload.get("source") == "ears"`. Changing that string silently disables
> speech. It must become a topic/constant with a test asserting voice-origin
> input produces speech.

### Chunk 3 — Reasoning contract and agent loop

**Risk:** high — this is the core rewrite.
**Gate:** T-0401, T-0402, T-0301, T-0307, T-0601, T-0602, T-0603, T-0604,
T-0605, T-0606, plus the loop-yield test.

| Task | Detail |
| --- | --- |
| `reasoning/` | Streaming `chat_stream`, providers, typed errors, `_strip_thinking` preserved (`reason.py:8`) |
| `agent/harness/base.py` | `AgentHarness`, `TurnEvent`, `HarnessCaps` |
| `agent/harness/native.py` | Our loop plus `reasoning/` plus `tools/` |
| `agent/loop.py` | Single-turn gate, retained task, delta coalescing to ≤20 Hz |
| Delete `understand.py`, `plan.py` | Keep `ToolCall` and `_repair_and_parse_json` |
| Make the policy retry | `RETRY` and `FALLBACK` must actually act (ADR-0009) |
| Merge `respond.py` into `agent/transcript.py` | One writer per turn |

**Verify:** `pytest`; a conformance suite parametrized over harnesses;
a loop-yield test proving no provider call blocks the loop.

### Chunk 4 — pi spike, then adapter

**Risk:** medium. The spike comes **first** so the adapter is not built on
assumptions.
**Gate:** T-0302, T-0303, T-0305, T-0306, T-0308, T-0309, T-0310.

#### The spike, as an executable procedure

Each step has a pass/fail, and the outcome is written back into IF-0003
(`docs/contracts/protocols.md`) and `docs/research/pi-rpc.md`. No step may be
assumed. (Both documents were removed in Round 5; the references are kept as the
record of what this step fed at the time.)

| Step | Action | Pass condition |
| --- | --- | --- |
| S1 | Run `./scripts/setup_pi.sh`; then `pi --version` | A version string prints; it equals the pinned version |
| S2 | Confirm the binary path and record it | The path is stable and absolute; no `npm`/Node required |
| S3 | Spawn `pi --mode rpc --no-session` with the start command; send `get_state` | One line of JSON returns with the same `id`, `success: true` |
| S4 | Send `prompt` with a trivial message; capture stdout to a file | `disposition` ∈ {started, queued, handled}; the first line of stdout is valid JSON (purity) |
| S5 | From the S4 capture, record every event type and the exact `message_end` content-block shape | The blocks are recorded as fixtures; the shape matches or corrects the mapping table |
| S6 | Send a prompt that invokes a long-running tool, then send `abort` mid-tool | Record whether `abort` returns and whether the turn ends. **If it does not, the cancel path must fall back to process restart, and IF-0003 is corrected.** |
| S7 | Send a second `prompt` while the first is still streaming | Record the error or the accepted behavior; the adapter must handle it, not crash |
| S8 | Verify `--no-session` writes no session file | No file appears under the agent dir; record what `get_state` reports |
| S9 | Write a non-JSON line and a wrong-shape line into the reader's input path | The reader logs and continues; the turn still reaches `agent_settled` |
| S10 | Install `workspace_guard.ts`; ask pi to read a file outside the workspace | The tool call is blocked with our reason string |
| S11 | Close stdin while a turn runs | pi exits cleanly (reap with no signal), and no cancel was attempted |

Fixtures recorded in S5 and S9 become `tests/test_pi_events.py`. S6 and S7
determine whether the "abort during a running tool" row stays unverified or is
resolved, and whether cancellation needs a process-restart fallback.

| Step | Detail |
| --- | --- |
| Spike | Install the pinned pi; verify the `[U]` items from IF-0003: `abort` during a running tool, `message_end` content-block shape, `--no-session` semantics, a `prompt` mid-stream |
| Record fixtures | JSONL transcripts for the mapping tests |
| Adapter | `agent/harness/pi/{process,protocol,events,adapter}.py` |
| Extension | `pi_extensions/workspace_guard.ts` |
| Provisioning | `scripts/setup_pi.sh`, standalone binary preferred (no Node) |

**Verify:** fixture tests for the event mapping; malformed-line resilience; a
kill-the-child-then-restart test; the workspace guard blocking an out-of-workspace
path; no zombie after quit.

### Chunk 5 — Voice pipeline

**Risk:** highest. Ship in slices.
**Gate:** T-0101..T-0108, of which T-0101..T-0105 and T-0107 are host-testable
and T-0106/T-0108 need the audio rig.

| Slice | Detail |
| --- | --- |
| 1 | Merge `ears` + `mouth` lifecycles into one module; fix the duplex FSM |
| 2 | Playback: `sounddevice` callback stream plus MP3 decoding |
| 3 | Capture: `sounddevice` input, 20 ms frames |
| 4 | VAD plane, bounded queues, overflow policy |
| 5 | Sentence chunker and streaming TTS |

**Verify:** pure-logic tests for the chunker and queue; a mock-playback
interrupt test; on-target latency and wake-gate checks on real hardware.

### Chunk 6 — Orb

**Risk:** medium.
**Gate:** T-0201..T-0207; T-0201, T-0206 are manual on both OSes, the rest run
against a fake bridge.

| Slice | Detail |
| --- | --- |
| G1 | `bridge/` client plus an orb skeleton: frameless always-on-top window, a state-colored circle, WS connect/subscribe — so a GPU problem never blocks the orb existing |
| G2 | Shader orb per `docs/ui/` |
| G3 | Text input, interrupt, controls, packaging via `pyside6-deploy` |

**Verify:** host tests with a fake bridge for state and delta handling; manual
runs on macOS and Linux; reconnect resync.

### Chunk 7 — Integration, cleanup, doc refresh

**Gate:** the full suite passes on macOS **and** Linux, and every acceptance
criterion in [scope.md](docs/requirements/scope.md) is checked by hand.

| Task | Detail |
| --- | --- |
| End-to-end | Config-default demo path: voice → agent → harness → voice → orb |
| Cleanup | Remove the web stub, `aiohttp`, `.gitmodules` |
| Docs | Update to as-built; retire `ARCH.md` and `PLAN.md`; rewrite `README.md` |
| Final verification | Full suite on macOS and Linux; manual acceptance per `docs/requirements/scope.md` |

## Risk register

| Risk | Retirement |
| --- | --- |
| pi behaviors assumed but unverified | The spike runs before the adapter; fixtures recorded |
| pi child dies mid-turn | Supervised lifecycle with bounded restart; kill test |
| User surprised by pi's permissions | Opt-in flag, workspace guard, no shell, and a written warning |
| Double-contexting pi turns | Explicit rule, contract test, restart-only prime |
| Qt and asyncio entanglement | Eliminated by the process split; `QWebSocket`, no qasync |
| GPU work consumes the schedule | G1 ships a working circle before any shader work |
| Linux audio differences | `sounddevice` plus a Linux hardware smoke in chunks 4–5 |
| The rename breaks hidden string couplings | One isolated chunk, grep sweep, topic constants, test fence |
| Delta flooding over the WS bridge | Publisher-side coalescing at ≤20 Hz |

## Verification posture

Stated per change, never assumed.

| Chunk | Verification |
| --- | --- |
| 0 | well-formedness, link check, trace completeness |
| 1 | `pytest`, live WS connect, non-loopback refusal |
| 2 | grep for old names, full suite, test count delta |
| 3 | `pytest`, conformance suite, loop-yield test |
| 4 | fixture tests, child-kill test, workspace-guard test |
| 5 | unit tests plus on-target audio rig |
| 6 | fake-bridge host tests plus manual on both OSes |
| 7 | full suite on both OSes, manual acceptance criteria |

## Round 2 — headless UI toggle and pi path relocation (2026-09-27)

Work that came after the refactor: make the assistant usable on a machine with
no display, and fix the pi confinement path bug found while doing it.

### Headless UI toggle (REQ-CONSOLE-006)

`display.mode` gained `auto` (now the default): the orb is shown only when a
display server is available, so a headless machine starts clean with no config
edit. `AIASSISTANT_DISPLAY_OFF` forces the console; an explicit `--mode ui` or
`--mode console` outranks it, matching the documented precedence (REQ-CFG-002).
Only Linux is probed for `DISPLAY`/`WAYLAND_DISPLAY`: macOS Aqua exports
neither, so probing it would wrongly force a Mac desktop headless.

| File | Change |
| --- | --- |
| `config.py` | `gui_available()`, `resolve_display_mode()` with CLI choice |
| `main.py` | `--mode ui`/`--mode console` passed as a display choice, not a config override |
| `config.yaml` | `display.mode` default `orb` → `auto` |
| `tests/test_display.py` | 20 cases: detection, auto, precedence, override |

### pi path relocation (ADR-0016)

`pi_extensions/workspace_guard.ts` and `pi_workspace/` were resolved against the
process CWD. Launched outside the repo root, `-e` pointed at a missing file, so
pi loaded **no** extension and the workspace guard was silently off. The adapter
also read `policy_extension` with no default, so an omitted key disabled the
guard.

| Change | Detail |
| --- | --- |
| Guard is package data | Moved to `agent/harness/pi/workspace_guard.ts`, shipped via `[tool.setuptools.package-data]`, resolved with `importlib.resources` |
| Workspace anchored | Default `~/.config/aiassistant/pi_workspace`, so it never moves with the CWD |
| Fail closed | `start()` verifies the guard file before the binary and raises if missing; `null` logs a loud warning |
| Guard internals | `realpathSync` before the prefix check (symlink escape) and `continue` not `return` in the allow-dir branch (multi-arg tools) |

### Verification this round

- Full suite: **360 passed, 5 skipped**, 5 failed. The 5 failures are
  environment-only and predate this round: two integration tests need a running
  Ollama; three `test_voice_asr` tests need `pkg_resources` and a Nix
  `libstdc++` on the test interpreter. Baseline before the round was 344 passed.
- Guard logic exercised under Node 24 (type-stripping): path-inside/outside,
  the `-evil` boundary, a symlink escape, and a `find` call whose `cwd` is
  outside all pass.
- Wheel contains `workspace_guard.ts` with both guard fixes.
- Live repro from `/tmp`: `-e` now resolves to a real file and the workspace to
  `~/.config/aiassistant/pi_workspace`; a missing guard raises, a disabled guard
  warns.
- Unverified: the on-target orb on a real macOS/Linux desktop (no display on the
  build machine), and frozen-build resource extraction.

## Round 3 — one frontend selection and the TUI orb (2026-09-27)

The user asked for a TUI orb for hosts with no display server, and a way to
choose `tui` or `gui` explicitly. Their directive defined the model: **`mode`
selects only the visual shell; text and audio are always-available
capabilities.** See [ADR-0017](docs/architecture/decisions/ADR-0017-frontend-selection-tui.md)
and [frontends.md](docs/requirements/features/frontends.md).

### The model

| Concern | Before | After |
| --- | --- | --- |
| Selection | `display.mode: orb\|console\|auto` | `gui\|tui\|none\|auto` (`orb`/`ui`→`gui`, `console`→`none`) |
| CLI | `--mode {console,audio,ui,auto}` | `--frontend {gui,tui,none,auto}`; `--mode` a hidden deprecated alias |
| `audio` | a `--mode` value | the `--audio` voice preset; not a frontend |
| `auto` | orb when a display exists | `gui` when a display exists, else `none`; never `tui` |

`auto` resolution now checks display variables first, then `SSH_CONNECTION`/
`SSH_TTY`, then platform — closing the gap where a macOS SSH session wrongly
reported a GUI and the orb failed three times.

### The TUI orb

A separate process (`python -m aiassistant.tui`), stdlib `curses` only, reusing
`OrbViewModel` and `bridge.Bridge`. It renders the same state, transcript, and
controls as the GUI orb via a new shared `feed(model, topic, payload)` dispatch,
so the two frontends cannot drift. Terminal preconditions are checked **before**
`curses.initscr()` (a failed `initscr` can exit the interpreter); the parent
yields the tty to the TUI and reclaims it when the TUI exits.

### Console fixes found while building this

The console was subscribed to topics nothing publishes:
`status.ears.listening/processing/transcribed/error` and `status.mouth.error`.
Its status handlers never ran, and it never subscribed to `agent.delta`, so
"text is always available" was partly false and REQ-CONSOLE-005 was unmet. It
now subscribes to `voice.state`, `voice.transcribed`, `agent.delta`,
`agent.final`, and `agent.turn.error`, and renders deltas incrementally.

### Review findings fixed before this landed

An adversarial review of the first draft found real defects, all fixed:

| Finding | Fix |
| --- | --- |
| A clean frontend exit (code 0) was treated as a crash, so `Ctrl+D` could not quit the TUI | A clean exit releases the tty and does not respawn |
| Restart counter reset on respawn and a new watcher scheduled per spawn | One watcher owns respawns; the counter resets only on the initial spawn |
| A failed TUI spawn left the console suspended forever | The spawn failure resumes the terminal |
| A delta gap made the GUI orb re-request a snapshot on every message | The snapshot request is gated to `agent.delta`, as before |
| The TUI double-subscribed on reconnect | Subscribe only on the first connect; the bridge replays its own |
| The TUI child was spawned with `stdout=DEVNULL`, so it always exited 3 (found by a pty test) | The TUI inherits the terminal; the GUI orb does not |

### Verification this round

- Full suite: **423 passed, 5 skipped**, 5 failed. The 5 failures are the same
  environment-only ones (no Ollama; missing `pkg_resources`). Baseline before
  round 3 was 413 passed.
- Supervised live under a pty: `--frontend tui` spawns the TUI, it registers with
  the bus, `Ctrl+D` exits 0, the parent does not respawn it, and the console
  resumes.
- `--frontend gui` with no display and no tty degrades loudly to text-only and
  keeps running.
- `--frontend none` starts no visual shell; all modules still start.
- Unverified: the TUI's visual rendering and resize on a real human terminal
  (only a pty was used here), and the GUI orb on a desktop with a display.

## Round 4 — defaults in code, config.yaml is the local override (2026-09-27)

Config model change. The first attempt (an auto-created
`~/.config/aiassistant/config.yaml`) was rejected: defaults should live in code,
and `~/.config` should not be set up. The final model:

| Layer | Path | Role |
| --- | --- | --- |
| Code defaults | `config.py` `DEFAULTS` | The single source of truth; the app runs on these alone. |
| Local override | `config.yaml` (`-c`) | Optional, git-ignored; deep-merged over the defaults. |
| Example | `config.example.yaml` | Tracked, commented copy of the defaults. |

`load_config` deep-copies `DEFAULTS`, then merges the local file over it, so it
names only what changes. No file is created anywhere; no `~/.config` setup.
Precedence: CLI > environment > `config.yaml` > code defaults.
The orb and TUI read the same loader, so a bus port set in `config.yaml`
reaches them.

### Verification this round

- `load_config()` with no `config.yaml` returns the code defaults, and a full
  live run starts and serves the console on defaults alone.
- A local file overrides only the keys it names; the rest keep their defaults.
- Fix found by the tests: an initial shallow copy let a local override mutate
  the global `DEFAULTS`; `load_config` now deep-copies.
- Tests: `tests/test_config.py` (14 cases) including a guard that
  `config.example.yaml` matches `DEFAULTS` key for key, so the example cannot
  drift into a lie (REQ-CFG-008). Full suite: **437 passed, 5 skipped**, 5
  failed (the same environment-only failures).

## Round 5 — remove the external pi harness (2026-09-27)

By user decision, the external `pi` coding agent was removed from the code and
its traces removed from the docs. This round records what changed; earlier rounds
stand as the record of what was true then.

**Kept intentionally:** the harness abstraction — `AgentHarness`, `HarnessCaps`,
`create_harness`, and `FakeHarness`. One implementation ships (`native`); the
seam stays open so a future harness is added by implementing the contract and
registering it in the factory (recorded as REQ-HARNESS-008). The `agent.harness`
and `agent.llm` config keys remain; the `agent.pi.*` block is gone.

**Withdrawn, not renumbered:**

- ADRs ADR-0007, ADR-0008, ADR-0012, ADR-0016 — files deleted, index rows
  marked withdrawn.
- REQ-HARNESS-003/004 and REQ-SEC-003..007 — withdrawn; REQ-HARNESS-001/002/005/
  006/007 were rewritten and REQ-HARNESS-008 added. The withdrawn numbers are
  not reused.
- Interface IF-0003 (pi RPC) — withdrawn; other IF numbers unchanged.
- MOD contract `pi-harness.md` — deleted. `docs/architecture/modules/tui.md` is
  now MOD-0012.

**Deleted:** `docs/architecture/modules/pi-harness.md`,
`docs/research/pi-rpc.md`, the four external-harness ADRs, `scripts/setup_pi.sh`,
`src/aiassistant/agent/harness/pi/` (and `workspace_guard.ts`).

**Files and tests:** the two pi test modules (`tests/test_pi_adapter.py`,
`tests/test_pi_spike_findings.py`) were deleted; test modules fall from 26 to 24
and test functions from 433 to 380. The suite collects 355 cases excluding
`tests/test_voice_asr.py`, which cannot import on this host (`libstdc++` absent);
of the rest, 352 pass, 1 skips, and 2 fail on the two Ollama-dependent integration
cases. No test file links to a deleted doc.

## Open questions

Each with the default taken unless the user says otherwise.

| # | Question | Default |
| --- | --- | --- |
| 1 | PTT start/end has no bus topic (noted in IF-0007) | Add `command.voice.ptt.start` / `.end` in chunk 1 |
| 2 | The resync snapshot topic is undefined | Add `agent.transcript.snapshot` in chunk 1; the orb shows "resync pending" if a gap is detected before it exists |
| 3 | Exact PCM playback queue depth | Tune during chunk 5 against the latency budget |
| 4 | Which MP3 decoder | Decide in chunk 5; `miniaudio` is the leading candidate |
| 5 | Wake phrase and identity | Ships as `jarvis` / "hi jarvis"; the `agents:` map already supports more |
| 6 | pi provisioning: binary or npm | Standalone binary, so Node is not required |
| 7 | Whether the orb should be a `.app` (macOS) | Yes, but notarization is deferred |
| 8 | Whether `vision` and `messaging` should get real work | No — renamed and frozen this round |

## Definition of done

The acceptance criteria in
[`docs/requirements/scope.md`](docs/requirements/scope.md), verifiable by a
human on both macOS and Linux:

1. Documented install and launch succeed on both OSes.
2. A native orb window opens with no browser or web server involved.
3. A spoken question gets a spoken answer, in `ptt`, `open`, and `wake` modes.
4. The orb cycles through its states visibly during a turn.
5. Stop cancels an in-flight turn and silences playback.
6. Switching `harness` between `native` and `pi` in config changes the backend
   with no code change.
7. pi runs as a managed subprocess: prompts stream, `agent_settled` ends the
   turn, and quitting leaves no orphan.
8. A tool result reaches the spoken answer on the native path.
9. Killing the harness mid-session shows backend-down and a visible error —
   never silence.
10. Unplugging the mic degrades to text/console without a crash.
11. Console mode runs headless with transcript, status, and errors.
12. No `brain`/`ears`/`mouth`/`eyes`/`hands`/`canvas`/`chat`/`cli` names remain.
13. The suite passes under the new layout, with counts reported.
14. With no backend installed, the app still starts and shows the setup path.
