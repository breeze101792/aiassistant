# Requirements

Numbered, individually testable. Every requirement traces to a user-stated goal
(`[S]`) or is marked as an assumption (`[A]`). No "fast", no "user-friendly".

Verification methods: `host` = pytest on the dev machine · `mock` = integration
with a fake backend/device · `mac` / `linux` = manual on that OS · `rig` =
on-target audio rig (loopback or fixture) · `inspection`.

## Voice I/O

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-VOICE-001 | Accept speech as input and transcribe it. | A spoken utterance while listening yields a transcript published on the bus within the configured finalize window. | [S] | host (mock), rig |
| REQ-VOICE-002 | Produce spoken audio output. | A voice-originated turn produces audio on the configured output device; spoken text equals the transcript text. | [S] | rig, mock |
| REQ-VOICE-003 | Turn latency is bounded and measurable. | End-of-speech to first output sample ≤ `voice.turn_latency_target_ms` on the reference machine with a healthy harness. | [A] | rig |
| REQ-VOICE-004 | STT and TTS backends are config-selectable. | Changing `voice.asr.backend` or `voice.tts.backend` and restarting selects another backend with no code change; an unknown value fails voice setup with an error naming the value, and the assistant continues text-only (REQ-BACKEND-002). | [S] | host, mock |
| REQ-VOICE-005 | Audio devices are selectable. | Input and output devices are selectable by name or index in config; an absent device is reported and falls back to the system default. | [A] | host, mac, linux |
| REQ-VOICE-006 | No self-feedback on the MVP path. | While TTS plays, the mic does not produce a new turn (half-duplex). | [A] | rig, mock |

## Wake and listening

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-WAKE-001 | Exactly one listening mode is active. | `voice.listen.mode` ∈ {`ptt`, `open`, `wake`} is mutually exclusive; in `ptt` nothing is transcribed until armed. | [S] | host, mac, linux |
| REQ-WAKE-002 | Wake phrase gates a turn. | In `wake` mode, speech without the wake phrase is not sent to the agent; speech with the wake phrase (plus further words) is. | [S] | rig, host |
| REQ-WAKE-003 | Wake detection is replaceable. | Wake detection sits behind a `WakeDetector` interface; a different detector implementation can replace it with no change to `voice/` callers. | [S] | host (contract test) |
| REQ-WAKE-004 | Push-to-talk controls exist. | A configured hotkey and an orb control both start and end a PTT turn. | [S] | mac, linux |
| REQ-WAKE-005 | Interrupt while speaking. | An interrupt from orb, console, or hotkey stops playback within `voice.barge_in.stop_ms` and cancels the in-flight turn. | [S] | host, mac, linux |
| REQ-WAKE-006 | Listening state is visible. | The orb shows idle / listening / transcribing / thinking / speaking consistent with bus events. | [S] | mac, linux |
| REQ-WAKE-007 | Mute works. | Toggling mute stops capture immediately and shows a muted state; unmute restores the configured mode. | [S] | mac, linux |
| REQ-WAKE-008 | Voice barge-in is explicitly deferred. | Voice-triggered barge-in is off unless AEC is configured; the half-duplex limitation is stated in `scope.md`. | [A] | inspection |

## Conversation

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-CONV-001 | Session context across turns. | The native harness request for turn *n* includes up to `conversation.context_turns` prior turns of the session. | [S] | host (fake provider) |
| REQ-CONV-002 | One in-flight turn at a time. | New input while a turn runs interrupts or queues per `conversation.busy`; two turns never run concurrently. | [A] | host |
| REQ-CONV-003 | Cancel always works. | The interrupt path cancels the turn, stops playback, and ends the turn with a terminal `cancelled` state. | [S] | host, mock |
| REQ-CONV-004 | Transcript is visible and persistent. | Each turn appends a role-labelled, timestamped entry; entries are readable after restart. | [S] | host, mac |
| REQ-CONV-005 | Text turns need not speak. | With `voice.speak_text_turns: false`, a text-originated turn produces no audio. | [A] | host, mock |
| REQ-CONV-006 | Every turn terminates. | Every user turn ends in a response, a cancellation, or a visible error. No turn is left without a terminal state. | [A] | host, mock |

