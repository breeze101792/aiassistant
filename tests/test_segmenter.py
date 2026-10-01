"""VadSegmenter tests: endpointing, pre-roll, min/max bounds (ADR-0018).

Deterministic by construction: the VAD is a scripted fake (a list of booleans),
so no DSP is involved and every assertion is about segmenter policy, not signal
processing. Frames are identified by their first byte, so the emitted PCM shows
exactly which frames were buffered and in what order.
"""

import pytest

from aiassistant.voice.audio import FRAME_MS
from aiassistant.voice.segmenter import (
    ONSET_MS,
    BYTES_PER_FRAME,
    MAX_UTTERANCE_MS,
    MIN_UTTERANCE_MS,
    PREROLL_MS,
    VadSegmenter,
)
from aiassistant.voice.vad import VADBackend

# One frame of tagged silence/padding: the tag is the first byte.
FRAME_TAG_BYTES = 1


def tagged_frame(tag: int) -> bytes:
    """A frame of BYTES_PER_FRAME whose first byte identifies it."""
    return bytes([tag]) + b"\x00" * (BYTES_PER_FRAME - FRAME_TAG_BYTES)


class FakeVAD(VADBackend):
    """A VAD driven by a script: one boolean per frame; last value repeats."""

    def __init__(self, script: list[bool]):
        self.script = list(script)
        self.calls = 0
        self.reset_calls = 0

    def is_speech(self, frame: bytes) -> bool:
        self.calls += 1
        if self.calls <= len(self.script):
            return self.script[self.calls - 1]
        return self.script[-1] if self.script else False

    def reset(self) -> None:
        self.reset_calls += 1


def frames_for(ms: int) -> int:
    return ms // FRAME_MS


def collect_segmenter(script: list[bool], **kwargs):
    """Build a segmenter, a capture list, and feed the script frame by frame."""
    emitted: list[bytes] = []
    vad = FakeVAD(script)
    seg = VadSegmenter(vad, emitted.append, **kwargs)
    return seg, vad, emitted


class TestEndpointing:
    def test_endpoint_fires_after_exactly_the_silence_run(self):
        silence_frames = frames_for(60)
        speech_frames = frames_for(MIN_UTTERANCE_MS)
        script = [True] * speech_frames + [False] * (silence_frames + 1)
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=60)

        for _ in range(speech_frames):
            seg.feed(tagged_frame(1))
        # Then silence_frames - 1 silence frames: not yet.
        for _ in range(silence_frames - 1):
            seg.feed(tagged_frame(9))
        assert emitted == [], "one short of the endpoint run must not emit"

        seg.feed(tagged_frame(9))
        assert len(emitted) == 1, "the endpoint frame must emit"

    def test_a_speech_frame_resets_the_silence_counter(self):
        silence_frames = frames_for(60)
        speech_frames = frames_for(MIN_UTTERANCE_MS)
        script = [True] * speech_frames + [False] * (silence_frames - 1) \
            + [True] + [False] * silence_frames
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=60)
        for _ in range(speech_frames):
            seg.feed(tagged_frame(1))
        for _ in range(silence_frames - 1):
            seg.feed(tagged_frame(9))
        assert emitted == [], "one short of the endpoint run must not emit"
        # A speech frame here restarts the run instead of completing it.
        seg.feed(tagged_frame(2))
        for _ in range(silence_frames - 1):
            seg.feed(tagged_frame(9))
        assert emitted == [], "the counter restarted at the speech frame"
        seg.feed(tagged_frame(9))
        assert len(emitted) == 1


