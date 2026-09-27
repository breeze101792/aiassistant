# ADR-0006 — Real-time audio plane, event plane on the bus

**Status:** accepted · **Date:** 2026-09-26

## Decision

Split audio into two planes. Raw PCM and per-frame VAD results stay on
dedicated threads with bounded queues. Only discrete events cross the bus.

## Why

The bus cannot carry a real-time signal:

| Constraint | Value | Consequence |
| --- | --- | --- |
| Frame period | 20 ms | A missed frame is an audible glitch |
| `bus.publish` | Synchronous dict fan-out, unbounded in principle (`bus/bus.py:44`) | No latency bound, and one slow subscriber stalls the publisher |
| PCM rate, 16 kHz mono 16-bit | ~32 kB/s per subscriber | Fan-out to N subscribers is N× that, for no benefit |
| Playback | Needs a continuously fed buffer | A queue drained by a bus callback is the wrong shape |

So the split is forced by the numbers, not a stylistic preference.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Send PCM over the bus | Violates the latency requirement and costs bandwidth per subscriber |
| Send every VAD frame as an event | ~50 events/s of no interest; only state changes matter |
| One thread for capture and processing | ASR is slow (hundreds of ms to seconds) and would drop frames |

## Consequences

- `voice/audio/capture.py` and `playback.py` own the threads.
- Bounded queues with an explicit drop policy (segment queue cap 2,
  drop-oldest) and an overflow event, because unbounded growth is a memory leak
  with a friendly name.
- `voice.level` is coalesced to ≤ 20 Hz, latest-wins, because the shader wants
  smooth input and the bus wants low volume.
- ASR runs in an executor and never on the event loop.
