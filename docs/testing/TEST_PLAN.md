# Test Plan

How the refactor is verified: what runs where, what each method can and cannot
prove, the test layout, the fakes, and the conformance and loop-yield suites.

Requirements and their verification methods: [../requirements/requirements.md](../requirements/requirements.md).
Case list: [cases.md](cases.md). Coverage matrix: [trace.md](trace.md).

## 1. Strategy — one case, one environment

The system spans four environments. Pick the method that can actually observe
the behavior; do not substitute a weaker method and call it proof.

| Method | Runs on | Proves | Cannot prove |
| --- | --- | --- | --- |
| `host` | CI / dev machine, pytest | Pure logic, async orchestration, config, bus semantics, error classification | Anything needing a real device, GUI, model, or wall-clock audio |
| `mock` | CI, pytest with fakes | Integration across module boundaries against a fake peer | That the real peer's behavior matches the fake |
| `mac` | This Mac, manual | Permissions, window behavior, hotkeys, real audio on macOS | Linux behavior |
| `linux` | Linux session, manual | Install, GUI under X11/Wayland, hotkeys, audio on Linux | macOS behavior |
| `rig` | On-target with loopback/fixture audio | Real audio timing, end-to-end latency, half-duplex, device selection | Anything reproducible without the rig |
| `inspection` | Read the source/docs | Structure, removals, no-browser, no-secret claims | Runtime behavior |

Rules:

- A `host` or `mock` pass never claims a `rig` or manual acceptance criterion.
- A case is proven only in the method its [REQ](../requirements/requirements.md)
  names.
- `inspection` is a method, not an excuse: it must name the artifact inspected.

## 2. Framework and layout

`pytest` with `pytest-asyncio` (async tests carry `@pytest.mark.asyncio`, as in
the current suite). No new test framework is introduced.

Target file layout mirrors the new module names:

| Target file | Module under test | Cases |
| --- | --- | --- |
| `tests/conftest.py` | — shared fixtures | — |
| `tests/test_bus.py` | `bus/` pub/sub, RPC, registry | T-0501..T-0504 |
| `tests/test_topics.py` | `bus/topics.py` constants, frozen values | T-0507 |
| `tests/test_remote_bus.py` | `bus/remote.py` WS server | T-0505..T-0510 |
| `tests/test_agent_loop.py` | `agent/` loop, gate, interrupt, persist | T-0301, T-0303, T-0401, T-0402, T-0906 |
| `tests/test_harness_contract.py` | `agent/harness` interface (parametrized) | T-0301, T-0302, T-0307 |
| `tests/test_pi_events.py` | `agent/harness/pi` event mapping, lifecycle | T-0302, T-0303, T-0305, T-0306, T-0308..T-0310 |
| `tests/test_reasoning.py` | `reasoning/` providers, streaming, embeddings | T-0601..T-0606 |
| `tests/test_tools.py` | `tools/` registry, sandbox, skills | T-0701..T-0705 |
| `tests/test_voice.py` | `voice/` backends, state machine, wake, device | T-0101, T-0104..T-0107 |
| `tests/test_voice_queue.py` | `voice/` segment and PCM queues | T-0102 |
| `tests/test_voice_chunker.py` | `voice/` TTS chunker (pure) | T-0103 |
| `tests/test_orb_bridge.py` | `orb/` view model against a fake bridge | T-0201..T-0206 |
| `tests/test_console.py` | `console/` commands and rendering | T-0901..T-0906 |
| `tests/test_scheduler.py` | `scheduler/` storage and clock loop | T-1001..T-1005 |
| `tests/test_memory.py` | `agent/memory`, `agent/transcript` | REQ-MEM-* (uncovered, see trace) |
| `tests/test_vision.py` | `vision/` (frozen) | T-1101 |
| `tests/test_messaging.py` | `messaging/` (frozen) | T-1102 |
| `tests/test_integration.py` | composition root, full flows | flows |

The layout list above is not exhaustive: if a gap in [trace.md](trace.md) is
closed later (config, security, setup), the new cases land in
`tests/test_config.py`, `tests/test_security.py`, `tests/test_setup.py`.

## 3. Migration — old tests to new

The existing `tests/` has 13 test modules plus `conftest.py` and
`tests/data/`. Every existing test either moves under the new layout or is
explicitly replaced; nothing is silently dropped
([REQ-STRUCT-002](../requirements/requirements.md)).

