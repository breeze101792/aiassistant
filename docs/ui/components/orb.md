# Component — Orb

The animated orb: the orb process's one shader. Implements the layer stack from
[README.md](../README.md#the-layer-model), the states from
[orb-states.md](../orb-states.md), and the level mapping from
[audio-reactivity.md](../audio-reactivity.md).

File: `orb/Orb.qml`. Owned by MOD-0008
([orb.md](../../architecture/modules/orb.md)).

## Layer stack

Painted back to front. Every layer except motes is computed in **one**
`ShaderEffect`; the QML item tree only positions the effect and holds uniforms.

```
 z5  motes        QML particles (Emitter + ImageParticle)      thinking / tool-call only
 z4  core         fragment: bright center, radius × coreScale
 z3  body         fragment: state gradient disc
 z2  ring         fragment: ring form (solid/arc/dual/dashed/slash/bar/jagged)
 z1  field        fragment: soft radial halo (glow)
 z0  (root)       transparent; on fallback, a rounded colorBg rectangle
```

| Layer | Drawn where | Source of geometry |
| --- | --- | --- |
| Field | fragment shader | `Theme.orbFieldRatio` |
| Ring | fragment shader | `Theme.orbRingRatio`, ring form per state |
| Body | fragment shader | `Theme.orbRadiusRatio` = 0.5 |
| Core | fragment shader | `CoreScale` uniform (level-mapped) |
| Motes | QML particles above the shader | count/period per state |

One shader means one draw call and no render-to-texture at 20 Hz. If a future
state needs a separate pass, it must go through `ShaderEffectSource`, which is a
performance decision requiring a new budget entry
([audio-reactivity.md § Performance budget](../audio-reactivity.md#performance-budget)).

## Uniforms

All uniforms are set from QML each frame from the smoothed level and the current
state. Token → uniform mapping is one-directional: GLSL cannot read `Theme`.

| Uniform | Type | Range | Source | Token / rule |
| --- | --- | --- | --- | --- |
| `iTime` | `float` | seconds | Frame clock | One clock; see [§ Frame clock](#frame-clock) |
| `iResolution` | `vec2` | dp | `ShaderEffect` size | — |
| `uStateHue` | `vec3` | sRGB | Current body color | `Theme.state<Name>` |
| `uStateHueAlt` | `vec3` | sRGB | Rim / gradient stop | `Theme.state<Name>Alt` |
| `uLevel` | `float` | `0..1` | Smoothed level | [audio-reactivity.md](../audio-reactivity.md#parameter-table) |
| `uLevelSource` | `float` | `0`=`none`, `1`=`input`, `2`=`output` | `voice.level.source` | Routes which property the level drives |
| `uBodyScale` | `float` | `0.90..1.14` | State + level | `listening` `+0.06·L`; `speaking` `+0.10·L` |
| `uRingRadius` | `float` | `0.30..0.55` | `Theme.orbRingRatio` ± level | `listening` contracts `−0.18·L` |
| `uRingWidth` | `float` | `0.01..0.06` | Per state | `transcribing` thinnest, `error` thicker |
| `uRingForm` | `int` | see enum | Current state | [§ Ring forms](#ring-forms) |
| `uRingPhase` | `float` | `0..1` | Clock × speed | Rotation/offset per state |
| `uCoreScale` | `float` | `0.12..0.55` | `Theme.orbCoreRatio` + level | `speaking` `+0.6·L` glow |
| `uGlow` | `float` | `0..1` | `orbGlowBase + L·orbGlowLevelAdd` | [tokens.md](../tokens.md#elevation-and-glow) |
| `uJitter` | `float` | `0..1` | `error` state | 0 elsewhere; `0.02` on `error` |
| `uAlpha` | `float` | `0..1` | Crossfade / opacity | Window opacity; reduced-motion cuts |
| `uReducedMotion` | `bool` | — | OS / config | When true, `iTime`-driven phase is frozen |

`uStateHue` / `uStateHueAlt` are converted to linear space in QML once per state
change (not per frame) and passed as `vec3`.

### Ring forms

`uRingForm` enum, used by the fragment shader to select the ring mask
([orb-states.md](../orb-states.md#the-full-state-table)):

| Value | Form | Mask |
| --- | --- | --- |
| `0` | `solid` | `abs(r - R) < w` |
| `1` | `arc` | as `solid`, `AND` angular window around `2π·uRingPhase` |
| `2` | `dual` | two angular windows at `phase` and `phase + π` |
| `3` | `dashed` | `solid` `AND` `fract(θ·N/2π + phase) < 0.5`, `N` = 12 **PLACEHOLDER** [8–20] |
| `4` | `slash` | `solid`, `OR` a chord `abs(θ - θ0) < ε` through the center |
| `5` | `bar` | `solid`, `OR` a horizontal chord `abs(y) < w` |
| `6` | `jagged` | `abs(r - (R + uJitter·noise(θ, t))) < w` |

`noise` is a static hash of `θ` (seeded, no `iTime` term) so the `error` ring is
perturbed but does not shimmer — shimmer would be a strobe risk.

## Frame clock

| Property | Value |
| --- | --- |
| Driver | One `FrameAnimation` (or `Timer` at the idle rate) in `Orb.qml` |
| `iTime` | Accumulated seconds; **frozen** when `uReducedMotion` is true |
| Active rate | `60 Hz` (vsync-capped by `Theme.perfMaxFps`) |
| Idle rate | `12 Hz` **PLACEHOLDER** [8–20] after one breath cycle with no level |
| Source | [audio-reactivity.md § Animation clock](../audio-reactivity.md#animation-clock-and-frame-rate) |

`iTime` is the **only** time source. A per-layer timer is forbidden.

## State switch

| Input | Effect |
| --- | --- |
| `voice.state` change | Set target hue pair + ring form + speeds; crossfade `uStateHue` over `Theme.durStateFade` = `320 ms` |
| Ring form | Applied at the crossfade midpoint (no morph) |
| `voice.level` sample | Update `uLevel` after smoothing; **no layout, no model change** |
| `source` change | Reset the smoothing state to 0, then apply ([audio-reactivity.md](../audio-reactivity.md#source-routing)) |
| Overlay `backend-down` | Desaturate the hue pair by `25 %`; switch ring form to `bar`; do **not** change the base hue |
| Overlay `transcript-error` | Draw the base with a `jagged` ring, hue retained |
| `muted` | Snap motion to still over `durFast`; draw the `slash` chord |
| `connecting` | `dashed` ring, `stateConnecting` hue; the orb starts here |
| `reduced_motion` | `iTime` frozen; crossfades become `80 ms` opacity; level mapped to a ±3 % scale only |

State resolution order when multiple sources apply (highest wins for the **hue**
channel):

```
connecting  >  backend-down overlay  >  voice.state base  >  idle default
```

The overlays win because they are the actionable condition; the ring form and
base hue are preserved beneath where possible.

## Hit behavior

| Target | Size | Action |
| --- | --- | --- |
| Compact orb | whole `orbSizeCompact` window | Click toggles the panel ([layout.md](../layout.md#mode-switching)) |
| Compact orb drag | movement past `4 dp` | `startSystemMove()` ([interactions.md](../interactions.md#drag)) |
| Expanded header orb | `orbSizeExpanded` | Click collapses |
| Focus | — | Orb is a focus stop with a `colorFocus` ring ([accessibility.md](../accessibility.md#focus-ring)); `Space`/`Enter` toggles |
| Hit area vs visual | The whole circle is hittable; the field beyond `orbRadius` is **not** | — |

The orb's accessible name carries the current state
([accessibility.md](../accessibility.md#screen-reader-labeling)); it changes on
state change and is announced politely.

## Inputs the orb requires

| Input | Source | Use |
| --- | --- | --- |
| Current state | `voice.state` | Hue, ring form, speed |
| Level + source | `voice.level` | Amplitude per [audio-reactivity.md](../audio-reactivity.md) |
| Bridge status | `QWebSocket` signals | `connecting` |
| Turn error class | `agent.turn.error` | Overlays |
| Reduced motion | OS hint / `display.reduced_motion` | Freeze `iTime` |
| Window size | QML layout | `iResolution`, scale |

The orb derives **nothing** from the assistant's internals; it displays what it
receives ([MOD-0008 § OWNS](../../architecture/modules/orb.md#owns)).

## Fallback

When the GPU/shader is unavailable — `ERR-ORB-SHADER`, a missing OpenGL/Vulkan
context, or `qsb` compilation failing — the orb falls back to a **plain QML
circle**. Silent, no error UI
([interactions.md § Error surfacing](../interactions.md#error-surfacing)).

| Aspect | Fallback behavior |
| --- | --- |
| Layer stack | Root `Rectangle` (`radius = width/2`) filled with `colorSurface`; one inner `Rectangle` circle filled with `uStateHue`; a `border` ring using the state alt color |
| Ring forms | **Not reproducible.** `solid` is the only ring; state is carried by hue + the state label + the non-color text. `dual`/`dashed`/`arc` degrade to `solid` |
| Level | Body scale animates with a `Behavior on scale` from the smoothed level (`listening` `+0.06·L`, `speaking` `+0.10·L`). No ripple, no contraction |
| Field glow | A `RadialGradient` (QtGraphicalEffects) or a soft outer `Rectangle` at `orbGlowBase` opacity; if effects are unavailable, omitted |
| Motes | Omitted |
| State legibility | Because forms are lost, the **state label is shown persistently** in fallback mode, not only on hover. This preserves REQ-ORB-007 |
| Detection | Try `ShaderEffect`; on `QQuickWindow::sceneGraphError` or a null program, set `Theme.shaderAvailable = false` and swap the QML subtree |
| Config override | `display.orb_shader: false` forces the fallback for debugging |

The fallback is a first-class path, not a degraded afterthought: REQ-ORB-002
still passes because hue, label, and scale remain; only the ring forms are
reduced, and the label compensates.

## Related

- [orb-states.md](../orb-states.md) — states, ring forms, transitions.
- [audio-reactivity.md](../audio-reactivity.md) — the level path and parameters.
- [tokens.md](../tokens.md) — every color and size used.
- [implementation-qt.md](../implementation-qt.md#shaders) — `qsb` and the QML bridge.
