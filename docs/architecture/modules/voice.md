# MOD-0004 — `voice`

**Purpose:** Own the entire duplex audio path: capture, VAD, wake gating, ASR,
TTS synthesis, and playback.

**Must not do:** reason, call a model, or import `agent/`. It publishes events
and consumes `command.*` topics.

**Dependencies:** the OS audio stack (via `sounddevice`), ASR and TTS backends,
`bus` topics.

**State it owns:** the duplex state machine, the capture and playback threads,
the VAD and segmenter, the bounded segment queue, the ASR worker thread, the PCM
queue, and the stop flag.

**Pipeline:** `Capture → VAD → VadSegmenter → SegmentQueue → ASR worker →
voice.transcribed`. The VAD, ASR, and TTS backends are built by one factory,
`voice/factory.py`; an unknown value is a hard error naming the value
(REQ-BACKEND-002, [ADR-0018](../decisions/ADR-0018-audio-pipeline-stages.md)).

See [features/voice-pipeline.md](../../requirements/features/voice-pipeline.md)
for the full pipeline and [ADR-0005](../decisions/ADR-0005-voice-merge.md) for
why this is one module.

## PROVIDES

### `setup() -> bool`

Builds the VAD, ASR, and TTS backends through `voice/factory.py` and
constructs the `VadSegmenter`; probes the audio devices. Returns `False` when a
backend value is unknown (`VoiceConfigError`) or the segmenter config is bad; a
missing device degrades rather than fails (REQ-VOICE-005). Voice is
`NON_CRITICAL`, so a `False` here leaves the assistant running text-only
(REQ-BACKEND-002).

### `start() / stop() -> None`

| Field | Content |
| --- | --- |
| Purpose | Open the capture and output streams, start the ASR worker, and subscribe to commands; on stop, close both streams and stop the worker and queues. |
| Parameters | none |
| Returns | none |
| Preconditions | `setup()` returned `True` |
| Postconditions | Streams are open; on stop, the ASR worker is joined within a timeout and the queues are closed |
| Side effects | Starts the ASR worker thread and two `sounddevice` streams; publishes the initial state |
| Context | async, called by `main.py` |
| Timing | `stop()` joins the ASR worker with a bounded timeout (`ASR_WORKER_JOIN_TIMEOUT = 2.0`) so a wedged ASR call cannot hang shutdown |

### `_handle_state_request(topic, payload) -> None`

| Field | Content |
| --- | --- |
| Purpose | Resync a late-connecting client (orb, tui) with the current state. |
| Parameters | none (`voice.state.request`, empty payload) |
| Returns | none |
| Preconditions | `start()` has run |
| Postconditions | `voice.state` is published with the last state actually published and the mute flag |
| Side effects | One `voice.state` publish. A level read: it does not move the FSM or run half-duplex gating |
| Context | async, bus thread |
| Timing | Immediate |

### `set_mute(muted: bool) -> None`

| Field | Content |
| --- | --- |
| Purpose | Stop capture immediately and publish the muted state. |
| Parameters | `muted` — `True` discards frames, `False` resumes the configured mode |
| Returns | none |
| Preconditions | `start()` has run |
| Postconditions | Capture is gated (`True`) or restored (`False`). A user mute is recorded separately from the transient half-duplex gate, so it survives a reply cycle and is the only condition that leaves the FSM in `MUTED` |
| Side effects | Publishes `voice.state: muted` or the restored mode; `True` closes any open wake-follow-up window |
| Context | async, safe from the bus thread |
| Timing | Immediate |

### `speak(text: str, interrupt: bool = False) -> None`

| Field | Content |
| --- | --- |
| Purpose | Queue text for synthesis and playback. |
| Parameters | `text` (str); `interrupt` (bool) clears the queue and stops current playback first |
| Returns | none |
| Preconditions | `start()` has run |
| Postconditions | The text is queued; playback proceeds in order |
| Side effects | Publishes `voice.state: speaking`, then `voice.state: idle` |
| Context | async; safe from the bus thread |
| Timing | Returns immediately; synthesis is bounded by the TTS backend |

### `stop_playback() -> None`

Sets the stop flag. The audio callback drains to silence at the next buffer.
This is what makes interrupt work, and why the subprocess playback path was
removed (REQ-WAKE-005).

