# MOD-0011 — `vision` and `messaging` (frozen)

Two renamed modules with no new features. Documented so the rename is
accountable and so nobody assumes they are dead.

> The old `canvas` module is not here: it is **deleted**, not frozen. Its
> disposition is at the end of this file and in
> [ADR-0003](../decisions/ADR-0003-delete-canvas.md).

## `vision` (was `eyes`)

**Purpose:** Capture a camera frame and optionally run a vision backend.

**Scope:** Renamed only. Backend stays `stub` by default. No new features
(REQ-PLAT-002, scope should-have).

| Aspect | Content |
| --- | --- |
| Depends on | `bus` topics, an optional camera backend |
| Provides | `capture()`, `analyze()` RPC, publishes `sensory.vision.frame` |
| Owns | The backend instance and the streaming flag |
| Must not do | Reason about frames, or speak them aloud |
| Errors | `ERR-VISION-NO-DEVICE`, `ERR-VISION-BACKEND-FAIL` |
| Concurrency | Capture runs on the loop; an `opencv` capture blocks it and must move to an executor if vision is ever unfrozen |
| Resources | One camera handle when a real backend is selected; none for `stub` |
| Verification | Backend selection and the stub path (T-1101) |

**Deliberately unchanged:** the vision frame path base64-encodes images onto the
bus. Wiring vision into agent turns is out of MVP scope.

## `messaging` (was `chat`)

**Purpose:** Bridge external messaging platforms to the bus.

**Scope:** Renamed only. Backend stays disabled by default
(`chat.backends: []`).

| Aspect | Content |
| --- | --- |
| Depends on | `bus` topics, an optional platform SDK |
| Provides | Message ingest to `user.input.text`, delivery of `agent.final` |
| Owns | The list of active backends |
| Must not do | Trust its input. Every inbound message is untrusted (see the threat model) |
| Errors | `ERR-MSG-BACKEND-FAIL` |
| Concurrency | One task per backend; delivery is fire-and-forget |
| Resources | One connection per enabled backend |
| Verification | Ingest and delivery with a fake backend (T-1102) |

**Security note:** a message from an external platform is **untrusted input**.
It reaches the agent as a `user.input.text` prompt and can invoke whatever tools
the sandbox allows. `messaging` is disabled by default
([threat model](../../security/threat-model.md)).

## What replaced `display` (was `canvas`)

The orb is the display. The canvas module is **deleted**, not renamed:

| Removed | Evidence |
| --- | --- |
| `backends/web.py` | Every method is `pass`; `start()` claims a server that does not exist |
| `backends/file.py` | Writes HTML/text wrappers to disk |
| `renderer.py` | A thin wrapper around image generation |
| `canvas.py` | Bus plumbing for the above |

Generated artifacts are written through `tools/file.write` to
`tools.artifacts_path`. See [ADR-0003](../decisions/ADR-0003-delete-canvas.md).