class TestPreroll:
    def test_preroll_frames_precede_the_segment(self):
        preroll_frames = frames_for(PREROLL_MS)  # 10 frames
        # First ten frames silence (pre-roll), then enough speech to be an
        # utterance, then silence to endpoint.
        script = [False] * preroll_frames + [True] * frames_for(200) \
            + [False] * frames_for(60)
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=60)

        # Feed only the pre-roll frames plus one speech frame; the emitted PCM is
        # checked after the endpoint, so feed the whole script.
        for i in range(preroll_frames):
            seg.feed(tagged_frame(0x10 + i))
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(0x80))
        for _ in range(frames_for(60)):
            seg.feed(tagged_frame(0x99))

        assert len(emitted) == 1
        pcm = emitted[0]
        tags = [pcm[i * BYTES_PER_FRAME] for i in range(len(pcm) // BYTES_PER_FRAME)]
        assert tags[:preroll_frames] == list(range(0x10, 0x10 + preroll_frames)), (
            "the emitted PCM must start with the pre-roll frames"
        )
        assert 0x80 in tags, "speech frames follow the pre-roll"

    def test_preroll_is_bounded(self):
        """A long run of idle silence must not all be prepended."""
        preroll_frames = frames_for(PREROLL_MS)
        script = [False] * (preroll_frames * 5) + [True] * frames_for(200) \
            + [False] * frames_for(60)
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=60)
        for _ in range(preroll_frames * 5):
            seg.feed(tagged_frame(0x10))  # same tag; only the count matters
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(0x80))
        for _ in range(frames_for(60)):
            seg.feed(tagged_frame(0x99))
        assert len(emitted) == 1
        # Count whole frames, not bytes: a tag byte repeats.
        tags = [emitted[0][i * BYTES_PER_FRAME]
                for i in range(len(emitted[0]) // BYTES_PER_FRAME)]
        assert tags.count(0x10) == preroll_frames, (
            "pre-roll is capped at preroll_ms worth of frames"
        )


class TestMinUtterance:
    def test_a_single_frame_click_does_not_emit(self):
        """min_utterance_ms counts speech frames, so one frame is a click."""
        # endpoint_silence_ms=20 -> a single silence frame ends the segment.
        seg, _, emitted = collect_segmenter([True, False], endpoint_silence_ms=20)
        seg.feed(tagged_frame(1))
        seg.feed(tagged_frame(9))
        assert emitted == [], "a one-frame click must be rejected"

    def test_an_utterance_at_the_minimum_emits(self):
        min_frames = frames_for(MIN_UTTERANCE_MS)
        script = [True] * min_frames + [False] * 2
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=20)
        for _ in range(min_frames):
            seg.feed(tagged_frame(1))
        seg.feed(tagged_frame(9))
        assert len(emitted) == 1, "exactly min_utterance_ms of speech must emit"

    def test_one_frame_below_the_minimum_does_not_emit(self):
        min_frames = frames_for(MIN_UTTERANCE_MS)
        assert min_frames > 1
        script = [True] * (min_frames - 1) + [False] * 2
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=20)
        for _ in range(min_frames - 1):
            seg.feed(tagged_frame(1))
        seg.feed(tagged_frame(9))
        assert emitted == []

    def test_preroll_cannot_make_a_click_an_utterance(self):
        """The min check uses speech frames, not buffer length. Ten frames of
        pre-roll plus one speech frame is still a click."""
        preroll_frames = frames_for(PREROLL_MS)
        seg, _, emitted = collect_segmenter(
            [False] * preroll_frames + [True] + [False] * 2,
            endpoint_silence_ms=20,
        )
        for i in range(preroll_frames):
            seg.feed(tagged_frame(0x10 + i))
        seg.feed(tagged_frame(0x80))
        seg.feed(tagged_frame(0x99))
        assert emitted == [], (
            "pre-roll frames must not satisfy the minimum-speech check"
        )


class TestMaxUtterance:
    def test_max_force_emits_even_without_silence(self):
        """A VAD wedged on speech must not grow memory without bound."""
        max_frames = frames_for(100)
        # onset_ms=20 (one frame) so the onset does not consume the cap; this
        # test is about the memory bound, not noise rejection.
        seg, _, emitted = collect_segmenter(
            [True] * (max_frames + 5),
            endpoint_silence_ms=2000,  # never reached in this test
            max_utterance_ms=100,
            onset_ms=20,
        )
        for _ in range(max_frames):
            seg.feed(tagged_frame(1))
        assert len(emitted) == 1, "the buffer cap must force an emit"
        assert len(emitted[0]) <= max_frames * BYTES_PER_FRAME

    def test_default_max_is_thirty_seconds(self):
        assert MAX_UTTERANCE_MS == 30000


