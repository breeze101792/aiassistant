import logging
import threading

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class EarsModule(BaseModule):
    """Captures audio, detects wake words, converts speech to text.

    Publishes transcribed text to the bus as user.input.text.
    """

    module_name = "ears"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        ears_cfg = config.get("ears", {})
        self.backend_name = ears_cfg.get("backend", "stub")
        self.hotwords = ears_cfg.get("hotwords", ["hey assistant"])
        self.silence_timeout = ears_cfg.get("silence_timeout", 20)
        self._backend = None
        self._state = "idle"  # idle | listening | paused
        self._state_lock = threading.Lock()

    async def setup(self) -> bool:
        if self.backend_name == "stub":
            from modules.ears.asr_backends.stub import StubASR
            self._backend = StubASR()
        elif self.backend_name == "funasr":
            from modules.ears.asr_backends.funasr import FunASRBackend
            self._backend = FunASRBackend()
        elif self.backend_name == "whisper":
            from modules.ears.asr_backends.whisper import WhisperBackend
            self._backend = WhisperBackend()
        elif self.backend_name == "halasr":
            from modules.ears.asr_backends.halasr import HalASRBackend
            self._backend = HalASRBackend(
                on_text=self._on_speech,
                hotwords=self.hotwords,
                silence_duration=1.0,
                speech_timeout=self.silence_timeout,
            )
        else:
            logger.warning(f"Unknown ears backend: {self.backend_name}, using stub")
            from modules.ears.asr_backends.stub import StubASR
            self._backend = StubASR()

        logger.info(f"Ears setup — backend={self.backend_name}")
        return True

    async def start(self) -> None:
        self.bus.subscribe("command.ears.start", self._handle_start)
        self.bus.subscribe("command.ears.stop", self._handle_stop)
        self.bus.subscribe("command.ears.pause", self._handle_pause)
        self.bus.subscribe("command.ears.resume", self._handle_resume)

        # Mute mic while TTS is speaking to avoid feedback loop
        self.bus.subscribe("status.mouth.started", self._handle_mouth_started)
        self.bus.subscribe("status.mouth.done", self._handle_mouth_done)

        # Auto-start listening if backend supports it
        if self.backend_name not in ("stub",):
            self._start_listening()

        self.bus.publish("status.ears.ready", {
            "backend": self.backend_name,
        })
        logger.info("Ears started")

    async def stop(self) -> None:
        self._state = "idle"
        if hasattr(self._backend, "stop"):
            self._backend.stop()
        logger.info("Ears stopped")

    async def health(self) -> dict:
        return {"status": "ok", "details": {"backend": self.backend_name, "state": self._state}}

    def _start_listening(self):
        if hasattr(self._backend, "start"):
            with self._state_lock:
                self._state = "listening"
            self._backend.start()

    def _on_speech(self, text: str):
        """Callback from ASR backend — publish transcribed text to bus."""
        self.bus.publish("user.input.text", {
            "text": text,
            "confidence": 0.95,
            "source": "ears",
        })

    async def _handle_start(self, topic: str, payload: dict) -> None:
        with self._state_lock:
            if self._state != "listening":
                self._start_listening()
                logger.debug("Ears: started listening")

    async def _handle_stop(self, topic: str, payload: dict) -> None:
        if hasattr(self._backend, "stop"):
            self._backend.stop()
        with self._state_lock:
            self._state = "idle"
        logger.debug("Ears: stopped")

    async def _handle_pause(self, topic: str, payload: dict) -> None:
        if hasattr(self._backend, "pause"):
            self._backend.pause()
        with self._state_lock:
            self._state = "paused"
        logger.debug("Ears: paused")

    async def _handle_resume(self, topic: str, payload: dict) -> None:
        if hasattr(self._backend, "start") and not hasattr(self._backend, "resume"):
            if not getattr(self._backend, '_running', False):
                self._backend.start()
        elif hasattr(self._backend, "resume"):
            self._backend.resume()
        with self._state_lock:
            self._state = "listening"
        logger.debug("Ears: resumed")

    async def _handle_mouth_started(self, topic: str, payload: dict) -> None:
        if hasattr(self._backend, "mute"):
            self._backend.mute()
            logger.debug("Ears: muted during TTS")

    async def _handle_mouth_done(self, topic: str, payload: dict) -> None:
        if hasattr(self._backend, "unmute"):
            self._backend.unmute()
            logger.debug("Ears: unmuted after TTS")
