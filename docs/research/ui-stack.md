# Native Desktop UI Stack — Research

Comparison of native desktop UI stacks for an always-on-top, audio-reactive orb
on macOS **and** Linux. Documentation only; nothing was installed. Claims are
marked `[V]` verified against the cited source or `[U]` unverified.

Scope: the orb is a small, frameless, always-on-top, possibly transparent window
whose animation is driven at frame rate by an audio level/bands. It needs global
hotkeys, reliable window positioning, and packaging for both platforms. The
project already runs Python (`main.py`, `bus/`, `modules/`), so host-language fit
matters.

## Comparison

| Stack | Rendering model | macOS + Linux support | Audio-reactive fit | Packaging / distribution | Language / toolchain | License | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Qt Quick / QML (PySide6)** | Native GPU scene graph; retained node tree rendered via OpenGL/Vulkan/Metal/Direct3D. Qt Quick has `Canvas`, `ShaderEffect`, and a dedicated render thread. [V] | First-class: macOS 13+ (x86_64, arm64), Ubuntu 24.04 and Debian 11/12 (x86_64, arm64) are supported desktop platforms. [V] | Best fit: QML `NumberAnimation`, `ShaderEffectSource`, `Canvas`, and `QSG` nodes drive 60 fps GPU animation from Python-set properties. | `pyside6-deploy` wraps Nuitka; final artifact `.app` on macOS, `.bin` on Linux. [V] macOS signing/notarization is separate work [U]. | Python 3 + Qt 6 (PySide6); optional C++/QML. | LGPL (or Qt Commercial) per Qt for Python licenses page. [V] | **Recommended.** Native GPU, real macOS+Linux support, matches the existing Python host. |
| **Flutter desktop** | Own GPU renderer (Skia; Impeller default on iOS/Android since 3.27). Renders to a native window; not a system webview. [V] | Officially targets Windows, macOS, Linux desktop. [V] | Capable: `AnimationController` + `CustomPainter`/fragment shaders at 60 fps. | `flutter build macos` / `linux`; bundle `.app` / Linux bundle. | Dart + Flutter SDK. | BSD-3-Clause (Flutter). [V] | Strong animation, but adds Dart and a second runtime beside the Python host. |
| **Tauri v2** | System webview (WRY): WebView2 / WebKit / WebKitGTK. Frontend is HTML/CSS/JS; Rust backend. [V] | Desktop: macOS, Windows, Linux supported. [V] | Webview animation is fine for an orb; audio must be captured in Rust or JS, not Python. | Rust bundler → `.app`/`.dmg`, `.deb`/`.rpm`/AppImage. [V] | Rust + web frontend. | MIT OR Apache-2.0. [V] | Small binaries, but a webview and a Rust toolchain for a pure animation window is overkill. |
| **GTK4 / libadwaita** | Native GPU (GSK/Vulkan or GL). [V] | Linux first-class; macOS support exists but is explicitly secondary/third-party. [V] | Possible via `GtkGLArea`, but animating a smooth orb in GTK is awkward. | Bundle per distro; no single macOS story. | C (GTK) or Python via PyGObject; also Rust/Vala. | GTK LGPL-2.1; libadwaita LGPL-2.1. [V] | GNOME-idiomatic, but the macOS path is weak and it is a poor fit for the Python host. |
| **SDL2 / SFML / raylib (+ immediate GUI)** | Direct GPU surface; you draw the orb yourself each frame. [V] | All three build on macOS, Linux, Windows. [V] | Excellent raw frame-rate control, but you build window chrome, transparency, and hotkeys yourself. | Manual; no app-framework packaging. | C/C++ (SDL2, SFML, raylib); Python bindings exist. | zlib (SDL2, raylib); zlib/png (SFML). [V] | Best frame control, worst ergonomics for transparent always-on-top window management. |
| **Electron** | Bundled Chromium renderer (not system webview), plus Node. [V] | macOS and Linux supported. [V] | CSS/Canvas/WebGL animation is easy. | `electron-builder` → `.app`/`.dmg`, `.deb`/`.rpm`/AppImage. | Node.js + web frontend. | MIT (Electron). [U] | Heavy runtime for a small orb; the wrong weight class. |

## Recommendation

**Use Qt Quick / QML through PySide6.**

Reasoning:

1. **Platform support is real on both targets.** Qt lists macOS 13+ and Ubuntu
   24.04 / Debian 11–12 as supported desktop platforms with official binaries.
   GTK, by contrast, treats macOS as a secondary port. [V]
2. **Native GPU rendering with a retained scene graph** — the orb animation runs
   on the render thread, not through a browser. [V]
