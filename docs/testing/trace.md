# Traceability Matrix

Two questions, one glance each:

1. Does every `REQ-*` have at least one proving `T-*`? (§1)
2. Does every `T-*` trace to a `REQ-*`? (§2)

`unverified` is allowed; **silently** unverified is not. Every gap below names a
reason. Case detail: [cases.md](cases.md). Method definitions:
[TEST_PLAN.md § 1](TEST_PLAN.md#1-strategy--one-case-one-environment).

## 1. REQ → T

All 93 requirements from
[../requirements/requirements.md](../requirements/requirements.md).

### Voice I/O

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-VOICE-001 | verified | T-0101, T-0102 | mock, host |
| REQ-VOICE-002 | verified | T-0103 | host |
| REQ-VOICE-003 | verified | T-0108 | rig |
| REQ-VOICE-004 | **failing test, real bug (BUG-5)** — T-0109 proves `halasr` does not select `HalASRBackend` | T-0109 | host |
| REQ-VOICE-005 | verified | T-0107 | host |
| REQ-VOICE-006 | verified | T-0104, T-0105 | mock, host |

### Wake and listening

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-WAKE-001 | **unverified — mutually-exclusive listening modes not tested** | — | — |
| REQ-WAKE-002 | verified | T-0106 | rig |
| REQ-WAKE-003 | verified | T-0106 | rig (via `WakeDetector` seam) |
| REQ-WAKE-004 | **unverified — PTT hotkey/orb control case missing** | — | — |
| REQ-WAKE-005 | verified | T-0104, T-0204, T-0906 | mock, host |
| REQ-WAKE-006 | verified | T-0105, T-0202 | host |
| REQ-WAKE-007 | **unverified — mute on/off not tested** | — | — |
| REQ-WAKE-008 | **unverified — deferred barge-in is an inspection claim; no T asserts it** | — | — |

### Conversation

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-CONV-001 | **unverified — native context window (`context_turns`) not tested** | — | — |
| REQ-CONV-002 | **failing test, real bug (BUG-4)** — `busy: queue` documented but unimplemented; T-0404 proves it cancels instead | T-0404 | host |
| REQ-CONV-003 | verified | T-0303, T-0204, T-0906 | host, mock |
| REQ-CONV-004 | verified | T-0903, T-0402 | host |
| REQ-CONV-005 | **unverified — `speak_text_turns: false` not tested** | — | — |
| REQ-CONV-006 | verified | T-0401, T-0403 | host |

### Orb UI

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-ORB-001 | verified | T-0201, T-0207 | mac, linux |
| REQ-ORB-002 | verified | T-0202, T-0604 | host |
| REQ-ORB-003 | **unverified — control set and shortcuts not tested** | — | — |
| REQ-ORB-004 | **unverified — always-on-top / geometry persistence not tested** | — | — |
| REQ-ORB-005 | verified | T-0203, T-0205, T-0604 | host |
| REQ-ORB-006 | verified | T-0202 | host |
| REQ-ORB-007 | verified | T-0206 | mac, linux, inspection |

### Backend and harness

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-HARNESS-001 | **unverified — config swap changes behavior not asserted** | — | — |
| REQ-HARNESS-002 | verified | T-0301, T-0302, T-0303, T-0307 | host |
| REQ-HARNESS-003 | withdrawn 2026-09-27 (external harness removed) | — | — |
| REQ-HARNESS-004 | withdrawn 2026-09-27 (external harness removed) | — | — |
| REQ-HARNESS-005 | verified | T-0301 | host |
| REQ-HARNESS-006 | verified | T-0304 | host |
| REQ-HARNESS-007 | verified | T-0304 | host |
| REQ-HARNESS-008 | **unverified — seam-open registration not asserted** | — | — |
| REQ-BACKEND-001 | verified | T-0601 | host |
| REQ-BACKEND-002 | verified | T-0603 | host |

### Tools

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-TOOL-001 | verified | T-0602, T-0702 | host |
| REQ-TOOL-002 | verified | T-0701 | host |
| REQ-TOOL-003 | **failing test, real bug (BUG-2)** — `tools.timeout_s` documented, `command_timeout` read; T-0703 pins the documented key | T-0703 | host |
| REQ-TOOL-004 | **failing test, real bug (BUG-1)** — T-0704 proves prefix and symlink escapes pass `startswith` containment | T-0704 | host |
| REQ-TOOL-005 | verified | T-0705 | host |

### Memory

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-MEM-001 | verified | T-0402, T-0607 | host |
| REQ-MEM-002 | verified | T-0402 | host |
| REQ-MEM-003 | **unverified — resume across restarts not tested** | — | — |
| REQ-MEM-004 | **unverified — no case asserts memory with a non-native harness** | — | — |
| REQ-MEM-005 | **unverified — no-secret-in-memory assertion missing** | — | — |
| REQ-MEM-006 | **failing test, real bug (BUG-6)** — T-0608 proves the unavailable latch is never cleared by `set_llm()` | T-0605, T-0608 | host (loop-yield) |

### Console

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-CONSOLE-001 | verified | T-0901 | mac, linux |
| REQ-CONSOLE-002 | verified | T-0902 | host |
| REQ-CONSOLE-003 | verified | T-0903 | host |
| REQ-CONSOLE-004 | verified | T-0904 | mac, linux |
| REQ-CONSOLE-005 | verified | T-0905 | host |
| REQ-CONSOLE-006 | verified | T-0907 | host |
| REQ-CONSOLE-007 | verified | T-0908 | host |
| REQ-CONSOLE-008 | verified | T-0909 | host |
| REQ-CONSOLE-009 | verified | T-0910, T-0913 | host |
| REQ-CONSOLE-010 | verified | T-0911 | host |
| REQ-CONSOLE-011 | verified | T-0912 | host |
| REQ-FRONTEND-001 | verified | T-1201, T-1210 | host |
| REQ-FRONTEND-002 | verified | T-1202 | host |
| REQ-FRONTEND-003 | verified | T-1203 | host |
| REQ-FRONTEND-004 | verified | T-1204 | host |
| REQ-FRONTEND-005 | verified | T-1205 | host, inspection |
| REQ-FRONTEND-006 | verified | T-1206 | host |
| REQ-FRONTEND-007 | verified | T-1207 | host |
| REQ-FRONTEND-008 | verified | T-1208 | host |
| REQ-FRONTEND-009 | verified | T-1209 | host |
| REQ-FRONTEND-010 | verified | T-1204, T-1208 | host |
| REQ-FRONTEND-011 | verified | T-1211 | host |
| REQ-FRONTEND-012 | verified | T-1210 | host |

### Cross-platform

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-PLAT-001 | **unverified — no single cross-OS acceptance run covering all MVP features** | — | — |
| REQ-PLAT-002 | **unverified — platform boundary is an inspection claim; no T asserts it** | — | — |
| REQ-PLAT-003 | **unverified — documented system packages not asserted by a test** | — | — |
| REQ-PLAT-004 | verified | T-0201 | mac, linux |

### Configuration

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-CFG-001 | **unverified — no config-selects-all-backends case** | — | — |
| REQ-CFG-002 | **partially verified** — CLI/env layering tested (T-1212); full chain unverified | T-1212 | host |
| REQ-CFG-007 | verified | T-1301, T-1302 | host |
| REQ-CFG-008 | verified | T-1303 | host |
| REQ-CFG-003 | **failing test, real bug (BUG-2)** — T-0703/T-1305 prove a documented key is silently ignored | T-1305 | host |
| REQ-CFG-004 | verified — T-1304 covers every section rename and the seconds→ms scale | T-1304 | host |
| REQ-CFG-005 | **unverified — no-secrets-in-config is an inspection claim; no T asserts it** | — | — |
| REQ-CFG-006 | **failing test, real bug (BUG-7)** — T-1601 proves the documented `agents:` map is ignored; `AgentModule` reads singular `agent` | T-1601 | host |

### Structure and refactor

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-STRUCT-001 | **partial — T-1101/T-1102 cover the `vision`/`messaging` renames only; the grep for `brain`/`ears`/`mouth`/`eyes`/`hands`/`canvas`/`chat`/`cli` has no T** | T-1101, T-1102 | host |
| REQ-STRUCT-002 | **unverified — before/after test-count report has no T** | — | — |
| REQ-STRUCT-003 | verified | T-0501..T-0511 | host |
| REQ-STRUCT-004 | **unverified — dead-code removal is an inspection claim; no T asserts it** | — | — |
| REQ-STRUCT-005 | **unverified — docs-as-built is an inspection claim; no T asserts it** | — | — |

### First-run and errors

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-SETUP-001 | **unverified — environment detection not tested** | — | — |
| REQ-SETUP-002 | **unverified — guided/skippable setup not tested** | — | — |
| REQ-SETUP-003 | **unverified — no-harness dead-end path not tested** | — | — |
| REQ-ERR-001 | verified | T-0606 | host |
| REQ-ERR-002 | **partially verified** — orb-crash recovery covered by T-0207; harness-crash recovery was external-harness-specific and is not re-tested | T-0207 | host |
| REQ-ERR-003 | **partially verified** — visible provider errors covered by T-0606; no fault-injection case for a dead harness | T-0606 | host |

### Scheduler

Kept as a first-class module (ADR-0010). It now has numbered requirements, so its
tests trace rather than being flagged as scope creep.

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-SCHED-001 | verified | T-1001, T-1005 | host |
| REQ-SCHED-002 | verified | T-1002 | host |
| REQ-SCHED-003 | **failing test, real bug (BUG-3)** — T-1006 proves an overdue recurring task re-arms into the past and re-fires every tick | T-1003, T-1006 | host |
| REQ-SCHED-004 | verified | T-1004 | host |

### Security

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-SEC-001 | verified | T-0509 | host |
| REQ-SEC-002 | verified | T-0508, T-0509 | host |
| REQ-SEC-003 | withdrawn 2026-09-27 (external harness removed) | — | — |
| REQ-SEC-004 | withdrawn 2026-09-27 (external harness removed) | — | — |
| REQ-SEC-005 | withdrawn 2026-09-27 (external harness removed) | — | — |
| REQ-SEC-006 | withdrawn 2026-09-27 (external harness removed) | — | — |
| REQ-SEC-007 | withdrawn 2026-09-27 (external harness removed) | — | — |

## 2. T → REQ

Every case and the requirement it traces to. A row with no REQ is scope creep.

| T | Title | REQ |
| --- | --- | --- |
| T-0101 | Segment → transcript published | REQ-VOICE-001 |
| T-0102 | Bounded segment queue drops oldest | REQ-VOICE-001 |
| T-0103 | Chunker flushes at sentence boundary | REQ-VOICE-002 |
| T-0109 | `halasr` backend selection | REQ-VOICE-004 |
| T-0104 | Stop flag silences playback | REQ-WAKE-005, REQ-VOICE-006 |
| T-0105 | State machine rejects impossible transitions | REQ-WAKE-006, REQ-VOICE-006 |
| T-0106 | Wake phrase strips and gates | REQ-WAKE-002, REQ-WAKE-003 |
| T-0107 | Device absent degrades, no crash | REQ-VOICE-005 |
| T-0108 | End-to-end turn latency | REQ-VOICE-003 |
| T-0201 | Window opens with no browser | REQ-ORB-001, REQ-PLAT-004 |
| T-0202 | State follows bus events | REQ-ORB-002, REQ-ORB-006, REQ-WAKE-006 |
| T-0203 | Delta appends incrementally | REQ-ORB-005 |
| T-0204 | Interrupt publishes the command | REQ-WAKE-005, REQ-CONV-003 |
| T-0205 | Reconnect resyncs without duplicates | REQ-ORB-005 |
| T-0206 | Reduced motion disables animation | REQ-ORB-007 |
| T-0207 | Orb crash does not take down the assistant | REQ-ORB-001, REQ-ERR-002 |
| T-0301 | Contract conformance | REQ-HARNESS-002, REQ-HARNESS-005, REQ-CONV-002 |
| T-0302 | Event mapping matches fixtures | REQ-HARNESS-002 |
| T-0303 | Cancel ends the turn as cancelled | REQ-CONV-003, REQ-HARNESS-002 |
| T-0304 | Unhealthy harness fails, no fallback | REQ-HARNESS-006, REQ-HARNESS-007 |
| T-0307 | `call_id` correlation | REQ-HARNESS-002 |
| T-0401 | Every turn is terminal | REQ-CONV-006 |
| T-0402 | Turn persisted exactly once | REQ-MEM-001, REQ-MEM-002 |
| T-0403 | Missing terminal event fails visibly | REQ-CONV-006 |
| T-0404 | `busy: queue` does not cancel | REQ-CONV-002 |
| T-0501 | Pub/sub delivery | REQ-STRUCT-003 |
| T-0502 | Bad subscriber isolation | REQ-STRUCT-003 |
| T-0503 | Cross-thread publish | REQ-STRUCT-003 |
| T-0504 | RPC timeout raises | REQ-STRUCT-003 |
| T-0505 | Connect, register, subscribe | REQ-STRUCT-003 |
| T-0506 | Reconnect resubscribes | REQ-STRUCT-003 |
| T-0507 | Subscribe then receive | REQ-STRUCT-003 |
| T-0508 | Auth reject with wrong token | REQ-SEC-002 |
| T-0509 | Non-loopback without token refuses | REQ-SEC-001, REQ-SEC-002 |
| T-0510 | Malformed frame does not kill the server | REQ-STRUCT-003 |
| T-0511 | Disconnect cleans up subscriptions | REQ-STRUCT-003 |
| T-0601 | Stream deltas then terminal chunk | REQ-BACKEND-001 |
| T-0602 | Tool calls normalized across providers | REQ-TOOL-001 |
| T-0603 | Unknown provider raises clearly | REQ-BACKEND-002 |
| T-0604 | Thinking tags stripped from final text | REQ-ORB-002, REQ-ORB-005 |
| T-0605 | No provider call blocks the loop | REQ-MEM-006 |
| T-0606 | Provider error is typed, not silent | REQ-ERR-001 |
| T-0607 | Embeddings search round-trip and dedup | REQ-MEM-001 |
| T-0608 | Unavailable latch clears on a new backend | REQ-MEM-006 |
| T-0701 | Discovery from configured paths | REQ-TOOL-002 |
| T-0702 | Tool call round-trip through the agent | REQ-TOOL-001 |
| T-0703 | Timeout honours the documented key | REQ-TOOL-003, REQ-CFG-003 |
| T-0704 | Path escape is refused (real-path) | REQ-TOOL-004 |
| T-0705 | Skill tool and LLM calls both complete | REQ-TOOL-005 |
| T-0901 | Headless run is usable | REQ-CONSOLE-001 |
| T-0902 | Same topics as the orb | REQ-CONSOLE-002 |
| T-0903 | Transcript, status, errors render | REQ-CONSOLE-003, REQ-CONV-004 |
| T-0904 | Console can be forced | REQ-CONSOLE-004 |
| T-0905 | Streaming render works | REQ-CONSOLE-005 |
| T-0906 | `/stop` produces a cancelled turn | REQ-CONV-003, REQ-WAKE-005 |
| T-0907 | Headless autodetect | REQ-CONSOLE-006 |
| T-0908 | Help names the wake phrase | REQ-CONSOLE-007 |
| T-0909 | Prompt survives async output | REQ-CONSOLE-008 |
| T-0910 | Streamed answer printed once | REQ-CONSOLE-009 |
| T-0911 | Reasoning is not transcript | REQ-CONSOLE-010 |
| T-0912 | Input echoed exactly once | REQ-CONSOLE-011 |
| T-0913 | Wrapped answer appears once | REQ-CONSOLE-009 |
| T-1201 | Frontend enum and aliases | REQ-FRONTEND-001 |
| T-1202 | Frontend precedence | REQ-FRONTEND-002 |
| T-1203 | auto resolution by host | REQ-FRONTEND-003 |
| T-1204 | gui without a display degrades | REQ-FRONTEND-004, REQ-FRONTEND-010 |
| T-1205 | TUI is stdlib and display-free | REQ-FRONTEND-005 |
| T-1206 | TUI state and transcript parity | REQ-FRONTEND-006 |
| T-1207 | TUI controls publish the same topics | REQ-FRONTEND-007 |
| T-1208 | TUI preconditions degrade | REQ-FRONTEND-008, REQ-FRONTEND-010 |
| T-1209 | One tty owner | REQ-FRONTEND-009 |
| T-1210 | audio is not a frontend | REQ-FRONTEND-001, REQ-FRONTEND-012 |
| T-1211 | none runs without a visual shell | REQ-FRONTEND-011 |
| T-1301 | Defaults run with no config file | REQ-CFG-007 |
| T-1302 | Local file overrides only its keys | REQ-CFG-007 |
| T-1303 | Example matches the defaults | REQ-CFG-008 |
| T-1001 | Add, list, delete round-trip | REQ-SCHED-001 |
| T-1002 | Due task publishes once | REQ-SCHED-002 |
| T-1003 | Recurring task re-arms future | REQ-SCHED-003 |
| T-1004 | `max_pending` refuses adds | REQ-SCHED-004 |
| T-1005 | Storage survives reload | REQ-SCHED-001 |
| T-1006 | Overdue recurring task re-arms future | REQ-SCHED-003 |
| T-1304 | Legacy section and key migration | REQ-CFG-004 |
| T-1305 | Unknown timeout key is named | REQ-CFG-003 |
| T-1601 | `agents:` map resolves the active agent | REQ-CFG-006 |
| T-1101 | Vision backend selection and stub | REQ-STRUCT-001 |
| T-1102 | Messaging ingest and delivery | REQ-STRUCT-001 |

## 3. Summary

Refined 2026-09-28 after the gap-closing pass. Counts are doc cases, not pytest
node ids; the suite collects 400 node ids across 24 files.

| Count | Value |
| --- | --- |
| Total requirements | 93 |
| Requirements withdrawn 2026-09-27 (external harness removed) | 7 |
| Requirements verified (full) | 67 |
| Requirements with a failing proving test (real bugs) | 8 (REQ-VOICE-004, REQ-CONV-002, REQ-TOOL-003, REQ-TOOL-004, REQ-MEM-006, REQ-CFG-003, REQ-CFG-006, REQ-SCHED-003) |
| Requirements partial (a proving T covers part of the clause) | 2 (REQ-STRUCT-001, REQ-CFG-002) |
| Requirements `unverified` | 20 |
| Total test cases | 84 |
| Cases tracing to a REQ | 84 |
| Cases flagged scope creep | 0 |

### Real bugs found by the tests (2026-09-28)

Each is pinned by a strict `xfail` test that fails on current code and passes
when the defect is fixed. No production code was changed.

| Bug | Requirement | Evidence | Fix owner |
| --- | --- | --- | --- |
| BUG-1 Sandbox prefix and symlink escape | REQ-TOOL-004 | `sandbox.py:58` uses `startswith`; `tools.md:41-44` already names this defect and requires `realpath` | tooling/security |
| BUG-2 `tools.timeout_s` ignored | REQ-TOOL-003, REQ-CFG-003 | `tools/module.py:29` reads `command_timeout`; `schemas.md:238` documents `timeout_s` | tooling |
| BUG-3 Overdue recurring task never advances | REQ-SCHED-003 | `scheduler/module.py:101` re-arms to `fire_time + interval`, still past; re-fires per tick | python |
| BUG-4 `conversation.busy: queue` unimplemented | REQ-CONV-002 | `agent/module.py:273-277` always cancels regardless of `busy_policy` | python |
| BUG-5 `voice.backend: halasr` silently stubbed | REQ-VOICE-004 | `voice/module.py:439-453` has no `halasr` branch; `HalASRBackend` lacks `transcribe`; `--audio` sets this value (`main.py:437`) | firmware/voice |
| BUG-6 Embeddings unavailable latch never resets | REQ-MEM-006 | `embeddings.py:66-68` sets `_embeddings_unavailable`; `set_llm` does not clear it | python |
| BUG-7 `agents:` map ignored | REQ-CFG-006 | `agent/module.py:30` reads singular `agent`; `schemas.md:200-223` documents `agents:` | python |

### Remaining unverified

The 20 unverified requirements cluster in: **first-run/setup** (3),
**platform** (3), **structure** (3), and deferred or inspection-only behavior
in wake/orb/conversation (`REQ-WAKE-001/004/007/008`, `REQ-CONV-001/005`,
`REQ-ORB-003/004`, `REQ-HARNESS-001/008`, `REQ-MEM-003/004/005`,
`REQ-CFG-001/005`, `REQ-ERR-002/003`). Most require `mac`/`linux`/`rig` or an
inspection step and cannot be proven on the host; `REQ-CONV-001` and
`REQ-MEM-003/004/005` are host-testable and remain the highest-value next cases.