## Orb UI

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-ORB-001 | Native desktop UI, not web. | The orb runs as an OS-managed window; no browser engine or HTTP server is required at runtime. | [S] | mac, linux, inspection |
| REQ-ORB-002 | Orb expresses state. | Distinct visuals for idle, listening, transcribing, thinking, speaking, error, backend-down, muted; each maps to a bus event. | [S] | mac, linux |
| REQ-ORB-003 | Controls exist. | Controls for push-to-talk, mute, stop, new session, backend switch, settings, transcript toggle, quit; each has a keyboard shortcut. | [S] | mac, linux |
| REQ-ORB-004 | Window behavior is configurable. | `display.always_on_top` controls stay-on-top; position and size persist across restarts; the idle window does not steal focus. | [A] | mac, linux |
| REQ-ORB-005 | Streaming transcript. | Assistant text appears incrementally as deltas arrive, not only at turn end. | [S] | host, mac |
| REQ-ORB-006 | Errors are surfaced. | Errors appear as a non-modal state plus an actionable message; they never block input. | [A] | mac, linux |
| REQ-ORB-007 | Accessibility. | Every control has an accessible name and is keyboard-operable; reduced motion is honored; state is never color-only. | [A] | mac, linux, inspection |

## Backend and harness

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-HARNESS-001 | Harness is config-selectable. | `agent.harness` selects the loop owner; the default and only shipped value is `native`. An unknown value fails startup, naming the value. | [S] | host |
| REQ-HARNESS-002 | Uniform harness contract. | Every harness implements one `AgentHarness` contract and emits one `TurnEvent` vocabulary; capabilities are reported through `HarnessCaps`, never silently ignored. | [A] | host (contract test) |
| REQ-HARNESS-005 | Tool ownership is unambiguous. | `HarnessCaps.owns_tools` reports whether the harness runs its own tools; when `False`, `tools/` executes and the sandbox applies. | [A] | host, inspection |
| REQ-HARNESS-006 | No silent harness fallback. | An unhealthy or unbuildable harness fails the turn with a clear error; it never silently switches to another harness. | [A] | host, mock |
| REQ-HARNESS-007 | Harness health is probed. | A probe runs at startup and before a turn; harness-down is shown in the orb and never results in a dropped turn. | [A] | host, mock |
| REQ-HARNESS-008 | The harness seam stays open. | A new harness is added by implementing `AgentHarness` and registering it in the factory; no caller, orb, TUI, or test outside the harness package changes. | [S] | host, inspection |
| REQ-BACKEND-001 | Model provider is config-selectable. | `agent.llm.provider` ∈ {`ollama`, `openai`} selects the provider for the native harness. | [S] | host, mock |
| REQ-BACKEND-002 | Invalid provider fails clearly. | An unknown provider yields a startup error naming the value and does not start the harness. | [A] | host |

> REQ-HARNESS-003 and REQ-HARNESS-004 described the external pi harness and were
> withdrawn on 2026-09-27 with it. The numbers are not reused.

## Tools

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-TOOL-001 | Tool call round-trip. | With `native`, the agent calls a configured tool, the result returns, and the final response reflects it. | [S] | host (fake tool + fake provider) |
| REQ-TOOL-002 | Tool set is config-driven. | Tools are discovered from `tools.paths`; adding or removing a path changes the available tools with no code edit. | [A] | host |
| REQ-TOOL-003 | Execution is bounded. | A tool exceeding `tools.timeout_s` returns a timeout error and the turn ends with a visible error. | [A] | host |
| REQ-TOOL-004 | Sandbox paths are enforced. | With sandboxing on, a path outside the safe roots is refused; path-prefix escapes (`/tmp/aiassistant-evil`) are rejected. | [A] | host |
| REQ-TOOL-005 | Skill bus calls work. | A skill can call a tool and can call the model, and neither blocks the event loop. | [A] | host |

