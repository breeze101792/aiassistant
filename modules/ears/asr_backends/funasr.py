import logging
import os
import tempfile
import wave

import numpy as np

from modules.ears.asr_backends.base import ASRBackend

logger = logging.getLogger(__name__)


class FunASRBackend(ASRBackend):
    """FunASR speech recognition — good for Chinese + multilingual (single-shot)."""

    def __init__(self, model: str = "iic/SenseVoiceSmall"):
        self.model_name = model
        self._model = None
        self._running = False

    def start(self):
        self._running = True
        logger.info("FunASRBackend started (single-shot mode)")

    def stop(self):
        self._running = False
        logger.info("FunASRBackend stopped")

    def transcribe(self, audio_bytes: bytes) -> dict:
        if self._model is None:
            try:
                from funasr import AutoModel
                self._model = AutoModel(model=self.model_name)
            except ImportError:
                return {"text": "FunASR not installed", "confidence": 0.0, "language": "en"}

        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_np.tobytes())

            result = self._model.generate(input=tmp_path)
            if result and len(result) > 0:
                return {
                    "text": result[0].get("text", ""),
                    "confidence": result[0].get("confidence", 0.0),
                    "language": result[0].get("language", "unknown"),
                }
        finally:
            os.unlink(tmp_path)

        return {"text": "", "confidence": 0.0, "language": "unknown"}
