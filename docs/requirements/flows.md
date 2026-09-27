# Functional Flows

Trigger → steps → branches → failure for every key use case. Each flow names
the requirements it satisfies.

## (a) Voice turn — push-to-talk or always-listening

**Trigger:** PTT armed, or speech detected in `open` mode.
**Requirements:** REQ-VOICE-001, 002, 003, REQ-CONV-001..006.

| # | Actor | Action |
| --- | --- | --- |
| 1 | `voice` | Capture thread emits 20 ms frames; VAD endpoints the utterance after `voice.asr.endpoint_silence_ms`. |
| 2 | `voice` | Publishes `voice.state: transcribing`; ASR worker transcribes the segment off the event loop. |
| 3 | `voice` | Publishes `voice.transcribed` and `user.input.text {channel: voice}`. |
| 4 | `agent` | Takes the single-turn gate, retains the turn task handle, builds context. |
| 5 | `agent`/harness | Streams `text_delta` → `agent.delta`; `thinking_delta` → orb state. |
| 6 | `agent` | Publishes `agent.final`; persists the turn once. |
| 7 | `voice` | Chunker flushes sentences; TTS synthesizes; PCM streams to the output device. |
| 8 | orb | Animates from `voice.state` / `voice.level`; transcript settles. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Empty or noise-only segment | No turn created | Return to idle |
| Low ASR confidence | Segment dropped if below threshold | User repeats |
| User cancels mid-turn | Cancel sequence (flow c) | Return to idle |
| Harness slow | `thinking` state persists; stop remains available | Wait or cancel |
| Assistant calls a tool | Continue at flow (f) | — |
| TTS synthesis fails | Text still shown; error surfaced | Retry, or continue text-only |

## (b) Wake-phrase turn

**Trigger:** speech in `wake` mode.
**Requirements:** REQ-WAKE-002, 003.

| # | Actor | Action |
| --- | --- | --- |
| 1 | `voice` | Each completed segment is checked against the configured wake phrases via `WakeDetector`. |
| 2 | `voice` | On a hit, the wake phrase is stripped. If words remain, that is the command. |
| 3 | `voice` | If nothing remains, a capture window opens for the next utterance. |
| 4 | — | Continues at flow (a) step 3. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| No wake phrase | Segment discarded; never reaches the agent | — |
| Wake hit, no follow-up | Capture window closes after `voice.wake.window_ms` | Return to passive |
| Wake false reject | Second attempt within the window is accepted | Retry |
| Detector unavailable | `wake` mode unavailable; orb offers `ptt` / `open` | Switch mode |

## (c) Interrupt

**Trigger:** orb click, hotkey, console command, or (future) voice barge-in.
**Requirements:** REQ-WAKE-005, REQ-CONV-003.

The ordered cancel sequence — order matters:

| # | Actor | Action |
| --- | --- | --- |
| 1 | `agent` | Receives `command.agent.interrupt`. |
| 2 | `agent` | Cancels the **retained** turn task. |
| 3 | `agent` | Calls `harness.cancel()` — pi: `clear_queue` then `abort`; native: cancel the provider stream. |
| 4 | `voice` | Stops playback; sets the stop flag so the audio callback drains silence. |
| 5 | `voice` | Clears the TTS queue; unmutes the mic. |
| 6 | `agent` | Ends the turn with `turn_done(cancelled=true)`; no `agent.final`. |
| 7 | — | `voice.state: idle`. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Interrupt with no active turn | No-op; state returns to idle | — |
| Harness ignores cancel | Task is still cancelled locally; error logged | Restart harness |
| Audio device wedged | Playback flag set regardless; device reopened on next turn | Retry from UI |

## (d) Text turn from the orb

**Trigger:** typing in the orb composer, or the console.
**Requirements:** REQ-CONV-005, REQ-ORB-005, REQ-CONSOLE-005.

| # | Actor | Action |
| --- | --- | --- |
| 1 | orb | Publishes `user.input.text {channel: orb}`. |
| 2 | `agent` | Processes as flow (a) steps 4–6. |
| 3 | `voice` | Speaks only if `voice.speak_text_turns` is true. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Input starts with `/` | Handled locally as a console command; not sent to the agent | — |
| Harness down | Error entry in the transcript; input stays usable | Switch harness |
| Empty input | Ignored | — |

## (e) Switching the harness

**Trigger:** config change plus restart, or a runtime switch command.
**Requirements:** REQ-HARNESS-001, 005, 006, 007.

