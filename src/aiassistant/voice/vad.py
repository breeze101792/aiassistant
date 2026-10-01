"""Voice activity detection: the first pipeline stage.

A VAD classifies one frame as speech or silence. The segmenter composes a VAD
into complete utterances, so the VAD choice (energy/webrtc, later silero) stays
swappable independently of endpointing policy. One class per backend, selected
by ``voice.factory.create_vad``.

Frame contract: one 20 ms frame at 16 kHz mono is 320 int16 LE samples, i.e.
640 bytes (``FRAME_MS`` / ``TARGET_SAMPLE_RATE`` / ``CHANNELS`` in
``voice.audio``).
"""

from aiassistant.voice.audio import TARGET_SAMPLE_RATE, rms_level

# Default energy threshold, normalized 0..1 (see ``rms_level``). Tuned for a
# typical quiet room with a laptop microphone; the one knob most users touch.
ENERGY_THRESHOLD = 0.02

# webrtcvad aggressiveness, 0..3. 3 filters the most non-speech, the safer
# default when a false positive costs a whole turn.
WEBRTC_AGGRESSIVENESS = 3


class VADBackend:
    """Classify one frame as speech or silence."""

    name = "base"

    def is_speech(self, frame: bytes) -> bool:
        raise NotImplementedError

    def reset(self) -> None:
        """Discard any state carried between frames. Default: no state."""


class EnergyVAD(VADBackend):
    """RMS threshold VAD. numpy-free and dependency-free; the working default."""

    name = "energy"

    def __init__(self, threshold: float = ENERGY_THRESHOLD):
        self.threshold = threshold

    def is_speech(self, frame: bytes) -> bool:
        return rms_level(frame) >= self.threshold


class WebRTCVAD(VADBackend):
    """Google's WebRTC VAD, more selective than an energy gate.

    Optional: requires the ``webrtcvad`` package (the ``vad`` extra). At import
    time that package also needs ``pkg_resources`` (``setuptools``), so on a
    minimal venv the import fails even when the wheel is installed. That is why
    it is not the default.
    """

    name = "webrtc"

    def __init__(self, aggressiveness: int = WEBRTC_AGGRESSIVENESS):
        try:
            import webrtcvad
        except ImportError as exc:
            raise RuntimeError(
                "webrtcvad is not installed; run: pip install webrtcvad "
                "(or pip install 'aiassistant[vad]'). Note it also needs "
                "setuptools for pkg_resources."
            ) from exc
        self.aggressiveness = aggressiveness
        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, frame: bytes) -> bool:
        # webrtcvad accepts 10/20/30 ms frames at 8/16/32/48 kHz. A wrong
        # frame size raises here, which is the correct loud failure.
        return self._vad.is_speech(frame, TARGET_SAMPLE_RATE)
