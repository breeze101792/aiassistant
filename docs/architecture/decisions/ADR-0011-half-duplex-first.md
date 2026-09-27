# ADR-0011 — Half-duplex audio first; barge-in behind AEC

**Status:** accepted · **Date:** 2026-09-26

## Decision

Ship half-duplex: the microphone is gated while TTS plays. Interrupt comes from
the orb, a hotkey, or the console. Voice-triggered barge-in (speaking over the
assistant) is deferred behind acoustic echo cancellation.

## Why

With speakers and an open microphone, the assistant hears its own voice. Without
AEC, the VAD detects the assistant's speech as user speech and the assistant
interrupts itself. The existing code worked around this by hard-muting the mic
during playback (`ears.py:68-70`), which is half-duplex by construction.

Two honest options exist:

1. Keep the mic gated, ship a real interrupt control, and defer barge-in.
2. Add AEC (`webrtc-audio-processing`) and enable true barge-in.

Option 1 preserves every stated requirement. The user's requirement is to
interrupt the assistant, and an explicit control satisfies that fully;
"interrupt by speaking" was never separately requested.

Option 2 adds a real-time DSP dependency with platform-specific behavior
(device selection, sample-rate handling, speaker reference) and a calibration
burden. It is a project of its own, and its failure mode — self-interruption —
is worse than the limitation it removes.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Enable barge-in with a VAD threshold hack | Self-triggers on speaker output; unreliable on both OSes |
| Require headphones to enable barge-in | Reasonable later as an opt-in, but not a default; it changes the user's setup |
| Skip the interrupt control entirely | Interrupting is a stated requirement, independent of how it is triggered |

## Consequences

- The requirement is written down as a limitation, not hidden
  (REQ-WAKE-008, `scope.md` "MVP limitations").
- The FSM already models the `SPEAKING → LISTENING` transition, so enabling
  barge-in later changes one edge and the AEC integration — not the
  architecture.
- Interrupt works from day one via `command.agent.interrupt`, and its ordered
  cancel sequence is verified (T-0303).
- When `voice.barge_in.enabled` is set without AEC, the docs state plainly that
  it may self-trigger.
