"""Audio capture and playback on real-time threads.

Raw PCM never crosses the bus: ``bus.publish`` is a synchronous dict fan-out
with no latency bound, and 16 kHz mono PCM is roughly 32 kB/s per subscriber.
Only discrete events leave this package.

Playback is a continuously open ``sounddevice`` output stream in callback mode.
That is what makes interrupt work: stopping is a flag the callback reads, so
sound stops at the next buffer. The pre-refactor code played through an
``afplay`` subprocess with no retained handle, so "interrupt" could not work at
all (docs/architecture/decisions/ADR-0005-voice-merge.md).
"""

import logging
import threading
from collections import deque

logger = logging.getLogger(__name__)

FRAME_MS = 20
TARGET_SAMPLE_RATE = 16000
CHANNELS = 1

# Bounded queues: unbounded growth is a memory leak with a friendly name.
PLAYBACK_QUEUE_FRAMES = 96   # ~2 s at 20 ms frames
SEGMENT_QUEUE_CAP = 2

# PCM silence, used to drain playback after a stop.
_SILENCE = b"\x00\x00"


class AudioUnavailable(RuntimeError):
    """No usable audio device, or the audio backend is missing."""


class SegmentQueue:
    """Bounded queue of completed speech segments.

    Drops the OLDEST on overflow and counts the drop, because a stale segment is
    worse than a missing one: transcribing speech from ten seconds ago produces
    a confusing turn.
    """

    def __init__(self, cap: int = SEGMENT_QUEUE_CAP):
        self.cap = cap
        self._items: deque = deque()
        self._lock = threading.Lock()
        self.dropped = 0

    def put(self, item) -> bool:
        """Enqueue. Returns False when an older item was dropped."""
        with self._lock:
            self._items.append(item)
            overflowed = len(self._items) > self.cap
            if overflowed:
                self._items.popleft()
                self.dropped += 1
            return not overflowed

    def get(self):
        with self._lock:
            return self._items.popleft() if self._items else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class Playback:
    """A callback-mode output stream that can be silenced instantly."""

    def __init__(self, sample_rate: int = TARGET_SAMPLE_RATE, device=None):
        self.sample_rate = sample_rate
        self.device = device
        self._stream = None
        self._frames: deque = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self.frames_played = 0

    # ── Device ───────────────────────────────────────────────

    def open(self) -> None:
        if self._stream is not None:
            return
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on the host
            raise AudioUnavailable(
                "sounddevice is not installed; run: pip install sounddevice"
            ) from exc

        try:
            self._stream = sd.RawOutputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                device=self.device,
                callback=self._callback,
                blocksize=int(self.sample_rate * FRAME_MS / 1000),
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise AudioUnavailable(f"could not open the output device: {exc}") from exc

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logger.debug("closing the output stream raised", exc_info=True)
        finally:
            self._stream = None

    # ── Queue ────────────────────────────────────────────────

    def enqueue(self, pcm: bytes) -> None:
        """Add PCM for playback, dropping the oldest audio on overflow."""
        if not pcm:
            return
        with self._lock:
            self._frames.append(pcm)
            while len(self._frames) > PLAYBACK_QUEUE_FRAMES:
                self._frames.popleft()
        self._idle.clear()

    def stop_now(self) -> None:
        """Silence output and drop what is queued.

        This is the interrupt path: the next callback returns silence, so sound
        stops within one buffer instead of at the end of an utterance.
        """
        self._stop.set()
        with self._lock:
            self._frames.clear()
        self._idle.set()

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        return self._idle.wait(timeout)

    @property
    def pending_frames(self) -> int:
        with self._lock:
            return len(self._frames)

    # ── Callback ─────────────────────────────────────────────

    def _callback(self, outdata, frames, time_info, status) -> None:
        if status:
            logger.debug("output stream status: %s", status)

        if self._stop.is_set():
            # Drained: keep the stream open and emit silence.
            outdata[:] = _SILENCE * frames
            return

        with self._lock:
            pcm = self._frames.popleft() if self._frames else None

        if pcm is None:
            outdata[:] = _SILENCE * frames
            self._idle.set()
            return

        needed = frames * 2  # int16 mono
        if len(pcm) >= needed:
            outdata[:] = pcm[:needed]
            with self._lock:
                if len(pcm) > needed:
                    self._frames.appendleft(pcm[needed:])
            self.frames_played += 1
        else:
            # Short final frame: pad and mark idle.
            outdata[:] = pcm + _SILENCE * max(0, (needed - len(pcm)) // 2)
            self._idle.set()


class Capture:
    """A framing input stream. Frames go to a callback, never to the bus."""

    def __init__(self, sample_rate: int = TARGET_SAMPLE_RATE, device=None,
                 on_frame=None, on_error=None):
        self.sample_rate = sample_rate
        self.device = device
        self.on_frame = on_frame
        self.on_error = on_error
        self._stream = None
        self._muted = False
        self._lock = threading.Lock()

    def open(self) -> None:
        if self._stream is not None:
            return
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on the host
            raise AudioUnavailable(
                "sounddevice is not installed; run: pip install sounddevice"
            ) from exc

        try:
            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                device=self.device,
                callback=self._callback,
                blocksize=int(self.sample_rate * FRAME_MS / 1000),
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise AudioUnavailable(f"could not open the input device: {exc}") from exc

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logger.debug("closing the input stream raised", exc_info=True)
        finally:
            self._stream = None

    def set_muted(self, muted: bool) -> None:
        """Gate capture. Frames are discarded while muted, not buffered."""
        with self._lock:
            self._muted = muted

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("input stream status: %s", status)
        if self.muted:
            return
        if self.on_frame:
            try:
                self.on_frame(bytes(indata))
            except Exception as exc:
                logger.exception("frame handler raised")
                if self.on_error:
                    self.on_error(exc)


def list_devices() -> dict:
    """List audio devices, for first-run detection and the UI (REQ-VOICE-005)."""
    try:
        import sounddevice as sd
    except Exception:
        return {"available": False, "inputs": [], "outputs": []}
    try:
        devices = sd.query_devices()
        return {
            "available": True,
            "inputs": [d["name"] for d in devices if d["max_input_channels"] > 0],
            "outputs": [d["name"] for d in devices if d["max_output_channels"] > 0],
            "default_input": sd.query_devices(kind="input")["name"]
            if sd.query_devices(kind="input") else None,
            "default_output": sd.query_devices(kind="output")["name"]
            if sd.query_devices(kind="output") else None,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc), "inputs": [], "outputs": []}


def rms_level(pcm: bytes) -> float:
    """Normalized RMS of one int16 frame, 0..1. Used for the orb's pulse."""
    if not pcm:
        return 0.0
    import array
    samples = array.array("h")
    usable = len(pcm) - (len(pcm) % 2)
    samples.frombytes(pcm[:usable])
    if not samples:
        return 0.0
    total = sum(s * s for s in samples)
    mean = total / len(samples)
    return min(1.0, (mean ** 0.5) / 32768.0)


def decode_mp3(data: bytes, sample_rate: int = TARGET_SAMPLE_RATE) -> bytes:
    """Decode MP3 bytes to int16 PCM.

    edge-tts emits MP3; sounddevice needs PCM. This is the dependency the first
    design draft missed, and it is required rather than optional.
    """
    try:
        import miniaudio
    except ImportError as exc:
        raise AudioUnavailable(
            "miniaudio is required to decode TTS audio; run: pip install miniaudio"
        ) from exc

    decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=CHANNELS, sample_rate=sample_rate)
    return bytes(decoded.samples)
