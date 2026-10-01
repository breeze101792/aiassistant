"""Shared pytest fixtures for all tests."""
import asyncio
import math
import struct
import time

import pytest
import pytest_asyncio

from aiassistant.bus import topics


@pytest.fixture
def message_bus():
    """Fresh MessageBus for each test."""
    from aiassistant.bus.bus import MessageBus
    return MessageBus()


@pytest.fixture
def temp_dir():
    """Temporary directory, auto-cleaned after test."""
    import tempfile
    import shutil
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


class _MockLLMBackend:
    """Configurable mock LLM for testing brain pipeline without real API calls.

    Set .chat_response and .embed_response before use.
    """

    def __init__(self, model="mock", url=""):
        self.model = model
        self.url = url
        self.api_key = ""
        self.chat_response = {"content": "mock assistant response", "tool_calls": None, "usage": {"total_tokens": 10}}
        self.embed_response = [0.1, 0.2, 0.3]
        self.chat_calls: list[dict] = []
        self.embed_calls: list[list[str]] = []

    def chat(self, messages, tools=None, max_tokens=4096, temperature=0.7):
        self.chat_calls.append({"messages": list(messages), "tools": tools})
        return dict(self.chat_response)

    def embed(self, text):
        self.embed_calls.append(text)
        return list(self.embed_response)

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

    def token_count(self, messages):
        return 100  # small enough not to trigger compression by default


@pytest.fixture
def mock_llm():
    """A mock LLM backend returning canned responses. Tweak .chat_response for specific tests."""
    return _MockLLMBackend()


# ── Voice conversation harness ───────────────────────────────
#
# Drives the voice FSM and wake-window behavior without a device, a model, or a
# network call. Frames are injected and the ASR result is canned, so the
# conversational properties are tested deterministically.

# One frame is 20 ms at 16 kHz mono int16 (voice.segmenter.BYTES_PER_FRAME / 2).
FRAME_SAMPLES = 320
# Peak amplitude well above the default 0.02 energy threshold.
LOUD_AMPLITUDE = 20000
SINE_HZ = 440.0
SILENCE_FRAME = b"\x00\x00" * FRAME_SAMPLES

# Endpointing: 3 frames of silence drains a segment quickly.
ENDPOINT_SILENCE_MS = 60
ENDPOINT_SILENCE_FRAMES = ENDPOINT_SILENCE_MS // 20
# 200 ms of speech, above the 100 ms minimum utterance.
SPEECH_FRAMES = 10

# Bounded poll for a worker result, never a fixed multi-second sleep.
_TERMINAL_POLL_TIMEOUT_S = 1.0
_TERMINAL_POLL_INTERVAL_S = 0.01
# A wait that comfortably exceeds a short test wake window, so the timeout
# task can fire; still bounded so the test cannot hang.
_WINDOW_POLL_TIMEOUT_S = 1.0
# A wait that exceeds the post-playback echo guard (default 400 ms).
_ECHO_GUARD_POLL_TIMEOUT_S = 1.0


def sine_frame(amplitude: int = LOUD_AMPLITUDE,
               samples: int = FRAME_SAMPLES) -> bytes:
    """A real speech-loud frame, no device involved."""
    values = [
        int(amplitude * math.sin(2.0 * math.pi * SINE_HZ * i / 16000))
        for i in range(samples)
    ]
    return struct.pack("<" + "h" * samples, *values)


class FakeCapture:
    """A capture stand-in so half-duplex mute/unmute is observable."""

    def __init__(self):
        self.muted = False
        self.closed = False

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def close(self) -> None:
        self.closed = True


class FakeASR:
    """A fake ASRBackend returning the text it was constructed with."""

    def __init__(self, text: str = "turn off the fan", confidence: float = 0.9):
        self.text = text
        self.confidence = confidence
        self.pcm: list[bytes] = []

    def transcribe(self, audio_bytes: bytes) -> dict:
        self.pcm.append(audio_bytes)
        return {"text": self.text, "confidence": self.confidence, "language": "en"}


class FakeTTS:
    """A TTSBackend that returns one frame of PCM without synthesis."""

    name = "fake_tts"

    def __init__(self):
        self.spoken: list[str] = []

    async def synthesize(self, text: str, voice: str | None = None,
                         speed: float = 1.0) -> bytes:
        if not text.strip():
            return b""
        self.spoken.append(text)
        return b"\x01\x00" * FRAME_SAMPLES

    async def close(self) -> None:
        pass


class FakePlayback:
    """A Playback stand-in that is idle the moment audio is enqueued."""

    def __init__(self):
        self.enqueued: list[bytes] = []
        self.stopped = False

    def enqueue(self, pcm: bytes) -> None:
        self.enqueued.append(pcm)

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        return True

    def stop_now(self) -> None:
        self.stopped = True

    def close(self) -> None:
        pass


