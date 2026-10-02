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
mic ──20 ms frames──> Segmenter (composes VAD) ──utterance──> SegmentQueue (cap 2, drop-oldest)
                       │  │                                             │
                       │  └─VAD: energy | webrtc                       │ PCM segment
                       ├─RMS──> voice.level (latest-wins, ≤20 Hz)      v
                       │                              ASR worker (thread) ──> voice.transcribed
                       │                                                              │
                       │                                                    user.input.text
                       │                                                              │
                       │                                                     agent ──> harness
                       │                                                              │
                       │                                        agent.delta ──────────┴── agent.final
                       │                                             │
                       │                                             v
                       └───────  TTS chunker ──> edge-tts ──> MP3→PCM ──> PCM queue
                                                                                   │
                                                 sounddevice callback ──> speaker <┘
```

The mic path is five explicit stages — capture, VAD, segmenter, segment queue,
ASR worker — each behind one interface and one factory (`voice/factory.py`).
The segmenter is the stage that did not exist before ADR-0018: nothing called
`on_utterance`, so the mic produced a level and no transcript.

### Turn boundary (the wait after you stop)

`voice.endpoint_silence_ms` (default 3000) is how long the segmenter keeps
listening after your **last speech frame** before it sends the turn. It is a
wait measured from when you stop, not a cap on how long you may talk: you can
speak for as long as you like, and the timer only starts once the VAD stops
hearing speech. A natural mid-sentence breath shorter than this stays in the
same utterance. Raise it if the assistant cuts in too soon; lower it if it feels
slow to respond. `voice.segmenter.onset_ms` is the separate, much shorter
threshold that rejects a room-noise click before a segment opens, and
`voice.segmenter.max_utterance_ms` is the only true duration cap (a safety bound
on a wedged VAD, default 30 s).

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

| Stage | Interface | Implementations | Config |
| --- | --- | --- | --- |
| VAD | `VADBackend` (`voice/vad.py`) | `energy` (default), `webrtc` (needs the `vad` extra) | `voice.vad.backend` |
| Segmenter | `VadSegmenter` (`voice/segmenter.py`) | one implementation, composes the VAD | `voice.segmenter.*` |
| ASR | `ASRBackend` | `faster_whisper` (offline, default), `whisper_server` (your own server), `whisper`, `funasr`, `stub` | `voice.asr.backend` |
| TTS | `TTSBackend` | `edge_tts`, `text` | `voice.tts.backend` |
| Wake | `WakeDetector` | `AsrHotwordDetector` (default), future KWS engine | `voice.listen.mode` |
| Capture | `Capture` (`voice/audio.py`) | sounddevice | — |
| Playback | `Playback` (`voice/audio.py`) | sounddevice callback stream | — |

Every backend is selected by config and replaced without touching callers
(REQ-VOICE-004, REQ-WAKE-003). The VAD, ASR, and TTS backends are built by
`voice/factory.py`; an unknown value is a hard error naming the value
(REQ-BACKEND-002). The wake detector is built by `voice/wake.py`
(`create_detector`). The fused pre-ADR backend was removed; see ADR-0018.

No ASR backend in this project requires a paid service, and the default
requires no account. `faster_whisper` runs locally. `whisper_server` targets an
OpenAI-compatible endpoint you run yourself (for example `whisper.cpp`'s
`server`); it takes a generic, optional `api_key`, but a self-hosted server
ignores it, and there is **no built-in hosted endpoint** to point at.
Provider-specific hosted backends were removed (ADR-0018).

`--audio` writes `voice.asr.backend: whisper_server` +
`voice.tts.backend: edge_tts` (set `voice.asr.base_url` to your server);
`--offline` writes `faster_whisper` + `text`. The two are mutually exclusive.
Presets are value sets materialised into per-stage keys at load time, not a
separate switch.

`faster_whisper` is offline for audio, but its model is fetched from Hugging
Face Hub on first use, so that first run needs the network (model weights, not
audio). After the model is cached, no network is used. `whisper`/`funasr` are
the older optional extras; the fused `halasr` backend was removed (ADR-0018).

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

The default detector (`AsrHotwordDetector`, `voice/wake.py`) matches configured
wake phrases against ASR output. It adds no new dependency. The cost is that ASR
runs continuously, and detection is only as fast as a segment.

When the detector is consulted depends on `voice.listen.mode`:

| Mode | Phrase required | Behavior |
| --- | --- | --- |
| `open` | no | Always listening. Every utterance is a turn; the detector accepts all (`AlwaysAwakeDetector`). |
| `wake` | yes | The phrase gates the turn. Speech without it is ignored; the phrase is stripped from the command. |
| `ptt` | no | The mic is armed by the user, so whatever is said while armed is the command. |

If the assistant answers everything it hears, the mode is `open`. Set
`voice.listen.mode: wake` to require the phrase.

Hearing the phrase opens a **follow-up window** (wake mode): the next utterances
are accepted without repeating the phrase, so a conversation flows naturally.
The window is refreshed on each utterance and stays open across a spoken reply;
it closes after `voice.wake_window_ms` of quiet, after which the phrase is
required again. An explicit mute also closes it.

A dedicated keyword-spotting engine runs before ASR, at far lower CPU. The
interface exists so it can be dropped in later; only the detector is replaced.

## Limitations

Half-duplex. The mic is gated during playback (REQ-VOICE-006). That gate is
transient: it is released when playback ends, and it is distinct from the user
mute (`command.voice.mute`), which is the only thing that leaves the module in
`muted`. Voice barge-in needs acoustic echo cancellation and is deferred; see
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
| Unknown backend hard-errors; setup returns `False` | host | T-0109 |
