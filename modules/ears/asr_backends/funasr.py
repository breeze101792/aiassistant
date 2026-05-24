from modules.ears.asr_backends.base import ASRBackend


class FunASRBackend(ASRBackend):
    """FunASR speech recognition — good for Chinese + multilingual."""

    def __init__(self, model: str = "iic/SenseVoiceSmall"):
        self.model_name = model
        self._model = None

    def transcribe(self, audio_bytes: bytes) -> dict:
        if self._model is None:
            try:
                from funasr import AutoModel
                self._model = AutoModel(model=self.model_name)
            except ImportError:
                return {"text": "FunASR not installed", "confidence": 0.0, "language": "en"}

        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
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