class TestFlushReset:
    def test_flush_emits_an_open_partial(self):
        seg, _, emitted = collect_segmenter([True] * frames_for(200),
                                            endpoint_silence_ms=2000)
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(1))
        assert emitted == [], "no endpoint yet"
        seg.flush()
        assert len(emitted) == 1, "flush must finalize the open utterance"

    def test_flush_with_nothing_open_is_a_noop(self):
        seg, _, emitted = collect_segmenter([False], endpoint_silence_ms=2000)
        seg.feed(tagged_frame(9))
        seg.flush()
        assert emitted == []

    def test_flush_rejects_an_open_click(self):
        seg, _, emitted = collect_segmenter([True, False], endpoint_silence_ms=2000)
        seg.feed(tagged_frame(1))  # one speech frame, no endpoint yet
        seg.flush()
        assert emitted == [], "flush still applies the minimum-speech check"

    def test_reset_discards_the_open_partial(self):
        seg, vad, emitted = collect_segmenter([True] * frames_for(200),
                                              endpoint_silence_ms=2000)
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(1))
        seg.reset()
        seg.flush()
        assert emitted == [], "reset must discard without emitting"
        assert vad.reset_calls == 1, "reset must reset the VAD too"

    def test_reset_clears_the_preroll(self):
        preroll_frames = frames_for(PREROLL_MS)
        seg, _, emitted = collect_segmenter(
            [False] * preroll_frames + [True] * frames_for(200)
            + [False] * frames_for(60),
            endpoint_silence_ms=60,
        )
        for i in range(preroll_frames):
            seg.feed(tagged_frame(0x10 + i))
        seg.reset()
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(0x80))
        for _ in range(frames_for(60)):
            seg.feed(tagged_frame(0x99))
        assert len(emitted) == 1
        tags = [emitted[0][i * BYTES_PER_FRAME]
                for i in range(len(emitted[0]) // BYTES_PER_FRAME)]
        assert not any(0x10 <= t < 0x20 for t in tags), (
            "pre-roll captured before reset must not reappear"
        )


class TestFrameContract:
    def test_emitted_pcm_is_a_multiple_of_the_frame_size(self):
        script = [False] * frames_for(PREROLL_MS) + [True] * frames_for(200) \
            + [False] * frames_for(60)
        seg, _, emitted = collect_segmenter(script, endpoint_silence_ms=60)
        for _ in range(frames_for(PREROLL_MS)):
            seg.feed(tagged_frame(0x10))
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(0x80))
        for _ in range(frames_for(60)):
            seg.feed(tagged_frame(0x99))
        assert emitted
        assert len(emitted[0]) % BYTES_PER_FRAME == 0

    def test_bytes_per_frame_is_the_20ms_contract(self):
        from aiassistant.voice.audio import CHANNELS, TARGET_SAMPLE_RATE

        expected = TARGET_SAMPLE_RATE * FRAME_MS // 1000 * CHANNELS * 2
        assert BYTES_PER_FRAME == expected == 640

    def test_a_non_16k_sample_rate_is_rejected(self):
        with pytest.raises(ValueError):
            VadSegmenter(FakeVAD([False]), lambda _pcm: None,
                         sample_rate=8000, endpoint_silence_ms=200)


class TestThreadSafety:
    """feed() runs on the audio thread while flush()/reset() run on the event
    loop (PTT, mute). Without a lock, reset() nulling `_buffered` between the
    check and the append raises AttributeError on the audio callback, and a
    torn join can emit a partial utterance."""

    def test_concurrent_feed_and_reset_never_raise(self):
        import threading

        emitted = []
        seg = VadSegmenter(FakeVAD([True]), emitted.append,
                           endpoint_silence_ms=200, preroll_ms=20,
                           min_utterance_ms=40)
        errors = []
        stop = threading.Event()

        def producer():
            try:
                while not stop.is_set():
                    seg.feed(tagged_frame(0x80))
            except Exception as exc:  # noqa: BLE001 - recorded for the assert
                errors.append(exc)

        def churner():
            try:
                for _ in range(2000):
                    seg.reset()
                    seg.flush()
            except Exception as exc:  # noqa: BLE001 - recorded for the assert
                errors.append(exc)

        workers = [threading.Thread(target=producer) for _ in range(2)]
        workers.append(threading.Thread(target=churner))
        for t in workers:
            t.start()
        workers[-1].join()
        stop.set()
        for t in workers:
            t.join()

        assert errors == []
        for utterance in emitted:
            assert len(utterance) % BYTES_PER_FRAME == 0

    def test_reset_then_feed_starts_a_clean_segment(self):
        emitted = []
        # onset_ms=20 (one frame): this test is about reset, not onset.
        seg = VadSegmenter(FakeVAD([True]), emitted.append,
                           endpoint_silence_ms=200, preroll_ms=20,
                           min_utterance_ms=40, onset_ms=20)
        seg.feed(tagged_frame(0x80))
        seg.feed(tagged_frame(0x80))
        seg.reset()
        seg.feed(tagged_frame(0x80))
        seg.feed(tagged_frame(0x80))
        seg.flush()
        assert emitted
        assert len(emitted[0]) == 2 * BYTES_PER_FRAME


class TestOnsetRejection:
    """A lone room-noise spike must not open a segment.

    Without onset debouncing the assistant opens a segment on any frame above
    the energy threshold and transcribes constantly; a person speaks for far
    longer than one 20 ms frame.
    """

    def test_a_short_spike_never_opens_a_segment(self):
        # onset defaults to 100 ms = 5 frames; a 2-frame spike is not speech.
        seg, _, emitted = collect_segmenter(
            [True, True] + [False] * frames_for(200), endpoint_silence_ms=200,
        )
        for _ in range(2):
            seg.feed(tagged_frame(0x80))
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(0x00))
        assert emitted == [], "a 2-frame spike must not be an utterance"

    def test_sustained_speech_over_the_onset_does_open_a_segment(self):
        onset = frames_for(ONSET_MS)
        seg, _, emitted = collect_segmenter(
            [True] * (onset + frames_for(100)) + [False] * frames_for(200),
            endpoint_silence_ms=200,
        )
        for _ in range(onset + frames_for(100)):
            seg.feed(tagged_frame(0x80))
        for _ in range(frames_for(200)):
            seg.feed(tagged_frame(0x00))
        assert len(emitted) == 1, "sustained speech must open a segment"

    def test_a_break_resets_the_onset(self):
        """Speech, a gap, then speech shorter than the onset must not fire."""
        # Two bursts each below the onset, separated by silence.
        burst = frames_for(ONSET_MS) - 1
        for _ in range(3):
            seg, _, emitted = collect_segmenter(
                [True] * burst + [False] * 2, endpoint_silence_ms=200,
            )
            for _ in range(burst):
                seg.feed(tagged_frame(0x80))
            for _ in range(2):
                seg.feed(tagged_frame(0x00))
            assert emitted == []
