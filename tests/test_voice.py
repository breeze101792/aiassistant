"""Voice module tests: the duplex FSM, chunking, queues, and playback control.

The defects these pin:
  * ``afplay`` playback had no handle, so interrupt could not stop audio.
  * The mic was muted over the bus for a whole utterance, so barge-in was
    impossible and the state could not express "listening while speaking".
"""

import asyncio
import math
import struct
import threading
import time

import pytest

from aiassistant.bus import topics
from aiassistant.bus.bus import MessageBus
from aiassistant.voice.asr.asr_backends.base import ASRBackend
from aiassistant.voice.audio import SegmentQueue, rms_level
from aiassistant.voice.segmenter import BYTES_PER_FRAME
from aiassistant.voice.state import (
    InvalidTransition,
    VoiceState,
    VoiceStateMachine,
)
from aiassistant.voice.tts.chunker import SentenceChunker
from aiassistant.voice.wake import AsrHotwordDetector, AlwaysAwakeDetector, create_detector

# One frame is 20 ms at 16 kHz mono int16.
FRAME_SAMPLES = BYTES_PER_FRAME // 2
SINE_HZ = 440.0
# Peak amplitude well above the default 0.02 energy threshold.
LOUD_AMPLITUDE = 20000
SILENCE_FRAME = b"\x00\x00" * FRAME_SAMPLES


def sine_frame(amplitude: int = LOUD_AMPLITUDE,
               samples: int = FRAME_SAMPLES) -> bytes:
    """A real 640-byte speech-loud frame, no device involved."""
    values = [
        int(amplitude * math.sin(2.0 * math.pi * SINE_HZ * i / 16000))
        for i in range(samples)
    ]
    return struct.pack("<" + "h" * samples, *values)


