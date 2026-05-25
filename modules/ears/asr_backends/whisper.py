import logging
import os
import tempfile
import warnings
import wave

import numpy as np

from modules.ears.asr_backends.base import ASRBackend

logger = logging.getLogger(__name__)


class WhisperBackend(ASRBackend):
    """OpenAI Whisper speech recognition — single-shot transcription."""

    def __init__(self, model: str = "base"):
        self.model_name = model
        self._model = None
        self._running = False

    def start(self):
        self._running = True
        logger.info("WhisperBackend started (single-shot mode)")

    def stop(self):
        self._running = False
        logger.info("WhisperBackend stopped")

    def transcribe(self, audio_bytes: bytes) -> dict:
        if self._model is None:
            try:
                import whisper
                warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
                self._model = whisper.load_model(self.model_name)
            except ImportError:
                return {"text": "Whisper not installed", "confidence": 0.0, "language": "en"}

        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_np.tobytes())

            result = self._model.transcribe(tmp_path)
            return {
                "text": result.get("text", "").strip(),
                "confidence": 0.9,
                "language": result.get("language", "unknown"),
            }
        finally:
            os.unlink(tmp_path)
