from modules.mouth.tts_backends.base import TTSBackend


class TextTTS(TTSBackend):
    """Prints text to stdout — no audio output."""

    def speak(self, text: str, voice: str | None = None, speed: float = 1.0) -> None:
        print(f"[Assistant] {text}")

    def stop(self) -> None:
        pass