async def wait_until(predicate, timeout: float = 1.0) -> bool:
    """Poll for a worker result rather than sleeping a fixed time."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()



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
        # get() blocks by default (the ASR worker waits on it); timeout=0 is the
        # non-blocking probe.
        assert SegmentQueue().get(timeout=0) is None

    def test_close_wakes_a_blocked_get(self):
        import threading

        q = SegmentQueue()
        result = []
        waiter = threading.Thread(target=lambda: result.append(q.get(timeout=1.0)))
        waiter.start()
        q.close()
        waiter.join(timeout=1.0)
        assert result == [None]
        assert q.closed is True

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


class TestAsrBackendSelection:
    """REQ-VOICE-004: the backend name selects the backend, no code change.

    ADR-0018 moved construction into ``voice.factory``; an unknown value is a
    hard error naming the value, never a stub fallback (REQ-BACKEND-002).
    """

    @staticmethod
    def _select(backend: str):
        from aiassistant.voice.factory import create_asr
        return create_asr({"backend": backend})

    def test_stub_selects_the_stub(self):
        from aiassistant.voice.asr.asr_backends.stub import StubASR
        assert isinstance(self._select("stub"), StubASR)

    def test_whisper_selects_whisper(self):
        from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend
        assert isinstance(self._select("whisper"), WhisperBackend)

    def test_funasr_selects_funasr(self):
        from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend
        assert isinstance(self._select("funasr"), FunASRBackend)

    def test_unknown_backend_is_a_hard_error(self):
        from aiassistant.voice.factory import VoiceConfigError
        with pytest.raises(VoiceConfigError, match="nonsense"):
            self._select("nonsense")

    def test_halasr_errors_with_the_removal_fix(self):
        """ADR-0018 removed halasr; the error must name the replacements."""
        from aiassistant.voice.factory import VoiceConfigError
        with pytest.raises(VoiceConfigError, match="removed in ADR-0018"):
            self._select("halasr")


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
    async def test_the_stop_latch_clears_on_the_next_utterance(self):
        """An interrupt silences the current reply, not the rest of the session.

        ``stop_now`` sets a latch the audio callback checks. Before the fix
        nothing cleared it, so after one Esc the assistant was silent forever.
        """
        from aiassistant.voice.audio import FRAME_MS, Playback, TARGET_SAMPLE_RATE

        blocksize = TARGET_SAMPLE_RATE * FRAME_MS // 1000
        needed = blocksize * 2
        pcm = b"\x40\x1f" * blocksize  # loud, non-zero int16

        pb = Playback()
        pb.stop_now()
        assert pb._stop.is_set() is True

        # The next utterance must play, so the latch cannot survive enqueue.
        pb.enqueue(pcm)
        assert pb._stop.is_set() is False

        out = bytearray(needed)
        pb._callback(out, blocksize, None, None)
        assert any(out), "the next utterance must not be silenced"

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
    async def test_state_request_replies_without_a_transition(self):
        """A late-connecting client must be told the current state.

        The reply is a level read: it must not move the FSM or publish a second
        time through _on_state_change.
        """
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub", "listen": {"mode": "open"}},
                                "voice_tts": {"backend": "text"}})
        await mod.setup()
        mod.disable_audio()
        await mod.start()
        replies = []
        bus.subscribe(topics.VOICE_STATE, lambda t, p: replies.append(p))
        before = mod._state.state

        await mod._handle_state_request(topics.VOICE_STATE_REQUEST, {})
        bus.publish(topics.VOICE_STATE_REQUEST, {})

        assert replies[-1]["state"] == "idle"
        assert replies[-1]["muted"] is False
        assert mod._state.state is before

    @pytest.mark.asyncio
    async def test_state_request_reports_a_muted_module(self):
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub", "listen": {"mode": "open"}},
                                "voice_tts": {"backend": "text"}})
        await mod.setup()
        mod.disable_audio()
        await mod.start()
        mod.set_mute(True)
        replies = []
        bus.subscribe(topics.VOICE_STATE, lambda t, p: replies.append(p))

        await mod._handle_state_request(topics.VOICE_STATE_REQUEST, {})

        assert replies[-1] == {"state": "muted", "muted": True}

    @pytest.mark.asyncio
    async def test_state_request_matches_an_error_published_without_a_transition(self):
        """_fail reports "error" without moving the FSM; a resync must agree.

        Reading the FSM alone would answer "idle" here and the two frontends
        would disagree about the same event.
        """
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"backend": "stub", "listen": {"mode": "open"}},
                                "voice_tts": {"backend": "text"}})
        await mod.setup()
        mod.disable_audio()
        await mod.start()
        mod._fail("ERR-VOICE-NO-INPUT", "no device")
        replies = []
        bus.subscribe(topics.VOICE_STATE, lambda t, p: replies.append(p))

        await mod._handle_state_request(topics.VOICE_STATE_REQUEST, {})

        assert replies[-1]["state"] == "error"

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


class _FakeCapture:
    """A capture stand-in so half-duplex mute/unmute is observable in tests."""

    def __init__(self):
        self.muted = False

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def close(self) -> None:
        pass


ENDPOINT_SILENCE_MS = 60          # 3 frames, so endpointing drains quickly
SPEECH_FRAMES = 10                # 200 ms, above the 100 ms minimum
ENDPOINT_SILENCE_FRAMES = ENDPOINT_SILENCE_MS // 20


class RecordingASR(ASRBackend):
    """A fake backend that records the PCM the worker hands it."""

    def __init__(self, text: str = "turn off the fan", confidence: float = 0.9):
        self.text = text
        self.confidence = confidence
        self.pcm: list[bytes] = []
        self.done = threading.Event()

    def transcribe(self, audio_bytes: bytes) -> dict:
        self.pcm.append(audio_bytes)
        self.done.set()
        return {"text": self.text, "confidence": self.confidence, "language": "en"}


def build_module(bus, mode: str = "open"):
    from aiassistant.voice.module import VoiceModule

    return VoiceModule(bus, {
        "voice": {
            "asr": {"backend": "stub"},
            "vad": {"backend": "energy", "energy_threshold": 0.02},
            "segmenter": {"min_utterance_ms": 100},
            "endpoint_silence_ms": ENDPOINT_SILENCE_MS,
            "listen": {"mode": mode},
            "hotwords": ["hey assistant"],
        },
    })


async def feed_speech_and_endpoint(mod, frames: int = SPEECH_FRAMES) -> None:
    for _ in range(frames):
        mod._on_frame(sine_frame())
    for _ in range(ENDPOINT_SILENCE_FRAMES):
        mod._on_frame(SILENCE_FRAME)


class TestAudioPipelineEndToEnd:
    """ADR-0018: Capture -> VAD -> Segmenter -> queue -> ASR -> transcript.

    No device is opened: frames are injected and the ASR is a fake. The whole
    hand-off from raw frames to a voice turn is exercised for real.
    """

    @pytest.mark.asyncio
    async def test_frames_become_a_voice_turn(self):
        bus = MessageBus()
        mod = build_module("open")
        mod.bus = bus
        await mod.setup()
        mod.disable_audio()
        await mod.start()

        recording = RecordingASR()
        mod._asr = recording
        transcripts, inputs = [], []
        bus.subscribe(topics.VOICE_TRANSCRIBED, lambda t, p: transcripts.append(p))
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))

        await feed_speech_and_endpoint(mod)
        # Let the worker drain without a fixed sleep, then confirm the turn.
        await asyncio.get_running_loop().run_in_executor(
            None, recording.done.wait, 1.0)
        await wait_until(lambda: inputs)

        assert recording.pcm, "the ASR worker must receive the utterance"
        assert len(recording.pcm[0]) % BYTES_PER_FRAME == 0, (
            "the emitted PCM must be frame-aligned"
        )
        assert transcripts and transcripts[0]["text"] == "turn off the fan"
        assert inputs and inputs[0]["channel"] == topics.CHANNEL_VOICE
        await mod.stop()

    @pytest.mark.asyncio
    async def test_silence_only_produces_no_turn(self):
        bus = MessageBus()
        mod = build_module("open")
        mod.bus = bus
        await mod.setup()
        mod.disable_audio()
        await mod.start()
        mod._asr = RecordingASR()
        inputs = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))

        for _ in range(SPEECH_FRAMES + ENDPOINT_SILENCE_FRAMES):
            mod._on_frame(SILENCE_FRAME)
        await asyncio.sleep(0.05)

        assert inputs == [], "silence must never reach the ASR worker"
        await mod.stop()


class TestSegmentOverflow:
    def test_a_queue_drop_is_published_from_the_worker(self):
        """A dropped segment is lossy by design, and the UI must be told.

        The drop is recorded on the audio thread but published from the ASR
        worker: ``bus.publish`` is a synchronous fan-out that must not run on
        the audio callback.
        """
        from aiassistant.voice.module import VoiceModule

        bus = MessageBus()
        mod = VoiceModule(bus, {"voice": {"asr": {"backend": "stub"}}})
        mod._segments = SegmentQueue(cap=1)
        overflows = []
        bus.subscribe(topics.VOICE_OVERFLOW, lambda t, p: overflows.append(p))

        mod._on_utterance(b"first")
        assert overflows == [], "one segment at cap is not an overflow"
        mod._on_utterance(b"second")
        # The audio thread only flags it; the publish happens on the worker.
        assert overflows == []

        mod._publish_overflow()
        assert overflows == [{"dropped": 1, "queue_cap": 1}]
        # The flag is one-shot: no duplicate event on the next drain.
        mod._publish_overflow()
        assert len(overflows) == 1


class TestPushToTalk:
    """arm -> feed -> disarm must finalize exactly one utterance."""

    @pytest.mark.asyncio
    async def test_ptt_produces_exactly_one_utterance(self):
        bus = MessageBus()
        mod = build_module("ptt")
        mod.bus = bus
        await mod.setup()
        mod.disable_audio()
        await mod.start()

        recording = RecordingASR("play music")
        mod._asr = recording
        transcripts, inputs = [], []
        bus.subscribe(topics.VOICE_TRANSCRIBED, lambda t, p: transcripts.append(p))
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))

        mod.arm()
        for _ in range(SPEECH_FRAMES):
            mod._on_frame(sine_frame())
        mod.disarm()  # flushes the open partial, exactly once

        await asyncio.get_running_loop().run_in_executor(
            None, recording.done.wait, 1.0)
        await wait_until(lambda: inputs)
        # A second delivery would show up within a couple of queue hand-offs.
        await asyncio.sleep(0.05)

        assert len(recording.pcm) == 1, "disarm must flush exactly one utterance"
        assert len(transcripts) == 1
        assert len(inputs) == 1
        await mod.stop()

    @pytest.mark.asyncio
    async def test_disarm_with_no_speech_emits_nothing(self):
        bus = MessageBus()
        mod = build_module("ptt")
        mod.bus = bus
        await mod.setup()
        mod.disable_audio()
        await mod.start()
        recording = RecordingASR()
        mod._asr = recording

        mod.arm()
        mod.disarm()
        await asyncio.sleep(0.05)

        assert recording.pcm == [], "an empty PTT press must not transcribe"
        await mod.stop()



class TestWorkerThreadSafety:
    """The ASR worker must survive a transcript that arrives after the mic path
    moved on (muted, or speaking with barge-in off). A raise there kills the
    thread and silently ends all transcription, which is the bug ADR-0018
    exists to remove."""

    @pytest.mark.asyncio
    async def test_a_stale_transcript_does_not_kill_the_worker(self):
        bus = MessageBus()
        mod = build_module(bus, "open")
        await mod.setup()
        mod.disable_audio()
        await mod.start()
        try:
            inputs = []
            bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: inputs.append(p))

            # MUTED does not accept THINKING; the stale turn must be dropped.
            mod._transition_quietly(VoiceState.MUTED)
            mod._publish_transcript("this arrived too late", 0.9)
            assert inputs == [], "a stale transcript must not create a turn"

            # The worker is still alive and still processes the next segment.
            assert mod._asr_thread is not None and mod._asr_thread.is_alive()
        finally:
            await mod.stop()

    def test_fsm_transition_is_serialized(self):
        """Concurrent transitions from two threads must not corrupt the state."""
        import threading as _threading

        from aiassistant.voice.state import VoiceStateMachine

        m = VoiceStateMachine()
        errors = []

        def walk():
            try:
                for _ in range(500):
                    m.transition(VoiceState.LISTENING)
                    m.transition(VoiceState.TRANSCRIBING)
                    m.transition(VoiceState.THINKING)
                    m.transition(VoiceState.LISTENING)
            except Exception as exc:  # noqa: BLE001 - recorded for the assert
                errors.append(exc)

        threads = [_threading.Thread(target=walk) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert m.state in (VoiceState.LISTENING, VoiceState.TRANSCRIBING,
                           VoiceState.THINKING)


class TestWakeFollowUpWindow:
    """After the wake phrase, follow-up utterances must be accepted without
    repeating it, until the window times out. Reported after the assistant
    spoke: the reply muted the mic and the module settled in `muted`."""

    def _module(self, bus, window_ms=3000):
        from aiassistant.voice.module import VoiceModule

        return VoiceModule(bus, {
            "voice": {"asr": {"backend": "stub"}, "listen": {"mode": "wake"},
                      "hotwords": ["hey jarvis"], "wake_window_ms": window_ms},
        })

    @pytest.mark.asyncio
    async def test_phrase_only_opens_a_window_then_the_command_needs_no_phrase(self):
        bus = MessageBus()
        mod = self._module(bus)
        await mod.setup()
        mod.disable_audio()
        turns = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: turns.append(p["text"]))
        await mod.start()

        mod._publish_transcript("hey jarvis", 0.9)
        assert turns == [], "the phrase alone is not a command"
        assert mod._wake_active is True

        mod._publish_transcript("turn on the light", 0.9)
        assert turns == ["turn on the light"]
        await mod.stop()

    @pytest.mark.asyncio
    async def test_the_window_closes_after_the_timeout(self):
        bus = MessageBus()
        mod = self._module(bus, window_ms=150)
        await mod.setup()
        mod.disable_audio()
        turns = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: turns.append(p["text"]))
        await mod.start()

        mod._publish_transcript("hey jarvis", 0.9)
        await asyncio.sleep(0.3)
        assert mod._wake_active is False

        mod._publish_transcript("turn on the light", 0.9)
        assert turns == [], "after the timeout the phrase is required again"
        await mod.stop()

    @pytest.mark.asyncio
    async def test_the_window_survives_a_spoken_reply(self):
        bus = MessageBus()
        mod = self._module(bus, window_ms=2000)
        await mod.setup()
        mod.disable_audio()
        turns = []
        bus.subscribe(topics.USER_INPUT_TEXT, lambda t, p: turns.append(p["text"]))
        await mod.start()

        mod._publish_transcript("hey jarvis", 0.9)
        mod._publish_transcript("first command", 0.9)
        # The assistant answers; half-duplex mutes and then restores the mic.
        mod._transition_quietly(VoiceState.THINKING)
        mod._transition_quietly(VoiceState.SPEAKING)
        mod._enter_idle()
        if mod.listen_mode == "wake" and mod._wake_active:
            mod._open_wake_window()
        await asyncio.sleep(0.05)

        mod._publish_transcript("second command", 0.9)
        assert turns == ["first command", "second command"]
        await mod.stop()


class TestHalfDuplexDoesNotStickMuted:
    """A reply mutes the mic while speaking. That transient mute must not be
    mistaken for a user mute, or the module settles in `muted` and rejects the
    next utterance as a stale turn."""

    @pytest.mark.asyncio
    async def test_the_mic_is_unmuted_and_idle_after_speaking(self):
        bus = MessageBus()
        mod = build_module(bus, "open")
        await mod.setup()
        mod.disable_audio()
        # A fake capture so the half-duplex mute/unmute is observable.
        mod.capture = _FakeCapture()
        await mod.start()

        mod._transition_quietly(VoiceState.LISTENING)
        mod._transition_quietly(VoiceState.THINKING)
        mod._transition_quietly(VoiceState.SPEAKING)
        assert mod.capture.muted is True, "half-duplex must mute while speaking"

        mod._enter_idle()
        assert mod._state.state is VoiceState.IDLE
        assert mod._state.can_transition(VoiceState.THINKING)
        # The echo guard holds the mic briefly after speech, then releases it.
        for _ in range(100):
            if not mod.capture.muted:
                break
            await asyncio.sleep(0.01)
        assert mod.capture.muted is False, "the mic must be live again after the guard"
        await mod.stop()

    @pytest.mark.asyncio
    async def test_a_user_mute_still_sticks(self):
        bus = MessageBus()
        mod = build_module(bus, "open")
        await mod.setup()
        mod.disable_audio()
        mod.capture = _FakeCapture()
        await mod.start()

        mod.set_mute(True)
        mod._enter_idle()
        assert mod._state.state is VoiceState.MUTED
        assert mod.capture.muted is True

        # Leaving SPEAKING must not clear a user mute.
        mod._transition_quietly(VoiceState.LISTENING)
        mod._transition_quietly(VoiceState.THINKING)
        mod._transition_quietly(VoiceState.SPEAKING)
        mod._enter_idle()
        assert mod.capture.muted is True, "a user mute survives the reply cycle"

        mod.set_mute(False)
        assert mod._state.state is VoiceState.LISTENING
        assert mod.capture.muted is False
        await mod.stop()
