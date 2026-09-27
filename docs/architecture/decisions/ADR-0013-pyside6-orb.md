# ADR-0013 — PySide6 / Qt Quick for the orb

**Status:** accepted · **Date:** 2026-09-26

## Decision

Build the native orb with **Qt Quick / QML via PySide6**, running as a separate
process and connecting to the bus WebSocket with `QWebSocket`.

## Why

The requirement is a native window on **both macOS and Linux** with a
GPU-animated, audio-reactive orb. That combination is the constraint that decides
it.

| Criterion | PySide6 / Qt Quick |
| --- | --- |
| Rendering | Native GPU scene graph — **not** a system webview |
| macOS + Linux | First-class on both |
| Shader orb | `ShaderEffect` with GLSL compiled to SPIR-V (`.qsb`) |
| Audio reactivity | Shader uniforms updated per frame |
| Always-on-top frameless | `Qt.FramelessWindowHint` + `Qt.WindowStaysOnTopHint` |
| WebSocket | `QWebSocket` ships with PySide6 |
| Toolchain | pip only — no second language for a Python team |
| Packaging | `pyside6-deploy` (Nuitka) on both OSes |

The decisive factor is the last-but-one row: the assistant is Python, and
PySide6 keeps one language and one dependency manager. Flutter would add Dart and
a second toolchain; a webview shell would violate "native".

## Ruled out

| Option | Why |
| --- | --- |
| **SwiftUI** | macOS-only — fails the macOS + Linux requirement outright |
| Tauri v2 | Renders a system webview; not genuinely native |
| Electron | Same, plus a large runtime |
| GTK4 / libadwaita | macOS support is second-class |
| SDL2 / SFML / raylib | Lower-level; needs a GUI layer and binding maintenance |
| Flutter desktop | Native rendering and a real contender; rejected on second-toolchain cost |

## Consequences

- **Process model:** the orb is a separate process running only the Qt loop.
  `QWebSocket` delivers messages as Qt signals, so there is no asyncio and no
  `qasync` inside the orb. A Qt crash cannot take the assistant down. See
  [orb module](../../architecture/modules/orb.md).
- **Licensing:** PySide6 is LGPLv3. Distribution requires dynamic linking, a
  license notice, and relink capability. Acceptable; recorded in
  `operations/deploy.md`.
- **Platform caveats are real and must be tested, not assumed:** Wayland does not
  reliably support always-on-top or client positioning; frameless transparency
  depends on the compositor; global hotkeys need native APIs and are a separate
  scoped item; macOS notarization is separate work.
- The design degrades gracefully: an opaque rounded window where transparency is
  unavailable, and a plain QML state circle where shaders are unavailable.
