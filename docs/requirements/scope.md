# Scope

The MVP line, and what is deliberately not in it.

## The MVP in one sentence

Refactor the bus-modular assistant into **`agent` / `voice` / `tools` / `vision`
/ `scheduler` / `messaging` / `console` / `orb` / `reasoning`**, make voice the
primary input and output, add a native orb window, and keep the agent harness
config-swappable behind an open seam — on **macOS and Linux**, with a console
fallback.

## Must-have

| Component | Why |
| --- | --- |
| `voice` (merges ears + mouth) | Requirements 1 and 7. One owner of the duplex device is what makes cancel possible. |
| `orb` (PySide6 / Qt Quick) | Requirement 2. The orb **is** the display. |
| `agent` + `agent/harness/native` | Requirement 3. The harness seam stays open for a future implementation. |
| `reasoning` (ollama, openai, streaming) | The native harness needs a provider with streaming. |
| `tools` | Tool use on the native path. |
| `console` | Headless fallback and the recovery path. |
| `bus` + `bridge` | The bus stays; the bridge is the orb's transport and it is currently broken. |
| `scheduler` | Kept: timed reminders are a real feature. |
| Config rename + legacy migration | The rename is a stated goal; silent breakage is not. |
| Docs set + `PLAN.md` | This deliverable. |

## Should-have

| Item | Note |
| --- | --- |
| `vision` | Renamed only. Backend stays `stub`; no new features. |
| `messaging` | Renamed only. Telegram backend stays disabled by default. |
| Semantic memory (embeddings recall) | Basic persistence is must-have; semantic recall sits behind `memory.semantic: false`. |
| Orb shader orb | A state-colored circle ships first; the shader is polish inside the same MVP. |
| OS-level sandbox for a future external harness | Documented as the next hardening step if one is ever added; not on the MVP path. |

## Out of scope

| Item | Why |
| --- | --- |
| Web UI / HTTP server | Explicitly unwanted. The canvas web backend was a dead stub. |
| `main_remote.py` and cross-machine module hosting | Never worked (wildcard subscribe unsupported, receive loop a comment). Replaced by `bridge/`. |
| Canvas module (file/web/gui output) | Dead. Artifacts are written through `tools/file.write`. |
| Voice barge-in (speak while it talks) | Needs acoustic echo cancellation. Half-duplex is the MVP; the FSM already models the transition. |
| Mobile / cross-platform beyond macOS + Linux | Not stated. |
| A second GUI toolchain (Flutter, Electron, Tauri) | PySide6 keeps one toolchain for a Python team. |

## MVP limitations — stated plainly

These are accepted, not oversights.

1. **Half-duplex audio.** The mic is gated while TTS plays. You cannot interrupt
   by speaking; you interrupt with the orb, a hotkey, or the console. An open
   mic plus speakers with no AEC hears the assistant's own voice and
   self-triggers. See [ADR-0011](../architecture/decisions/ADR-0011-half-duplex-first.md).
2. **Tools are not confined by the OS.** File tools are confined by the sandbox
   and `safe_paths`; network access and prompt injection are **not** contained.
   See [security/threat-model.md](../security/threat-model.md).
3. **No wake-word engine.** Wake detection reuses ASR hotword matching, which
   costs a continuously running ASR. A dedicated KWS engine is a future swap
   behind `WakeDetector` (REQ-WAKE-003).
4. **Embedding search is linear.** `_search_table` scans the whole table in
   Python. Fine for a personal transcript; noted for v2.

## Assumptions

Marked `[A]` in [requirements.md](requirements.md). The load-bearing ones:

- The user runs this on their own machines, as their own user. No multi-tenant
  trust boundary exists inside the process.
- `ptt` is a safe default posture; `open` and `wake` are opted into.
- One agent identity (`jarvis`) ships by default, with the schema supporting more.
