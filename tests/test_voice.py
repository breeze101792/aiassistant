"""Voice module tests: the duplex FSM, chunking, queues, and playback control.

The defects these pin:
  * ``afplay`` playback had no handle, so interrupt could not stop audio.
  * The mic was muted over the bus for a whole utterance, so barge-in was
    impossible and the state could not express "listening while speaking".
"""

import pytest

from aiassistant.bus import topics
from aiassistant.bus.bus import MessageBus
from aiassistant.voice.audio import SegmentQueue, rms_level
from aiassistant.voice.state import (
    InvalidTransition,
    VoiceState,
    VoiceStateMachine,
)
from aiassistant.voice.tts.chunker import SentenceChunker
from aiassistant.voice.wake import AsrHotwordDetector, AlwaysAwakeDetector, create_detector


class TestStateMachine:
    def test_starts_idle(self):
        assert VoiceStateMachine().state is VoiceState.IDLE

    def test_full_turn_cycle_is_legal(self):
        m = VoiceStateMachine()
        for state in (VoiceState.LISTENING, VoiceState.TRANSCRIBING,
                      VoiceState.THINKING, VoiceState.SPEAKING, VoiceState.LISTENING):
            m.transition(state)
        assert m.state is VoiceState.LISTENING

    def test_impossible_transition_is_rejected(self):
        """The old two-variable design could express listening while speaking."""
        m = VoiceStateMachine()
        with pytest.raises(InvalidTransition):
            m.transition(VoiceState.SPEAKING)  # idle -> speaking is illegal

    def test_repeating_the_current_state_is_a_noop(self):
        m = VoiceStateMachine()
        m.transition(VoiceState.LISTENING)
        assert m.transition(VoiceState.LISTENING) is False

    def test_change_callback_fires(self):
        seen = []
        m = VoiceStateMachine(on_change=lambda prev, cur: seen.append((prev, cur)))
        m.transition(VoiceState.LISTENING)
        assert seen == [(VoiceState.IDLE, VoiceState.LISTENING)]

    def test_mic_is_gated_only_while_speaking_or_muted(self):
        m = VoiceStateMachine()
        assert m.mic_should_be_live is True
        m.transition(VoiceState.LISTENING)
        m.transition(VoiceState.TRANSCRIBING)
        m.transition(VoiceState.THINKING)
        m.transition(VoiceState.SPEAKING)
        assert m.mic_should_be_live is False
        m.transition(VoiceState.MUTED)
        assert m.mic_should_be_live is False

    def test_interrupt_returns_to_listening(self):
        """The real flow reaches speaking via transcribing and thinking; the
        interrupt edge is speaking -> listening."""
        m = VoiceStateMachine()
        for state in (VoiceState.LISTENING, VoiceState.TRANSCRIBING,
                      VoiceState.THINKING, VoiceState.SPEAKING):
            m.transition(state)
        m.transition(VoiceState.LISTENING)  # the interrupt edge
        assert m.state is VoiceState.LISTENING

    def test_speaking_without_transcribing_is_rejected(self):
        m = VoiceStateMachine()
        m.transition(VoiceState.LISTENING)
        with pytest.raises(InvalidTransition):
            m.transition(VoiceState.SPEAKING)

    def test_a_transcript_may_arrive_while_idle(self):
        """Push-to-talk released before the ASR result lands: the FSM must not
        reject a legitimate transcript."""
        m = VoiceStateMachine()
        m.transition(VoiceState.THINKING)
        assert m.state is VoiceState.THINKING


class TestChunker:
    def test_single_short_delta_waits(self):
        """Nothing is spoken until a boundary; otherwise every token is a clip."""
        c = SentenceChunker()
        assert c.push("Hello") == []

    def test_flushes_at_a_sentence_boundary(self):
        c = SentenceChunker(min_chars=5)
        chunks = c.push("Hello there, friend. And more text")
        assert chunks == ["Hello there, friend."]
        assert c.pending.strip() == "And more text"

    def test_flush_emits_the_remainder(self):
        c = SentenceChunker()
        c.push("no terminator here")
        assert c.flush() == ["no terminator here"]
        assert c.pending == ""

    def test_streaming_emits_early_and_often(self):
        """The point of chunking: audio starts before the model finishes."""
        c = SentenceChunker(min_chars=10)
        spoken = []
        for delta in ["The first sentence is long enough. ",
                      "The second one follows. ",
                      "And a third."]:
            spoken.extend(c.push(delta))
        spoken.extend(c.flush())
        assert len(spoken) == 3

    def test_max_length_forces_a_cut_without_punctuation(self):
        c = SentenceChunker(min_chars=10, max_chars=30)
        chunks = c.push("word " * 20)
        assert chunks, "a long run must be cut rather than buffered forever"

    def test_empty_delta_is_ignored(self):
        c = SentenceChunker()
        assert c.push("") == []

    def test_reset_clears_the_buffer(self):
        c = SentenceChunker()
        c.push("partial")
        c.reset()
        assert c.pending == ""


