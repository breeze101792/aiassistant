# Architecture Decision Records

One file per decision. Format: decision, why, alternatives rejected, and the
evidence that forced the choice.

| ADR | Decision | Status |
| --- | --- | --- |
| [ADR-0001](ADR-0001-keep-bus.md) | Keep the in-process message bus, harden it | accepted |
| [ADR-0002](ADR-0002-module-renames.md) | Rename modules to functional names | accepted |
| [ADR-0003](ADR-0003-delete-canvas.md) | Delete the canvas module, not rename it | accepted |
| [ADR-0004](ADR-0004-harness-vs-provider.md) | Two axes: agent harness and model provider | accepted |
| [ADR-0005](ADR-0005-voice-merge.md) | Merge `ears` and `mouth` into `voice` | accepted |
| [ADR-0006](ADR-0006-rt-audio-event-plane.md) | Real-time audio plane, event plane on the bus | accepted |
| [ADR-0007](ADR-0007-pin-pi-not-vendor.md) | Pin pi; do not fork or submodule it | accepted |
| [ADR-0008](ADR-0008-pi-owns-tools.md) | pi owns tools on its own turns | accepted |
| [ADR-0009](ADR-0009-collapse-thinking-stages.md) | Collapse the 7-stage thinking loop | accepted |
| [ADR-0010](ADR-0010-keep-scheduler.md) | Keep the scheduler as a first-class module | accepted |
| [ADR-0011](ADR-0011-half-duplex-first.md) | Half-duplex audio first; barge-in behind AEC | accepted |
| [ADR-0012](ADR-0012-pi-confinement.md) | Confine pi at the coding level, document the gap | accepted |
| [ADR-0013](ADR-0013-pyside6-orb.md) | PySide6 / Qt Quick for the orb | accepted |
| [ADR-0014](ADR-0014-storage-unchanged.md) | Keep markdown memory and the SQLite cache | accepted |
| [ADR-0015](ADR-0015-docs-first.md) | Design docs are the gate before implementation | accepted |
