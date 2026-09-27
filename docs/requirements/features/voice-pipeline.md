# Feature: Voice Pipeline

**Requirements:** REQ-VOICE-001..006, REQ-WAKE-001..008.
**Contract:** [IF-0005 `voice.state` / `voice.level`](../../contracts/protocols.md#if-0005-voice-events), [IF-0006 audio plane](../../contracts/protocols.md#if-0006-audio-plane).

## What it does

Owns the whole duplex audio path: microphone capture, voice activity detection,
wake-phrase gating, speech recognition, text-to-speech synthesis, and playback.
It replaces two modules that could not cooperate.

## Why it is one module

`ears` and `mouth` were separate, so neither could own the audio device. The
result was a mute dance over the bus: `ears.py:68-70` subscribed to
`status.mouth.started` to mute the microphone, and `mouth` had no way to be
stopped once `afplay` was running (`edge_tts.py:39-47`). Two bugs followed
directly:

1. **Interrupt could not work.** The playing utterance was a subprocess with no
   retained handle.
2. **Barge-in was impossible by construction.** The mic was hard-muted for the
   whole utterance.

One module owning both directions fixes both: the module can stop its own
playback and decide when the mic is live. See
[ADR-0005](../../architecture/decisions/ADR-0005-voice-merge.md).

## Two planes

Raw audio never crosses the bus. This is forced, not stylistic: `bus.publish`
is a synchronous dict fan-out (`bus/bus.py:44`) and cannot meet a 20 ms
deadline, and 16 kHz mono PCM is roughly 32 kB/s per subscriber.

| Plane | Runs on | Carries |
| --- | --- | --- |
| Real-time audio plane | Dedicated threads, no bus | PCM frames, VAD verdicts, RMS, PCM playback buffers |
| Event plane | asyncio | Discrete events only: state changes, transcripts, level samples |

## Pipeline

```
mic ──20 ms frames──> VAD ──segment──> bounded queue (cap 2, drop-oldest)
                       │
                       ├─RMS──> voice.level (latest-wins, ≤20 Hz)
                       │
                       │ WAV segment
                       v
        ASR worker (executor) ──> voice.transcribed ──> user.input.text
                                                              │
                                                    agent ──> harness
                                                              │
                                       agent.delta ───────────┴── agent.final
                                            │
                                            v
                              TTS chunker ──> edge-tts ──> MP3→PCM ──> PCM queue
                                                                          │
                        sounddevice callback ──> speaker  <────────────────┘
```

## States

One duplex finite state machine, published as `voice.state`:

```
IDLE ──> LISTENING ──> TRANSCRIBING ──> THINKING ──> SPEAKING ──> LISTENING
             ^                                │            │
             └──────────── interrupt / error ─┴────────────┘
```

This replaces `ears.py:24` (`self._state`) plus `mouth.py:21`
(`self._processing`), which together could express impossible combinations such
as listening while speaking.

## Backends

| Stage | Interface | Implementations |
| --- | --- | --- |
| ASR | `ASRBackend` | whisper, funasr, halasr, stub |
| TTS | `TTSBackend` | edge_tts, text, stub |
| Wake | `WakeDetector` | `AsrHotwordDetector` (default), future KWS engine |
| Capture | `AudioCapture` | sounddevice |
| Playback | `AudioPlayback` | sounddevice callback stream |

Every backend is selected by config and replaced without touching callers
(REQ-VOICE-004, REQ-WAKE-003).

## Playback

Replaces the `afplay` / `aplay` subprocess (`edge_tts.py:35-44`) with one
continuously open `sounddevice` output stream in callback mode. Benefits:

- Interrupt is a flag check in the callback, so it stops at the next buffer
  instead of waiting for a subprocess.
- No temporary files.
- Identical code on macOS and Linux.
- Gapless chunk playback, which is what makes streaming TTS useful.

One consequence: edge-tts emits MP3 (`audio-24khz-48kbitrate-mono-mp3`) and
`sounddevice` consumes PCM, so a decoder sits between them. That dependency was
missed in the first draft; it is required, not optional.

## Wake detection

The default detector matches configured wake phrases against ASR output. This
reuses the existing hotword path (`halasr.py:187` region) and adds no new
dependency. The cost is that ASR runs continuously, and detection is only as
fast as a segment.

A dedicated keyword-spotting engine runs before ASR, at far lower CPU. The
interface exists so it can be dropped in later; only the detector is replaced.

## Limitations

Half-duplex. The mic is gated during playback (REQ-VOICE-006). Voice barge-in
needs acoustic echo cancellation and is deferred; see
[ADR-0011](../../architecture/decisions/ADR-0011-half-duplex-first.md). The FSM
already models the transition, so enabling it later changes one edge.

## Verification

| Clause | Method | Test |
| --- | --- | --- |
| Segment → text published | mock ASR | T-0101 |
| Bounded queue drops oldest, reports overflow | host | T-0102 |
| Chunker flushes at sentence boundary | host (pure) | T-0103 |
| Stop flag silences playback | mock playback | T-0104 |
| State machine rejects impossible transitions | host | T-0105 |
| Wake phrase strips and gates correctly | rig (fixture audio) | T-0106 |
| Device absent degrades, no crash | host (injected failure) | T-0107 |
| End-to-end turn latency | rig (timestamps) | T-0108 |
