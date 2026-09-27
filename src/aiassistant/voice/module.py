"""The voice module: one owner of the duplex audio path.

Merged from the old ``ears`` and ``mouth`` modules. Two modules owning one
duplex device produced two real defects, both of which this merge fixes:

* Interrupt could not stop playback: the old code played through an ``afplay``
  subprocess with no retained handle.
* Barge-in was impossible by construction: the mic was hard-muted over the bus
  for the whole utterance.

One module can stop its own playback and decide when the mic is live, so both
are tractable. See ADR-0005 and docs/requirements/features/voice-pipeline.md.

Raw PCM never crosses the bus. Only state, transcripts, and level samples do.
"""

import asyncio
import logging
import time

from aiassistant.base import BaseModule
from aiassistant.bus import topics
from aiassistant.voice import wake as wake_mod
from aiassistant.voice.audio import (
    AudioUnavailable,
    Capture,
    Playback,
    decode_mp3,
    list_devices,
    rms_level,
)
from aiassistant.voice.state import InvalidTransition, VoiceState, VoiceStateMachine
from aiassistant.voice.tts.chunker import SentenceChunker

logger = logging.getLogger(__name__)

# Level publishes are coalesced to this rate. The orb wants smooth input and the
# bus wants low volume; latest-wins, so dropping samples is correct.
LEVEL_HZ = 20

# Sentence chunking targets. Placeholders to tune.
CHUNK_MIN_CHARS = 40
CHUNK_MAX_CHARS = 240


