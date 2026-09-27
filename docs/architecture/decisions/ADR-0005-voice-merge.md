# ADR-0005 — Merge `ears` and `mouth` into `voice`

**Status:** accepted · **Date:** 2026-09-26

## Decision

Merge the speech input and output modules into one `voice/` module that owns
both audio directions.

## Why

Two modules owning one duplex device produced two real defects, not hypothetical
ones.

| Defect | Evidence |
| --- | --- |
| Interrupt could not stop playback | `edge_tts.py:39-47` plays via an `afplay`/`aplay` subprocess with no retained handle, so "interrupt" was a no-op |
| Voice barge-in was impossible by construction | `ears.py:68-70` subscribed `status.mouth.started` and hard-muted the mic for the whole utterance |

The workaround was a mute dance across the bus: `ears` muted itself when `mouth`
started, and unmuted when `mouth` finished (`ears.py:145-153`), while `mouth` had
no way to be stopped and `ears` had no way to know playback had actually ended.
State was split across `ears.py:24` (`self._state`) and `mouth.py:21`
(`self._processing`), which could express impossible combinations.

One owner fixes all of it: the module can stop its own playback, and it decides
when the mic is live. It also makes the duplex state machine expressible as one
FSM.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Keep both, add a coordinator module | A third module to coordinate two that fight; the coordinator needs the device authority anyway |
| Keep both, coordinate over the bus | This is what exists, and it is the source of both bugs |
| Split into capture and playback services | Same ownership problem, plus an IPC surface |

## Consequences

- The `voice/` module owns both threads, both queues, the FSM, and the stop flag.
- `sounddevice` replaces `afplay`/`aplay` so playback has a real handle.
- The orb animates from `voice.state` and `voice.level`, which is only coherent
  because one module owns both.
- Tests that pinned the old internals (`test_ears.py`'s `chunk == 960`,
  `_save_wav`, `mute`/`unmute`; `test_mouth.py`'s queue semantics) are replaced.
