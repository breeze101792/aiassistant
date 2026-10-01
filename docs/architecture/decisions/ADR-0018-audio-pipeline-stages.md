# ADR-0018 — The voice pipeline as explicit stages, one factory per stage

**Status:** proposed · **Date:** 2026-10-01

## Decision

The mic path becomes five explicit stages, each behind one interface with one
factory, all selected by config:

```
Capture → VAD → Segmenter → SegmentQueue → ASR → transcript
```

1. A **VAD backend** classifies one 20 ms frame: `energy` (default, numpy
   only), `webrtc`, later `silero`. New file `voice/vad.py`.
2. A **segmenter** owns buffering, pre-roll, and endpointing; it composes a
   VAD and emits complete utterances. New file `voice/segmenter.py`. This is
   the stage that never existed — nothing ever called `on_segment`
   (`voice/module.py:216`).
3. **ASR** and **TTS** keep their existing interfaces; construction moves from
   `VoiceModule._build_asr`/`_build_tts` (`module.py:474,490`, silent stub
   fallback) to one factory module `voice/factory.py` with the
   hard-error-naming-the-value rule (REQ-BACKEND-002).
4. `HalASRBackend` is **dropped**, not adapted. It is a competing fused
   pipeline (own PyAudio capture, own VAD loop, own hotword gating) that
   duplicates every stage above. Its endpointing parameters are salvaged into
   the segmenter; its recognizers already exist as `funasr.py`/`whisper.py`.
5. Config moves to per-stage sections: `voice.asr`, `voice.vad`,
   `voice.tts`, `voice.segmenter`. "Online" and "offline" are **presets**
   (documented value sets + CLI sugar), not a new switch — per-stage keys are
   the only persisted truth.

## Why

- The mic produces no transcript today: `_on_frame`
  (`voice/module.py:196`) computes RMS and discards the PCM; `on_segment`
  has no caller; `--audio` selects `halasr`, which `_build_asr` does not
  recognize and silently degrades to `StubASR` (`module.py:486-488`).
- The user requirement is modularity: online default, offline swap,
  per-stage override. Fused `halasr` proved the alternative — a backend that
  owns capture cannot be replaced without rewriting the pipeline.
- The stub fallback hid both breaks for weeks. The reasoning factory
  (`reasoning/factory.py:59-62`) already established the repo rule: unknown
  backend = hard error naming the value. Voice adopts it.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Adapt `halasr` behind `ASRBackend` | It has no `transcribe()` and owns a second capture stream on the same device; adapting it preserves the duplication this ADR removes |
| Split `halasr` into segmenter + recognizer | Both halves already exist (`VadSegmenter`, `funasr.py`/`whisper.py`); splitting produces code we would then delete |
| A `voice.preset: online\|offline` config key | Competes with per-stage keys and needs a conflict rule; presets as CLI overrides (`--audio`, `--offline`) materialize into per-stage keys at load time, one source of truth |
| Fuse VAD into the segmenter | The VAD choice (energy/webrtc/silero) must be swappable independently of endpointing policy; one fused class is what made `halasr` unreplaceable |
| Stream partial transcripts to ASR | No streaming backend is installed or requested; complete utterances satisfy REQ-VOICE-001 |

## Consequences

- `--audio` stops writing `voice.backend: halasr`; it writes the self-hosted
  preset (`voice.asr.backend: whisper_server`). `voice.backend`/
  `voice.recognizer`/`voice_tts` migrate via `LEGACY_*` tables; a config still
  naming `halasr` hard-errors with the fix.
- `voice.recognizer` (halasr-only) is dropped with a warning, not migrated.
- Unit tests inject frames and fake backends; no device is opened
  (`VoiceModule.disable_audio()`).
- **ASR ships no hosted or paid service (revised 2026-10-01).** The default is
  **`faster_whisper`**, which runs locally and needs no account. The only
  network backend, `whisper_server`, targets an OpenAI-compatible endpoint the
  user runs themselves (for example `whisper.cpp`'s `server`); it accepts a
  generic optional `api_key`, but a self-hosted server ignores it, and there is
  no built-in endpoint. Provider-specific backends (`groq`, `openai`) hard-error
  naming the replacement. Key support is generic and retained; a hosted
  provider is not.