class VoiceModule(BaseModule):
    """Speech in, speech out, and the state both share."""

    module_name = "voice"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        voice_cfg = config.get("voice", {})
        tts_cfg = config.get("voice_tts", {})

        self.listen_mode = voice_cfg.get("listen", {}).get("mode", "ptt")
        self.asr_backend_name = voice_cfg.get("backend", "stub")
        self.hotwords = voice_cfg.get("hotwords", ["hey assistant"])
        self.endpoint_silence_ms = voice_cfg.get("endpoint_silence_ms", 2000)
        self.tts_backend_name = tts_cfg.get("backend", "text")
        self.tts_voice = tts_cfg.get("voice", "en-US-AriaNeural")
        self.tts_speed = tts_cfg.get("speed", 1.0)
        self.speak_text_turns = voice_cfg.get("speak_text_turns", False)
        self.barge_in_enabled = voice_cfg.get("barge_in", {}).get("enabled", False)

        self._asr = None
        self._tts = None
        self._detector: wake_mod.WakeDetector = wake_mod.create_detector(
            self.listen_mode, self.hotwords,
        )
        self._state = VoiceStateMachine(on_change=self._on_state_change)
        self._chunker = SentenceChunker(CHUNK_MIN_CHARS, CHUNK_MAX_CHARS)

        self.capture: Capture | None = None
        self.playback: Playback | None = None
        self._speak_task: asyncio.Task | None = None
        self._level_last_published = 0.0
        self._last_level = 0.0
        self._audio_available = True
        self._device_error = ""
        # Set by tests (or a headless runner) to avoid opening real devices.
        self._audio_disabled = False

    # ── Lifecycle ────────────────────────────────────────────

    async def setup(self) -> bool:
        self._asr = self._build_asr()
        self._tts = self._build_tts()

        devices = list_devices()
        if not devices.get("available"):
            self._audio_available = False
            self._device_error = devices.get("error", "audio backend unavailable")
            logger.warning("Audio devices unavailable: %s", self._device_error)
        else:
            logger.info(
                "Audio devices — in: %s, out: %s",
                devices.get("default_input"), devices.get("default_output"),
            )
        logger.info(
            "Voice setup — asr=%s tts=%s listen=%s audio=%s",
            self.asr_backend_name, self.tts_backend_name, self.listen_mode,
            self._audio_available,
        )
        return True

    async def start(self) -> None:
        self.bus.subscribe(topics.VOICE_SPEAK, self._handle_speak)
        self.bus.subscribe(topics.COMMAND_AGENT_INTERRUPT, self._handle_interrupt)
        self.bus.subscribe(topics.COMMAND_VOICE_MUTE, self._handle_mute_command)
        self.bus.subscribe(topics.COMMAND_VOICE_PTT_START, self._handle_ptt_start)
        self.bus.subscribe(topics.COMMAND_VOICE_PTT_END, self._handle_ptt_end)

        self._open_audio()
        self._enter_idle()
        logger.info("Voice started — mode=%s", self.listen_mode)

    async def stop(self) -> None:
        await self._cancel_speak_task()
        if self.capture is not None:
            self.capture.close()
            self.capture = None
        if self.playback is not None:
            self.playback.stop_now()
            self.playback.close()
            self.playback = None
        if self._tts is not None:
            await self._tts.close()
        self._state.transition(VoiceState.IDLE)
        logger.info("Voice stopped")

    async def health(self) -> dict:
        return {
            "status": "ok",
            "details": {
                "state": self._state.state.value,
                "asr": self.asr_backend_name,
                "tts": self.tts_backend_name,
                "audio": self._audio_available,
            },
        }

    def disable_audio(self) -> None:
        """Run without opening real audio devices.

        Used by tests and by a headless runner: opening a device in a unit test
        can segfault the host audio stack, which makes the suite unreliable.
        """
        self._audio_disabled = True
        self._audio_available = False

    # ── Audio device management ──────────────────────────────

    def _open_audio(self) -> None:
        """Open capture and playback. A failure degrades, never crashes."""
        if not self._audio_available or self._audio_disabled:
            return
        try:
            self.playback = Playback()
            self.playback.open()
        except AudioUnavailable as exc:
            self._fail("ERR-VOICE-NO-OUTPUT", str(exc))
            self.playback = None

        if self.listen_mode == "ptt":
            # Push-to-talk opens capture on demand; nothing to do yet.
            return
        try:
            self.capture = Capture(on_frame=self._on_frame, on_error=self._on_capture_error)
            self.capture.open()
        except AudioUnavailable as exc:
            self._fail("ERR-VOICE-NO-INPUT", str(exc))
            self.capture = None

    def _fail(self, code: str, detail: str) -> None:
        """Report a classified audio error and keep running (REQ-ERR-002)."""
        logger.error("%s: %s", code, detail)
        self._device_error = detail
        self.bus.publish(topics.VOICE_STATE, {"state": VoiceState.ERROR.value})
        self.bus.publish(topics.AGENT_TURN_ERROR, {
            "message": detail,
            "class": "audio",
            "hint": "Check the audio device and permissions, then retry from the UI.",
            "code": code,
        })

    # ── Real-time plane ──────────────────────────────────────

    def _on_frame(self, pcm: bytes) -> None:
        """Real-time callback: compute a level, publish it, hand off the frame.

        Runs on the audio thread. It must not block, allocate heavily, or touch
        the bus beyond a fire-and-forget publish.
        """
        level = rms_level(pcm)
        self._last_level = level
        now = time.monotonic()
        if now - self._level_last_published >= 1.0 / LEVEL_HZ:
            self._level_last_published = now
            self.bus.publish(topics.VOICE_LEVEL, {
                "level": round(level, 4), "source": "input", "ts": time.time(),
            })

    def _on_capture_error(self, exc: Exception) -> None:
        self._fail("ERR-VOICE-ASR-FAIL", f"capture error: {exc}")

    # ── ASR ──────────────────────────────────────────────────

    def on_segment(self, wav_bytes: bytes) -> None:
        """Transcribe a completed speech segment and publish the result.

        Runs from a worker thread, so ASR never blocks the event loop. The
        result is published on the loop.
        """
        if self._asr is None:
            return
        try:
            result = self._asr.transcribe(wav_bytes)
        except Exception as exc:
            self._fail("ERR-VOICE-ASR-FAIL", f"transcription failed: {exc}")
            return

        text = (result.get("text") or "").strip()
        if not text:
            return
        confidence = result.get("confidence", 1.0)
        self._publish_transcript(text, confidence)

    def _publish_transcript(self, text: str, confidence: float = 1.0) -> None:
        """Apply wake gating and turn the transcript into a turn."""
        self.bus.publish(topics.VOICE_TRANSCRIBED, {"text": text, "confidence": confidence})

        if self.listen_mode in ("wake", "ptt"):
            command = self._detector.strip_wake(text)
            if self.listen_mode == "wake" and not self._detector.should_wake(text):
                logger.debug("Wake phrase absent; segment discarded")
                self._enter_idle()
                return
            if not command:
                # Only the wake phrase was spoken: open a short capture window.
                logger.info("Wake phrase heard with no command; listening for one")
                self.bus.publish(topics.VOICE_STATE, {"state": VoiceState.LISTENING.value})
                return
            text = command

        self._state.transition(VoiceState.THINKING)
        self.bus.user_input(text, channel=topics.CHANNEL_VOICE)

    # ── TTS and playback ─────────────────────────────────────

    async def _handle_speak(self, topic: str, payload: dict) -> None:
        text = (payload.get("text") or "").strip()
        interrupt = bool(payload.get("interrupt", False))
        source = payload.get("source", "")

        if interrupt:
            # The agent cancelled a turn: stop and go quiet.
            await self.interrupt_playback()
            return

        if not text:
            return
        if not self._should_speak(payload):
            return

        await self._cancel_speak_task()
        self._chunker.reset()
        self._speak_task = asyncio.ensure_future(self._speak_whole(text))

    def _should_speak(self, payload: dict) -> bool:
        """Whether this text should be voiced.

        Text-originated turns are silent unless configured otherwise
        (REQ-CONV-005). The channel is already checked by the agent, so this is
        a second, local guard.
        """
        channel = payload.get("channel")
        if channel and not topics.should_speak(channel):
            return self.speak_text_turns
        return True

    async def _speak_whole(self, text: str) -> None:
        """Synthesize a complete utterance and play it."""
        await self._speak_text(text, first=True)

    async def _speak_text(self, text: str, first: bool = False) -> None:
        if self._tts is None or not text.strip():
            return
        if first:
            self._state.transition(VoiceState.SPEAKING)

        try:
            audio = await self._tts.synthesize(text, self.tts_voice, self.tts_speed)
        except Exception as exc:
            self._fail("ERR-VOICE-TTS-FAIL", f"synthesis failed: {exc}")
            self._enter_idle()
            return

        if not audio:
            self._enter_idle()
            return

        pcm = audio
        if getattr(self._tts, "name", "") == "edge_tts":
            try:
                pcm = decode_mp3(audio)
            except AudioUnavailable as exc:
                self._fail("ERR-VOICE-DECODE-FAIL", str(exc))
                self._enter_idle()
                return

        if self.playback is None:
            self._enter_idle()
            return

        self.playback.enqueue(pcm)
        # Level from the output, so the orb pulses while the assistant speaks.
        asyncio.ensure_future(self._publish_output_level(pcm))
        await asyncio.get_running_loop().run_in_executor(None, self.playback.wait_until_idle, 30.0)
        self._enter_idle()

    async def _publish_output_level(self, pcm: bytes) -> None:
        self.bus.publish(topics.VOICE_LEVEL, {
            "level": round(rms_level(pcm), 4), "source": "output", "ts": time.time(),
        })

    async def _cancel_speak_task(self) -> None:
        task = self._speak_task
        self._speak_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def interrupt_playback(self) -> None:
        """The ordered stop: silence output, then return to idle.

        Called by the agent's cancel sequence. Stopping is a flag check in the
        audio callback, so audio stops within one buffer.
        """
        if self.playback is not None:
            self.playback.stop_now()
        await self._cancel_speak_task()
        self._chunker.reset()
        self._enter_idle()

    # ── Commands ─────────────────────────────────────────────

    async def _handle_interrupt(self, topic: str, payload: dict) -> None:
        await self.interrupt_playback()

    async def _handle_mute_command(self, topic: str, payload: dict) -> None:
        self.set_mute(bool(payload.get("muted", True)))

    async def _handle_ptt_start(self, topic: str, payload: dict) -> None:
        self.arm()

    async def _handle_ptt_end(self, topic: str, payload: dict) -> None:
        self.disarm()

    def set_mute(self, muted: bool) -> None:
        """Stop capture immediately and publish the state (REQ-WAKE-007)."""
        if self.capture is not None:
            self.capture.set_muted(muted)
        state = VoiceState.MUTED if muted else (
            VoiceState.LISTENING if self.listen_mode != "ptt" else VoiceState.IDLE
        )
        try:
            self._state.transition(state)
        except InvalidTransition:
            logger.debug("mute transition %s -> %s suppressed", self._state.state, state)
        self.bus.publish(topics.VOICE_STATE, {"state": state.value, "muted": muted})

    def arm(self) -> None:
        """Push-to-talk pressed: start capturing."""
        if self.listen_mode != "ptt":
            return
        if self.capture is None and self._audio_available:
            try:
                self.capture = Capture(on_frame=self._on_frame,
                                       on_error=self._on_capture_error)
                self.capture.open()
            except AudioUnavailable as exc:
                self._fail("ERR-VOICE-NO-INPUT", str(exc))
                return
        if self.capture is not None:
            self.capture.set_muted(False)
        self._transition_quietly(VoiceState.LISTENING)
        self.bus.publish(topics.VOICE_STATE, {"state": VoiceState.LISTENING.value})

    def disarm(self) -> None:
        """Push-to-talk released: finalize the utterance and transcribe."""
        self._enter_idle()

    # ── State helpers ────────────────────────────────────────

    def _enter_idle(self) -> None:
        target = VoiceState.MUTED if (self.capture is not None and self.capture.muted) \
            else VoiceState.IDLE
        self._transition_quietly(target)
        self.bus.publish(topics.VOICE_STATE, {"state": target.value})

    def _transition_quietly(self, target: VoiceState) -> None:
        """Move state, ignoring an illegal pair rather than raising at runtime.

        Transitions are validated in the FSM so tests catch design errors, but a
        live audio path must never crash on an unexpected ordering.
        """
        try:
            self._state.transition(target)
        except InvalidTransition:
            logger.debug("suppressed transition %s -> %s",
                         self._state.state.value, target.value)

    def _on_state_change(self, previous: VoiceState, current: VoiceState) -> None:
        self.bus.publish(topics.VOICE_STATE, {
            "state": current.value, "previous": previous.value,
        })
        self._apply_half_duplex(current)

    def _apply_half_duplex(self, current: VoiceState) -> None:
        """Gate the mic while speaking.

        Half-duplex by design: with speakers and no echo cancellation an open
        mic hears the assistant and self-triggers (ADR-0011). When barge-in is
        explicitly enabled the mic stays live, which may self-trigger unless AEC
        is present.
        """
        if self.capture is None:
            return
        if self.barge_in_enabled:
            return
        self.capture.set_muted(current is VoiceState.SPEAKING)

    # ── Backend construction ─────────────────────────────────

    def _build_asr(self):
        name = self.asr_backend_name
        if name == "stub":
            from aiassistant.voice.asr.asr_backends.stub import StubASR
            return StubASR()
        if name == "funasr":
            from aiassistant.voice.asr.asr_backends.funasr import FunASRBackend
            return FunASRBackend()
        if name == "whisper":
            from aiassistant.voice.asr.asr_backends.whisper import WhisperBackend
            return WhisperBackend()

        logger.warning("Unknown ASR backend %r; using stub", name)
        from aiassistant.voice.asr.asr_backends.stub import StubASR
        return StubASR()

    def _build_tts(self):
        name = self.tts_backend_name
        if name == "edge_tts":
            from aiassistant.voice.tts.tts_backends.edge_tts import EdgeTTSBackend
            return EdgeTTSBackend(voice=self.tts_voice, speed=self.tts_speed)
        if name == "text":
            from aiassistant.voice.tts.tts_backends.text import TextTTS
            return TextTTS()
        logger.warning("Unknown TTS backend %r; using text", name)
        from aiassistant.voice.tts.tts_backends.text import TextTTS
        return TextTTS()