| Field | Content |
| --- | --- |
| Purpose | Silence output now, without tearing down the output stream. |
| Parameters | none |
| Returns | none |
| Preconditions | `start()` has run |
| Postconditions | The next callback buffer is silence; the queue is cleared by the caller. The latch is per-utterance: `enqueue` clears it, so the next reply plays instead of staying silent |
| Side effects | Sets the stop flag the audio callback reads |
| Context | thread-safe; callable from the loop or an interrupt handler |
| Timing | Bounded by one audio buffer |

## REQUIRES

- `bus.publish` / `bus.subscribe`
- Backend interfaces: `VADBackend`, `ASRBackend`, `TTSBackend`, `WakeDetector`,
  and the `Capture` / `Playback` classes
- `voice.factory` — builds the VAD, ASR, and TTS backends; raises
  `VoiceConfigError` naming an unknown value
- `audio.decode_mp3(bytes) -> PCM` for the TTS path

## OWNS

- The duplex state machine and its published state.
- The audio threads, the ASR worker thread, and both queues.
- The VAD and the segmenter's pre-roll and open-utterance buffers.
- The stop flag, the user-mute flag, the wake follow-up window, and the
  post-speech echo guard.
- The RMS level computation.

The bus carries **no** PCM. Only events cross (REQ-VOICE-006).

## INVARIANTS

- At most one capture stream and one output stream are open.
- The `SegmentQueue` never exceeds its cap (`2`); on overflow the oldest segment
  is dropped and `voice.overflow` is published with `{dropped, queue_cap}`.
- The segmenter's open utterance is bounded by `voice.segmenter.max_utterance_ms`
  (default 30 s): a VAD wedged on "speech" force-emits instead of growing memory.
- `voice.state: speaking` implies playback is active; the mic is gated while it
  holds, unless barge-in is explicitly enabled.
- The half-duplex gate is released when playback ends, so the mic is live again
  after a reply. Only an explicit user mute leaves the FSM in `MUTED`.
- In wake mode, an open follow-up window accepts utterances without the phrase;
  it closes after `voice.wake_window_ms` of quiet or on an explicit mute.
- An utterance ends only after `voice.endpoint_silence_ms` of silence measured
  from the last speech frame, so a shorter mid-sentence pause stays in the same
  utterance and speech duration is not capped (only `max_utterance_ms` bounds a
  wedged VAD).
- The state machine never enters an impossible combination.

## ERRORS

| Code | Meaning |
| --- | --- |
| `ERR-VOICE-NO-INPUT` | No usable input device |
| `ERR-VOICE-NO-OUTPUT` | No usable output device |
| `ERR-VOICE-ASR-FAIL` | The ASR backend raised or returned an error |
| `ERR-VOICE-TTS-FAIL` | The TTS backend raised or returned an error |
| `ERR-VOICE-DECODE-FAIL` | The MP3 decode step failed |
| `ERR-VOICE-OVERFLOW` | The segment queue dropped a segment |

## CONCURRENCY

| Context | May call |
| --- | --- |
| Capture thread | `VAD.is_speech` and `VadSegmenter.feed` (one O(1) deque append, one callback); publishes level via `bus.publish` (thread-safe) |
| ASR worker thread | Blocks on `SegmentQueue.get`; calls `ASRBackend.transcribe`; publishes transcripts |
| Playback callback | Reads the PCM queue, checks the stop flag |
| asyncio loop | `speak`, `set_mute`, command handlers, state publishing |

`transcribe` is blocking (network or model inference), so it runs on the ASR
worker thread named `voice-asr` — never on the event loop and never on the audio
thread.

## RESOURCES

- Three threads: the audio callback threads, plus the ASR worker (`voice-asr`);
  one `sounddevice` input stream and one output stream.
- Bounded `SegmentQueue` (cap 2, drop-oldest) and a bounded PCM playback queue.
- The segmenter holds at most `max_utterance_ms` of PCM, plus a short pre-roll.
- RMS state is scalar per frame.

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| Segment → text published | mock ASR | T-0101 |
| Bounded queue drops oldest and reports | host | T-0102 |
| Chunker flushes at sentence boundary | host (pure) | T-0103 |
| Stop flag silences playback | mock playback | T-0104 |
| State machine rejects impossible transitions | host | T-0105 |
| Wake phrase gates correctly | rig (fixture) | T-0106 |
| Device absent degrades | host (injected failure) | T-0107 |
| End-to-end latency | rig | T-0108 |
