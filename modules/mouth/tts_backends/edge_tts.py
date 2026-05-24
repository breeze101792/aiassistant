from modules.mouth.tts_backends.base import TTSBackend


class EdgeTTSBackend(TTSBackend):
    """Microsoft Edge TTS — cloud-based, natural voices."""

    def __init__(self, voice: str = "en-US-AriaNeural", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._process = None

    async def speak(self, text: str, voice: str | None = None, speed: float = 1.0) -> None:
        try:
            import edge_tts
            import tempfile
            import os

            v = voice or self.voice
            sp = speed or self.speed

            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                rate = f"{int((sp - 1.0) * 100):+d}%"
                communicate = edge_tts.Communicate(text, v, rate=rate)
                await communicate.save(tmp_path)
                self._play_audio(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except ImportError:
            print(f"[Assistant TTS] {text}")

    def _play_audio(self, path: str) -> None:
        try:
            import subprocess
            import platform
            if platform.system() == "Darwin":
                subprocess.run(["afplay", path], check=False)
            elif platform.system() == "Linux":
                subprocess.run(["aplay", path], check=False)
        except Exception:
            pass

    def stop(self) -> None:
        pass