| Old file | Covers today | New file(s) | What changes |
| --- | --- | --- | --- |
| `conftest.py` | `message_bus`, `temp_dir`, `mock_llm` fixtures | `conftest.py` | Keep; add `fake_provider`, `fake_harness`, `fake_pi`, `fake_bridge`, `fake_audio`, per-test `tmp_memory` |
| `test_brain.py` | Reasoner compression, Reflector retry, Responder, `_strip_thinking`, reasoner tools, ToolCache wiring | `test_reasoning.py`, `test_agent_loop.py`, `test_memory.py` | `Reasoner` splits: provider/strip → `test_reasoning.py`; loop, tool feedback, retry policy → `test_agent_loop.py`; `Responder` persistence collapses into transcript → `test_memory.py` |
| `test_brain_core.py` | Perceiver, Understander, Planner, Reflector | `test_agent_loop.py` | `understand`/`plan` are deleted; retain only the Reflector policy assertions that survive |
| `test_bus.py` | Pub/sub, RPC, module lifecycle, user input, remote cleanup, registry | `test_bus.py`, `test_remote_bus.py`, `test_topics.py` | Core bus stays; `TestRemoteBusSubscriptionCleanup` moves to `test_remote_bus.py`; topic-string assertions move to `test_topics.py` |
| `test_canvas.py` | `modules/canvas` | — | Deleted with the module ([REQ-STRUCT-004](../requirements/requirements.md)) |
| `test_cli.py` | Tab completion, log level, init | `test_console.py` | Rename `CLIModule` → console; command set changes (`/stop`, `/harness`, `/new`, `/mute`) |
| `test_ears.py` | Stub/Hal/Whisper/FunASR ASR, VAD, EarsModule | `test_voice.py`, `test_voice_queue.py` | ASR backends and state → `test_voice.py`; queue/segment behavior → `test_voice_queue.py`; keep optional-dep skip guards |
| `test_eyes.py` | Stub vision, EyesModule | `test_vision.py` | Rename `eyes` → `vision`, `EyesModule` → `VisionModule` |
| `test_hands.py` | Tool base, datetime, file ops, sandbox, websearch, skills, webfetch | `test_tools.py` | Rename `hands` → `tools`; add real-path sandbox assert (T-0704); drop shell `Sandbox.run` |
| `test_integration.py` | Full flow, mock-LLM tool flow, module lifecycle | `test_integration.py` | Keep; replace real-Ollama cases with fake-provider cases; rename topics to `agent.final` |
| `test_llm.py` | LLM interface, Ollama/OpenAI init, backend smoke | `test_reasoning.py` | `llm/` → `reasoning/`; smoke test becomes skip-guarded optional-dep |
| `test_memory.py` | MemoryManager, EmbeddingsEngine, Persona, ToolCache | `test_memory.py` | Keep; assert single-writer (T-0402) and no-secret (REQ-MEM-005) |
| `test_mouth.py` | TextTTS, MouthModule, interrupt queue | `test_voice_queue.py`, `test_voice_chunker.py` | `mouth` → `voice`; queue tests → `test_voice_queue.py`; chunker → `test_voice_chunker.py` |
| `test_scheduler.py` | ScheduleStorage, SchedulerModule | `test_scheduler.py` | Keep; add exactly-once fire (T-1002) |
| `tests/data/user_memory.txt` | Fixture data | `tests/data/` | Keep or replace with recorded JSONL fixtures |

## 4. Fakes and fixtures

Each fake replaces one peer at one boundary. Build them in `conftest.py` unless
noted.

| Fake | What it is | How it is built | Used by |
| --- | --- | --- | --- |
| **Fake harness** | `AgentHarness` with a scripted event list and declared `HarnessCaps` | Class holds `events: list[TurnEvent]`, `caps`; `run_turn` is an async generator yielding them then `turn_done`; `cancel()` flips the terminal event to `cancelled=True`; `health()` returns a settable `HarnessHealth` | T-0301, T-0303, T-0304, T-0307 |
| **Fake provider** | `ModelProvider` returning canned streams, embeddings, and typed errors | `chat_stream` yields scripted `StreamChunk`s then a terminal chunk; records each call; `embed`/`embed_batch` return fixed vectors; a `raise_on` switch produces each `ERR-PROVIDER-*` | T-0601..T-0606 |
| **Fake pi subprocess** | A real child process replaying recorded JSONL, so the pi adapter's pipes are exercised without the `pi` binary | Ship `tests/fake_pi.py` that reads `prompt` lines and writes a `.jsonl` fixture line by line; fixture spawns `sys.executable tests/fake_pi.py` as the configured `pi.command`; fixtures include malformed-line, crash-mid-turn, and guard-block cases | T-0302, T-0303, T-0305, T-0306, T-0308, T-0309 |
| **Fake bridge** | The `bridge/` client surface the orb consumes | Object capturing `publish()` calls and exposing `emit(topic, payload)` to drive subscribed handlers synchronously; no socket | T-0201..T-0205 |
| **Fake audio device** | `AudioCapture` and `AudioPlayback` | Capture yields pre-recorded 20 ms int16 frames from a list then stops; Playback records queued buffers, honors the stop flag, and can be told the device is absent | T-0101..T-0108 (mock/rig boundary) |

Injection: fakes are passed through config or constructor, matching the
module's existing dependency-injection seam. No test monkeypatches a concrete
backend where a documented interface exists
([REQ-WAKE-003](../requirements/requirements.md), [REQ-VOICE-004](../requirements/requirements.md)).

