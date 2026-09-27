# Audio Reactivity

How a `voice.level` sample becomes motion on the orb. The orb **consumes** this
signal; it never computes it and never touches an audio device
([MOD-0008 § Must not do](../architecture/modules/orb.md)). The publisher
computes RMS and coalesces to ≤ 20 Hz ([IF-0006](../contracts/protocols.md#if-0006-audio-plane)).

## Payload

```json
{"topic":"voice.level","payload":{"level":0.42,"source":"input","ts":1043.51}}
```

| Field | Type | Range | Meaning |
| --- | --- | --- | --- |
| `level` | float | `0.0 .. 1.0` | RMS, already normalized by the publisher |
| `source` | enum | `"input"` \| `"output"` | Mic while listening, TTS while speaking |
| `ts` | float | monotonic seconds | Publish time; used to detect a stalled stream |

The orb treats `level` as an **arbitrary monotonic signal**, not calibrated dBFS.
Its job is to look alive, not to meter accurately. All parameters below are UI
taste, not audio fidelity, and are marked tunable.

## Signal path

Per incoming sample, in order. The whole chain is O(1) scalar math on the Qt
loop; no allocation, no timer.

```
raw level ──> [1] noise gate ──> [2] gain ──> [3] tanh compression
          ──> [4] perceptual gamma ──> [5] attack/decay smoothing
          ──> reactive properties (scale, glow, ring radius, ripple)
```

| # | Stage | Formula (reference) | Purpose |
| --- | --- | --- | --- |
| 1 | Noise gate | `g = level < gate ? 0 : (level - gate) / (1 - gate)` | Kill mic hiss so idle-looking silence reads as still, not jitter |
| 2 | Gain | `v = g × gain` | Bring typical speech into the useful range before compression |
| 3 | Soft compression | `c = tanh(v × k) / tanh(k)` | Musical, never clips; loud and quiet both stay expressive |
| 4 | Perceptual gamma | `p = c ^ gamma` | Human loudness is roughly logarithmic; gamma lifts mid-levels |
| 5 | Attack/decay | see below | Fast to respond, slow to release — this is what makes it feel organic |

Stages 3 and 4 are deliberately in that order: compression first keeps the
gamma curve in a bounded domain, so `gamma` has a predictable effect and the
output cannot exceed 1.

### Attack/decay smoothing

A one-pole filter, evaluated per sample; `dt` is seconds since the last sample
(capped at `Theme`/`params.levelFrameMaxDt` = `0.1 s` **PLACEHOLDER** [0.05–0.2]
so a stalled stream decays instead of latching).

```
target = p
tau    = (target > smoothed) ? attackTau : decayTau
alpha  = 1 - exp(-dt / tau)
smoothed += alpha * (target - smoothed)
```

`attackTau < decayTau` gives the characteristic "bright flash, slow fade".
This single filter produces both the fast `listening` contraction and the
slower `speaking` ripple feel; per-state differences come from how the smoothed
value is mapped, not from a second filter.

## Parameter table

All **PLACEHOLDER** — tune by eye against a real mic and real TTS on both OSes.
`τ` is a time constant in seconds; `~5τ` is the visible settle time.

| Parameter | Token / symbol | Unit | Suggested | Range | Effect of raising |
| --- | --- | --- | --- | --- | --- |
| Noise gate | `Theme.paramLevelGate` | normalized | `0.02` | 0.0–0.08 | Higher → more silence dead zones, less jitter |
| Gain | `Theme.paramLevelGain` | × | `2.2` | 1.0–4.0 | Higher → louder reaction to quiet speech |
| Compression sharpness | `Theme.paramLevelCompK` | — | `2.0` | 1.0–4.0 | Higher → flatter, more uniform response |
| Perceptual gamma | `Theme.paramLevelGamma` | — | `0.75` | 0.5–1.2 | Lower → lifts mid-levels more (< 1 brightens) |
| Attack τ | `Theme.paramLevelAttackTau` | s | `0.045` | 0.01–0.12 | Higher → slower onset, less twitchy |
| Decay τ | `Theme.paramLevelDecayTau` | s | `0.240` | 0.10–0.60 | Higher → longer trailing glow |
| Frame dt cap | `Theme.paramLevelFrameMaxDt` | s | `0.10` | 0.05–0.20 | Higher → tolerates longer gaps before decaying |
| Stale-stream timeout | `Theme.paramLevelStaleMs` | ms | `400` **PLACEHOLDER** [250–800] | — | After this with no sample, hold last value and start decaying to 0 |

### Reactive properties and amounts

`smoothed` ∈ `[0, 1]`. Each state maps it to properties; the multipliers are the
design contract ([orb-states.md § Per-state level reactivity](orb-states.md#per-state-level-reactivity)).

| Property | State | Formula | Max effect |
| --- | --- | --- | --- |
| Body scale | `listening` | `1.00 + smoothed × 0.06` | +6 % |
| Body scale | `speaking` | `1.00 + smoothed × 0.10` | +10 % |
| Ring radius | `listening` | `baseR × (1 - smoothed × 0.18)` | −18 %, contracts inward |
| Ring ripple | `speaking` | spawn ring at `0.8 + 0.4 × smoothed` opacity | outward ripple |
| Field glow | `listening`, `speaking` | `orbGlowBase + smoothed × orbGlowLevelAdd` | see [tokens.md](tokens.md#elevation-and-glow) |
| Core glow | `speaking` | `+ smoothed × orbCoreGlowAdd` | core brightens |

No property reacts to more than one source at a time (see below).

## Source routing

`source` decides which state is allowed to consume the sample. This prevents the
orb from reacting to the assistant's own voice during half-duplex playback and
from twitching on mic noise while it is talking.

| `source` | Consumed by | Ignored by | Rationale |
| --- | --- | --- | --- |
| `input` | `listening` | every other state | The mic is only live while listening (half-duplex, REQ-VOICE-006) |
| `output` | `speaking` | every other state | TTS level should drive playback motion only |

| Condition | Behavior |
| --- | --- |
| Sample arrives for a state that ignores it | Dropped; no state update, no error |
| Sample arrives while in `connecting` | Dropped; the orb has no live session |
| Rapid `source` flips (listening → speaking) | Smoothing state is **reset** on source change, so the new source starts from 0 rather than inheriting the old envelope |
| `level` exactly `0.0` for a full turn | Valid; the orb animates a still form and shows no error |
| `ts` goes backward or repeats | Ignored; the orb uses its own monotonic frame clock for `dt`, not `ts` |
| No sample for `paramLevelStaleMs` | `smoothed` decays toward 0 at `decayTau`; the state form remains |

`source` is also a **non-color accessibility cue**: in `reduced_motion`, the
level label reads "Mic" or "Audio" so the direction of the level is still
available as text ([accessibility.md](accessibility.md#reduced-motion)).

## Animation clock and frame rate

| Mode | Render cadence | When |
| --- | --- | --- |
| Active | 60 Hz (vsync), capped at `Theme.perfMaxFps` = `60` | Any state with motion: `listening`, `transcribing`, `thinking`, `speaking`, `connecting` |
| Idle | `12 Hz` **PLACEHOLDER** [8–20] | `idle`, `muted`, `error`, `backend-down` after one breath cycle with no input |
| Still | 1 Hz (or on change only) | `reduced_motion`, or the window is fully occluded |
| Suspended | 0 Hz | Window hidden/minimized; the orb stops its timers |

The orb drives animation from a single `FrameAnimation`/`Timer` feeding the
shader's `time` uniform; it does **not** use one timer per layer. Level samples
only update the smoothed value; they never trigger a layout pass.

## Performance budget

An always-on always-on-top window must be cheap. These are targets for the
**idle/ambient** case on the reference machine (macOS 13+, integrated GPU;
Ubuntu 24.04, integrated GPU). Marked as targets, not measurements; verify with
`instruments`/`perf` on target.

| Metric | Target (idle) | Target (active) | Notes |
| --- | --- | --- | --- |
| CPU, orb process | ≤ `1.5 %` of one core **PLACEHOLDER** [≤ 3 %] | ≤ `6 %` **PLACEHOLDER** [≤ 10 %] | Measure with the render loop running, window visible |
| GPU | No measurable baseline load | ≤ `5 %` **PLACEHOLDER** | One `ShaderEffect`, no per-frame texture uploads |
| Resident memory | ≤ `120 MB` **PLACEHOLDER** [≤ 180 MB] | same | Qt + QML baseline dominates |
| Wakeups/s | ≤ `15` at 12 Hz idle | ≤ `70` at 60 Hz | Fewer is better for battery |
| Window occlusion | Animations suspend when hidden | — | Qt surface visibility drives this |

Rules that keep the budget:

1. **One shader, one pass.** Field, ring, body, and core are computed in a single
   fragment shader; no `ShaderEffectSource` chains, no render-to-texture at
   20 Hz ([components/orb.md](components/orb.md)).
2. **No QML `Timer` per layer.** One clock, many uniforms.
3. **Idle drops to 12 Hz.** Visual breath at 12 Hz is indistinguishable from
   60 Hz for a 4 s period; the saving is real.
4. **Motes are off except in `thinking`/tool-call.** They are the only particle
   system and the only per-frame allocation risk.
5. **No text re-layout on level.** The state label changes on state change, not
   per frame.
6. **Shader is pre-compiled** via `qsb`, never at runtime
   ([implementation-qt.md](implementation-qt.md#shaders)).

## Related

- [orb-states.md](orb-states.md) — which state reacts to which source.
- [components/orb.md](components/orb.md) — the uniforms these properties feed.
- [accessibility.md](accessibility.md#reduced-motion) — level under reduced motion.
- [implementation-qt.md](implementation-qt.md#performance-cautions) — implementation cautions.
