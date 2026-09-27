"""The duplex voice state machine.

One module owns both audio directions, so the state is one FSM rather than two
loose variables. The pre-refactor code held ``ears._state`` and
``mouth._processing`` separately and could therefore express impossible states
such as listening while speaking.

Transitions are validated: an invalid one raises rather than silently putting
the system in a state no consumer expects.
"""

from enum import Enum


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
    MUTED = "muted"


# Legal transitions. Any pair not listed here is a programming error.
_ALLOWED: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE: {
        VoiceState.LISTENING, VoiceState.MUTED, VoiceState.ERROR,
        # A transcript can arrive while idle: push-to-talk that was armed and
        # released, or a segment finalized while the FSM had already settled.
        VoiceState.TRANSCRIBING, VoiceState.THINKING,
    },
    VoiceState.LISTENING: {
        VoiceState.TRANSCRIBING, VoiceState.IDLE, VoiceState.MUTED,
        VoiceState.ERROR, VoiceState.THINKING,
    },
    VoiceState.TRANSCRIBING: {
        VoiceState.THINKING, VoiceState.LISTENING, VoiceState.IDLE,
        VoiceState.ERROR, VoiceState.MUTED,
    },
    VoiceState.THINKING: {
        VoiceState.SPEAKING, VoiceState.LISTENING, VoiceState.IDLE,
        VoiceState.ERROR, VoiceState.MUTED,
    },
    VoiceState.SPEAKING: {
        VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR,
        VoiceState.MUTED,
    },
    VoiceState.MUTED: {
        VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR,
    },
    VoiceState.ERROR: {
        VoiceState.LISTENING, VoiceState.IDLE, VoiceState.MUTED,
    },
}


class InvalidTransition(RuntimeError):
    """A transition that would produce an impossible state."""

    def __init__(self, current: VoiceState, target: VoiceState):
        super().__init__(f"illegal voice transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


class VoiceStateMachine:
    """Tracks the duplex state and reports changes.

    A transition to the current state is a no-op, not an error: publishers are
    allowed to be idempotent.
    """

    def __init__(self, on_change=None):
        self._state = VoiceState.IDLE
        self._on_change = on_change

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def is_playing(self) -> bool:
        return self._state is VoiceState.SPEAKING

    @property
    def mic_should_be_live(self) -> bool:
        """Half-duplex: the mic is live except while speaking or muted."""
        return self._state not in (VoiceState.SPEAKING, VoiceState.MUTED)

    def can_transition(self, target: VoiceState) -> bool:
        if target is self._state:
            return True
        return target in _ALLOWED[self._state]

    def transition(self, target: VoiceState) -> bool:
        """Move to ``target``. Returns True when the state actually changed."""
        if target is self._state:
            return False
        if not self.can_transition(target):
            raise InvalidTransition(self._state, target)
        previous, self._state = self._state, target
        if self._on_change:
            self._on_change(previous, target)
        return True
