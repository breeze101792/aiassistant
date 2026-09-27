# Not applicable — registers and memory map

**Status:** Not applicable — this is a desktop software project, not a firmware
target. There is no MCU, no memory-mapped IO, and no register map.

Hardware-facing interfaces that *do* exist are documented instead as:

| Interface | Where |
| --- | --- |
| The OS audio device | [IF-0006 audio plane](protocols.md#if-0006-audio-plane) |
| The local WebSocket transport | [IF-0001 bus bridge](protocols.md#if-0001-bus-websocket-bridge-protocol) |
| The pi child process | [IF-0003 pi RPC](protocols.md#if-0003-pi-rpc) |
| On-disk state | [data-model.md](../architecture/data-model.md) |

Note the ID scheme: `ERR-PART-NNN` in the playbook is reserved for **erratum
workarounds** (a datasheet erratum applied in firmware). This project has no
errata, and uses `ERR-<MODULE>-<NAME>` for **runtime error codes** instead — a
deliberate deviation recorded in [requirements.md](../requirements/requirements.md).
