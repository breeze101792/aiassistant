"""Endpointing: turn a stream of frames into complete utterances.

The segmenter composes a :class:`~aiassistant.voice.vad.VADBackend` and owns the
buffering, pre-roll, and silence-endpoint state. This is the stage that never
existed: before ADR-0018 nothing called ``on_segment``, so the mic produced a
level and no transcript.

``feed`` runs on the audio callback thread. It does one O(1) deque append, one
``vad.is_speech`` call, and one callback when an utterance completes; it never
blocks on I/O or waits for a lock held by another thread.
"""

from collections import deque
from threading import Lock

from aiassistant.voice.audio import (
    CHANNELS,
    FRAME_MS,
    TARGET_SAMPLE_RATE,
)
from aiassistant.voice.vad import VADBackend

# Bytes in one int16 mono frame.
_FRAME_SAMPLES = TARGET_SAMPLE_RATE * FRAME_MS // 1000
_BYTES_PER_SAMPLE = 2
BYTES_PER_FRAME = _FRAME_SAMPLES * CHANNELS * _BYTES_PER_SAMPLE  # 640

# Defaults from the ADR: 200 ms of pre-roll, 100 ms to reject an energy spike,
# 30 s force-emit (about 960 kB of PCM, a hard memory cap on a stuck VAD).
PREROLL_MS = 200
MIN_UTTERANCE_MS = 100
MAX_UTTERANCE_MS = 30000
# Speech must persist this long before a segment opens. One 20 ms frame of room
# noise is not speech; without this the assistant wakes on every click and
# transcribes constantly.
ONSET_MS = 100


def _frames_for(ms: int) -> int:
    """Frames in ``ms``, floored to whole frames."""
    return max(1, ms // FRAME_MS)


class VadSegmenter:
    """Emit complete utterances from frames, driven by a VAD and silence.

    ``on_utterance(pcm)`` receives complete int16 LE mono 16 kHz PCM: the
    pre-roll followed by every buffered speech frame.
    """

    def __init__(
        self,
        vad: VADBackend,
        on_utterance,
        *,
        sample_rate: int = TARGET_SAMPLE_RATE,
        endpoint_silence_ms: int,
        preroll_ms: int = PREROLL_MS,
        min_utterance_ms: int = MIN_UTTERANCE_MS,
        max_utterance_ms: int = MAX_UTTERANCE_MS,
        onset_ms: int = ONSET_MS,
    ):
        if sample_rate != TARGET_SAMPLE_RATE:
            raise ValueError(
                f"VadSegmenter expects {TARGET_SAMPLE_RATE} Hz; got {sample_rate}"
            )
        self.vad = vad
        self.on_utterance = on_utterance
        self.endpoint_silence_frames = _frames_for(endpoint_silence_ms)
        self.min_utterance_frames = _frames_for(min_utterance_ms)
        self.max_utterance_frames = _frames_for(max_utterance_ms)
        # Consecutive speech frames required to open a segment. A lone spike
        # from a room noise (a click, a door) must not trigger a transcription;
        # a person speaks for far longer than a frame.
        self.onset_required = _frames_for(onset_ms)

        # ``feed`` runs on the audio callback thread; ``flush``/``reset`` run on
        # the event loop (PTT, mute). The lock is held only for the O(1) state
        # update, never across ``on_utterance``.
        self._lock = Lock()

        # Frames seen while idle, so a word onset is not clipped when speech is
        # first detected (a VAD fires a frame or two late).
        self._preroll: deque = deque(maxlen=_frames_for(preroll_ms))
        # A segment is open once speech has persisted past the onset threshold.
        self._buffered: deque | None = None
        # Candidate frames while confirming an onset. Held apart from the
        # pre-roll so they cannot evict it; prepended when the onset confirms.
        self._onset_candidates: list[bytes] = []
        self._onset_run = 0
        self._silence_run = 0
        # Speech frames in the open segment. Used instead of the buffer length
        # for the minimum-length check: pre-roll and trailing silence must not
        # make a single click look like an utterance.
        self._speech_frames = 0

    # ── Audio thread ─────────────────────────────────────────

    def feed(self, frame: bytes) -> None:
        """Classify one frame and endpoint when silence runs long enough."""
        is_speech = self.vad.is_speech(frame)
        utterance = None
        with self._lock:
            if self._buffered is None:
                # Idle: collect candidate frames and require a sustained onset
                # before opening a segment. Candidates are held apart from the
                # pre-roll so they cannot evict it.
                if not is_speech:
                    self._onset_run = 0
                    self._onset_candidates.clear()
                    self._preroll.append(frame)
                    return
                self._onset_run += 1
                self._onset_candidates.append(frame)
                if self._onset_run < self.onset_required:
                    return
                # Confirmed: the utterance is the pre-roll (the sound just
                # before speech) followed by the onset frames.
                self._buffered = deque(self._preroll)
                self._buffered.extend(self._onset_candidates)
                self._preroll.clear()
                self._onset_candidates.clear()
                self._speech_frames = self._onset_run
                self._onset_run = 0
                self._silence_run = 0
                return

            self._buffered.append(frame)
            if is_speech:
                self._silence_run = 0
                self._speech_frames += 1
            else:
                self._silence_run += 1

            # A VAD wedged on "speech" must not grow memory without bound.
            if (len(self._buffered) >= self.max_utterance_frames
                    or self._silence_run >= self.endpoint_silence_frames):
                utterance = self._take_utterance()
        if utterance:
            self.on_utterance(utterance)

    def flush(self) -> None:
        """Force-emit the current partial utterance, if any."""
        with self._lock:
            utterance = self._take_utterance()
        if utterance:
            self.on_utterance(utterance)

    def reset(self) -> None:
        """Drop the current partial utterance and pre-roll without emitting."""
        with self._lock:
            self._buffered = None
            self._preroll.clear()
            self._onset_candidates.clear()
            self._onset_run = 0
            self._silence_run = 0
            self._speech_frames = 0
            self.vad.reset()

    # ── Internal ─────────────────────────────────────────────

    def _take_utterance(self) -> bytes | None:
        """Detach the open utterance as PCM, or None if it is too short.

        The caller holds the lock; ``on_utterance`` is invoked outside it so a
        slow callback cannot stall the audio thread or the event loop.
        """
        buffered, self._buffered = self._buffered, None
        speech_frames, self._speech_frames = self._speech_frames, 0
        self._silence_run = 0
        if buffered is None or speech_frames < self.min_utterance_frames:
            # An energy spike, not speech: too short to be worth a request.
            return None
        return b"".join(buffered)
