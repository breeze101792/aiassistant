# Orb UI Design

The design documentation for the native orb (`orb/`, PySide6 / Qt Quick). The
implementation contract is [MOD-0008](../architecture/modules/orb.md); the data
it renders is [IF-0004](../contracts/protocols.md#if-0004-orb-bridge-api) and
[IF-0005](../contracts/protocols.md#if-0005-voice-events). This folder specifies
*how it looks and behaves*; it never changes *what* those contracts carry.

Read [README.md](README.md) → this file → [tokens.md](tokens.md) →
[orb-states.md](orb-states.md). A coder can implement from these alone.

Status legend: `draft` written, not yet reviewed · `reviewed` passed
`challenger` · `as-built` reflects shipped code · `unverified` no test or source
confirms it yet.

## Files

| File | Subject | Status |
| --- | --- | --- |
| [README.md](README.md) | Index, concept, layer model, state channels | draft |
| [tokens.md](tokens.md) | Color, spacing, radii, type, motion — QML-ready | draft |
| [orb-states.md](orb-states.md) | Full state table, transitions, grayscale check | draft |
| [audio-reactivity.md](audio-reactivity.md) | `voice.level` signal path and parameters | draft |
| [layout.md](layout.md) | Window modes, zones, transcript, Wayland degradation | draft |
| [interactions.md](interactions.md) | Input map, interrupt, error surfacing | draft |
| [accessibility.md](accessibility.md) | Contrast, motion, keyboard, screen readers | draft |
| [components/orb.md](components/orb.md) | Layer stack, shader uniforms, fallback | draft |
| [components/transcript.md](components/transcript.md) | Streaming rows, deltas, scrollback | draft |
| [components/composer.md](components/composer.md) | Text input, validation, states | draft |
| [components/controls.md](components/controls.md) | Mute, stop, badge, settings, quit | draft |
| [implementation-qt.md](implementation-qt.md) | Qt modules, qsb, event bridge, perf | draft |
| [mockup.html](mockup.html) | Self-contained reference mockup | draft |

## What this designs against

| Fact | Value | Source |
| --- | --- | --- |
| Identity | default `jarvis` | [scope.md](../requirements/scope.md) |
| Wake phrase | `hi jarvis` | [schemas.md](../contracts/schemas.md) |
| Stack | Qt Quick / QML via PySide6, separate process, Qt loop only | [ADR-0013](../architecture/decisions/ADR-0013-pyside6-orb.md) |
| Platforms | macOS 13+ and current Linux | [build.md](../operations/build.md) |
| Orb states | `idle\|listening\|transcribing\|thinking\|speaking\|error\|muted` | [IF-0005](../contracts/protocols.md#if-0005-voice-events) |
| Level signal | `{level: 0..1, source: "input"\|"output", ts}`, ≤ 20 Hz | [schemas.md](../contracts/schemas.md) |
| Stream | `agent.delta` delta-only, monotonic `index`; `agent.final` authoritative | [schemas.md](../contracts/schemas.md) |
| Constraints | frameless, transparent, configurable always-on-top; Wayland degrades | [orb-ui.md](../requirements/features/orb-ui.md) |

## Concept

The orb is a **presence indicator**, not an avatar and not a control surface.

An avatar implies a face, personality, and a body to read; a control surface
implies buttons to hunt for. Neither is honest here: the assistant is a
voice-first loop whose only reliable output channel is text and audio, and whose
one durable truth is *what state it is in right now*. The orb renders that state
as light. It answers a single question at a glance: **is it listening, thinking,
speaking, or stuck?** Everything else — transcript, composer, controls — is
secondary chrome the user opens when they want it.

Consequences of this stance, and they are load-bearing for the whole design:

1. **The orb owns no functionality.** It displays and it is a hit target; it is
   never the only path to an action. Every action it exposes also has a keyboard
   shortcut and, where it makes sense, a visible control
   ([interactions.md](interactions.md), REQ-ORB-003).
2. **Chrome recedes.** Near-black surfaces, quiet text, no ornament. The orb is
   the only high-chroma element on screen
   ([tokens.md](tokens.md#color--chrome)).
3. **State is legible without color.** Color is one channel of three, never the
   only one (REQ-ORB-007, [accessibility.md](accessibility.md#colorblind-safe-cues)).
4. **Motion is expressive but bounded.** No strobing, no perpetual high-energy
   motion; an always-on window must be calm at idle and cheap on the battery
   ([audio-reactivity.md](audio-reactivity.md#performance-budget)).

## The layer model

The orb is five concentric layers, painted back to front. Each has one job and
its own token set. The stack is fixed: a later layer never reuses an earlier
layer's channel.

```
      field   ── faint halo; carries presence and level glow
        ring  ── a moving/breathing outline; carries motion state
          body ── the solid state-colored disc; carries hue
            core ── a bright center; carries level intensity
           motes ── sparse orbiting particles; carries activity (thinking/tools)
```

| Layer | Token source | Channel it carries | At rest |
| --- | --- | --- | --- |
| **Field** | `Theme.orbFieldRatio`, `orbGlowBase` | Glow, ambient presence | Faint, static |
| **Ring** | `Theme.orbRingRatio`, state alt color | Form: rotating arc, breathing circle, or dashed | Slow or still |
| **Body** | `Theme.state<Name>`, `state<Name>Alt` | Hue → state identity | Solid |
| **Core** | `Theme.orbCoreRatio`, `orbCoreGlowAdd` | Level intensity | Small, dim |
| **Motes** | accent color, count by state | Activity volume | Absent |

Layer geometry is defined once in [components/orb.md](components/orb.md). The
shader renders field, ring, body, and core in one `ShaderEffect`; motes are QML
particles above it (or skipped entirely in the fallback circle).

## Three independent state channels

State is encoded on **hue**, **motion**, and **ring form** independently. This is
the central accessibility decision of the design.

| Channel | What varies | Who relies on it |
| --- | --- | --- |
| **Hue** | Body/ring color, one per state | Users with full color vision; fastest read at a glance |
| **Motion** | Speed, direction, pulse pattern, amplitude | Users with reduced color vision, grayscale displays, peripheral vision |
| **Ring form** | Ring geometry: solid, arc, rotating, broken, dashed | Colorblind users, low-vision users, screenshots and static captures |

Why three channels:

- **REQ-ORB-007** forbids color-only state. Any single channel can be hidden —
  by a monochrome display, by a color vision deficiency, by `reduced_motion`, by
  a screenshot — so no single channel is allowed to carry a state alone.
- The channels are **orthogonal, not redundant**: they are not three copies of
  the same signal but three views of it, so a user can attend to whichever is
  most legible for them without the others creating noise.
- **Grayscale distinguishability is a hard requirement**, not a nicety: every
  state pair must differ in luminance, motion, or form. The pairwise check is in
  [orb-states.md § Grayscale check](orb-states.md#grayscale-check), and the
  luminance ordering is deliberate (calm states dim, alert states bright).

A fourth channel, **text**, is always available as a fallback: a one-line state
label appears under the orb on hover, on focus, and whenever
`reduced_motion` is on ([layout.md](layout.md#compact-ambient-mode)).

## Non-goals

| Non-goal | Why |
| --- | --- |
| An animated character or face | The assistant has no body; a face would promise expressiveness the loop does not have |
| A full settings UI | Settings are a config file plus a small panel; the orb opens the panel, it does not become one |
| A transcript editor | Transcript is read-and-scroll; editing belongs to the console or the store |
| A notification center | Errors are non-modal state plus an actionable line, not a queue |
| Any web content | REQ-ORB-001, REQ-PLAT-004: no browser, no HTTP server |

## Related

- [tokens.md](tokens.md) — every value used above.
- [orb-states.md](orb-states.md) — the state contract in full.
- [components/orb.md](components/orb.md) — how the layers are built.
