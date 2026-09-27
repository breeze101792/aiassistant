# UI Tokens

The single source of every color, size, and duration in the orb. Implemented as
the QML singleton `theme/Theme.qml` (`pragma Singleton`, registered in
`main()` via `qmlRegisterSingletonType`).

**No component may hard-code a value.** If a value is not here, add it here
first. The one exception is a shader constant that is not addressable from QML
(see [components/orb.md](components/orb.md)).

**Placeholder convention.** A value marked **PLACEHOLDER** is tunable and not
yet validated on target. The suggested range and unit follow in parentheses.
Everything unmarked is part of the design contract and should be implemented as
written.

Units: `dp` = device-independent pixels (QML `Item` units, points on macOS).
`ms` = milliseconds. `s` = seconds. `Hz` = cycles per second.

Design language: **dark ambient**. The window is near-black; the orb is the only
light source. Contrast comes from the orb, not from the chrome. Chrome is quiet
and recedes.

---

## How tokens are referenced

QML:

```qml
import "theme"

Rectangle {
    color: Theme.colorSurface
    radius: Theme.radiusLg
    implicitHeight: Theme.space8
    Behavior on color { ColorAnimation { duration: Theme.durStateFade } }
}
```

Shaders receive tokens as uniforms; a token may not be read from within GLSL.
See [components/orb.md § Uniforms](components/orb.md#uniforms).

---

## Color — chrome

| Token | Hex | Use |
| --- | --- | --- |
| `Theme.colorBg` | `#0A0C10` | Window base; the dark field behind everything |
| `Theme.colorSurface` | `#11151C` | Panel background |
| `Theme.colorSurfaceRaised` | `#171C25` | Transcript rows, cards, composer field |
| `Theme.colorSurfaceHover` | `#1E2531` | Hover state of an interactive surface |
| `Theme.colorSurfaceActive` | `#232B39` | Pressed / selected surface |
| `Theme.colorBorder` | `#232A37` | Hairline separators, 1 dp |
| `Theme.colorBorderStrong` | `#333C4D` | Input outlines, emphasis borders |
| `Theme.colorScrim` | `#CC0A0C10` | 80 % scrim behind transient overlays |

## Color — text and iconography

| Token | Hex | Use | Contrast on `colorSurface` |
| --- | --- | --- | --- |
| `Theme.colorTextPrimary` | `#E6EAF2` | Transcript body, headings | 15.2:1 (16.2:1 on `colorBg`) |
| `Theme.colorTextSecondary` | `#98A2B3` | Labels, control text | 7.1:1 |
| `Theme.colorTextMuted` | `#7C8698` | Timestamps, metadata | 5.0:1 |

Accent `#4CC2FF` is 9.1:1, danger `#F87171` is 6.6:1, warning `#FBBF24` is 11.0:1,
and success `#34D399` is 9.5:1 against `colorSurface`. All text and icon tokens
clear WCAG AA; the target level is in [accessibility.md](accessibility.md#contrast).

Contrast targets and the WCAG clause are in
[accessibility.md](accessibility.md#contrast). `colorTextMuted` is the *lowest*
text token and still passes AA for normal text; nothing dimmer may carry text.

## Color — accent and feedback

| Token | Hex | Use |
| --- | --- | --- |
| `Theme.colorAccent` | `#4CC2FF` | Primary action (send, active toggle) |
| `Theme.colorAccentHover` | `#6FD0FF` | Hover of an accent control |
| `Theme.colorAccentPressed` | `#2FA8E8` | Pressed accent control |
| `Theme.colorFocus` | `#8BD5FF` | Keyboard focus ring (2 dp, see [accessibility.md](accessibility.md#focus-ring)) |
| `Theme.colorDanger` | `#F87171` | Destructive action, error text |
| `Theme.colorDangerHover` | `#FCA5A5` | Hover of a destructive control |
| `Theme.colorWarning` | `#FBBF24` | Backend degraded, non-fatal warning |
| `Theme.colorSuccess` | `#34D399` | Connected, ready, healthy |

## Color — orb states

The orb's hue channel. One token per state, plus an `*Alt` companion used as the
outer stop of the body gradient (the body is a two-stop radial gradient from
`state<Name>Alt` at the rim to `state<Name>` at the core). State meanings and
ring forms: [orb-states.md](orb-states.md).

| Token | Hex | State | Rel. luminance |
| --- | --- | --- | --- |
| `Theme.stateConnecting` | `#1E4A73` | `connecting` (orb-local) | 0.064 |
| `Theme.stateConnectingAlt` | `#2E5C8A` | `connecting` rim | 0.101 |
| `Theme.stateMuted` | `#4B5563` | `muted` | 0.089 |
| `Theme.stateMutedAlt` | `#6B7280` | `muted` rim | 0.167 |
| `Theme.stateIdle` | `#3E6480` | `idle` | 0.117 |
| `Theme.stateIdleAlt` | `#5B87A6` | `idle` rim | 0.223 |
| `Theme.stateBackendDown` | `#B45309` | `backend-down` overlay | 0.159 |
| `Theme.stateBackendDownAlt` | `#D97706` | `backend-down` rim | 0.280 |
| `Theme.stateThinking` | `#9B7BF0` | `thinking` | 0.274 |
| `Theme.stateThinkingAlt` | `#B9A0FA` | `thinking` rim | 0.424 |
| `Theme.stateError` | `#F87171` | `error` overlay | 0.330 |
| `Theme.stateErrorAlt` | `#FCA5A5` | `error` rim | 0.503 |
| `Theme.stateTranscribing` | `#38BDF8` | `transcribing` | 0.440 |
| `Theme.stateTranscribingAlt` | `#6DD3FA` | `transcribing` rim | 0.567 |
| `Theme.stateListening` | `#2DD4A7` | `listening` | 0.504 |
| `Theme.stateListeningAlt` | `#5CE8C4` | `listening` rim | 0.640 |
| `Theme.stateSpeaking` | `#FBBF24` | `speaking` | 0.579 |
| `Theme.stateSpeakingAlt` | `#FCD34D` | `speaking` rim | 0.678 |

Luminance is WCAG relative luminance of the body color. The ordering is
deliberate: quiet states dim, active states bright. The grayscale
distinguishability check (including the two closest pairs) is in
[orb-states.md § Grayscale check](orb-states.md#grayscale-check).

---

## Spacing

A 4 dp base scale. Use the named step, never a raw number.

| Token | Value | Typical use |
| --- | --- | --- |
| `Theme.space0` | `0 dp` | Reset |
| `Theme.space1` | `4 dp` | Icon-to-label, tight pairs |
| `Theme.space2` | `8 dp` | Inside a control |
| `Theme.space3` | `12 dp` | Between related rows |
| `Theme.space4` | `16 dp` | Panel padding, row padding |
| `Theme.space5` | `24 dp` | Between zones |
| `Theme.space6` | `32 dp` | Panel outer margin |
| `Theme.space7` | `48 dp` | Empty-state breathing room |
| `Theme.space8` | `64 dp` | Hero spacing (rare) |

## Radii

| Token | Value | Use |
| --- | --- | --- |
| `Theme.radiusSm` | `6 dp` | Badges, small chips |
| `Theme.radiusMd` | `10 dp` | Buttons, input fields |
| `Theme.radiusLg` | `16 dp` | Transcript rows, cards |
| `Theme.radiusXl` | `24 dp` | Expanded panel, opaque fallback window |
| `Theme.radiusPill` | `999 dp` | Pills, the composer field |
| `Theme.orbRadiusRatio` | `0.5` | The orb body is a circle: radius = size × ratio |

## Typography

Two families plus a mono face for machine text. All are system stacks; no font is
bundled, so the orb stays dependency-free and starts instantly. Bundling Inter
is an optional polish and does not change these tokens.

| Token | Value |
| --- | --- |
| `Theme.fontFamilyDisplay` | `"Inter", "SF Pro Display", "Noto Sans", system-ui, sans-serif` |
| `Theme.fontFamilyBody` | `"Inter", "SF Pro Text", "Noto Sans", system-ui, sans-serif` |
| `Theme.fontFamilyMono` | `"JetBrains Mono", "SF Mono", "DejaVu Sans Mono", monospace` |

Type scale. `size/lineHeight` in dp.

| Token | Size / line | Weight | Family | Use |
| --- | --- | --- | --- | --- |
| `Theme.typeDisplay` | `20 / 28` | 600 | Display | Panel title, identity name |
| `Theme.typeTitle` | `16 / 24` | 600 | Display | Section titles |
| `Theme.typeBody` | `14 / 22` | 400 | Body | Transcript text, input text |
| `Theme.typeLabel` | `12 / 16` | 500 | Body | Control labels, badges |
| `Theme.typeCaption` | `11 / 16` | 400 | Body | Timestamps, hints |
| `Theme.typeMono` | `12 / 20` | 400 | Mono | Tool-call rows, IDs, usage |

Weights: `Theme.weightRegular` 400 · `Theme.weightMedium` 500 ·
`Theme.weightSemibold` 600.

## Motion

Durations.

| Token | Value | Use |
| --- | --- | --- |
| `Theme.durInstant` | `80 ms` | Press feedback, toggle snap |
| `Theme.durFast` | `140 ms` | Hover, small reveals |
| `Theme.durBase` | `220 ms` | Panel expand/collapse, row insert |
| `Theme.durSlow` | `420 ms` | Window mode morph |
| `Theme.durStateFade` | `320 ms` | Orb hue crossfade between states |
| `Theme.durAmbient` | `1200 ms` | Idle breath reference period (see states) |

Easing. QML name first, CSS equivalent second.

| Token | QML | CSS cubic-bezier |
| --- | --- | --- |
| `Theme.easeLinear` | `Easing.Linear` | `cubic-bezier(0,0,1,1)` |
| `Theme.easeOutCubic` | `Easing.OutCubic` | `cubic-bezier(0.215,0.61,0.355,1)` |
| `Theme.easeOutQuad` | `Easing.OutQuad` | `cubic-bezier(0.25,0.46,0.45,0.94)` |
| `Theme.easeInOutQuad` | `Easing.InOutQuad` | `cubic-bezier(0.455,0.03,0.515,0.955)` |
| `Theme.easeAmbient` | `Easing.InOutSine` | `cubic-bezier(0.445,0.05,0.55,0.95)` |

## Geometry and window sizing

| Token | Value | Use |
| --- | --- | --- |
| `Theme.orbSizeCompact` | `112 dp` **PLACEHOLDER** (88–160) | Orb diameter in compact mode |
| `Theme.orbSizeExpanded` | `64 dp` **PLACEHOLDER** (48–88) | Orb diameter in the expanded header |
| `Theme.orbFieldRatio` | `1.65` **PLACEHOLDER** (1.2–2.0) | Field (halo) diameter ÷ orb diameter |
| `Theme.orbRingRatio` | `0.44` | Ring radius ÷ orb diameter |
| `Theme.orbCoreRatio` | `0.28` **PLACEHOLDER** (0.18–0.40) | Core diameter ÷ orb diameter at rest |
| `Theme.windowCompactSize` | `112 dp` **PLACEHOLDER** (88–160) | Compact window width = height |
| `Theme.windowExpandedWidth` | `420 dp` **PLACEHOLDER** (360–520) | Expanded panel width |
| `Theme.windowExpandedHeight` | `560 dp` **PLACEHOLDER** (min 420–720) | Expanded panel height |
| `Theme.windowRadiusOpaque` | `Theme.radiusXl` | Radius of the opaque Wayland-fallback window |

## Hit targets

WCAG 2.2 SC 2.5.8 Target Size (Minimum) is 24×24 dp. Design larger.

| Token | Value | Use |
| --- | --- | --- |
| `Theme.hitMin` | `24 dp` | Absolute floor; never place a target smaller |
| `Theme.hitIcon` | `32 dp` | Icon buttons (mute, stop, transcript, settings) |
| `Theme.hitPrimary` | `44 dp` | The orb's compact hit area, the mic-hold button |
| `Theme.hitComposer` | `40 dp` | Composer text field height (full-width, so target is large) |

## Elevation and glow

Shadows are used only on the expanded panel and transient overlays. The orb uses
*glow*, not shadow.

| Token | Value | Use |
| --- | --- | --- |
| `Theme.elevPanel` | `0 8 32 0 #00000099` | Expanded panel drop shadow |
| `Theme.elevOverlay` | `0 4 16 0 #000000CC` | Banner, context menu |
| `Theme.orbGlowBase` | `0.35` **PLACEHOLDER** (0.2–0.5) | Field opacity at rest |
| `Theme.orbGlowLevelAdd` | `0.45` **PLACEHOLDER** (0.3–0.6) | Field opacity added at full level |
| `Theme.orbCoreGlowAdd` | `0.6` **PLACEHOLDER** (0.4–0.8) | Core brightness added at full level |

---

## Related

- [orb-states.md](orb-states.md) — how tokens encode state.
- [audio-reactivity.md](audio-reactivity.md) — level smoothing that feeds the orb.
- [accessibility.md](accessibility.md) — contrast ratios behind the text tokens.
- [components/orb.md](components/orb.md) — token → shader uniform mapping.
