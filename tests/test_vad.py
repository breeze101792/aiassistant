"""VAD backend tests: the first pipeline stage (ADR-0018).

``EnergyVAD`` is the dependency-free default, so it is fully unit tested with
generated frames. ``WebRTCVAD`` is optional: it needs the ``webrtcvad`` wheel
*and* ``pkg_resources`` (setuptools), which a minimal venv lacks, so its tests
skip rather than fail — a missing optional dependency is not a defect.
"""

import math
import struct

import pytest

from aiassistant.voice.audio import TARGET_SAMPLE_RATE
from aiassistant.voice.vad import (
    ENERGY_THRESHOLD,
    VADBackend,
    WebRTCVAD,
)
from aiassistant.voice.vad import EnergyVAD
from aiassistant.voice.segmenter import BYTES_PER_FRAME

# A frame is 20 ms at 16 kHz mono int16: 320 samples, 640 bytes.
FRAME_SAMPLES = BYTES_PER_FRAME // 2
TONAL_HZ = 440.0


def sine_frame(amplitude: int, samples: int = FRAME_SAMPLES,
               frequency: float = TONAL_HZ) -> bytes:
    """One int16 LE frame holding a sine wave of the given peak amplitude."""
    values = [
        int(amplitude * math.sin(2.0 * math.pi * frequency * i / TARGET_SAMPLE_RATE))
        for i in range(samples)
    ]
    return struct.pack("<" + "h" * samples, *values)


class TestEnergyVAD:
    def test_sine_frame_is_speech(self):
        assert EnergyVAD().is_speech(sine_frame(32767)) is True

    def test_zero_frame_is_silence(self):
        assert EnergyVAD().is_speech(b"\x00\x00" * FRAME_SAMPLES) is False

    def test_empty_frame_is_silence(self):
        """rms_level(b"") is 0.0; the VAD must not raise on a short read."""
        assert EnergyVAD().is_speech(b"") is False

    def test_threshold_boundary_is_inclusive(self):
        vad = EnergyVAD(threshold=0.02)
        # A 0.02-amplitude sine has an RMS just above the threshold; a zero frame
        # is below it. Pin the boundary explicitly with a threshold of 0.0.
        assert EnergyVAD(threshold=0.0).is_speech(b"") is True
        assert vad.is_speech(sine_frame(1000)) is True   # RMS ~0.0216
        assert vad.is_speech(sine_frame(100)) is False   # RMS ~0.0021

    def test_a_higher_threshold_rejects_a_quiet_frame(self):
        assert EnergyVAD(threshold=0.5).is_speech(sine_frame(1000)) is False
        assert EnergyVAD(threshold=0.5).is_speech(sine_frame(32767)) is True

    def test_threshold_is_the_documented_default(self):
        assert EnergyVAD().threshold == ENERGY_THRESHOLD

    def test_reset_is_a_noop(self):
        """The base contract: a stateless VAD's reset() discards nothing."""
        vad = EnergyVAD()
        assert vad.reset() is None
        assert vad.is_speech(sine_frame(32767)) is True  # unchanged by reset

    def test_is_a_vad_backend(self):
        assert isinstance(EnergyVAD(), VADBackend)


class TestWebRTCVAD:
    """Optional dependency; skip when the wheel or pkg_resources is absent."""

    def test_selects_a_valid_frame(self):
        pytest.importorskip("webrtcvad")
        vad = WebRTCVAD(aggressiveness=0)
        # A loud tone is the best a non-speech model can be asked for here; the
        # point is that a correctly sized frame is accepted, not misclassified.
        assert isinstance(vad.is_speech(sine_frame(32767)), bool)

    def test_reset_is_a_noop(self):
        pytest.importorskip("webrtcvad")
        vad = WebRTCVAD()
        assert vad.reset() is None

    def test_missing_dependency_raises_a_loud_error(self, monkeypatch
                                                   ):
        """When webrtcvad is importable this is skipped by importorskip; the
        construction error path is pinned by faking the import failure."""
        import builtins

        real_import = builtins.__import__

        def deny(name, *args, **kwargs):
            if name == "webrtcvad":
                raise ImportError("simulated: no webrtcvad")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", deny)
        with pytest.raises(RuntimeError, match="webrtcvad is not installed"):
            WebRTCVAD()
