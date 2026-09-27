# AI Assistant — Design Documentation

The single entry point for this project's design docs. Read this first.

This doc set describes the **target** system: a refactor of the existing
bus-modular Python assistant into a voice-first assistant with a native orb UI
and a pluggable agent harness (native or pi). It was written before the first
line of implementation, per the project design playbook.

> **Implementation status (2026-09-27):** the refactor described here is
> implemented. `docs/` remains the design of record; `PLAN.md` records what was
> built and the two findings that changed it (live pi behavior, the audio
> segfault in tests).
>
> **Status legend**
> - `draft` — written, not yet reviewed
> - `reviewed` — passed `challenger`
> - `as-built` — reflects shipped code
> - `unverified` — a claim that no test or source confirms yet

## The doc set

| Doc | ID prefix | Status | Purpose |
| --- | --- | --- | --- |
| [requirements/requirements.md](requirements/requirements.md) | `REQ-*` | as-built | Numbered, testable requirements |
| [requirements/scope.md](requirements/scope.md) | — | as-built | Must / should / out-of-scope, the MVP line |
| [requirements/flows.md](requirements/flows.md) | — | as-built | Use cases: trigger, happy path, branches, failure |
| [requirements/features/](requirements/features/) | — | as-built | One file per feature |
| [architecture/overview.md](architecture/overview.md) | — | as-built | Components, boundaries, dependency direction |
| [architecture/modules/](architecture/modules/) | `MOD-0001`..`MOD-0011` | as-built | Per-module PROVIDES/REQUIRES contracts |
| [architecture/data-model.md](architecture/data-model.md) | — | as-built | Entities, storage, lifetime |
| [architecture/decisions/](architecture/decisions/) | `ADR-*` | as-built | Decision log: decision, why, rejected alternatives |
| [contracts/protocols.md](contracts/protocols.md) | `IF-*` | as-built | Bus topics, pi RPC, audio plane |
| [contracts/schemas.md](contracts/schemas.md) | `IF-*` | as-built | Payload and config schemas |
| [contracts/api.md](contracts/api.md) | `IF-*` | as-built | Orb ↔ assistant bridge API |
| [testing/TEST_PLAN.md](testing/TEST_PLAN.md) | — | as-built | Strategy, host vs on-target, layout |
| [testing/cases.md](testing/cases.md) | `T-*` | as-built | Test cases |
| [testing/trace.md](testing/trace.md) | — | as-built | REQ → T coverage matrix |
| [operations/build.md](operations/build.md) | — | as-built | Toolchain, install, run |
| [operations/deploy.md](operations/deploy.md) | — | as-built | Packaging and release |
| [operations/repos.md](operations/repos.md) | — | as-built | Dependency pinning (pi, models) |
| [security/threat-model.md](security/threat-model.md) | `RISK-*` | as-built | Trust boundaries, pi confinement |
| [research/pi-rpc.md](research/pi-rpc.md) | — | reviewed | Established pi RPC facts with citations |
| [research/ui-stack.md](research/ui-stack.md) | — | reviewed | Native UI stack comparison |
| [ui/](ui/) | — | as-built | Orb design: tokens, states, layout, a11y |
| [../PLAN.md](../PLAN.md) | — | as-built | Execution plan and work breakdown |

## What this project is

A voice-first desktop assistant. It listens, transcribes, reasons, speaks, and
shows an ambient orb. The reasoning backend is swappable between a first-party
loop (`native`) and the external **pi** coding agent.

- **Voice in / audio out** — speech input, spoken output, interruptible.
- **Native orb UI** — PySide6 / Qt Quick, macOS and Linux. No browser, no
  terminal as the primary interface.
- **Pluggable agent harness** — the loop owner is selectable per agent:
  `native` (our loop + a model provider) or `pi` (external harness via JSONL RPC).
- **Console fallback** — the assistant stays usable headless and in text.

## The three-layer model

Confusion about "the model" is the most common trap here. Three distinct layers:

| Layer | What it is | In this project |
| --- | --- | --- |
| Model provider | Serves an LLM over an API | Ollama, OpenAI |
| Model | The specific weights | `qwen3:latest` |
| **Agent harness** | Owns the reasoning loop: prompts the model, parses and runs tool calls, manages context | `native`, `pi` |

"Switching the brain" means switching the **harness**. pi is a harness, not a
provider and not an inference engine — it calls its own provider. See
[ADR-0004](architecture/decisions/ADR-0004-harness-vs-provider.md).

## Reading order

1. [requirements/scope.md](requirements/scope.md) — what is in and out.
2. [architecture/overview.md](architecture/overview.md) — the shape.
3. [contracts/protocols.md](contracts/protocols.md) — the wire.
4. [../PLAN.md](../PLAN.md) — the work order.

## Optional folders not created, and why

Two folders the playbook allows are deliberately absent. Absence is a decision,
not an oversight:

| Folder | Why it is not here |
| --- | --- |
| `reference/` | This set documents the **target** design, written before the refactor. As-built docs supersede it during chunk 7, when the code matches. Creating an as-built folder now would describe code that is about to be deleted. |
| `hardware/` | Not applicable — this is a desktop application, not a board with a pinout or power design. |

Two required files whose subject does not apply are present and marked, rather
than silently omitted:

| File | Status |
| --- | --- |
| [contracts/registers.md](contracts/registers.md) | Not applicable — no MCU, no register map |
| [operations/calibration.md](operations/calibration.md) | Not applicable — no NVM, no per-unit calibration |

Required folders with no applicable content are marked in place rather than
padded. `testing/trace.md` lists every requirement with no proving test as
`unverified` rather than leaving it blank.

## Open decisions

Live questions are tracked in the `Open questions` section of
[PLAN.md](../PLAN.md#open-questions). Nothing below is silently assumed.