## Memory

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-MEM-001 | Turns are persisted. | Turns are written to the configured store and re-readable after restart. | [S] | host |
| REQ-MEM-002 | One writer per turn. | A turn is written by exactly one persistence path; no duplicate write occurs. | [A] | host |
| REQ-MEM-003 | Resume across restarts. | With `memory.resume_session: true`, a new session includes recent prior turns; with false it starts empty. | [A] | host |
| REQ-MEM-004 | Memory works with any harness. | Recall and persistence are provided by the app, not the harness, so a harness that reports `owns_memory: False` (our `native`) gets both from us. | [A] | host, mock |
| REQ-MEM-005 | No secrets in memory. | No API key or token value is written into transcripts or facts. | [A] | host, inspection |
| REQ-MEM-006 | Embeddings do not block the loop. | Embedding calls run off the event loop or from cache. | [A] | host (loop-yield test) |

## Console

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-CONSOLE-001 | Headless fallback works. | When the orb cannot start, the assistant runs in console mode and remains usable. | [A] | mac, linux |
| REQ-CONSOLE-002 | Same behavior in both frontends. | Console and orb drive the same bus topics; a turn behaves identically. | [A] | host, mac |
| REQ-CONSOLE-003 | Console shows transcript, status, errors. | Console renders transcript entries, module status, and errors. | [A] | host |
| REQ-CONSOLE-004 | Text-only can be forced. | `display.mode: none` (legacy `console`) starts no visual shell even when a GUI is available; text still runs. | [A] | mac, linux |
| REQ-CONSOLE-005 | Streaming in console. | Assistant text renders incrementally from deltas. | [A] | host |
| REQ-CONSOLE-006 | Headless autodetect. | `display.mode: auto` starts no visual shell on a machine with no display server, and the GUI orb when one is present. `AIASSISTANT_DISPLAY_OFF` forces `none` unless the CLI names a frontend. | [A] | host, mac, linux |
| REQ-CONSOLE-007 | Help names the wake phrase. | `/help` (and the TUI help overlay) prints the configured `voice.hotwords`, never a hard-coded phrase; with none configured it says input is not gated. | [A] | host |
| REQ-CONSOLE-008 | Async output never corrupts the prompt. | A banner, transcript line, or log record arriving while the prompt is shown is written above it and the prompt is redrawn; exactly one prompt remains, and it is never glued to the text. Log records keep going to stderr. | [A] | host |
| REQ-CONSOLE-009 | A streamed answer is printed once. | Deltas open one `Assistant:` line and append in place. `agent.final` settles it without reprinting when the text matches, and erases every wrapped row before rewriting when the model revised. The answer is never displayed twice, including when it wraps. | [A] | host |
| REQ-CONSOLE-010 | Reasoning is not transcript. | Thinking deltas and the reasoning summary never enter the transcript; they go to the debug log, and the summary is also shown only when `/thinking` is on. | [A] | host |
| REQ-CONSOLE-011 | Input is echoed exactly once. | On a tty the terminal echoes the typed line, so the console does not print it again; a piped or redirected run, which has no terminal echo, keeps the turn in the transcript. A voice transcript is always shown. | [A] | host |

## Frontends

