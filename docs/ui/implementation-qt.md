# Implementation — Qt / QML

How the design maps onto Qt Quick via PySide6. This is guidance for the
implementer, not code to copy; the source of truth for behavior is the other
files in this folder.

Stack decision: [ADR-0013](../architecture/decisions/ADR-0013-pyside6-orb.md).
Process model: separate process, Qt loop only, no asyncio
([MOD-0008](../architecture/modules/orb.md)).

## Qt modules used

| Module | PySide6 import | Use | Notes |
| --- | --- | --- | --- |
| QtCore | `PySide6.QtCore` | Objects, properties, signals, timers, geometry | — |
| QtGui | `PySide6.QtGui` | `QGuiApplication`, palette, screen info, `QSurfaceFormat` | No `QApplication`/widgets needed |
| QtQml | `PySide6.QtQml` | `QQmlApplicationEngine`, singleton registration | — |
| QtQuick | `PySide6.QtQuick` | Scene graph, items, `ShaderEffect`, `FrameAnimation` | The render path |
| QtQuick.Controls | `PySide6.QtQuickControls2` | Buttons, fields, popups, menus | Use the **Basic** style; see below |
| QtQuick.Particles | `PySide6.QtQuickParticles` | Motes layer ([components/orb.md](components/orb.md#layer-stack)) | Optional; omitted in fallback |
| QtQuick.Shapes | `PySide6.QtQuickShapes` | Vector icons if not using a font | Optional |
| QtWebSockets | `PySide6.QtWebSockets` | `QWebSocket` client | The only transport |
| QtGraphicalEffects | `PySide6.Qt5Compat.GraphicalEffects` | `RadialGradient` for the shader fallback | Qt6 moved it to `Qt5Compat`; avoid on the main path |

Explicitly **not** used: `QtWidgets` (no widget stack), `QtNetwork` HTTP,
`QtMultimedia` (the orb never touches audio — it displays `voice.level` only).

**Style:** call `QQuickStyle.setStyle("Basic")` before loading QML, or set
`QT_QUICK_CONTROLS_STYLE=Basic`. The platform style would fight the design and
add native look-and-feel the design does not want. All visual styling comes from
[Theme](tokens.md).

## Application skeleton

| Step | Call | Notes |
| --- | --- | --- |
| 1 | `QGuiApplication(sys.argv)` | A GUI app, but no widgets |
| 2 | `QQuickStyle.setStyle("Basic")` | Before the engine |
| 3 | Set `Qt.AA_UseHighDpiPixmaps` / high-DPI policy | Crisp on Retina |
| 4 | `qmlRegisterSingletonType` for `Theme` | The token singleton |
| 5 | Create `BridgeClient`, expose it to QML | Context property or a registered type |
| 6 | `QQmlApplicationEngine` + `load("orb/main.qml")` | — |
| 7 | `app.exec()` | Qt loop only; no `qasync`, no asyncio |

On `ERR-ORB-NO-DISPLAY` (no platform plugin / no display), exit non-zero so the
assistant stays in console mode ([MOD-0008 § ERRORS](../architecture/modules/orb.md#errors)).

## Theme singleton

`orb/theme/Theme.qml` with `pragma Singleton`, registered in step 4:

```qml
pragma Singleton
import QtQuick

QtObject {
    // color
    readonly property color colorBg: "#0A0C10"
    readonly property color stateIdle: "#3E6480"
    // spacing
    readonly property int space4: 16
    // motion
    readonly property int durStateFade: 320
    readonly property int easeOutCubic: Easing.OutCubic
    // ... every token from tokens.md
}
```

Registration:

```python
from PySide6.QtQml import qmlRegisterSingletonType
from PySide6.QtCore import QUrl

qmlRegisterSingletonType(QUrl.fromLocalFile("orb/theme/Theme.qml"), "Theme", 1, 0, "Theme")
```

`tokens.md` is the manifest; every property there must exist here with the same
name. A test can diff the two lists.

## Shaders

Qt 6's `ShaderEffect` consumes **QSB** (Qt Shader Baker) files. Runtime GLSL
compilation is not supported and must not be attempted. The `.qsb` is built
ahead of time and shipped as a resource.

### Build

```
qsb --glsl "100 es,120,150" --hlsl 50 --msl 12 \
    -o orb.frag.qsb orb.frag
```

| Flag | Meaning |
| --- | --- |
| `--glsl "100 es,120,150"` | GLSL ES 1.00, GLSL 1.20, GLSL 1.50 for OpenGL/GLES |
| `--hlsl 50` | Direct3D (not a target OS, but harmless) |
| `--msl 12` | Metal on macOS |
| Output | `orb.frag.qsb` |
| Build step | A script in `scripts/` or the packaging step; **never** at runtime |

Then:

```qml
ShaderEffect {
    fragmentShader: "orb.frag.qsb"
    property real uLevel: 0.0
    // ...
}
```

### Uniform plumbing

| Step | Detail |
| --- | --- |
| Declare | Each uniform used by the fragment shader is declared on the `ShaderEffect` as a QML `property` with the **same name** |
| Source | QML sets the property from the state machine and the smoothed level |
| Vertex stage | **Caution:** Qt 6's `ShaderEffect` reflects custom uniforms from the vertex stage. Declare each custom uniform in the vertex shader as well (or in a shared `shaders/` include) so Qt creates the binding. Verify against the Qt 6 `ShaderEffect` docs for the exact Qt version in use |
| Frequency | Only `uLevel`, `uBodyScale`, `uRingPhase`, `iTime`, `uGlow`, `uAlpha` change per frame; hue pair changes per state |
| Cost | A property write that exceeds a threshold may force a node rebuild; keep per-frame writes to plain real/int uniforms and avoid changing types |

The shader itself: a single fragment shader computing field, ring, body, and
core from `iResolution`, `iTime`, and the uniforms in
[components/orb.md § Uniforms](components/orb.md#uniforms). No texture inputs, no
`ShaderEffectSource` on the hot path.

## How `voice.level` reaches a uniform

The chain, end to end:

```
voice/ RMS (20 ms frames)
  └─ voice.level  (≤ 20 Hz, {level, source, ts})
       └─ bus WebSocket → QWebSocket frame
            └─ BridgeClient.frameReceived (Python slot, Qt loop)
                 ├─ parse JSON
                 └─ emit levelChanged(level: float, source: str)
                      └─ QML connection updates BridgeModel.rawLevel
                           └─ LevelSmoother (QML or Python) applies
                              gate → gain → tanh → gamma → attack/decay
                                └─ Orb's uLevel / uGlow / uBodyScale
```

Key points:

| Point | Rule |
| --- | --- |
| Arrives on the Qt loop | `QWebSocket` emits on the thread that owns it; the orb's socket lives on the main (GUI) thread, so no cross-thread hop |
| Coalescing | Already done at the publisher ([IF-0004](../contracts/protocols.md#if-0004-orb-bridge-api)); the orb does not re-coalesce |
| Smoothing | Where it lives is an implementation choice: a small QML function or a Python `QObject`. It must be O(1) and allocation-free ([audio-reactivity.md](audio-reactivity.md#signal-path)) |
| Latest-wins | A newer sample replaces an unprocessed older one; never queue samples |
| No re-layout | Updating the level must not trigger `ListModel` changes, text re-layout, or item creation |
| Source routing | Apply the `source` gate before smoothing ([audio-reactivity.md](audio-reactivity.md#source-routing)) |
| Reduced motion | When `Theme.reducedMotion`, still update `uLevel` but map it only to a small scale, and freeze `iTime` |

A per-frame `Behavior` is **not** used for the level; the smoothing is explicit in
code so its timing is deterministic and matches the parameter table.

## QML WebSocket event bridge

The bridge is best implemented in Python (`bridge_client.py`, testable) and
exposed to QML as one object with typed signals. A QML-native `WebSocket` type
also exists, but keeping JSON parsing and reconnect in Python keeps the QML layer
view-only and matches the module layout
([orb.md § Internal components](../architecture/modules/orb.md#internal-components)).

`orb/bridge_client.py` (shape, not final code):

```python
from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtWebSockets import QWebSocket
import json

SUBSCRIBE = [
    "voice.state", "voice.level", "agent.delta", "agent.final",
    "agent.turn.error", "status.assistant.ready", "status.harness",
]

class BridgeClient(QObject):
    stateChanged   = Signal(str)          # voice.state
    levelChanged   = Signal(float, str)   # voice.level, source
    deltaReceived  = Signal(str, str, int)  # kind, text, index
    finalReceived  = Signal(str, dict)
    turnError      = Signal(str, str)     # message, class
    harnessChanged = Signal(str, str)     # harness, model
    ready          = Signal()
    socketState    = Signal(str)          # connecting|open|closed

    def __init__(self, url: str, token: str = ""):
        super().__init__()
        self._ws = QWebSocket()
        self._ws.textMessageReceived.connect(self._on_text)
        self._ws.connected.connect(self._on_open)
        self._ws.disconnected.connect(self._on_close)
        self._url, self._token = QUrl(url), token

    def connect_bus(self):
        self.socketState.emit("connecting")
        self._ws.open(self._url)

    @Slot()
    def _on_open(self):
        if self._token:
            self._send({"token": self._token})
        self._send({"action": "register", "module_name": "orb", "capabilities": {}})
        for topic in SUBSCRIBE:
            self._send({"action": "subscribe", "topic": topic})
        self.socketState.emit("open")

    @Slot(str)
    def _on_text(self, raw: str):
        try:
            msg = json.loads(raw)
        except ValueError:
            return                       # malformed frame is ignored, not fatal
        topic, payload = msg.get("topic"), msg.get("payload", {})
        if topic == "voice.state":
            self.stateChanged.emit(payload["state"])
        elif topic == "voice.level":
            self.levelChanged.emit(float(payload["level"]), payload["source"])
        elif topic == "agent.delta":
            self.deltaReceived.emit(payload["kind"], payload["text"], int(payload["index"]))
        elif topic == "agent.final":
            self.finalReceived.emit(payload["text"], payload.get("usage") or {})
        elif topic == "agent.turn.error":
            self.turnError.emit(payload["message"], payload["class"])
        elif topic == "status.harness":
            self.harnessChanged.emit(payload["harness"], payload["model"])
        elif topic == "status.assistant.ready":
            self.ready.emit()

    @Slot()
    def _on_close(self):
        self.socketState.emit("closed")  # orchestrator schedules reconnect w/ backoff

    def publish(self, topic: str, payload: dict):
        self._send({"action": "publish", "topic": topic, "payload": payload})

    def _send(self, obj: dict):
        self._ws.sendTextMessage(json.dumps(obj))
```

QML consumes it through the exposed object and a thin view-model — no parsing in
QML:

```qml
Connections {
    target: Bridge     // context property

    function onStateChanged(state) { OrbModel.state = state }
    function onLevelChanged(level, source) { LevelSmoother.push(level, source) }
    function onDeltaReceived(kind, text, index) { TranscriptModel.appendDelta(kind, text, index) }
    function onFinalReceived(text, usage) { TranscriptModel.settle(text, usage) }
    function onTurnError(message, cls) { TranscriptModel.appendError(message, cls) }
    function onHarnessChanged(harness, model) { OrbModel.harness = harness; OrbModel.model = model }
    function onSocketState(s) { OrbModel.bridge = s }   // "connecting" drives the orb state
}
```

Rules the example enforces:

| Rule | Where |
| --- | --- |
| Malformed frame is ignored, not fatal | `_on_text` `except ValueError` ([IF-0001](../contracts/protocols.md#if-0001-bus-websocket-bridge-protocol)) |
| Deltas are fragments, keyed by `index` | `deltaReceived` |
| `agent.final` is authoritative | `finalReceived` → `settle` |
| State strings are passthrough | The orb maps them; it never derives state |
| Reconnect + re-subscribe + snapshot | `_on_close` signals the orchestrator; the client re-registers and re-subscribes, and gap detection lives in the transcript model ([api.md](../contracts/api.md#reconnect-and-resync)) |

## Window flags and transparency

| Goal | Approach |
| --- | --- |
| Frameless | `flags: Qt.FramelessWindowHint \| Qt.Window` on the root `Window` |
| Transparent | `color: "transparent"` and `flags: ... \| Qt.WA_TranslucentBackground` (set on the `QWindow`) |
| Always-on-top | Add `Qt.WindowStaysOnTopHint` only when `display.always_on_top` |
| No focus steal | `Qt.WindowDoesNotAcceptFocus` while idle; `show()` without `activateWindow()` ([layout.md](layout.md#focus-policy-detail)) |
| Drag | `Window.startSystemMove()` on press in the orb/header ([interactions.md](interactions.md#drag)) |
| Platform detect | `QGuiApplication.platformName()`; Wayland → opaque fallback ([layout.md](layout.md#wayland-degradation)) |

Setting window flags after `show()` can recreate the native window and flicker;
set them before the first `show()`, and when `always_on_top` changes at runtime,
accept one flicker or document that it applies on next launch.

## Performance cautions

Ordered by how often they cause an always-on window to be expensive:

| Caution | Why | Do instead |
| --- | --- | --- |
| `ShaderEffectSource` chains | Each is a render-to-texture per frame | One `ShaderEffect`, no intermediate textures |
| Binding-heavy per-frame JS | Every property read re-evaluates bindings; JS in a binding is a loop hazard | Compute the level in one place; assign plain properties |
| A `Timer` per layer | Many wakeups, no vsync alignment | One clock; see [audio-reactivity.md](audio-reactivity.md#animation-clock-and-frame-rate) |
| 60 Hz at idle | Burns battery for an invisible difference | Idle at `12 Hz`; suspend when hidden |
| `ListModel` append per delta with new rows | Item churn | Mutate the current row's text; append a row only per turn |
| Text re-layout per frame | The transcript is the expensive item | Level never touches text; state label changes per state |
| `console.log` in bindings | Serializes every frame under debug | Remove; use a logging category, gated |
| QML `Timer` while occluded | Fires with nothing to draw | Qt's surface visibility can stop the render loop; also stop timers on `visibilityChanged` |
| Particle system left running | Continuous allocation | Motes only in `thinking`/tool-call, then `Emitter.enabled = false` |
| Large `Canvas` repaints | CPU raster | Prefer `ShaderEffect` or `Shape`; no `Canvas` on the hot path |
| Recreating the native window | Flag changes after `show()` | Set flags before `show()` |

Budget and targets: [audio-reactivity.md § Performance budget](audio-reactivity.md#performance-budget).

## Resource packaging

| Asset | How |
| --- | --- |
| `.qml` files | Qt resource system (`pyside6-rcc`) or plain files next to the package |
| `.qsb` shaders | Resource; built by a script, committed or built in CI |
| Icons | An icon font, or SVG via `Shape`/`Image`; no external downloads |
| No network assets | REQ-ORB-001: the orb loads nothing from the network |

`pyside6-deploy` (Nuitka) bundles Python + Qt for both OSes
([build.md](../operations/build.md)); the `.qsb` and QML resources ship inside
the bundle. macOS signing/notarization is separate work
([ADR-0013](../architecture/decisions/ADR-0013-pyside6-orb.md)).

## Where Flutter would differ

Flutter was the runner-up ([ui-stack.md](../research/ui-stack.md)). If the orb
were ever rewritten in Flutter, the design survives — it is tokens, states, and
motion — but the implementation differs:

| Concern | Qt Quick / QML (chosen) | Flutter |
| --- | --- | --- |
| Language | Python + QML; one toolchain with the host | Dart + Flutter SDK; a second toolchain |
| Shader | GLSL → `qsb`; `ShaderEffect` | GLSL via `FragmentProgram` + `CustomPainter`; no `qsb`, compiled by the Flutter tool |
| Level to shader | QML property → uniform | `uniforms:` on `Shader` from a `Listenable`/`ValueNotifier` |
| WebSocket | `QWebSocket` | `dart:io` `WebSocket` / `web_socket_channel` |
| Always-on-top / transparency | Qt window flags; compositor-dependent | `window_manager` plugin; same compositor caveats on Linux |
| Frameless drag | `startSystemMove()` | `window_manager.startDragging()` |
| Accessibility | `Accessible.*`; macOS QML bridge is uneven | `Semantics` widget; generally more consistent, still per-platform work |
| State rebuild | Property bindings; retained scene graph | Widget rebuilds; needs care to avoid full-tree rebuilds at 20 Hz |
| Packaging | `pyside6-deploy` (Nuitka) | `flutter build macos` / `linux` |
| Hot reload | None (QML can be live-reloaded in dev) | Yes, strong developer loop |

The reason Qt Quick wins is the **one-toolchain, Python-host** argument
([ADR-0013](../architecture/decisions/ADR-0013-pyside6-orb.md)), not a rendering
limitation. Nothing in this design depends on QML-specific behavior except the
window-flag and shader-plumbing mechanics documented above, which have direct
Flutter equivalents.

## Related

- [components/orb.md](components/orb.md) — uniforms and the shader.
- [tokens.md](tokens.md) — the Theme singleton's contents.
- [audio-reactivity.md](audio-reactivity.md) — the level pipeline.
- [layout.md](layout.md) — window flags and Wayland degradation.
- [ADR-0013](../architecture/decisions/ADR-0013-pyside6-orb.md) — the stack decision.
