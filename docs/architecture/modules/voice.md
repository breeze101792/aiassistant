# MOD-0004 — `voice`

**Purpose:** Own the entire duplex audio path: capture, VAD, wake gating, ASR,
TTS synthesis, and playback.

**Must not do:** reason, call a model, or import `agent/`. It publishes events
and consumes `command.*` topics.

**Dependencies:** the OS audio stack (via `sounddevice`), ASR and TTS backends,
`bus` topics.

**State it owns:** the duplex state machine, the capture and playback threads,
the bounded segment queue, the PCM queue, and the stop flag.

See [features/voice-pipeline.md](../../requirements/features/voice-pipeline.md)
for the full pipeline and [ADR-0005](../decisions/ADR-0005-voice-merge.md) for
why this is one module.

## PROVIDES

### `setup() -> bool`

Resolves the ASR, TTS, and wake backends from config; probes the audio devices.
Returns `False` only when no usable configuration exists; a missing device
degrades rather than fails (REQ-VOICE-005).

### `start() / stop() -> None`

| Field | Content |
| --- | --- |
| Purpose | Open the capture and output streams and subscribe to commands; on stop, close both and flush the queues. |
| Parameters | none |
| Returns | none |
| Preconditions | `setup()` returned `True` |
| Postconditions | Streams are open; on stop, both threads are joined within a timeout and the queues are empty |
| Side effects | Starts two threads and two `sounddevice` streams; publishes the initial state |
| Context | async, called by `main.py` |
| Timing | `stop()` joins with a bounded timeout so a wedged device cannot hang shutdown |

### `set_mute(muted: bool) -> None`

| Field | Content |
| --- | --- |
| Purpose | Stop capture immediately and publish the muted state. |
| Parameters | `muted` — `True` discards frames, `False` resumes the configured mode |
| Returns | none |
| Preconditions | `start()` has run |
| Postconditions | Capture is gated (`True`) or restored (`False`) |
| Side effects | Publishes `voice.state: muted` or the restored mode |
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
| Postconditions | The next callback buffer is silence; the queue is cleared by the caller |
| Side effects | Sets the stop flag the audio callback reads |
| Context | thread-safe; callable from the loop or an interrupt handler |
| Timing | Bounded by one audio buffer |

## REQUIRES

- `bus.publish` / `bus.subscribe`
- Backend interfaces: `ASRBackend`, `TTSBackend`, `WakeDetector`, `AudioCapture`,
  `AudioPlayback`
- `audio.decode_mp3(bytes) -> PCM` for the TTS path

## OWNS

- The duplex state machine and its published state.
- Both audio threads and both queues.
- The stop flag and mute flag.
- The RMS level computation.

The bus carries **no** PCM. Only events cross (REQ-VOICE-006).

## INVARIANTS

- At most one capture stream and one output stream are open.
- The segment queue never exceeds its cap; on overflow the oldest is dropped and
  `voice.overflow` is published.
- `voice.state: speaking` implies playback is active; the mic is gated while it
  holds, unless barge-in is explicitly enabled.
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
| Capture thread | Publishes level and state via `bus.publish` (thread-safe) |
| Playback callback | Reads the PCM queue, checks the stop flag |
| asyncio loop | `speak`, `set_mute`, command handlers, ASR worker scheduling |

ASR runs in an executor; it must never run on the event loop.

## RESOURCES

- Two threads; one `sounddevice` input stream, one output stream.
- Bounded segment queue (cap 2) and a bounded PCM queue.
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
