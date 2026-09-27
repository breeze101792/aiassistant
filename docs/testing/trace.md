# Traceability Matrix

Two questions, one glance each:

1. Does every `REQ-*` have at least one proving `T-*`? (§1)
2. Does every `T-*` trace to a `REQ-*`? (§2)

`unverified` is allowed; **silently** unverified is not. Every gap below names a
reason. Case detail: [cases.md](cases.md). Method definitions:
[TEST_PLAN.md § 1](TEST_PLAN.md#1-strategy--one-case-one-environment).

## 1. REQ → T

All 80 requirements from
[../requirements/requirements.md](../requirements/requirements.md).

### Voice I/O

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-VOICE-001 | verified | T-0101, T-0102 | mock, host |
| REQ-VOICE-002 | verified | T-0103 | host |
| REQ-VOICE-003 | verified | T-0108 | rig |
| REQ-VOICE-004 | **unverified — no voice backend-selection case; `test_voice.py` must add one** | — | — |
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
| REQ-CONV-002 | verified | T-0301 | host |
| REQ-CONV-003 | verified | T-0303, T-0204, T-0906 | host, mock |
| REQ-CONV-004 | verified | T-0903, T-0402 | host |
| REQ-CONV-005 | **unverified — `speak_text_turns: false` not tested** | — | — |
| REQ-CONV-006 | verified | T-0401 | host |

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
| REQ-HARNESS-002 | verified | T-0301, T-0302, T-0303, T-0305, T-0307 | host |
| REQ-HARNESS-003 | verified | T-0302, T-0306 | host |
| REQ-HARNESS-004 | verified | T-0308, T-0310 | host, mac, linux |
| REQ-HARNESS-005 | verified | T-0301 | host |
| REQ-HARNESS-006 | verified | T-0304 | host |
| REQ-HARNESS-007 | verified | T-0304 | host |
| REQ-BACKEND-001 | verified | T-0601 | host |
| REQ-BACKEND-002 | verified | T-0603 | host |

### Tools

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-TOOL-001 | verified | T-0602, T-0702 | host |
| REQ-TOOL-002 | verified | T-0701 | host |
| REQ-TOOL-003 | verified | T-0703 | host |
| REQ-TOOL-004 | verified | T-0704 | host |
| REQ-TOOL-005 | verified | T-0705 | host |

### Memory

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-MEM-001 | verified | T-0402 | host |
| REQ-MEM-002 | verified | T-0402 | host |
| REQ-MEM-003 | **unverified — resume across restarts not tested** | — | — |
| REQ-MEM-004 | verified | T-0305 | host |
| REQ-MEM-005 | **unverified — no-secret-in-memory assertion missing** | — | — |
| REQ-MEM-006 | verified | T-0605 | host (loop-yield) |

### Console

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-CONSOLE-001 | verified | T-0901 | mac, linux |
| REQ-CONSOLE-002 | verified | T-0902 | host |
| REQ-CONSOLE-003 | verified | T-0903 | host |
| REQ-CONSOLE-004 | verified | T-0904 | mac, linux |
| REQ-CONSOLE-005 | verified | T-0905 | host |

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
| REQ-CFG-002 | **unverified — precedence chain not tested** | — | — |
| REQ-CFG-003 | **unverified — invalid-key error not tested** | — | — |
| REQ-CFG-004 | **unverified — legacy-key migration not tested** | — | — |
| REQ-CFG-005 | **unverified — no-secrets-in-config is an inspection claim; no T asserts it** | — | — |
| REQ-CFG-006 | **unverified — multi-agent `agents:` map not tested** | — | — |

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
| REQ-ERR-002 | verified | T-0308, T-0207 | host |
| REQ-ERR-003 | verified | T-0308 | host |

### Scheduler

Kept as a first-class module (ADR-0010). It now has numbered requirements, so its
tests trace rather than being flagged as scope creep.

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-SCHED-001 | verified | T-1001, T-1005 | host |
| REQ-SCHED-002 | verified | T-1002 | host |
| REQ-SCHED-003 | verified | T-1003 | host |
| REQ-SCHED-004 | verified | T-1004 | host |

### Security

| REQ | Status | Proving T | Method |
| --- | --- | --- | --- |
| REQ-SEC-001 | verified | T-0509 | host |
| REQ-SEC-002 | verified | T-0508, T-0509 | host |
| REQ-SEC-003 | **unverified — pi opt-in refusal not tested** | — | — |
| REQ-SEC-004 | verified | T-0309 | host |
| REQ-SEC-005 | **unverified — RPC `bash` never sent is an inspection claim; no T asserts it** | — | — |
| REQ-SEC-006 | **unverified — minimal child env not tested** | — | — |
| REQ-SEC-007 | **unverified — threat-model doc is an inspection claim; no T asserts it** | — | — |

## 2. T → REQ

Every case and the requirement it traces to. A row with no REQ is scope creep.

| T | Title | REQ |
| --- | --- | --- |
| T-0101 | Segment → transcript published | REQ-VOICE-001 |
| T-0102 | Bounded segment queue drops oldest | REQ-VOICE-001 |
| T-0103 | Chunker flushes at sentence boundary | REQ-VOICE-002 |
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
| T-0301 | Contract conformance, both harnesses | REQ-HARNESS-002, REQ-HARNESS-005, REQ-CONV-002 |
| T-0302 | Event mapping matches fixtures | REQ-HARNESS-002, REQ-HARNESS-003 |
| T-0303 | Cancel ends the turn as cancelled | REQ-CONV-003, REQ-HARNESS-002 |
| T-0304 | Unhealthy harness fails, no fallback | REQ-HARNESS-006, REQ-HARNESS-007 |
| T-0305 | pi prompt has no memory prefix | REQ-MEM-004, REQ-HARNESS-002 |
| T-0306 | Malformed stdout does not kill the reader | REQ-HARNESS-003 |
| T-0307 | `call_id` correlation | REQ-HARNESS-002 |
| T-0308 | Crash mid-turn errors and restarts | REQ-HARNESS-004, REQ-ERR-002, REQ-ERR-003 |
| T-0309 | Workspace guard blocks out-of-workspace path | REQ-SEC-004 |
| T-0310 | No zombie after quit | REQ-HARNESS-004 |
| T-0401 | Every turn is terminal | REQ-CONV-006 |
| T-0402 | Turn persisted exactly once | REQ-MEM-001, REQ-MEM-002 |
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
| T-0701 | Discovery from configured paths | REQ-TOOL-002 |
| T-0702 | Tool call round-trip through the agent | REQ-TOOL-001 |
| T-0703 | Timeout returns an error | REQ-TOOL-003 |
| T-0704 | Path escape is refused | REQ-TOOL-004 |
| T-0705 | Skill tool and LLM calls both complete | REQ-TOOL-005 |
| T-0901 | Headless run is usable | REQ-CONSOLE-001 |
| T-0902 | Same topics as the orb | REQ-CONSOLE-002 |
| T-0903 | Transcript, status, errors render | REQ-CONSOLE-003, REQ-CONV-004 |
| T-0904 | Console can be forced | REQ-CONSOLE-004 |
| T-0905 | Streaming render works | REQ-CONSOLE-005 |
| T-0906 | `/stop` produces a cancelled turn | REQ-CONV-003, REQ-WAKE-005 |
| T-1001 | Add, list, delete round-trip | REQ-SCHED-001 |
| T-1002 | Due task publishes once | REQ-SCHED-002 |
| T-1003 | Recurring task re-arms future | REQ-SCHED-003 |
| T-1004 | `max_pending` refuses adds | REQ-SCHED-004 |
| T-1005 | Storage survives reload | REQ-SCHED-001 |
| T-1101 | Vision backend selection and stub | REQ-STRUCT-001 |
| T-1102 | Messaging ingest and delivery | REQ-STRUCT-001 |

## 3. Summary

| Count | Value |
| --- | --- |
| Total requirements | 84 |
| Requirements verified (full) | 52 |
| Requirements partial (a proving T covers part of the clause) | 1 (REQ-STRUCT-001) |
| Requirements `unverified` | 31 |
| Total test cases | 62 |
| Cases tracing to a REQ | 62 |
| Cases flagged scope creep | 0 |

The 31 unverified requirements cluster in five backlog areas the current T set
does not touch: **configuration** (all 6), **first-run/setup** (3),
**platform** (3), **security** (4), and **structure** (3), plus the deferred and
inspection-only behavior in voice/wake/orb (`REQ-VOICE-004`,
`REQ-WAKE-001/004/007/008`, `REQ-CONV-001/005`, `REQ-ORB-003/004`,
`REQ-HARNESS-001`, `REQ-MEM-003/005`). Closing them adds
`tests/test_config.py`, `tests/test_security.py`, and `tests/test_setup.py`;
those files are named as the target extension in
[TEST_PLAN.md § 2](TEST_PLAN.md#2-framework-and-layout).