| # | Actor | Action |
| --- | --- | --- |
| 1 | config / orb | New harness selected. |
| 2 | `agent` | Resolves the harness and probes health. |
| 3 | `agent` | If a turn is in flight, cancels it per `conversation.busy`. |
| 4 | `agent` | Swaps the harness and its capability set. |
| 5 | orb | Shows the active harness; the transcript notes the switch. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Target harness unavailable | Keeps the current harness; error shown | Fix config, retry |
| pi binary missing | Actionable install message | Run `scripts/setup_pi.sh`, or pick native |
| pi model invalid | Startup error from pi; previous harness retained | Set a valid model in pi's config |
| pi exits unexpectedly | Backend-down state; bounded restart | Switch harness or restart |

**Note:** there is no automatic fallback between harnesses. They differ in tool
ownership, so a silent switch would silently change what the assistant can do
(REQ-HARNESS-006).

## (f) Tool use

**Trigger:** the native harness decides a tool is needed, or pi calls its own.
**Requirements:** REQ-TOOL-001..005, REQ-HARNESS-005.

| # | Actor | Action |
| --- | --- | --- |
| 1 | harness | Emits a tool call; orb marks activity in the transcript. |
| 2 | `tools` (native only) | Validates the call; applies sandbox policy. |
| 3 | `tools` (native only) | Executes within `tools.timeout_s`; returns result or error. |
| 4 | `agent` | Policy decides: proceed, retry, or abort. |
| 5 | `agent` | Synthesizes the final response from the tool result. |

With `harness: pi`, steps 2–3 happen **inside pi**; the host only observes
`tool_result` events for display. Our tools are not consulted for that turn.

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Unknown tool | Error to the model; it explains | — |
| Timeout | Timeout error; turn ends with a visible error | Retry |
| Path outside safe roots | Refused before execution | Correct the path |
| Tool raises | Error captured; policy retries per `max_retries` | — |

## (g) Harness unavailable / model down

**Trigger:** health probe fails, or a request errors or times out.
**Requirements:** REQ-HARNESS-004, 006, 007, REQ-ERR-001..003.

| # | Actor | Action |
| --- | --- | --- |
| 1 | `agent` | Classifies: connection, auth, model-missing, process-dead. |
| 2 | `agent` | Retries transient failures up to `conversation.retry_max`. |
| 3 | orb | Shows backend-down with a recovery hint. |
| 4 | `agent` | The turn terminates with a visible error. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Local model not pulled | Message names the model and the pull command | Pull it |
| Provider auth failure | Message names the missing credential | Set the env var |
| pi process dead | Bounded restart (backoff), then fail fast | Switch harness |
| Persistent failure | Stays degraded; setup path available | Flow (i) |

## (h) Mic or speaker unavailable

**Trigger:** device missing, permission denied, or in use.
**Requirements:** REQ-VOICE-005, REQ-ERR-002.

| # | Actor | Action |
| --- | --- | --- |
| 1 | `voice` | Device probe fails; publishes a classified error. |
| 2 | orb | Shows "no microphone" / "no audio output"; disables the affected control. |
| 3 | app | Continues in the remaining modes. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Mic missing | Voice input disabled; text works | Plug in, retry from UI |
| Speaker missing | Text-only responses | Retry when available |
| Permission denied (macOS) | Actionable Settings instruction | Grant, retry |
| Device lost mid-session | Degrade; do not crash | Retry from UI |

## (i) First-run setup

**Trigger:** first launch, or a failed probe.
**Requirements:** REQ-SETUP-001..003.

| # | Actor | Action |
| --- | --- | --- |
| 1 | app | Detects: harness availability, model availability, audio devices, GUI. |
| 2 | orb / console | Shows a checklist of what is present and missing. |
| 3 | app | Offers instructions or alternatives; skipping is allowed. |
| 4 | app | Starts in the best available mode. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| pi not installed | Offer `scripts/setup_pi.sh`; suggest native | Install or switch |
| Model not pulled | Offer the pull command | Pull |
| No GUI | Console mode | Install GUI deps |
| Nothing available | Limited mode with setup visible | Complete setup |

## (j) Scheduled task fires

**Trigger:** `scheduler` clock loop reaches a task time.
**Requirements:** REQ-CONV-004, REQ-CONV-006.

| # | Actor | Action |
| --- | --- | --- |
| 1 | `scheduler` | Publishes `schedule.triggered`. |
| 2 | `agent` | Treats it as a turn with the task text. |
| 3 | `voice` | Speaks the reminder if the schedule's origin was voice. |

| Condition | Behavior | Recovery |
| --- | --- | --- |
| Recurring task | Next time computed and re-stored | — |
| Unparseable time | Task skipped; error logged | Fix the task |
