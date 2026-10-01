"""Orb view model: bus events in, display state out.

Pure logic with no Qt import, so the mapping from bus events to what the orb
shows is unit-testable. The QML layer only renders what this produces.

This is the seam that keeps the orb honest: it never derives state the assistant
has not published.
"""

import time

from aiassistant.bus import topics

LEVEL_GATE = 0.02
LEVEL_GAIN = 2.2
LEVEL_GAMMA = 0.7
ATTACK = 0.55
DECAY = 0.08

# Above this gap in the delta index, the orb asks for a snapshot instead of
# rendering a visible hole.
DELTA_GAP_TOLERANCE = 1


class OrbViewModel:
    """Tracks the assistant's state as the orb should display it."""

    def __init__(self):
        self.state = "connecting"
        self.harness = ""
        self.model = ""
        self.level = 0.0
        self.level_source = "input"
        self.transcript: list[dict] = []
        self._streaming: dict | None = None
        self._last_index: int | None = None
        self._smoothed_level = 0.0
        self._error: str = ""
        self._hint: str = ""
        self.needs_snapshot = False

    # ── Bus events ───────────────────────────────────────────

    def on_voice_state(self, payload: dict) -> None:
        state = payload.get("state")
        if state:
            self.state = state
            if state != "error":
                self._error = ""

    def on_level(self, payload: dict) -> None:
        """Smooth the raw level so the animation does not jitter.

        Attack is fast and decay slow, which is what reads as "reacting" rather
        than "flickering" (docs/ui/audio-reactivity.md).
        """
        raw = float(payload.get("level", 0.0) or 0.0)
        self.level_source = payload.get("source", "input")
        if raw < LEVEL_GATE:
            raw = 0.0
        shaped = min(1.0, (raw * LEVEL_GAIN) ** LEVEL_GAMMA)
        factor = ATTACK if shaped > self._smoothed_level else DECAY
        self._smoothed_level += (shaped - self._smoothed_level) * factor
        self.level = round(self._smoothed_level, 4)

    def on_delta(self, payload: dict) -> None:
        """Append a streamed fragment, detecting a gap in the index."""
        index = payload.get("index")
        kind = payload.get("kind", "text")
        text = payload.get("text", "")

        if index is not None:
            if self._last_index is not None and index > self._last_index + DELTA_GAP_TOLERANCE:
                # A missed delta means the transcript is incomplete; ask for a
                # snapshot rather than render a hole (REQ-ORB-005).
                self.needs_snapshot = True
            self._last_index = index

        if kind == "thinking":
            return  # thinking drives the animation, never the transcript text

        if self._streaming is None:
            self._streaming = {"role": "assistant", "text": "", "ts": time.time(),
                               "streaming": True}
            self.transcript.append(self._streaming)
        self._streaming["text"] += text

    def on_final(self, payload: dict) -> None:
        """Settle the streamed entry with the authoritative text."""
        text = payload.get("text", "")
        if self._streaming is not None:
            self._streaming["text"] = text
            self._streaming["streaming"] = False
            self._streaming = None
        elif text:
            self.transcript.append({"role": "assistant", "text": text,
                                    "ts": time.time(), "streaming": False})
        self._last_index = None
        self.state = "idle"

    def on_user_input(self, payload: dict) -> None:
        text = payload.get("text", "")
        if text:
            self.transcript.append({"role": "user", "text": text,
                                    "ts": time.time(), "streaming": False})

    def on_error(self, payload: dict) -> None:
        self._error = payload.get("message", "something went wrong")
        self._hint = payload.get("hint", "")
        self.state = "error"

    def on_harness(self, payload: dict) -> None:
        self.harness = payload.get("harness", "")
        self.model = payload.get("model", "")

    def on_tool_event(self, payload: dict) -> None:
        """Tool activity is display-only; it never changes the transcript."""
        if payload.get("status") == "running":
            self.transcript.append({
                "role": "tool",
                "text": f"{payload.get('name', 'tool')}…",
                "ts": time.time(),
                "streaming": True,
            })

    def on_snapshot(self, payload: dict) -> None:
        entries = payload.get("transcript") or []
        self.transcript = list(entries)
        self._streaming = None
        self.needs_snapshot = False
        self._last_index = payload.get("index")

    # ── Queries ──────────────────────────────────────────────

    @property
    def error(self) -> str:
        return self._error

    @property
    def hint(self) -> str:
        return self._hint

    @property
    def transcript_text(self) -> str:
        return "\n".join(f"{e['role']}: {e['text']}" for e in self.transcript)

    def clear(self) -> None:
        self.transcript.clear()
        self._streaming = None
        self._last_index = None


# Topic -> handler. The single dispatch table for a view model, so the GUI orb
# and the terminal orb cannot drift apart (ADR-0017). The caller owns the
# transport: after a delta, check ``model.needs_snapshot`` and request one.
def feed(model: OrbViewModel, topic: str, payload: dict) -> None:
    """Apply one bus message to a view model."""
    handler = _FEED_HANDLERS.get(topic)
    if handler is not None:
        handler(model, payload)


_FEED_HANDLERS = {
    topics.VOICE_STATE: lambda m, p: m.on_voice_state(p),
    topics.VOICE_LEVEL: lambda m, p: m.on_level(p),
    # Speech the user said is shown as their turn. This is what makes voice
    # input visible; the frontends only add typed input optimistically.
    topics.VOICE_TRANSCRIBED: lambda m, p: m.on_user_input(p),
    topics.AGENT_DELTA: lambda m, p: m.on_delta(p),
    topics.AGENT_FINAL: lambda m, p: m.on_final(p),
    topics.AGENT_TOOL_EVENT: lambda m, p: m.on_tool_event(p),
    topics.AGENT_TURN_ERROR: lambda m, p: m.on_error(p),
    topics.STATUS_HARNESS: lambda m, p: m.on_harness(p),
    topics.AGENT_TRANSCRIPT_SNAPSHOT: lambda m, p: m.on_snapshot(p),
}