`mode` selects only the visual shell; text and audio always run (ADR-0017).

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-FRONTEND-001 | One frontend concept. | A single selection with values `gui`/`tui`/`none`/`auto` chooses the visual shell; legacy `orb`/`ui` alias `gui` and `console` aliases `none`. | [S] | inspection, host |
| REQ-FRONTEND-002 | Deterministic precedence. | CLI `--frontend` beats `AIASSISTANT_DISPLAY_OFF`, which beats `display.mode`, which beats the `auto` default. | [A] | host |
| REQ-FRONTEND-003 | `auto` resolves by host. | `gui` on a Linux desktop (display var set) or a local macOS session; `none` on a headless host or an SSH session with nothing forwarded. `auto` never picks `tui`. | [A] | host, mac, linux |
| REQ-FRONTEND-004 | Explicit `gui` without a display degrades loudly. | `--frontend gui` with no display server starts no orb, logs the reason, and uses `tui` when a terminal is usable, else `none`. | [S] | mac, linux |
| REQ-FRONTEND-005 | TUI is stdlib and display-free. | The TUI runs with no display server, using only the standard library; no new runtime dependency. | [S] | linux, inspection |
| REQ-FRONTEND-006 | TUI shows the same state and transcript as the GUI. | State, transcript rows, streaming text, and the harness badge match the GUI orb for the same bus sequence. | [S] | host |
| REQ-FRONTEND-007 | TUI controls exist. | Interrupt, mute, scroll/clear, input, and quit are keyboard-operable and publish the same topics as the GUI orb. | [S] | host, linux |
| REQ-FRONTEND-008 | TUI preconditions degrade, never crash. | With a non-tty, unset/`dumb` `TERM`, or a curses init failure, the TUI does not start and text mode continues; the terminal stays usable. | [A] | host, linux |
| REQ-FRONTEND-009 | One tty owner. | The console and the TUI never both read stdin; while the TUI owns the terminal the console's I/O is suppressed, and it resumes when the TUI exits. | [A] | host, inspection |
| REQ-FRONTEND-010 | No frontend failure stops the assistant. | An orb, TUI, or console startup failure leaves the assistant running in the next available frontend. | [A] | mac, linux |
| REQ-FRONTEND-011 | `none` runs without a visual shell. | `--frontend none` starts no orb and no TUI; the assistant remains operational (text, voice, bridge, scheduler). | [S] | host, linux |
| REQ-FRONTEND-012 | Text and audio are not modes. | The frontend selection never changes the voice backends or whether text input works; `audio` is not a frontend value. | [A] | host, inspection |

## Cross-platform

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-PLAT-001 | Runs on macOS and Linux. | Documented install and launch works on both; all MVP features work on both or degrade with a clear message. | [S] | mac, linux |
| REQ-PLAT-002 | No macOS-only API on the MVP path. | Platform-specific code is isolated behind a documented boundary. | [A] | inspection |
| REQ-PLAT-003 | Platform requirements documented. | Required system packages (audio, GUI) are listed for both OSes. | [A] | inspection |
| REQ-PLAT-004 | No web UI. | No web server or browser is required for the primary UI. | [S] | inspection |

## Configuration

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-CFG-001 | One config selects all backends. | A single file selects each component's backend; no code edit is needed. | [S] | host |
| REQ-CFG-002 | Deterministic precedence. | CLI override > environment > `config.yaml` > code defaults; each layer is tested to win over the next. | [A] | host |
| REQ-CFG-003 | Invalid config is actionable. | An unknown or invalid key errors with the key and value named; the app starts with defaults where safe. | [A] | host |
| REQ-CFG-004 | Legacy keys migrate. | Old section keys (`brain`, `ears`, `mouth`, `hands`, `eyes`, `canvas`, `chat`, `cli`) are accepted with a deprecation warning and mapped to the new keys. | [A] | host |
| REQ-CFG-005 | Secrets stay out of config. | API keys come from environment or keychain; the checked-in config contains no secret values. | [A] | inspection |
| REQ-CFG-006 | Multiple agents are definable. | `agents:` is a map; more than one identity (wake phrase, persona, harness, voice) can be defined. | [S] | host |
| REQ-CFG-007 | Config is local and optional. | Every default lives in code, so the assistant runs with no config file. `config.yaml` is git-ignored and overlays only the keys it names. | [S] | host |
| REQ-CFG-008 | The example matches the defaults. | `config.example.yaml` is tracked and mirrors `DEFAULTS` key for key; a test fails if the two drift. | [A] | host |