class VoiceSession:
    """Test harness around one ``VoiceModule`` running on the event loop.

    The module is built with audio disabled and a fake capture, so no device is
    opened. The test drives the pipeline directly: ``speak`` injects a
    transcript as the ASR worker would, and ``reply`` runs the real
    ``_speak_text`` path (``THINKING -> SPEAKING -> IDLE``), so half-duplex
    gating and the post-playback wake-window refresh are exercised for real.
    """

    def __init__(self, bus, mod, wake_window_ms: int, asr: FakeASR):
        self.bus = bus
        self.mod = mod
        self.wake_window_ms = wake_window_ms
        self.asr = asr
        self.tts = FakeTTS()
        self.playback = FakePlayback()
        self.turns: list[str] = []
        self.states: list[dict] = []
        self.bus.subscribe(topics.USER_INPUT_TEXT,
                           lambda t, p: self.turns.append(p["text"]))
        self.bus.subscribe(topics.VOICE_STATE, lambda t, p: self.states.append(p))

    # ── Lifecycle ────────────────────────────────────────────

    async def setup(self) -> "VoiceSession":
        assert await self.mod.setup(), "voice setup must succeed with fake backends"
        self.mod.disable_audio()
        self.mod.capture = FakeCapture()
        self.mod._asr = self.asr
        self.mod._tts = self.tts
        self.mod.playback = self.playback
        return self

    async def start(self) -> "VoiceSession":
        await self.mod.start()
        return self

    async def stop(self) -> None:
        await self.mod.stop()

    # ── Driving ──────────────────────────────────────────────

    def speak(self, text: str, confidence: float = 0.9) -> None:
        """Simulate a transcript arriving from the ASR worker."""
        self.mod._publish_transcript(text, confidence)

    async def feed_utterance(self, frames: int = SPEECH_FRAMES) -> None:
        """Inject speech plus endpointing silence, then wait for a turn.

        Goes through the real pipeline: frames -> VAD -> segmenter -> queue ->
        the ASR worker -> ``voice.transcribed`` -> a turn.
        """
        for _ in range(frames):
            self.mod._on_frame(sine_frame())
        for _ in range(ENDPOINT_SILENCE_FRAMES):
            self.mod._on_frame(SILENCE_FRAME)
        await self.wait_until(lambda: self.turns)

    async def reply(self, text: str = "okay") -> None:
        """Simulate the assistant answering and finishing playback.

        Runs the real ``_speak_text`` path on the event loop: it transitions to
        SPEAKING (which applies the half-duplex mute), synthesizes, enqueues,
        waits for playback, and calls ``_enter_idle``. The wake window refresh
        after playback is part of that same real path.
        """
        await self.mod._speak_whole(text)
        await asyncio.sleep(0)

    async def wait_for_mic_live(self,
                                timeout: float = _ECHO_GUARD_POLL_TIMEOUT_S) -> bool:
        """Wait out the post-playback echo guard, then report the mic state.

        The mic stays gated briefly after speech so the speaker tail is not
        captured; ``reply`` alone therefore leaves it muted for the guard window.
        """
        return await self.wait_until(
            lambda: self.mod.capture is not None and not self.mod.capture.muted,
            timeout,
        )

    def mute(self, muted: bool = True) -> None:
        self.mod.set_mute(muted)

    # ── Observation ──────────────────────────────────────────

    @property
    def published_states(self) -> list[str]:
        return [s["state"] for s in self.states]

    def idle_muted_pairs(self) -> list[dict]:
        """Every published payload that reports idle *and* muted."""
        return [s for s in self.states if s.get("state") == "idle"
                and s.get("muted") is True]

    async def wait_until(self, predicate, timeout: float = _TERMINAL_POLL_TIMEOUT_S) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            await asyncio.sleep(_TERMINAL_POLL_INTERVAL_S)
        return predicate()

    async def wait_for_wake_window(self, open_: bool,
                                   timeout: float = _WINDOW_POLL_TIMEOUT_S) -> bool:
        return await self.wait_until(lambda: self.mod._wake_active is open_, timeout)


def build_voice_session(bus, mode: str = "open", wake_window_ms: int = 3000,
                        hotwords: list[str] | None = None,
                        text: str = "turn off the fan") -> VoiceSession:
    """Build a ``VoiceSession`` with a fake ASR and no audio device."""
    from aiassistant.voice.module import VoiceModule

    config = {
        "voice": {
            "asr": {"backend": "stub"},
            "tts": {"backend": "text"},
            "vad": {"backend": "energy", "energy_threshold": 0.02},
            "segmenter": {"min_utterance_ms": 100},
            "endpoint_silence_ms": ENDPOINT_SILENCE_MS,
            "listen": {"mode": mode},
            "hotwords": hotwords if hotwords is not None else ["hey jarvis"],
            "wake_window_ms": wake_window_ms,
        },
    }
    session = VoiceSession(bus, VoiceModule(bus, config), wake_window_ms,
                           FakeASR(text))
    return session


@pytest_asyncio.fixture
async def voice_session(request):
    """A started ``VoiceModule`` harness; parametrize the mode with
    ``@pytest.mark.parametrize("voice_session", [...], indirect=True)``.

    The fixture always stops the module and cancels any wake-window task, so no
    task leaks past the test.
    """
    params = getattr(request, "param", {})
    from aiassistant.bus.bus import MessageBus

    mode = params.get("mode", "open")
    wake_window_ms = params.get("wake_window_ms", 3000)
    hotwords = params.get("hotwords")
    text = params.get("text", "turn off the fan")

    bus = MessageBus()
    session = build_voice_session(bus, mode=mode, wake_window_ms=wake_window_ms,
                                  hotwords=hotwords, text=text)
    await session.setup()
    await session.start()
    try:
        yield session
    finally:
        await session.stop()
