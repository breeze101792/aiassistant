# Orb States

The state contract for the orb. Every state is encoded on three independent
channels — **hue**, **motion**, **ring form** — plus a non-color **cue**
([README.md § Three channels](README.md#three-independent-state-channels), REQ-ORB-002,
REQ-ORB-007). Any pair of states must be distinguishable in grayscale.

Colors are tokens from [tokens.md](tokens.md#color--orb-states). Speeds are token
values; a value marked **PLACEHOLDER** carries a suggested range in brackets.

## State sources

Not every visual state comes from `voice.state`. There are three tiers, and the
orb must not confuse them:

| Tier | States | Source | Lifetime |
| --- | --- | --- | --- |
| **Base** | `idle`, `listening`, `transcribing`, `thinking`, `speaking`, `error`, `muted` | `voice.state` | Until the next `voice.state` |
| **Orb-local** | `connecting` | The orb's own socket state (bridge unreachable) | Until the first forward arrives |
| **Overlay** | `backend-down` | Derived: `agent.turn.error` with `class: "harness"`, or a failed health probe (REQ-HARNESS-007) | Until the next successful turn event, or the next `voice.state` change |
| **Overlay** | `transcript-error` | Derived: `agent.turn.error` with `class` ≠ `harness` | Until dismissed or the next turn |

`backend-down` and `transcript-error` are **overlays**: they desaturate and ring
the base state rather than replacing it, so the user can see "speaking, but the
backend is down". Full behavior in [interactions.md § Errors](interactions.md#error-surfacing).

## The full state table

Ring forms:

- `solid` — one continuous, unbroken ring
- `arc` — one ring segment with a moving gap (a comet)
- `dual` — two segments with opposite gaps
- `dashed` — many short segments, evenly spaced
- `slash` — a solid ring with one full chord through the body (a mute slash)
- `bar` — a solid ring with one horizontal chord (a broken-link bar)
- `jagged` — a solid ring whose radius is perturbed by a static noise pattern

| State | Meaning | Body color | Scale | Ring form | Motion / speed | Glow (field) | Non-color cue |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `idle` | Not listening, not speaking | `stateIdle` | `1.00` | `solid` | Breath, scale `1.00→1.03`, period `4000 ms` **PLACEHOLDER** [3000–6000] | Base `0.35` | Flat baseline; text "Idle" |
| `connecting` | Bridge unreachable; retrying (orb-local) | `stateConnecting` | `0.98` | `dashed` | Dash rotate, period `2400 ms` **PLACEHOLDER** [1800–3600] | Base `0.30` | Text "Connecting…" + retry dot |
| `muted` | Capture stopped by the user | `stateMuted` | `0.94` | `slash` | **Still** (no motion) | Base `0.22` | Full chord slash; muted glyph; text "Muted" |
| `listening` | Capture live, awaiting speech | `stateListening` | `1.00 + level × 0.06` | `solid`, ring radius tracks level | Inward breath, period `1600 ms` **PLACEHOLDER** [1200–2200] | `0.35 + level × 0.30` | Ring contracts toward the center on peaks |
| `transcribing` | Segment captured, ASR running | `stateTranscribing` | `0.96` | `dual` | Counter-rotation, period `700 ms` **PLACEHOLDER** [500–1000] | `0.40` | Fastest motion of any state; text "Transcribing" |
| `thinking` | Turn dispatched, awaiting the harness | `stateThinking` | `1.02` | `arc` | Arc rotation, period `1400 ms` **PLACEHOLDER** [1000–2000] | `0.42` | Motes drift; text "Thinking" |
| `speaking` | Playback active | `stateSpeaking` | `1.00 + level × 0.10` | `solid`, ripples emitted outward | Outward ripple every `500 ms` **PLACEHOLDER** [350–800]; level-reactive | `0.40 + level × 0.45` | Ring expands **outward** on peaks |
| `error` | A classified error is showing | `stateError` | `0.92 + jitter` | `jagged` | Slow pulse, period `1800 ms` **PLACEHOLDER** [1500–2500] | `0.45` | 2 % radius jitter; `!` badge; text "Error" |
| `backend-down` (overlay) | Harness unhealthy (`class: harness`) | `stateBackendDown`, desaturated `25 %` | `0.94` | `bar` | Slow pulse, period `2600 ms` **PLACEHOLDER** [2200–3200] | `0.30` | Horizontal bar chord; text "Backend down" |
| `transcript-error` (overlay) | Turn failed, non-harness class | inherits base, `stateError` ring | base − `0.04` | `jagged` | base motion, halved speed | `0.40` | `!` badge on the transcript row, not the orb |

Motes: present only in `thinking` (6 motes, period `3000 ms`) and during a tool
call (12 motes, period `1800 ms`); absent in every other state. Motes are QML
particles rendered above the shader ([components/orb.md](components/orb.md)),
and are omitted in the shader fallback.

## Per-state level reactivity

`voice.level` is routed by `source` ([audio-reactivity.md](audio-reactivity.md#source-routing)).
The table above uses `level` for brevity; this is which property each state
actually drives:

| State | `source: input` drives | `source: output` drives | No level seen |
| --- | --- | --- | --- |
| `listening` | Body scale, ring radius, field glow | Ignored (not playing) | Static `solid` ring; no contraction |
| `speaking` | Ignored (mic gated) | Body scale, core glow, ripple emission | Ripples on a fixed clock; no amplitude |
| `transcribing` | Ignored | Ignored | Constant-speed counter-rotation |
| `thinking` | Ignored | Ignored | Constant arc rotation |
| `idle`, `muted`, `error`, `connecting`, `backend-down` | Ignored | Ignored | No level reaction |
| `transcript-error` | per base state | per base state | per base state |

Rule: a state reacts to **at most one** source. Reacting to both would make the
orb twitch on the assistant's own voice during half-duplex playback.

## Transitions

### Allowed base-state transitions

From [IF-0005 § voice.state](../contracts/protocols.md#if-0005-voice-events) and
[voice-pipeline.md § States](../requirements/features/voice-pipeline.md#states):

```
IDLE ──> LISTENING ──> TRANSCRIBING ──> THINKING ──> SPEAKING ──> LISTENING
             ^                                │            │
             └──────────── interrupt / error ─┴────────────┘
```

| From | To | Trigger | Orb animation |
| --- | --- | --- | --- |
| `idle` | `listening` | PTT armed, or VAD detects speech in `open`/`wake` | Hue crossfade `320 ms`; ring settles from breath to level-tracking |
| `listening` | `transcribing` | Utterance endpointed | Crossfade; ring form `solid → dual`; speed jumps |
| `listening` | `idle` | Wake window closed, or PTT released with no speech | Crossfade; level decays |
| `transcribing` | `thinking` | `user.input.text` accepted by the agent | Crossfade; `dual → arc` |
| `thinking` | `speaking` | First TTS chunk starts | Crossfade; `arc → solid`; ripples begin |
| `thinking` | `idle` | Turn errored with no speech, or cancelled | Crossfade; motes fade `220 ms` |
| `speaking` | `listening` | Playback drains (half-duplex returns to listening) | Crossfade; ripple stops, level decays |
| `speaking` | `idle` | `speak_text_turns: false` and playback drains | Crossfade |
| any base | `error` | `voice.state: error`, or `agent.turn.error` with a non-harness class | Overlay `transcript-error`; hue `→ error` if a base error |
| `error` | `idle` | Error dismissed or superseded | Crossfade `320 ms` |
| `idle`/`listening` | `muted` | User toggles mute (`command.voice.mute`) | Crossfade; motion snaps to still over `140 ms` |
| `muted` | `idle`/`listening` | User unmutes; returns to the configured `voice.listen.mode` | Crossfade; motion resumes |

Impossible combinations (e.g. `listening` while `speaking`) are rejected upstream
by the single FSM; the orb never has to arbitrate them. If one arrives anyway,
the orb applies it — it displays what it receives
([MOD-0008 § OWNS](../architecture/modules/orb.md#owns)).

### Orb-local and overlay transitions

| From | To | Trigger | Notes |
| --- | --- | --- | --- |
| `connecting` | any base | First forward received after (re)subscribe | The orb starts in `connecting`, not `idle` |
| any | `connecting` | `QWebSocket` disconnect or `ERR-ORB-BRIDGE-UNREACHABLE` | Reconnect with backoff; see [interactions.md](interactions.md#error-surfacing) |
| overlay `backend-down` set | — | `agent.turn.error {class: "harness"}` | Layered on the base state; does not change the base |
| overlay `backend-down` cleared | — | Next `agent.delta`, `agent.final`, or `voice.state` change | Or a successful probe (REQ-HARNESS-007) |
| overlay `transcript-error` set | — | `agent.turn.error {class ≠ "harness"}` | Row badge + orb ring, base hue retained |
| overlay `transcript-error` cleared | — | Next turn begins | Any `voice.state` change to `listening`/`thinking` |

### Transition motion rules

| Rule | Value |
| --- | --- |
| Hue crossfade between base states | `Theme.durStateFade` = `320 ms`, `Theme.easeInOutQuad` |
| Ring form change | Instant at the crossfade midpoint; a morph animation is **not** required |
| Level decay on leaving `listening`/`speaking` | Exponential, `τ` = `180 ms` **PLACEHOLDER** [120–300] |
| Mote fade in/out | `Theme.durBase` = `220 ms`, `Theme.easeOutCubic` |
| Overlay apply/clear | `Theme.durFast` = `140 ms` opacity |
| `reduced_motion` on | All crossfades become `80 ms` opacity cuts; rotation, breath, ripple, and jitter stop (see [accessibility.md](accessibility.md#reduced-motion)) |

## Grayscale check

Requirement: every pair of states is distinguishable in grayscale (REQ-ORB-007;
"state is never color-only"). A grayscale rendering keeps **relative luminance**
and **motion** and **form**; it loses hue. So a pair is distinguishable if it
differs in luminance by ≥ 1.3:1 **or** in ring form **or** in motion.

Body-color relative luminance (WCAG), from [tokens.md](tokens.md#color--orb-states):

| State | Luminance | Motion |
| --- | --- | --- |
| `connecting` | 0.064 | dash rotate |
| `muted` | 0.089 | still |
| `idle` | 0.117 | breath |
| `backend-down` | 0.159 | slow pulse |
| `thinking` | 0.274 | arc rotate |
| `error` | 0.330 | jagged pulse |
| `transcribing` | 0.440 | counter-rotate (fastest) |
| `listening` | 0.504 | inward breath |
| `speaking` | 0.579 | outward ripple |

Pairs whose luminance ratio is **below 1.3:1** — these are the ones the ring form
and motion must separate. Every one of them does:

| Pair | Luminance ratio | Separated by ring form | Separated by motion |
| --- | --- | --- | --- |
| `connecting` / `muted` | 1.22 | `dashed` vs `slash` | rotate vs still |
| `muted` / `idle` | 1.20 | `slash` vs `solid` | still vs breath |
| `idle` / `backend-down` | 1.25 | `solid` vs `bar` | breath vs slow pulse |
| `thinking` / `error` | 1.17 | `arc` vs `jagged` | smooth arc vs jagged pulse |
| `error` / `transcribing` | 1.29 | `jagged` vs `dual` | slow vs fastest |
| `transcribing` / `listening` | 1.13 | `dual` vs `solid` | counter-rotate vs inward breath |
| `transcribing` / `speaking` | 1.28 | `dual` vs `solid+ripple` | counter-rotate vs outward ripple |
| `listening` / `speaking` | 1.13 | ring radius direction | inward vs outward |

All other pairs have a luminance ratio ≥ 1.3:1 and separate on luminance alone.
**Rule for change:** adding a state requires re-running this check; a new state
that is within 1.3:1 of an existing one and shares both its ring form and its
motion is not allowed. The grayscale check is the acceptance gate for
REQ-ORB-002/007 and is inspected under T-0202/T-0206
([trace.md](../testing/trace.md)).

## Related

- [README.md](README.md) — the layer model and the three channels.
- [tokens.md](tokens.md) — state color tokens and luminance table.
- [audio-reactivity.md](audio-reactivity.md) — how `level` becomes motion.
- [components/orb.md](components/orb.md) — the ring forms as shader uniforms.
- [accessibility.md](accessibility.md) — reduced motion and colorblind cues.
