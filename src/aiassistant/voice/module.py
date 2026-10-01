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
import threading
import time

from aiassistant.base import BaseModule
from aiassistant.bus import topics
from aiassistant.voice import factory as voice_factory
from aiassistant.voice import wake as wake_mod
from aiassistant.voice.audio import (
    AudioUnavailable,
    Capture,
    Playback,
    SegmentQueue,
    decode_mp3,
    list_devices,
    rms_level,
)
from aiassistant.voice.segmenter import VadSegmenter
from aiassistant.voice.state import InvalidTransition, VoiceState, VoiceStateMachine
from aiassistant.voice.tts.chunker import SentenceChunker

logger = logging.getLogger(__name__)

# Level publishes are coalesced to this rate. The orb wants smooth input and the
# bus wants low volume; latest-wins, so dropping samples is correct.
LEVEL_HZ = 20

# Sentence chunking targets. Placeholders to tune.
CHUNK_MIN_CHARS = 40
CHUNK_MAX_CHARS = 240

# Seconds to wait for the ASR worker to drain and exit during shutdown. ASR is
# a network or model call and may be past the point of cancelling.
ASR_WORKER_JOIN_TIMEOUT = 2.0

# Wake mode: how long a follow-up utterance is accepted without repeating the
# wake phrase after the phrase was heard.
DEFAULT_WAKE_WINDOW_MS = 8000

# After playback stops, keep the mic gated this long so the speaker's tail and
# the room reverb are not captured as a new utterance (the assistant otherwise
# hears itself and starts a turn).
DEFAULT_ECHO_GUARD_MS = 400