class TestSegmentQueue:
    def test_cap_drops_the_oldest(self):
        """A stale segment is worse than a missing one."""
        q = SegmentQueue(cap=2)
        q.put("first")
        q.put("second")
        assert q.put("third") is False
        assert len(q) == 2
        assert q.get() == "second"
        assert q.dropped == 1

    def test_get_on_empty_returns_none(self):
        assert SegmentQueue().get() is None

    def test_clear_empties(self):
        q = SegmentQueue()
        q.put("x")
        q.clear()
        assert len(q) == 0


class TestRms:
    def test_silence_is_zero(self):
        assert rms_level(b"\x00\x00" * 100) == 0.0

    def test_full_scale_is_near_one(self):
        import struct
        pcm = struct.pack("<" + "h" * 100, *([32767] * 100))
        assert rms_level(pcm) > 0.9

    def test_empty_input_is_zero(self):
        assert rms_level(b"") == 0.0


class TestWakeDetection:
    def test_wake_phrase_matches_case_insensitively(self):
        d = AsrHotwordDetector(["hey jarvis"])
        assert d.should_wake("Hey Jarvis, what time is it?")

    def test_wake_phrase_absent(self):
        d = AsrHotwordDetector(["hey jarvis"])
        assert not d.should_wake("what time is it")

    def test_wake_phrase_must_be_a_whole_word(self):
        d = AsrHotwordDetector(["jarvis"])
        assert not d.should_wake("jarvisx is a different word")

    def test_strip_returns_the_command(self):
        d = AsrHotwordDetector(["hey jarvis"])
        assert d.strip_wake("Hey Jarvis what time is it") == "what time is it"

    def test_strip_with_only_the_phrase_returns_empty(self):
        d = AsrHotwordDetector(["hey jarvis"])
        assert d.strip_wake("Hey Jarvis!") == ""

    def test_asr_punctuation_between_words_is_tolerated(self):
        d = AsrHotwordDetector(["hey jarvis"])
        assert d.should_wake("Hey, Jarvis. play music")

    def test_no_phrases_configured_accepts_everything(self):
        assert AsrHotwordDetector([]).should_wake("anything")

    def test_open_mode_accepts_everything(self):
        assert AlwaysAwakeDetector().should_wake("anything at all")

    def test_factory_selects_by_mode(self):
        assert isinstance(create_detector("open", ["hi"]), AlwaysAwakeDetector)
        assert isinstance(create_detector("wake", ["hi"]), AsrHotwordDetector)


class TestPlaybackControl:
    """Interrupt must silence output, and the module must publish state."""

    @pytest.mark.asyncio
    async def test_interrupt_clears_the_queue(self):
        from aiassistant.voice.audio import Playback

        class FakeStream:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

            def close(self):
                pass

        pb = Playback()
        pb._stream = FakeStream()  # avoid opening a real device
        pb.enqueue(b"\x01\x00" * 100)
        assert pb.pending_frames == 1
        pb.stop_now()
        assert pb.pending_frames == 0
        assert pb._stop.is_set() is True

    @pytest.mark.asyncio
    async def test_module_publishes_state_on_interrupt(self):
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        bus._loop = None
        mod = VoiceModule(bus, {"voice": {"backend": "stub"},
                                "voice_tts": {"backend": "text"}})
        await mod.setup()
        mod.disable_audio()
        states = []
        bus.subscribe(topics.VOICE_STATE, lambda t, p: states.append(p["state"]))
        await mod.start()
        await mod.interrupt_playback()
        assert "idle" in states

    @pytest.mark.asyncio
    async def test_mute_publishes_and_gates(self):
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub", "listen": {"mode": "open"}},
                                "voice_tts": {"backend": "text"}})
        await mod.setup()
        mod.disable_audio()
        states = []
        bus.subscribe(topics.VOICE_STATE, lambda t, p: states.append(p))
        await mod.start()
        mod.set_mute(True)
        assert any(s.get("muted") is True for s in states)

    @pytest.mark.asyncio
    async def test_voice_channel_transcript_creates_a_turn(self):
        """A voice transcript must reach the agent as a voice-channel turn."""
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub", "listen": {"mode": "open"}},
                                "voice_tts": {"backend": "text"}})
        await mod.setup()
        mod.disable_audio()
        inputs = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))
        await mod.start()
        mod._publish_transcript("what is the time", 0.9)
        assert inputs and inputs[0]["channel"] == topics.CHANNEL_VOICE

    @pytest.mark.asyncio
    async def test_wake_mode_discards_a_segment_without_the_phrase(self):
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {
            "voice": {"backend": "stub", "listen": {"mode": "wake"},
                      "hotwords": ["hey jarvis"]},
            "voice_tts": {"backend": "text"},
        })
        await mod.setup()
        mod.disable_audio()
        inputs = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))
        await mod.start()
        mod._publish_transcript("just some background speech", 0.9)
        assert inputs == [], "a segment without the wake phrase must not create a turn"

        mod._publish_transcript("hey jarvis what time is it", 0.9)
        assert len(inputs) == 1
        assert "jarvis" not in inputs[0]["text"].lower()