## Structure and refactor

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-STRUCT-001 | Ratified names replace the body metaphor. | Source, config, and docs use `agent`, `voice`, `tools`, `vision`, `scheduler`, `messaging`, `console`, `orb`, `reasoning`; no `brain`/`ears`/`mouth`/`eyes`/`hands`/`canvas`/`chat`/`cli`/`llm` remain as module names. | [S] | host (grep) |
| REQ-STRUCT-002 | No silent coverage loss. | Every prior test passes under the new layout or is explicitly replaced; before/after counts are reported. | [A] | host |
| REQ-STRUCT-003 | Bus semantics preserved. | Pub/sub and RPC semantics are unchanged; topic renames are covered by tests. | [A] | host |
| REQ-STRUCT-004 | Dead code removed. | The canvas module, the web stub, `main_remote.py`, the `aiohttp` dependency, and the stale `utility` submodule entry are gone. | [S] | inspection |
| REQ-STRUCT-005 | Docs describe as-built behavior. | `docs/` exists and matches the code; `ARCH.md` and `PLAN.md` are retired. | [S] | inspection |

## First-run and errors

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-SETUP-001 | First-run detects the environment. | At launch the app detects harness availability, model availability, audio devices, and GUI availability. | [A] | mac, linux |
| REQ-SETUP-002 | Setup is guided and skippable. | Each missing item is reported with instructions and can be skipped, leading to a degraded but running state. | [A] | mac, linux |
| REQ-SETUP-003 | No dead end. | With no harness available, the app still starts, shows the requirement, and accepts input for console/text only. | [A] | mac, linux |
| REQ-ERR-001 | Errors are classified. | Every error carries a class (config, audio, harness, tool, memory) and a recovery hint. | [A] | host, mac |
| REQ-ERR-002 | Recover without restart. | A lost audio device or a crashed harness can be retried from the UI without restarting the process. | [A] | mac, linux |
| REQ-ERR-003 | No silent failures. | Fault injection (kill the harness, remove a device) produces a visible error on the next turn. | [A] | host |

## Scheduler

Kept as a first-class module (ADR-0010). Timed reminders are a real assistant
capability, so it gets requirements rather than being an untraced orphan.

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-SCHED-001 | Timed tasks can be added, listed, and deleted. | An add appears in the list; a delete removes it; both survive a reload. | [A] | host |
| REQ-SCHED-002 | A due task fires exactly once. | A task whose time has passed publishes `schedule.triggered` once on the next clock tick. | [A] | host |
| REQ-SCHED-003 | Recurring tasks re-arm with a future time. | A `daily` / `weekly` / `hourly` task, once fired, is re-stored with a next time in the future. | [A] | host |
| REQ-SCHED-004 | The pending set is bounded. | At `scheduler.max_pending`, a further add is refused with a visible error. | [A] | host |

## Security

| ID | Requirement | Acceptance criterion | Source | Verify |
| --- | --- | --- | --- | --- |
| REQ-SEC-001 | The bus is not exposed by default. | The bridge binds loopback unless `bus.bind` explicitly widens it. | [A] | host, inspection |
| REQ-SEC-002 | A token is required when the bus is reachable. | With a non-loopback bind, a non-empty token is mandatory or startup fails. | [A] | host |

> REQ-SEC-003..007 governed the external pi harness (opt-in, file-tool
> confinement, RPC shell surface, child environment, and the documented
> confinement gap) and were withdrawn on 2026-09-27 with it. The numbers are not
> reused. In-process tool confinement is now covered by REQ-TOOL-* and the
> sandbox; `REQ-SEC-001/002` remain the boundary that matters.