class VoiceModule(BaseModule):
    """Speech in, speech out, and the state both share."""

    module_name = "voice"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        voice_cfg = config.get("voice", {})
        # Legacy flat keys are accepted so a config that predates ADR-0018 still
        # builds; the migration writes the nested form, this is the fallback.
        asr_cfg = voice_cfg.get("asr") or {}
        if "backend" not in asr_cfg and voice_cfg.get("backend"):
            asr_cfg = {"backend": voice_cfg["backend"]}
        tts_cfg = voice_cfg.get("tts") or config.get("voice_tts") or {}
        vad_cfg = voice_cfg.get("vad") or {}
        segmenter_cfg = voice_cfg.get("segmenter") or {}

        self.listen_mode = voice_cfg.get("listen", {}).get("mode", "ptt")
        self._asr_cfg = asr_cfg
        self._tts_cfg = tts_cfg
        self._vad_cfg = vad_cfg
        self.asr_backend_name = asr_cfg.get("backend", voice_factory.DEFAULT_ASR_BACKEND)
        self.tts_backend_name = tts_cfg.get("backend", voice_factory.DEFAULT_TTS_BACKEND)
        self.hotwords = voice_cfg.get("hotwords", ["hey assistant"])
        self.endpoint_silence_ms = voice_cfg.get("endpoint_silence_ms", 2000)
        self.wake_window_s = voice_cfg.get("wake_window_ms", DEFAULT_WAKE_WINDOW_MS) / 1000.0
        self.echo_guard_s = voice_cfg.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS) / 1000.0
        self.segmenter_cfg = segmenter_cfg
        self.tts_voice = tts_cfg.get("voice", "en-US-AriaNeural")
        self.tts_speed = tts_cfg.get("speed", 1.0)
        self.speak_text_turns = voice_cfg.get("speak_text_turns", False)
        self.barge_in_enabled = voice_cfg.get("barge_in", {}).get("enabled", False)

        self._asr = None
        self._tts = None
        self._vad = None
        self._segmenter: VadSegmenter | None = None
        self._segments = SegmentQueue()
        self._overflow_pending = False
        self._asr_thread: threading.Thread | None = None
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
        # A user mute (command/PTT), distinct from the half-duplex mute applied
        # while speaking. Conflating them left the FSM stuck in MUTED after the
        # assistant finished a reply, which then rejected the next utterance.
        self._user_muted = False
        # Wake mode: while set, a follow-up utterance needs no wake phrase.
        self._wake_active = False
        self._wake_window_task: asyncio.Task | None = None
        # Brief post-playback mic gate so the assistant does not hear itself.
        self._echo_guard_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Set by tests (or a headless runner) to avoid opening real devices.
        self._audio_disabled = False
        # The last state actually published. Some paths publish without a legal
        # FSM transition (an audio failure reports "error"; a suppressed
        # transition still publishes its target), so the FSM alone would let a
        # resync contradict the live stream.
        self._published_state = VoiceState.IDLE
        self._published_muted = False

    # ── Lifecycle ────────────────────────────────────────────

    async def setup(self) -> bool:
        try:
            self._vad = voice_factory.create_vad(self._vad_cfg)
            self._asr = voice_factory.create_asr(self._asr_cfg)
            self._tts = voice_factory.create_tts(self._tts_cfg)
            self._segmenter = VadSegmenter(
                self._vad,
                self._on_utterance,
                endpoint_silence_ms=self.endpoint_silence_ms,
                **self.segmenter_cfg,
            )
        except voice_factory.VoiceConfigError as exc:
            # Voice is NON_CRITICAL (main.py), so a bad backend degrades to
            # text-only rather than taking the assistant down.
            logger.error(
                "Voice disabled: %s. Fix voice.* in config.yaml and restart.",
                exc,
            )
            return False
        except (TypeError, ValueError) as exc:
            logger.error("Voice disabled: bad voice.segmenter config: %s", exc)
            return False

        # A backend can be valid but unusable (for example an online ASR with no
        # key). Catch that now, once, so it never fires on every utterance.
        problem = self._asr.preflight() if self._asr is not None else ""
        if problem:
            logger.error("Voice disabled: %s Fix voice.* in config.yaml and restart.", problem)
            return False

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
        # Idempotent: a second start must not duplicate subscriptions or leak
        # the first worker thread. The framework starts each module once, but a
        # stop/start cycle is cheap to keep correct.
        if self._asr_thread is not None:
            return
        self.bus.subscribe(topics.VOICE_SPEAK, self._handle_speak)
        self.bus.subscribe(topics.COMMAND_AGENT_INTERRUPT, self._handle_interrupt)
        self.bus.subscribe(topics.COMMAND_VOICE_MUTE, self._handle_mute_command)
        self.bus.subscribe(topics.COMMAND_VOICE_PTT_START, self._handle_ptt_start)
        self.bus.subscribe(topics.COMMAND_VOICE_PTT_END, self._handle_ptt_end)
        self.bus.subscribe(topics.VOICE_STATE_REQUEST, self._handle_state_request)

        # A prior stop() closed the queue; a fresh one is needed per run.
        if self._segments.closed:
            self._segments = SegmentQueue()
        self._open_audio()
        self._loop = asyncio.get_running_loop()
        self._asr_thread = threading.Thread(
            target=self._asr_worker, name="voice-asr", daemon=True,
        )
        self._asr_thread.start()
        self._enter_idle()
        logger.info("Voice started — mode=%s", self.listen_mode)

    async def stop(self) -> None:
        await self._cancel_speak_task()
        await self._cancel_wake_window_async()
        await self._cancel_echo_guard_async()
        if self.capture is not None:
            self.capture.close()
            self.capture = None
        if self.playback is not None:
            self.playback.stop_now()
            self.playback.close()
            self.playback = None
        self._segments.close()
        self._stop_asr_worker()
        if self._asr is not None:
            close = getattr(self._asr, "close", None)
            if callable(close):
                close()
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
        self._publish_state(VoiceState.ERROR)
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

        if self._segmenter is not None:
            self._segmenter.feed(pcm)

    def _on_capture_error(self, exc: Exception) -> None:
        self._fail("ERR-VOICE-ASR-FAIL", f"capture error: {exc}")

    # ── ASR ──────────────────────────────────────────────────

    def _on_utterance(self, pcm: bytes) -> None:
        """Audio-thread callback: hand a complete utterance to the ASR worker.

        Runs on the audio callback thread, so it must not block. Only a flag is
        set here; the overflow event is published from the worker, because
        ``bus.publish`` is a synchronous fan-out with no latency bound.
        """
        if not self._segments.put(pcm):
            self._overflow_pending = True

    def _publish_overflow(self) -> None:
        """Publish a pending queue-overflow event from the worker thread."""
        if not self._overflow_pending:
            return
        self._overflow_pending = False
        self.bus.publish(topics.VOICE_OVERFLOW, {
            "dropped": self._segments.dropped,
            "queue_cap": self._segments.cap,
        })

    def _asr_worker(self) -> None:
        """Long-lived worker: transcribe queued utterances off both loops.

        Never on the event loop and never on the audio thread. ``transcribe``
        is blocking (network or model inference), which is why it lives here.
        The per-item ``except`` is deliberate: an exception escaping this loop
        would kill the thread and silently end all transcription for the
        session, which is the failure ADR-0018 exists to remove.
        """
        while True:
            pcm = self._segments.get()
            self._publish_overflow()
            if pcm is None:
                if self._segments.closed:
                    return
                continue
            if self._asr is None:
                continue
            try:
                self._transition_quietly(VoiceState.TRANSCRIBING)
                result = self._asr.transcribe(pcm)
                text = (result.get("text") or "").strip()
                if text:
                    confidence = result.get("confidence", 1.0)
                    # publish + wake gating + THINKING, unchanged.
                    self._publish_transcript(text, confidence)
            except Exception as exc:
                logger.exception("ASR worker failed to transcribe a segment")
                self._fail("ERR-VOICE-ASR-FAIL", f"transcription failed: {exc}")

    def _stop_asr_worker(self) -> None:
        thread = self._asr_thread
        self._asr_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=ASR_WORKER_JOIN_TIMEOUT)

    def _publish_transcript(self, text: str, confidence: float = 1.0) -> None:
        """Apply wake gating and turn the transcript into a turn.

        Runs on the ASR worker thread. A transcript can be stale by the time it
        arrives: the FSM may already have moved to SPEAKING (barge-in off) or
        MUTED. Those states do not accept THINKING, so the turn is dropped
        rather than raising and killing the worker.
        """
        self.bus.publish(topics.VOICE_TRANSCRIBED, {"text": text, "confidence": confidence})

        if self.listen_mode in ("wake", "ptt"):
            command = self._detector.strip_wake(text)
            if self.listen_mode == "wake":
                if self._wake_active:
                    # Inside the follow-up window: accept the utterance as-is,
                    # so a multi-turn exchange needs the phrase only once.
                    command = command or text
                elif not self._detector.should_wake(text):
                    logger.debug("Wake phrase absent; segment discarded")
                    self._enter_idle()
                    return
                elif not command:
                    # Only the wake phrase: open the follow-up window.
                    logger.info("Wake phrase heard; listening for the command")
                    self._open_wake_window()
                    self._publish_state(VoiceState.LISTENING)
                    return
            elif not command:
                # Push-to-talk: an empty command is just an empty utterance.
                self._enter_idle()
                return
            text = command

        if not self._state.can_transition(VoiceState.THINKING):
            logger.debug("Transcript arrived in %s; dropping stale turn", self._state.state.value)
            return

        # Keep the window open across turns: the timeout, not a single turn,
        # ends the follow-up mode.
        if self.listen_mode == "wake" and self._wake_active:
            self._open_wake_window()
        self._transition_quietly(VoiceState.THINKING)
        self.bus.user_input(text, channel=topics.CHANNEL_VOICE)

    def _open_wake_window(self) -> None:
        """Accept follow-up utterances without the wake phrase for a while.

        Called on the ASR worker thread. The window is armed when the phrase is
        heard and refreshed after each utterance, so a continued conversation
        keeps it alive; it closes after ``wake_window_s`` of quiet.
        """
        self._wake_active = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._arm_wake_timer)

    def _arm_wake_timer(self) -> None:
        """Loop thread: (re)start the wake-window timeout.

        Task creation and cancellation stay on the loop; the worker thread only
        requests them, so there is no cross-thread task access.
        """
        task, self._wake_window_task = self._wake_window_task, None
        if task is not None:
            task.cancel()
        self._wake_window_task = asyncio.get_running_loop().create_task(
            self._wake_window()
        )

    async def _wake_window(self) -> None:
        try:
            await asyncio.sleep(self.wake_window_s)
        except asyncio.CancelledError:
            return
        self._wake_active = False
        logger.info("Wake window closed after %.0fs; the wake phrase is required again",
                    self.wake_window_s)

    def _close_wake_window(self) -> None:
        """End the window: the next turn needs the wake phrase again."""
        self._wake_active = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._disarm_wake_timer)

    def _disarm_wake_timer(self) -> None:
        """Loop thread: cancel the wake-window timeout."""
        task, self._wake_window_task = self._wake_window_task, None
        if task is not None:
            task.cancel()

    async def _cancel_wake_window_async(self) -> None:
        """Loop thread (``stop``): cancel and await the timeout task."""
        task, self._wake_window_task = self._wake_window_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._wake_active = False

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
        # Half-duplex muted the mic while speaking; return to idle now. In wake
        # mode, keep the follow-up window open so the next utterance needs no
        # wake phrase.
        self._enter_idle()
        if self.listen_mode == "wake" and self._wake_active:
            self._open_wake_window()

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
        self._user_muted = muted
        if muted:
            # An explicit mute ends any follow-up window.
            self._close_wake_window()
        if self.capture is not None:
            self.capture.set_muted(muted)
        if muted and self._segmenter is not None:
            # Do not transcribe frames captured before the mute.
            self._segmenter.reset()
        state = VoiceState.MUTED if muted else (
            VoiceState.LISTENING if self.listen_mode != "ptt" else VoiceState.IDLE
        )
        try:
            self._state.transition(state)
        except InvalidTransition:
            logger.debug("mute transition %s -> %s suppressed", self._state.state, state)
        self._publish_state(state, muted=muted)

    def arm(self) -> None:
        """Push-to-talk pressed: start capturing."""
        if self.listen_mode != "ptt":
            return
        if self._segmenter is not None:
            self._segmenter.reset()
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
        self._publish_state(VoiceState.LISTENING)

    def disarm(self) -> None:
        """Push-to-talk released: finalize the utterance and transcribe."""
        if self._segmenter is not None:
            self._segmenter.flush()
        self._enter_idle()

    # ── State helpers ────────────────────────────────────────

    def _enter_idle(self) -> None:
        # Base the state on the *user* mute. The capture-level mute is also set
        # for half-duplex while speaking; reading it here made the module settle
        # in MUTED after every reply, and MUTED rejects the next utterance.
        target = VoiceState.MUTED if self._user_muted else VoiceState.IDLE
        self._transition_quietly(target)
        self._publish_state(target)

    def _publish_state(self, state: VoiceState, muted: bool | None = None,
                       previous: VoiceState | None = None) -> None:
        """Publish a state and remember it as the authoritative published state.

        Every voice.state publish goes through here so a resync can report what
        the live stream last reported, not what the FSM holds: a failure reports
        "error" without a transition and a suppressed transition still publishes.
        """
        if muted is None:
            # Report the *user* mute, not the capture gate. The half-duplex and
            # echo guards gate the mic internally while the state is speaking or
            # settling; exposing those would make the UI read "Muted" during a
            # normal reply.
            muted = self._user_muted
        payload = {"state": state.value, "muted": muted}
        if previous is not None:
            payload["previous"] = previous.value
        self._published_state = state
        self._published_muted = muted
        self.bus.publish(topics.VOICE_STATE, payload)

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

    async def _handle_state_request(self, topic: str, payload: dict) -> None:
        """Resync a late-connecting client with the current state.

        A level read, not a transition: it must not publish again through
        _on_state_change or re-run half-duplex gating. It reports the last state
        actually published, so it matches the live stream rather than the FSM.
        """
        self.bus.publish(topics.VOICE_STATE, {
            "state": self._published_state.value,
            "muted": self._published_muted,
        })

    def _on_state_change(self, previous: VoiceState, current: VoiceState) -> None:
        # Apply the half-duplex gate before publishing, so the published
        # `muted` flag already reflects it (otherwise every SPEAKING->IDLE
        # briefly reports idle+muted and the UI flashes the mute indicator).
        self._apply_half_duplex(previous, current)
        self._publish_state(current, previous=previous)

    def _apply_half_duplex(self, previous: VoiceState, current: VoiceState) -> None:
        """Gate the mic while speaking, and briefly after.

        Half-duplex by design: with speakers and no echo cancellation an open
        mic hears the assistant and self-triggers (ADR-0011). When barge-in is
        explicitly enabled the mic stays live, which may self-trigger unless AEC
        is present.

        Leaving SPEAKING does not reopen the mic immediately: the speaker and
        the room reverb tail are still audible, so a short guard keeps it gated
        until the sound has died away.
        """
        if self.capture is None:
            return
        if self.barge_in_enabled:
            return
        if current is VoiceState.SPEAKING:
            self._cancel_echo_guard()
            self.capture.set_muted(True)
            return
        if self._user_muted:
            return
        if previous is VoiceState.SPEAKING:
            # Stay gated (the mute from SPEAKING still holds) and reopen later.
            self._schedule_echo_guard()
        else:
            self.capture.set_muted(False)

    def _schedule_echo_guard(self) -> None:
        """Keep the mic gated briefly after playback, then reopen it.

        Runs on the state-change thread, which may be the ASR worker, so the
        guard task is created on the event loop. Resetting the segmenter drops
        any partial utterance the mic buffered as the assistant finished.
        """
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._arm_echo_guard)

    def _arm_echo_guard(self) -> None:
        """Loop thread: arm the guard window; the mic is already gated."""
        task, self._echo_guard_task = self._echo_guard_task, None
        if task is not None:
            task.cancel()
        if self._segmenter is not None:
            # Discard whatever the mic buffered as the assistant finished.
            self._segmenter.reset()
        self._echo_guard_task = asyncio.get_running_loop().create_task(
            self._echo_guard()
        )

    async def _echo_guard(self) -> None:
        try:
            await asyncio.sleep(self.echo_guard_s)
        except asyncio.CancelledError:
            return
        if self.capture is not None and not self._user_muted:
            self.capture.set_muted(False)

    def _cancel_echo_guard(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._disarm_echo_guard)

    def _disarm_echo_guard(self) -> None:
        """Loop thread: cancel a pending guard (a new SPEAKING supersedes it)."""
        task, self._echo_guard_task = self._echo_guard_task, None
        if task is not None:
            task.cancel()

    async def _cancel_echo_guard_async(self) -> None:
        """Loop thread (``stop``): cancel and await the guard task."""
        task, self._echo_guard_task = self._echo_guard_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
