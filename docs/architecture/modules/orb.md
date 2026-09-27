# MOD-0008 — `orb`

**Purpose:** Render the ambient orb, the transcript, and the controls, and drive
the assistant from the UI.

**Must not do:** touch audio devices, reason, or import `agent/`. It speaks the
bridge protocol only.

**Dependencies:** PySide6 / Qt Quick · `bridge/` · [IF-0004](../../contracts/api.md).

**State it owns:** local view state (window mode, geometry, transcript model,
current animation state).

See [features/orb-ui.md](../../requirements/features/orb-ui.md) and
[docs/ui/](../../ui/README.md).

## PROVIDES

### `main() -> int`

Starts the Qt application. Returns a process exit code. No asyncio in this
process.

### Internal components

| Component | Responsibility |
| --- | --- |
| `bridge_client.py` | QWebSocket connection, subscribe, publish, reconnect |
| `Orb.qml` | The orb visual and its animation |
| `Transcript.qml` | Streaming transcript model and scrollback |
| `Composer.qml` | Text input and send |
| `Controls.qml` | Mute, stop, backend badge, settings, quit |
| `theme/Theme.qml` | Design tokens as a singleton |

## REQUIRES

- `bridge.connect`, `subscribe`, `publish`
- Topics: `voice.state`, `voice.level`, `agent.delta`, `agent.final`,
  `agent.turn.error`, `status.assistant.ready`, `status.harness`

## OWNS

Local view state only. It never derives state the assistant has published; it
displays what it receives.

## INVARIANTS

- No asyncio loop runs in this process.
- The orb process can crash and restart without affecting the assistant.
- Delta text is accumulated with the monotonic `index`; a gap triggers a resync
  request rather than a silent hole.

## ERRORS

| Code | Behavior |
| --- | --- |
| `ERR-ORB-BRIDGE-UNREACHABLE` | `connecting` state, retry with backoff |
| `ERR-ORB-SHADER` | Fall back to the QML state circle |
| `ERR-ORB-NO-DISPLAY` | Exit non-zero; the assistant stays in console mode |

## CONCURRENCY

Qt event loop only. `QWebSocket` signals marshal into it.

## RESOURCES

One process, one window, one shader (when used). The idle render cap is intended
to keep an always-on window cheap.

## Lifecycle and supervision

Previously unspecified, which would have become an implementation guess. Who owns
what:

| Question | Answer |
| --- | --- |
| Who spawns the orb? | `main.py`, as a child process, after `status.assistant.ready` is published, unless `display.mode` resolves to `console` (REQ-CONSOLE-004). `auto` resolves to the orb when a GUI is available, console otherwise |
| What is the command? | `sys.executable -m orb` — the same interpreter and venv, so PySide6 resolution matches |
| Is spawning synchronous? | No. It is fire-and-forget; a failure to spawn must not block the assistant |
| Who restarts it on crash? | `main.py`, bounded: max 3 restarts in 10 minutes with backoff `[1, 2, 5]s`, then it stops trying and logs a warning. This mirrors the pi child policy. |
| How is a crash detected? | By the child's exit code via the asyncio subprocess watcher |
| What if it cannot start at all? | The assistant continues in console mode and publishes `ERR-ORB-NO-DISPLAY`; this is the REQ-CONSOLE-001 fallback. It is not fatal. |
| Does the assistant wait for it? | No. The assistant is usable over the console immediately. |
| Who owns shutdown? | `main.py`, in the ordered `stop()`: terminate the orb, wait, then kill. Same policy as a remote client. |
| Can the orb run standalone? | Yes — `python -m orb` for development and for the design mockup workflow. It then registers as a client like any other. |
| Does the orb need a restart when config changes? | Only for restart-scoped keys. Runtime-scoped display keys are pushed over the bridge (see the reload policy in [schemas.md](../../contracts/schemas.md#reload-policy)). |

The orb holds no state the assistant needs. Killing it, crashing it, or never
starting it changes nothing except the UI.

## VERIFICATION

| Clause | Method | Test |
| --- | --- | --- |
| Window opens with no browser | manual, mac + linux | T-0201 |
| State follows bus events | host (fake bridge) | T-0202 |
| Delta appends incrementally | host | T-0203 |
| Interrupt publishes the command | host | T-0204 |
| Reconnect resyncs without duplicates | host | T-0205 |
| Reduced motion disables animation | manual, inspection | T-0206 |
| `display.mode` resolves to `none` suppresses the orb | host | T-0904 |
| A crash does not take down the assistant | host (kill child) | T-0207 |
