# Test Cases

One row per case: ID, title, requirement(s), method, preconditions, steps,
expected result, and the module contract clause it verifies. Methods are defined
in [TEST_PLAN.md § Strategy](TEST_PLAN.md#1-strategy--one-case-one-environment).

Coverage and the reverse T → REQ map: [trace.md](trace.md).

## Voice — `tests/test_voice.py`, `test_voice_queue.py`, `test_voice_chunker.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0101 | Segment → transcript published | REQ-VOICE-001 | mock | `voice` started with fake `AudioCapture` yielding a fixture segment and stub ASR | Feed one speech segment; await the ASR worker | Exactly one `voice.transcribed` and one `user.input.text {channel: voice}` within the finalize window; transcript equals stub output | voice.md PROVIDES.setup / IF-0005 `voice.transcribed` |
| T-0102 | Bounded segment queue drops oldest | REQ-VOICE-001 | host | Queue cap 2; ASR worker blocked | Enqueue 3 segments without draining | Queue len stays ≤ 2; oldest dropped; exactly one `voice.overflow` published per drop | voice.md INVARIANTS (segment queue cap, drop-oldest) |
| T-0103 | Chunker flushes at sentence boundary | REQ-VOICE-002 | host | Chunker with a known sentence splitter | Feed deltas ending mid-sentence, then a sentence end, then a flush | One `voice.speak` per complete sentence, in order; trailing fragment flushed at turn end | voice.md PROVIDES.speak / IF-0008 chunking |
| T-0104 | Stop flag silences playback | REQ-WAKE-005 | mock | Fake `AudioPlayback` filling buffers | Queue audio; call `stop_playback()` mid-buffer | Next callback drains to silence; queued buffers cleared; playback stops without waiting for a backend | voice.md PROVIDES.stop_playback |
| T-0105 | State machine rejects impossible transitions | REQ-WAKE-006, REQ-VOICE-006 | host | Fresh FSM | Attempt `listening → speaking` and any non-adjacent transition; drive the legal cycle | Illegal transitions rejected; published `voice.state` is always a legal value; never `speaking` while capture is live | voice.md INVARIANTS (state machine) / IF-0005 transition diagram |
| T-0106 | Wake phrase strips and gates | REQ-WAKE-002, REQ-WAKE-003 | rig | `wake` mode; fixture audio of phrase, phrase+command, and non-wake speech | Run all three fixtures through the `WakeDetector` | Non-wake never reaches the agent; phrase+command yields command text with the phrase stripped; phrase alone opens the capture window | voice.md PROVIDES.setup / flows.md (b) |
| T-0107 | Device absent degrades, no crash | REQ-VOICE-005 | host | Fake capture/playback reporting device absent | Call `setup()`; attempt a turn | `ERR-VOICE-NO-INPUT`/`ERR-VOICE-NO-OUTPUT` published; falls back to system default; process stays up; text path usable | voice.md PROVIDES.setup / ERRORS |
| T-0108 | End-to-end turn latency | REQ-VOICE-003 | rig | Reference machine, healthy harness, loopback timing | Speak a fixture; timestamp end-of-speech and first output sample | End-of-speech → first output sample ≤ `voice.turn_latency_target_ms`; timestamps logged | voice.md / REQ-VOICE-003 acceptance |

## Orb — `tests/test_orb_bridge.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0201 | Window opens with no browser | REQ-ORB-001, REQ-PLAT-004 | mac, linux | Built app, GUI available | Launch the orb; inspect running processes | OS window appears; no browser engine and no HTTP server listening; exit code 0 | orb.md PROVIDES.main / IF-0004 |
| T-0202 | State follows bus events | REQ-ORB-002, REQ-WAKE-006 | host | Orb view model attached to fake bridge | Emit each `voice.state`, `status.harness`, `agent.turn.error` | View state matches the emitted state for all eight states; unknown state ignored, not crashed | orb.md REQUIRES topics / IF-0004 subscribes |
| T-0203 | Delta appends incrementally | REQ-ORB-005 | host | Fake bridge; empty transcript model | Emit `agent.delta` with increasing `index`; then `agent.final` | Text grows per delta, not only at end; `agent.final` replaces assembled text | orb.md INVARIANTS (monotonic index) |
| T-0204 | Interrupt publishes the command | REQ-WAKE-005, REQ-CONV-003 | host | Fake bridge; active turn simulated | Invoke orb stop/interrupt control | Exactly one `command.agent.interrupt` published; no local turn state left dangling | orb.md REQUIRES / IF-0004 publishes |
| T-0205 | Reconnect resyncs without duplicates | REQ-ORB-005 | host | Fake bridge that drops and reconnects | Build transcript with a gap; drop connection; reconnect and emit snapshot + replay | Re-subscribes; requests snapshot; transcript has no duplicated or dropped lines; resync requested on gap | orb.md INVARIANTS / bus-bridge.md INVARIANTS |
| T-0206 | Reduced motion disables animation | REQ-ORB-007 | mac, linux, inspection | OS "reduce motion" enabled | Launch orb; observe idle and state changes | Ambient animation disabled; state still conveyed by shape/text, not color alone | orb.md PROVIDES / REQ-ORB-007 |
| T-0207 | Orb crash does not take down the assistant | REQ-ORB-001, REQ-ERR-002 | host (kill child) | Orb running as a child of `main.py` | Kill the orb process | Assistant keeps running; orb restarts with bounded backoff; after 3 crashes in 10 min it stops retrying and logs a warning | orb.md Lifecycle and supervision |

## Agent harness — `tests/test_harness_contract.py`, `tests/test_pi_events.py`, `tests/test_agent_loop.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0301 | Contract conformance, both harnesses | REQ-HARNESS-002, REQ-HARNESS-005, REQ-CONV-002 | host (parametrized) | Fake provider (native) and fake pi child (pi) | Run the conformance suite against both | `run_turn` terminates; exactly one terminal event; second concurrent turn raises; `caps` reported truthfully | agent-harness.md (whole contract) |
| T-0302 | Event mapping matches fixtures | REQ-HARNESS-002, REQ-HARNESS-003 | host (recorded JSONL) | Recorded pi JSONL fixtures | Replay each fixture through the pi adapter | Each pi event maps to the documented `TurnEvent`; usage `totalTokens` → `total`; unmapped kinds logged only | pi-harness.md Event mapping |
| T-0303 | Cancel ends the turn as cancelled | REQ-CONV-003, REQ-HARNESS-002 | host (fake pi) | Active turn | Call `cancel()` | Iterator ends `turn_done(cancelled=True)`; no `agent.final`; pi receives `clear_queue` then `abort`; stdin stays open | agent-harness.md PROVIDES.cancel / pi-harness.md PROVIDES.cancel |
| T-0304 | Unhealthy harness fails, no fallback | REQ-HARNESS-006, REQ-HARNESS-007 | host | `health()` returns `{ok: False}` | Start a turn | Turn ends with a visible error naming the harness; the other harness is never used | agent-harness.md PROVIDES.health / features/agent-harness.md |
| T-0305 | pi prompt has no memory prefix | REQ-MEM-004, REQ-HARNESS-002 | host (fake pi) | pi harness with owned memory | Send two turns, then restart the child and send one | Normal prompts are bare user text; only the post-restart prime carries a compact recent-conversation summary | pi-harness.md Memory / features/agent-harness.md |
| T-0306 | Malformed stdout does not kill the reader | REQ-HARNESS-003 | host (fixture) | Fixture emits a non-JSON line amid valid lines | Replay fixture | Reader logs `ERR-PI-PROTOCOL` for the bad line and continues; the turn still reaches `agent_settled` | pi-harness.md ERRORS / protocols.md framing |
| T-0307 | `call_id` correlation | REQ-HARNESS-002 | host | Fixture with `toolcall_end` then `tool_execution_*` | Replay and collect events | Every `tool_result.call_id` matches an earlier `tool_call.call_id` in the same turn | agent-harness.md INVARIANTS |
| T-0308 | Crash mid-turn errors and restarts | REQ-HARNESS-004, REQ-ERR-002, REQ-ERR-003 | host (kill child) | Active turn, fake pi child | Kill the child mid-turn | Turn ends with `ERR-PI-DEAD`/`ERR-HARNESS-DEAD`; respawn with backoff; backend-down shown; no silent success | pi-harness.md Process lifecycle / ERRORS |
| T-0309 | Workspace guard blocks out-of-workspace path | REQ-SEC-004 | host (fixture) | Fixture tool call resolving outside the workspace | Replay fixture | Guard hook returns `{block: true}`; tool call blocked; no filesystem write outside the workspace | pi-harness.md Confinement |
| T-0310 | No zombie after quit | REQ-HARNESS-004 | host, mac, linux | pi child running | Quit the app | stdin closed, child reaped within the shutdown window; no zombie process remains | pi-harness.md Process lifecycle (Shutdown) |

## Agent loop — `tests/test_agent_loop.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0401 | Every turn is terminal | REQ-CONV-006 | host (fault injection) | Fake harness able to end, cancel, or error | Drive a turn to completion, cancel one, and force a harness error | Each turn ends in exactly one of `final`, `cancelled`, `error`; no turn is left without a terminal state | agent.md INVARIANTS |
| T-0402 | Turn persisted exactly once | REQ-MEM-001, REQ-MEM-002 | host | Temp memory store | Run a turn; inspect the store | Exactly one entry written; re-readable after a simulated restart; no duplicate from a second writer | agent.md INVARIANTS / data-model.md Conversation turn |

## Bus and bridge — `tests/test_bus.py`, `test_remote_bus.py`, `test_topics.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0501 | Pub/sub delivery | REQ-STRUCT-003 | host | Fresh bus | Subscribe one and multiple handlers; publish | All subscribers receive the exact `(topic, payload)`; wrong topic receives nothing | bus-bridge.md PROVIDES / INVARIANTS |
| T-0502 | Bad subscriber isolation | REQ-STRUCT-003 | host | Bus with a raising and a good handler | Publish | Good handler still receives the message; exception contained | bus-bridge.md INVARIANTS |
| T-0503 | Cross-thread publish | REQ-STRUCT-003 | host | Bus; async handler | Publish from a non-loop thread | Async callback is scheduled onto the loop and runs; no `get_event_loop` misuse | bus-bridge.md INVARIANTS / Changes from as-built |
| T-0504 | RPC timeout raises | REQ-STRUCT-003 | host | Subscriber that never responds | `request()` with a short timeout | Raises `TimeoutError`; `NoSubscriberError` when no subscriber | bus-bridge.md PROVIDES.request |
| T-0505 | Connect, register, subscribe | REQ-STRUCT-003 | host (mock) | Fake WS server/client | Connect, register, subscribe | Register ack received; subscription id tracked; client-only (no register) supported | bus-bridge.md PROVIDES / remote.py INVARIANTS |
| T-0506 | Reconnect resubscribes | REQ-STRUCT-003 | host (mock) | Established bridge with subscriptions | Drop the connection; reconnect | Re-registers and re-subscribes; a dropped connection surfaces as a typed error | bus-bridge.md INVARIANTS |
| T-0507 | Subscribe then receive | REQ-STRUCT-003 | host (mock) | Registered client subscribed to a topic | Publish on the in-process bus | Forward frame `{topic, payload}` delivered to the client; topic constant matches frozen value | remote.py VERIFICATION / protocols.md Topic registry |
| T-0508 | Auth reject with wrong token | REQ-SEC-002 | host (mock) | Server with non-empty token | First frame carries a wrong token | Server sends `{"error":"auth failed"}` then closes | remote.py Auth |
| T-0509 | Non-loopback without token refuses | REQ-SEC-001, REQ-SEC-002 | host | Config with a non-loopback bind and empty token | Start the bridge | Startup fails with a clear error; default bind is loopback | remote.py As-built defects / REQ-SEC-001/002 |
| T-0510 | Malformed frame does not kill the server | REQ-STRUCT-003 | host (mock) | Connected client | Send a non-JSON frame, then a valid one | Bad frame ignored, not fatal; valid frame still processed | remote.py INVARIANTS / protocols.md framing |
| T-0511 | Disconnect cleans up subscriptions | REQ-STRUCT-003 | host (mock) | Client subscribed to a topic, then disconnects | Publish after disconnect | The dead client's subscription is removed; no error on publish; registry entry cleared | remote.py INVARIANTS |

## Reasoning — `tests/test_reasoning.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0601 | Stream deltas then terminal chunk | REQ-BACKEND-001 | host (fake provider) | Fake provider yielding scripted chunks | Consume `chat_stream` | Text deltas arrive in order, then one terminal chunk with content, tool_calls, usage; iterator exhausted once | reasoning.md PROVIDES.chat_stream |
| T-0602 | Tool calls normalized across providers | REQ-TOOL-001 | host | Ollama-shaped and OpenAI-shaped tool-call payloads | Normalize both | Both produce the same `{call_id, name, args}` shape | reasoning.md Stream mapping into TurnEvent |
| T-0603 | Unknown provider raises clearly | REQ-BACKEND-002 | host | Config with an unknown provider | Call `create_provider` | Raises naming the value; harness does not start | reasoning.md PROVIDES.create_provider |
| T-0604 | Thinking tags stripped from final text | REQ-ORB-002, REQ-ORB-005 | host | qwen3 `<thinking>`/` response` and deepseek XML samples | Run `_strip_thinking` and a reasoner turn | Final text contains no raw thinking; empty fallback preserved; streamed display clean | reasoning.md Behavior preserved from as-built |
| T-0605 | No provider call blocks the loop | REQ-MEM-006 | host (loop-yield) | Ticker task on the loop | Run `embed_batch`/`chat` while ticking | Ticks keep rising; call runs off the loop thread; negative control stalls | reasoning.md INVARIANTS / TEST_PLAN § 6 |
| T-0606 | Provider error is typed, not silent | REQ-ERR-001 | host (fake provider) | Provider configured to raise each class | Run a turn for each error | Each yields its typed `ERR-PROVIDER-*` with a recovery hint; never an empty-string success | reasoning.md ERRORS |

## Tools — `tests/test_tools.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0701 | Discovery from configured paths | REQ-TOOL-002 | host | `tools.paths` pointing at a temp dir with a `ToolBase` subclass | Call `setup()` and `list_schemas()` | Tool registered; schema present; a missing path is logged, not fatal; zero tools returns `True` | tools.md PROVIDES.setup |
| T-0702 | Tool call round-trip through the agent | REQ-TOOL-001 | host (fake tool + fake provider) | Fake provider emitting a tool call | Run a turn | Tool executes once; result returns to the provider; final response reflects it | tools.md PROVIDES.execute / flows.md (f) |
| T-0703 | Timeout returns an error | REQ-TOOL-003 | host | Tool that sleeps past `tools.timeout_s` | Execute | `ERR-TOOL-TIMEOUT` returned; turn ends with a visible error; no hang | tools.md INVARIANTS |
| T-0704 | Path escape is refused | REQ-TOOL-004 | host | Sandbox with safe root `/tmp/aiassistant` | Check `/tmp/aiassistant-evil/x` and a symlink escape | Both refused via real-path containment; inside paths allowed | tools.md PROVIDES.Sandbox.check_path |
| T-0705 | Skill tool and LLM calls both complete | REQ-TOOL-005 | host | Skill with bus reference | Call a tool then the model from the skill | Both await to completion; neither blocks the loop; no `run_until_complete` on a running loop | tools.md Fixed from as-built |

## Console — `tests/test_console.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-0901 | Headless run is usable | REQ-CONSOLE-001 | mac, linux | No GUI available | Launch the app | Console starts; a typed turn completes; transcript shown | console.md PROVIDES.start |
| T-0902 | Same topics as the orb | REQ-CONSOLE-002 | host | Console attached to the bus | Submit input and observe publishes | Uses `user.input.text` / `command.*`, the same topics as the orb; identical turn behavior | console.md INVARIANTS |
| T-0903 | Transcript, status, errors render | REQ-CONSOLE-003, REQ-CONV-004 | host | Console with captured stdout | Emit `agent.delta`, `agent.final`, `voice.state`, `agent.turn.error` | Transcript entries, one-line status, and inline errors all render; errors do not block input | console.md Rendering / Errors |
| T-0904 | Console can be forced | REQ-CONSOLE-004 | mac, linux | GUI available; `display.mode: console` | Launch | Starts headless with no window even though a GUI is present | console.md / REQ-CONSOLE-004 |
| T-0905 | Streaming render works | REQ-CONSOLE-005 | host | Captured stdout | Emit successive deltas | Text appears incrementally in place; final settles the line | console.md Rendering |
| T-0906 | `/stop` produces a cancelled turn | REQ-CONV-003, REQ-WAKE-005 | host | Turn in flight | Issue `/stop` | Publishes `command.agent.interrupt`; turn ends cancelled; no final | console.md Commands / flows.md (c) |

## Scheduler — `tests/test_scheduler.py`

Scheduler has no numbered REQ; flow (j) links it to REQ-CONV-004/006. Rows are
flagged `scope creep` in [trace.md](trace.md).

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-1001 | Add, list, delete round-trip | — (scope creep) | host | Temp storage file | Add two tasks; list; delete one; list | Correct tasks returned; deleted task gone | scheduler.md PROVIDES.setup |
| T-1002 | Due task publishes once | — (scope creep) | host | Clock loop; a task whose time has passed | Advance the loop | Exactly one `schedule.triggered`; one-shot removed | scheduler.md PROVIDES.\_clock_loop / flows.md (j) |
| T-1003 | Recurring task re-arms future | — (scope creep) | host | Recurring task just fired | Inspect next time | Next time is strictly in the future; task retained | scheduler.md INVARIANTS |
| T-1004 | `max_pending` refuses adds | — (scope creep) | host | Store at cap | Add one more | `ERR-SCHED-FULL`; pending count unchanged | scheduler.md ERRORS |
| T-1005 | Storage survives reload | — (scope creep) | host | Written storage file | Reload a fresh instance | Tasks re-read intact; unparseable time skipped, not crashed on | scheduler.md ERRORS / data-model.md Schedule task |

## Vision and messaging (frozen) — `tests/test_vision.py`, `tests/test_messaging.py`

| ID | Title | REQ(s) | Method | Preconditions | Steps | Expected | Contract clause |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-1101 | Vision backend selection and stub | REQ-STRUCT-001 | host | `vision.backend: stub` | Construct, `setup()`, `capture()`, `analyze()` | Module name `vision`; stub backend selected; placeholder frame fields present | frozen-modules.md vision |
| T-1102 | Messaging ingest and delivery | REQ-STRUCT-001 | host (fake backend) | Fake platform backend | Inject an inbound message; deliver an `agent.final` | Inbound maps to `user.input.text`; outbound delivered; module name `messaging` | frozen-modules.md messaging |