## 5. Conformance suite — one suite, both harnesses

**Goal:** prove [REQ-HARNESS-002](../requirements/requirements.md) by running
one parametrized suite against both implementations.

```
@pytest.mark.parametrize("harness", [native_with_fake_provider, pi_with_fake_child])
```

Every case asserts the same contract clauses from
[MOD-0002](../architecture/modules/agent-harness.md):

| Assertion | Clause |
| --- | --- |
| `run_turn` is an async iterator that always terminates | agent-harness.md `run_turn` |
| Exactly one terminal event, `turn_done` or `turn_error` | agent-harness.md INVARIANTS |
| `cancel()` ends the active iterator with `turn_done(cancelled=True)` | agent-harness.md `cancel` |
| Every `tool_result.call_id` matches an earlier `tool_call.call_id` | agent-harness.md INVARIANTS |
| `text_final`, when emitted, is authoritative | agent-harness.md INVARIANTS |
| `caps` match declared capability table; a consumer never ignores a `False` cap | agent-harness.md `caps` |
| A second concurrent `run_turn` raises | agent-harness.md CONCURRENCY |
| `health()` returns `{ok, detail}` | agent-harness.md `health` |

The `native` side uses the fake provider; the `pi` side uses the fake child.
The same assertions run for both, which is what makes the vocabularies
provably identical.

## 6. Loop-yield testing — proving nothing blocks the loop

**Goal:** [REQ-MEM-006](../requirements/requirements.md) and the no-blocking
invariant in [reasoning.md](../architecture/modules/reasoning.md) and
[tools.md](../architecture/modules/tools.md).

Method (timing/await based, no sleep race in the assertion):

1. Start a ticker: an async task that increments `ticks` on every loop
   iteration via `await asyncio.sleep(0)`.
2. Start the operation under test — `provider.embed_batch(...)` or a skill's
   `call_tool` — as a task.
3. While it is in flight, assert `ticks` keeps rising; sample at several awaits,
   not one fixed delay.
4. Assert the operation ran off the loop thread:
   `threading.get_ident()` captured inside the call differs from the loop
   thread's ident.
5. Negative control: run the same operation with the off-loop dispatch disabled
   and assert `ticks` stalls. A test that never fails when the loop blocks is
   not a test.

Apply the same pattern to the ASR worker ([voice.md](../architecture/modules/voice.md)
CONCURRENCY: "ASR runs in an executor; it must never run on the event loop").

## 7. What cannot be tested on the host, and why

| Cannot prove on host | Why | Method |
| --- | --- | --- |
| Real audio timing, latency, half-duplex | Needs a real clock, device, and loopback audio; the host has no bounded 20 ms frame path | `rig` |
| Shader / GPU orb rendering and fallback | Needs a GPU and a compositor; Qt shaders are not headless | `mac`, `linux` (manual) |
| Global hotkeys | Native per-platform APIs; cannot be registered portably or in CI | `mac`, `linux` |
| Wayland always-on-top, position, transparency | Compositor-dependent; behavior differs from X11 | `linux` (manual) |
| macOS permissions (mic, camera, accessibility) | TCC prompts cannot be scripted in CI | `mac` |
| Real model quality and prompt behavior | Depends on weights, not code | `rig` / manual |
| Actual `pi` upstream behavior | `abort`-mid-tool, `message_end` shape, `--no-session` semantics are unverified ([protocols.md](../contracts/protocols.md#if-0003-pi-rpc-protocol)) | host spike, then `pi` fixtures |

The host suite covers these only to the edge of the fake. Beyond the edge is a
`rig` or manual case, never a host assertion dressed up as one.

## 8. CI posture

| Suite | macOS | Linux | Notes |
| --- | --- | --- | --- |
| Pure host (`test_bus`, `test_topics`, `test_reasoning`, `test_tools`, `test_memory`, `test_voice_chunker`, `test_voice_queue`, `test_agent_loop`, `test_harness_contract`, `test_pi_events`) | run | run | No device, no network |
| Integration with fakes (`test_integration`) | run | run | Fake provider/child only |
| Optional-dependency tests | skip if missing | skip if missing | Import-guarded |
| Manual (`mac`/`linux`) | manual | manual | Documented, not in CI |
| Rig (`rig`) | — | target | Separate job on hardware |

Optional-dependency guard pattern already in the tree: `bus/remote.py:25-28`
wraps `import websockets` in `try/except ImportError` and disables the feature
with a log line. Tests follow it:

- `pytest.importorskip("websockets")` for the remote-bus suite.
- `pytest.importorskip("sounddevice")` / `webrtcvad` / `whisper` / `funasr` for
  audio-backend suites, matching the existing `test_ears.py` skips.
- `pytest.importorskip("PySide6")` for any orb import beyond the pure view model.

Config/security/structural cases that today have no T are listed in
[trace.md](trace.md) as `unverified`. They are the backlog this plan must close
before the refactor is called done.
