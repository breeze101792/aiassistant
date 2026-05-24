from modules.ears.asr_backends.base import ASRBackend


class WhisperBackend(ASRBackend):
    """OpenAI Whisper speech recognition."""

    def __init__(self, model: str = "base"):
        self.model_name = model
        self._model = None

    def transcribe(self, audio_bytes: bytes) -> dict:
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self.model_name)
            except ImportError:
                return {"text": "Whisper not installed", "confidence": 0.0, "language": "en"}

        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            result = self._model.transcribe(tmp_path)
            return {
                "text": result.get("text", "").strip(),
                "confidence": 0.9,
                "language": result.get("language", "unknown"),
            }
        finally:
            os.unlink(tmp_path)
