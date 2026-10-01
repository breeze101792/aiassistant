"""Offline ASR via faster-whisper.

CTranslate2-based, so it installs without torch and runs on macOS and Linux
(the ``asr-offline`` extra). The model is loaded once and cached; transcription
runs on the ASR worker thread, never on the event loop.
"""

import logging

import numpy as np

from aiassistant.voice.asr.asr_backends.base import ASRBackend

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "base"
# int16 full scale; faster-whisper wants float32 in [-1, 1].
_INT16_SCALE = 32768.0
# CPU by default: "auto" picks CUDA when ctranslate2 sees it, which then fails
# on a host without the CUDA runtime libs (for example libcublas). Set
# voice.asr.device to "cuda" to opt into the GPU explicitly.
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"


class FasterWhisperBackend(ASRBackend):
    """Local Whisper inference with the faster-whisper runtime."""

    def __init__(self, model: str = DEFAULT_MODEL, *, device: str = DEFAULT_DEVICE,
                 compute_type: str = DEFAULT_COMPUTE_TYPE, language: str = ""):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model = None

    def preflight(self) -> str:
        """Report a missing package at setup, not on every utterance.

        The model itself is downloaded on first use, which is allowed to happen
        lazily; only the runtime import is checked here.
        """
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return (
                "faster-whisper is not installed. Install it with "
                "'pip install aiassistant[asr-offline]', or set "
                "voice.asr.backend to another backend."
            )
        return ""

    def transcribe(self, audio_bytes: bytes) -> dict:
        model = self._load_model()
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / _INT16_SCALE
        options = {}
        if self.language:
            options["language"] = self.language
        segments, info = model.transcribe(audio, **options)
        text = "".join(segment.text for segment in segments).strip()
        language = getattr(info, "language", "") or self.language or ""
        return {"text": text, "confidence": 1.0, "language": language}

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed; run: "
                "pip install 'aiassistant[asr-offline]'"
            ) from exc
        self._model = WhisperModel(
            self.model_name, device=self.device, compute_type=self.compute_type,
        )
        return self._model
