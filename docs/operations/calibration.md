# Not applicable — calibration

**Status:** Not applicable — there is no NVM, no per-unit calibration, and no
production line. This is a desktop application.

Two settings are sometimes called "calibration" in voice software. Neither is
a factory calibration, so they are documented as ordinary config:

| Setting | Where | Why it is not calibration |
| --- | --- | --- |
| VAD aggressiveness and endpoint silence | `voice.asr.*` | A user preference; not per-device, not stored in NVM, not versioned |
| Audio reactivity tuning (noise gate, gain, gamma) | [audio-reactivity.md](../ui/audio-reactivity.md) | Visual tuning for the orb, applied at runtime |

If a per-device audio profile is ever needed, it belongs in the config file
(which is already user-editable and versionable), not in a calibration
procedure.