3. **It fits the existing Python host.** The project is Python-first; PySide6
   lets the orb import from the existing bus/modules instead of introducing a
   second language and IPC boundary.
4. **One toolchain, two platforms.** `pyside6-deploy` produces `.app` on macOS
   and `.bin` on Linux from the same project. [V]
5. **It is already the documented choice** in this project (`docs/README.md`
   names PySide6 / Qt Quick for the native orb).

The runner-up is Flutter desktop if the animation sophistication later outgrows
QML; it is the strongest cross-platform native-rendering alternative. Electron
and Tauri are rejected because they put a webview between the host and the orb.
SDL2/SFML/raylib are rejected because window management (transparency,
always-on-top, hotkeys) is manual work on every platform.

### SwiftUI was ruled out

SwiftUI is **macOS-only** and cannot run on Linux. [V] A single native orb that
ships on both targets cannot use it without writing a second Linux UI. It is
therefore out of scope regardless of its macOS advantages.

## Platform caveats

These apply to **every** stack and must be handled by the chosen one.

| Caveat | Detail | Flag |
| --- | --- | --- |
| Wayland always-on-top | On Wayland, compositors control stacking; an app cannot reliably position, move, focus, blur, or keep itself above other windows. Electron documents that on Wayland it is "generally not possible to programmatically resize windows after creation, or to position, move, focus, or blur windows without user input", and recommends running under Xwayland (`--ozone-platform=x11`) when these are required. [V] | [V] |
| Wayland global coordinates | Electron notes some position getters return `{x:0,y:0}` on Wayland because global coordinates are prohibited. The same compositor restriction affects Qt/GTK. [V] (Electron doc); Qt/GTK specifics [U] |
| Frameless transparency | Transparent frameless windows are compositor-dependent. Qt Quick supports `Qt.FramelessWindowHint` + `Qt.WA_TranslucentBackground`; Tauri documents `decorations: false` and transparent backgrounds per-platform. [V] (Qt/Tauri docs); exact Linux compositor behavior [U] |
| Global hotkeys | Need native APIs. Electron uses the `globalShortcut` module, which on Wayland binds through `org.freedesktop.portal.GlobalShortcuts` and may show a consent dialog; GNOME shows one the first time an app binds shortcuts. [V] | [V] |
| macOS packaging / notarization | `pyside6-deploy` produces a `.app` but code signing and notarization are additional, separate steps. [U] | [U] |
| Linux packaging | `pyside6-deploy` produces a `.bin`; shipping to users usually still needs a `.desktop` file and a bundle/AppImage/deb. [V] for the artifact; distribution wrapper [U] | [V]/[U] |

**Implication for the design:** the orb should degrade gracefully on Wayland and
prefer X11/Xwayland for always-on-top and positioning, or accept
compositor-mediated behavior. A global-hotkey backend must be selected per
platform (native event filter / portal), not assumed.

## Sources

- Qt Quick Scene Graph — `https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph.html`
- Qt supported platforms — `https://doc.qt.io/qt-6/supported-platforms.html`
- Qt for Python licenses — `https://doc.qt.io/qtforpython-6/licenses.html`
- `pyside6-deploy` — `https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html`
- Flutter desktop support — `https://docs.flutter.dev/platform-integration/desktop`
- Flutter Impeller — `https://raw.githubusercontent.com/flutter/website/main/sites/docs/src/content/perf/impeller.md`
- Flutter license — `https://raw.githubusercontent.com/flutter/flutter/master/LICENSE`
- Tauri architecture — `https://v2.tauri.app/concept/architecture/`
- Tauri window customization — `https://raw.githubusercontent.com/tauri-apps/tauri-docs/v2/src/content/docs/learn/window-customization.mdx`
- Tauri window API (`always_on_top`) — `https://raw.githubusercontent.com/tauri-apps/tauri/dev/crates/tauri/src/window/mod.rs`
- Electron BrowserWindow (Wayland notes, always-on-top, transparent) — `https://raw.githubusercontent.com/electron/electron/main/docs/api/browser-window.md`
- Electron globalShortcut (Wayland portal) — `https://raw.githubusercontent.com/electron/electron/main/docs/api/global-shortcut.md`
- GTK macOS install — `https://www.gtk.org/docs/installations/macos/`
- GTK license — `https://raw.githubusercontent.com/GNOME/gtk/main/COPYING`
- libadwaita license — `https://raw.githubusercontent.com/GNOME/libadwaita/main/COPYING`
- SDL license — `https://raw.githubusercontent.com/libsdl-org/SDL/main/LICENSE.txt`
- raylib license — `https://raw.githubusercontent.com/raysan5/raylib/master/LICENSE`
- SFML license — `https://www.sfml-dev.org/license.php`
