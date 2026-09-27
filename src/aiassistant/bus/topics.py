"""Bus topic constants.

Topic strings are the real interface between modules, and they were bare
literals scattered across the codebase — which is why a rename could silently
disable routing (for example, the TTS trigger compared ``source == "ears"``).
Import from here instead of writing a literal.

Values marked ``as-built`` are unchanged from the current code so frozen
modules keep working. See docs/contracts/protocols.md IF-0007.
"""

# ── Input ────────────────────────────────────────────────────
USER_INPUT_TEXT = "user.input.text"

# ── Agent output ─────────────────────────────────────────────
AGENT_DELTA = "agent.delta"
AGENT_TOOL_EVENT = "agent.tool.event"
AGENT_FINAL = "agent.final"
AGENT_TURN_ERROR = "agent.turn.error"
AGENT_TRANSCRIPT_SNAPSHOT = "agent.transcript.snapshot"
AGENT_ASK = "brain.ask"  # as-built: RPC request for a reasoning subtask

# ── Voice ────────────────────────────────────────────────────
VOICE_STATE = "voice.state"
VOICE_LEVEL = "voice.level"
VOICE_TRANSCRIBED = "voice.transcribed"
VOICE_SPEAK = "voice.speak"
VOICE_OVERFLOW = "voice.overflow"

# ── Commands ─────────────────────────────────────────────────
COMMAND_AGENT_INTERRUPT = "command.agent.interrupt"
COMMAND_VOICE_MUTE = "command.voice.mute"
COMMAND_VOICE_PTT_START = "command.voice.ptt.start"
COMMAND_VOICE_PTT_END = "command.voice.ptt.end"

# ── Tools ────────────────────────────────────────────────────
TOOL_EXECUTE = "action.execute"          # as-built
STATUS_TOOL_DONE = "status.hand.done"    # as-built
STATUS_TOOL_ERROR = "status.hand.error"  # as-built
STATUS_TOOLS_READY = "status.hands.ready"  # as-built

# ── Status ───────────────────────────────────────────────────
STATUS_ASSISTANT_READY = "status.assistant.ready"
STATUS_HARNESS = "status.harness"
BUS_MODULE_CONNECTED = "bus.module.connected"
BUS_MODULE_DISCONNECTED = "bus.module.disconnected"

# ── Scheduler ────────────────────────────────────────────────
SCHEDULE_TRIGGERED = "schedule.triggered"

# ── Frozen modules ───────────────────────────────────────────
# Kept at their as-built values so the frozen vision/messaging modules keep
# working; see docs/architecture/modules/frozen-modules.md.
SENSORY_VISION_FRAME = "sensory.vision.frame"
VISION_ANALYZE = "eyes.analyze"
STATUS_VISION_READY = "status.eyes.ready"
MESSAGING_RESPONSE = "response.text"

# ── Voice channels ───────────────────────────────────────────
# Which input channel originated a turn. These drive routing decisions that
# were previously magic strings (for example, whether to speak a response).
CHANNEL_VOICE = "voice"
CHANNEL_ORB = "orb"
CHANNEL_CONSOLE = "console"
CHANNEL_SCHEDULE = "schedule"
CHANNEL_MESSAGING = "messaging"

SPEAKING_CHANNELS = frozenset({CHANNEL_VOICE})


def should_speak(channel: str) -> bool:
    """Whether a turn from this channel should produce speech.

    A single source of truth: the old code compared ``source == "ears"``
    inline, so renaming the module silently disabled speech.
    Returns False for any channel not explicitly speaking.
    """
    return channel in SPEAKING_CHANNELS
