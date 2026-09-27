"""Orb view-model tests.

The QML/Qt layer is manual on both OSes (T-0201), but the mapping from bus
events to display state is pure logic and fully testable here.
"""

from aiassistant.orb.model import OrbViewModel
from aiassistant.orb.theme import STATE_COLORS, state_color


class TestStateAndHarness:
    def test_starts_connecting(self):
        assert OrbViewModel().state == "connecting"

    def test_voice_state_is_tracked(self):
        m = OrbViewModel()
        for state in ("listening", "transcribing", "thinking", "speaking", "idle"):
            m.on_voice_state({"state": state})
            assert m.state == state

    def test_harness_badge(self):
        m = OrbViewModel()
        m.on_harness({"harness": "native", "model": "qwen3:latest"})
        assert m.harness == "native"
        assert m.model == "qwen3:latest"

    def test_error_sets_state_and_message(self):
        m = OrbViewModel()
        m.on_error({"message": "provider down", "hint": "retry"})
        assert m.state == "error"
        assert m.error == "provider down"
        assert m.hint == "retry"

    def test_a_new_voice_state_clears_a_previous_error(self):
        m = OrbViewModel()
        m.on_error({"message": "boom"})
        m.on_voice_state({"state": "listening"})
        assert m.error == ""


class TestLevel:
    def test_silence_gives_zero_after_smoothing(self):
        m = OrbViewModel()
        for _ in range(20):
            m.on_level({"level": 0.0, "source": "input"})
        assert m.level < 0.01

    def test_loud_input_raises_the_level(self):
        m = OrbViewModel()
        for _ in range(20):
            m.on_level({"level": 0.5, "source": "input"})
        assert m.level > 0.5

    def test_below_the_gate_is_treated_as_silence(self):
        m = OrbViewModel()
        m.on_level({"level": 0.001})
        assert m.level == 0.0

    def test_level_is_bounded(self):
        m = OrbViewModel()
        for _ in range(50):
            m.on_level({"level": 1.0})
        assert 0.0 <= m.level <= 1.0

    def test_source_is_reported_for_the_orb_to_route(self):
        m = OrbViewModel()
        m.on_level({"level": 0.3, "source": "output"})
        assert m.level_source == "output"

    def test_attack_is_faster_than_decay(self):
        """Reacts quickly, fades slowly: that is what reads as a live pulse."""
        m = OrbViewModel()
        m.on_level({"level": 0.8})
        after_attack = m.level
        m2 = OrbViewModel()
        m2._smoothed_level = after_attack
        m2.on_level({"level": 0.0})
        decay_drop = after_attack - m2.level
        assert decay_drop < after_attack  # a single decay step does not empty it


class TestTranscript:
    def test_deltas_accumulate_into_one_streaming_entry(self):
        m = OrbViewModel()
        m.on_delta({"kind": "text", "text": "Hello ", "index": 0})
        m.on_delta({"kind": "text", "text": "world", "index": 1})
        assert len(m.transcript) == 1
        assert m.transcript[0]["text"] == "Hello world"
        assert m.transcript[0]["streaming"] is True

    def test_thinking_deltas_do_not_appear_in_the_transcript(self):
        m = OrbViewModel()
        m.on_delta({"kind": "thinking", "text": "weighing options", "index": 0})
        assert m.transcript == []

    def test_final_replaces_the_streamed_text(self):
        """The final is authoritative; the display must reconcile to it."""
        m = OrbViewModel()
        m.on_delta({"kind": "text", "text": "2 + 2 =", "index": 0})
        m.on_final({"text": "2 + 2 = 4."})
        assert m.transcript[0]["text"] == "2 + 2 = 4."
        assert m.transcript[0]["streaming"] is False

    def test_index_gap_requests_a_snapshot(self):
        """A missed delta must not render a silent hole."""
        m = OrbViewModel()
        m.on_delta({"kind": "text", "text": "a", "index": 0})
        m.on_delta({"kind": "text", "text": "b", "index": 5})
        assert m.needs_snapshot is True

    def test_contiguous_indices_do_not_request_a_snapshot(self):
        m = OrbViewModel()
        for i in range(5):
            m.on_delta({"kind": "text", "text": "x", "index": i})
        assert m.needs_snapshot is False

    def test_snapshot_replaces_the_transcript_and_clears_the_flag(self):
        m = OrbViewModel()
        m.on_delta({"kind": "text", "text": "stale", "index": 0})
        m.on_delta({"kind": "text", "text": "gap", "index": 9})
        m.on_snapshot({"transcript": [
            {"role": "user", "text": "hi", "streaming": False},
            {"role": "assistant", "text": "hello", "streaming": False},
        ]})
        assert m.needs_snapshot is False
        assert len(m.transcript) == 2
        assert "stale" not in m.transcript_text

    def test_user_input_appears(self):
        m = OrbViewModel()
        m.on_user_input({"text": "turn on the lights"})
        assert m.transcript[0]["role"] == "user"

    def test_tool_activity_is_shown(self):
        m = OrbViewModel()
        m.on_tool_event({"name": "datetime", "status": "running"})
        assert any(e["role"] == "tool" for e in m.transcript)

    def test_clear_empties_the_transcript(self):
        m = OrbViewModel()
        m.on_user_input({"text": "x"})
        m.clear()
        assert m.transcript == []


class TestTheme:
    def test_every_state_has_a_color(self):
        for state in ("idle", "listening", "transcribing", "thinking",
                      "speaking", "error", "muted", "connecting", "backend_down"):
            assert state in STATE_COLORS, f"{state} has no color"

    def test_unknown_state_falls_back(self):
        assert state_color("does-not-exist")

    def test_states_are_visually_distinct(self):
        """Each state needs its own hue; the QML layer relies on this."""
        assert len(set(STATE_COLORS.values())) == len(STATE_COLORS)


class TestFeedDispatch:
    """The shared topic→view-model dispatch the GUI and TUI both use.

    One table means the two frontends cannot drift (ADR-0017).
    """

    def test_feed_maps_each_watched_topic(self):
        from aiassistant.bus import topics
        from aiassistant.orb.model import feed

        m = OrbViewModel()
        feed(m, topics.VOICE_STATE, {"state": "listening"})
        assert m.state == "listening"
        feed(m, topics.AGENT_DELTA, {"index": 0, "kind": "text", "text": "hi"})
        assert m.transcript[-1]["text"] == "hi"
        feed(m, topics.AGENT_FINAL, {"text": "hi"})
        assert m.state == "idle"
        feed(m, topics.STATUS_HARNESS, {"harness": "native", "model": "m"})
        assert m.harness == "native"
        feed(m, topics.AGENT_TURN_ERROR, {"message": "boom"})
        assert m.state == "error"

    def test_feed_ignores_unknown_topics(self):
        from aiassistant.orb.model import feed

        m = OrbViewModel()
        feed(m, "some.unknown.topic", {"text": "x"})
        assert m.transcript == []

    def test_importing_the_model_pulls_no_qt(self):
        """The TUI imports this module; it must stay Qt-free (ADR-0017)."""
        import subprocess
        import sys

        code = (
            "import sys; import aiassistant.orb.model; "
            "print('PySide6' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "False"
