# Architecture Overview

How the system is built. Components, responsibilities, boundaries, dependency
direction, and the modularization decision.

## The shape

A single Python process hosts an in-process pub/sub bus and a fixed set of
modules. The native orb runs as a **separate process** and connects over a local
WebSocket. When the `pi` harness is selected, pi runs as a **child process**
speaking JSONL over stdin/stdout.

```mermaid
graph TD
    subgraph main["main process (asyncio)"]
        MAIN[main.py] --> BUS[bus/<br/>MessageBus + topics.py]
        BUS --> BRIDGE_SRV[bus/remote.py<br/>WS server :8765 loopback]
        AGENT[agent/<br/>loop, gate, memory, policy] -->|bus topics| BUS
        AGENT --> HARNESS[agent/harness/<br/>native | pi]
        HARNESS --> REASON[reasoning/<br/>ollama, openai]
        HARNESS -.->|spawn JSONL| PI[pi --mode rpc<br/>child process]
        PI -.->|its own tools| FS[workspace files]
        VOICE[voice/<br/>asr, tts, audio, wake] -->|bus topics| BUS
        TOOLS[tools/] --> BUS
        VISION[vision/] --> BUS
        MSG[messaging/] --> BUS
        CONSOLE[console/] --> BUS
        SCHED[scheduler/] --> BUS
    end
    subgraph orbproc["orb process (Qt loop only)"]
        ORB[orb/<br/>PySide6 QML] --> BCLIENT[bridge/<br/>WS client]
    end
    BRIDGE_SRV <-->|"register / subscribe / publish"| BCLIENT
```

Solid arrows are imports; dotted arrows are process boundaries. Every module
reaches every other module **only through bus topics**. `orb/` imports only
`bridge/`.

## Dependency direction

Must be acyclic. The layering:

```
bus/ (no dependencies)
  ↑
modules/base.py, bridge/
  ↑
reasoning/ (provider abstraction)
  ↑
agent/harness/ (native uses reasoning/; pi uses subprocess)
  ↑
agent/ (loop, policy, memory) → tools/, scheduler/, voice/, vision/, messaging/, console/
  ↑
main.py (composition root)
orb/ (separate process; depends only on bridge/)
```

Rules:

- A module may REQUIRE only another module's PROVIDES, never its internals.
- `bus/` depends on nothing.
- `agent/` never imports `voice/`; it communicates by topic.
- `orb/` never imports `agent/`; it speaks the bridge protocol.

## The modularization decision

Modules exist where a real trigger justifies the boundary. This system's
triggers are **portability**, **testability in isolation**, and **a real
duplication or ownership conflict** — not tidiness.

| Module | Trigger that justifies it |
| --- | --- |
| `bus` | Already exists and works; a real seam for remote modules, stub mode, and tests. Replacing it buys nothing. |
| `agent/harness` | Two real implementations must be interchangeable at config time. This is the core requirement. |
| `reasoning` | Multiple providers behind one streaming interface, and it must be testable without a network. |
| `voice` | One owner is required for the duplex audio device. Two owners produced two real bugs. |
| `tools` | Tools are dynamically discovered; the registry must be testable without the agent. |
| `orb` | A separate process is required so a GUI crash cannot take down the assistant, and so Qt and asyncio never share a loop. |
| `bridge` | Two out-of-process clients (orb, future modules) share one protocol implementation. |
| `console` | The headless fallback, and the fastest text debugging surface. |
| `vision`, `messaging`, `scheduler` | Real features that already exist; renamed, kept, and frozen. |

Rejected: **"one process, fewer modules"**. It would merge voice back into the
agent, which re-creates the mute-race defect, and put Qt in the asyncio process,
which couples two event loops. Both are named defects, not hypotheticals.

Rejected: **"split into services"**. There is one user, one machine, and no
scale requirement. Every extra process is a protocol to version and a failure
mode to handle (YAGNI).

## Boundaries

Two kinds, and the distinction matters:

| Kind | Location | Test |
| --- | --- | --- |
| **Module boundary** (internal) | `architecture/modules/` | Can we change both sides at once? Yes, both are our code. |
| **Contract** (external) | `contracts/` | The other side is not ours — pi, Qt, the OS audio stack. |

Applied here:

- **pi's RPC wire format** is a contract (`contracts/protocols.md`), because the
  other side is upstream pi. Our adapter's structure is a module boundary
  (`architecture/modules/pi-harness.md`).
- **Bus topics** are a contract between modules we own, but they are also the
  interface the orb subscribes to. The topic set is documented once in
  `contracts/protocols.md`.
- **The audio device** is a contract with the OS. Our capture/playback wrappers
  are module boundaries.

## Data flow: one voice turn

```
mic → VAD → ASR ──user.input.text──> agent/loop
                                        │
                                harness.run_turn()
                                        │
              ┌── agent.delta ──────────┤────────── agent.final
              v                          v
        orb transcript            voice/tts/chunker
        + orb animation                    │
                                    TTS → MP3 → PCM
                                           │
                                     playback callback → speaker
```

Raw audio never crosses the bus. Only state, transcripts, and level samples do.
See [ADR-0006](decisions/ADR-0006-rt-audio-event-plane.md).

## Real-time vs event plane

| Plane | Thread | Deadline | Carries |
| --- | --- | --- | --- |
| Real-time audio | Dedicated threads | 20 ms per frame | PCM frames, VAD verdicts, RMS, playback buffers |
| Event | asyncio | Soft | State, transcripts, deltas, errors |

The 20 ms deadline is why the audio plane cannot use `bus.publish`: it is a
synchronous dict fan-out (`bus/bus.py:44`) with no bounded latency guarantee.

## Composition root

`main.py` is the only place that knows every concrete class. It:

1. Loads config, applies precedence, migrates legacy keys.
2. Builds the `MessageBus`.
3. Starts the bridge server.
4. Instantiates modules from a spec table and calls `setup()`, then `start()`.
5. Handles signals and performs an ordered `stop()`.

Modules never construct each other.

## What was deliberately removed

Verified dead or actively harmful; see [REQ-STRUCT-004](../requirements/requirements.md).

| Removed | Evidence |
| --- | --- |
| `modules/canvas/` (5 files) | `backends/web.py:7-21` every method is `pass`; `start()` claims a server that does not exist. |
| `main_remote.py` | Wildcard subscribe (`:64`) unsupported by the bus; receive loop is a comment (`:76-77`). |
| `aiohttp` dependency | Never imported anywhere. |
| `utility` submodule entry | Gitlink deleted in commit `cf88cfd`; directory absent. |
| `brain/understand.py`, `brain/plan.py` | Not dead, but thin ceremony: English keyword intent feeds one clarification branch. See [ADR-0009](decisions/ADR-0009-collapse-thinking-stages.md). |

## Related

- [MOD contracts](modules/) — per-module PROVIDES/REQUIRES.
- [Data model](data-model.md) — entities and storage.
- [ADR log](decisions/) — decisions with rejected alternatives.
- [Contracts](../contracts/protocols.md) — the external wire.
