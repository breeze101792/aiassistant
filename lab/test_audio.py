#!/usr/bin/env python3
"""Lab: test audio pipeline stage by stage.

Usage:
  ./run.sh python lab/test_audio.py             # capture 3s, save WAV, no ASR
  ./run.sh python lab/test_audio.py --duration 5   # capture 5 seconds
  ./run.sh python lab/test_audio.py --asr          # capture + transcribe (needs torch)
  ./run.sh python lab/test_audio.py --playback     # capture + play back the WAV
  ./run.sh python lab/test_audio.py --vad          # test VAD on live mic input
"""

import argparse
import sys
import time
import wave

import numpy as np

try:
    import pyaudio
except ImportError:
    print("ERROR: PyAudio not installed. Run: pip install pyaudio")
    sys.exit(1)

try:
    import webrtcvad
except ImportError:
    print("ERROR: WebRTC VAD not installed. Run: pip install webrtcvad")
    sys.exit(1)


def test_mic(duration: float = 3.0, sample_rate: int = 48000) -> bytes:
    """Capture audio from default mic and return raw PCM bytes."""
    audio = pyaudio.PyAudio()
    default = audio.get_default_input_device_info()
    device_index = default["index"]
    chunk = int(sample_rate * 20 / 1000)  # 20ms frames

    print(f"Mic: {default['name']}")
    print(f"Device index: {device_index}")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Recording {duration}s... (speak now)")

    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk,
        input_device_index=device_index,
    )

    frames = []
    num_chunks = int(duration * sample_rate / chunk)
    for _ in range(num_chunks):
        data = stream.read(chunk, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    audio.terminate()

    raw = b"".join(frames)
    print(f"Captured: {len(frames)} chunks, {len(raw)} bytes, {len(raw)/2/sample_rate:.2f}s")
    return raw


def save_wav(raw: bytes, path: str, sample_rate: int = 48000):
    """Save raw 16-bit PCM to WAV file."""
    audio_np = np.frombuffer(raw, dtype=np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_np.tobytes())
    print(f"Saved: {path}")


def test_vad(raw: bytes, sample_rate: int = 48000) -> None:
    """Run WebRTC VAD on audio chunks and report speech/silence."""
    vad = webrtcvad.Vad()
    vad.set_mode(3)  # most aggressive
    chunk = int(sample_rate * 20 / 1000)

    speech_frames = 0
    silence_frames = 0
    for i in range(0, len(raw) - chunk, chunk):
        frame = raw[i:i + chunk]
        if len(frame) < chunk:
            break
        if vad.is_speech(frame, sample_rate):
            speech_frames += 1
        else:
            silence_frames += 1

    total = speech_frames + silence_frames
    if total == 0:
        print("VAD: no frames to analyze")
        return
    print(f"VAD: {speech_frames}/{total} speech frames ({100*speech_frames/total:.0f}%)")


def test_asr(wav_path: str) -> None:
    """Transcribe a WAV file with FunASR."""
    try:
        from funasr import AutoModel
    except ImportError:
        print("SKIP: FunASR not installed. Run: pip install funasr torch")
        return

    print("Loading FunASR model...")
    try:
        model = AutoModel(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            disable_update=True,
            disable_log=True,
            disable_pbar=True,
        )
    except Exception as e:
        print(f"ERROR loading model: {e}")
        return

    print("Transcribing...")
    result = model.generate(input=wav_path)
    if result and len(result) > 0:
        text = result[0].get("text", "").strip()
        print(f"ASR result: \"{text}\"")
    else:
        print("ASR: no text recognized")


def play_wav(path: str) -> None:
    """Play a WAV file using afplay (macOS)."""
    import subprocess
    import platform
    if platform.system() == "Darwin":
        subprocess.run(["afplay", path])
    else:
        print(f"Playback not supported on this platform. File saved at: {path}")


def main():
    parser = argparse.ArgumentParser(description="Test audio pipeline stage by stage")
    parser.add_argument("--duration", type=float, default=3.0, help="Recording duration in seconds")
    parser.add_argument("--asr", action="store_true", help="Also transcribe captured audio")
    parser.add_argument("--playback", action="store_true", help="Play back captured audio")
    parser.add_argument("--vad", action="store_true", help="Run VAD analysis on captured audio")
    args = parser.parse_args()

    wav_path = "/tmp/lab_test_audio.wav"

    # Stage 1: capture
    print("=" * 50)
    print("STAGE 1: Microphone capture")
    print("=" * 50)
    raw = test_mic(duration=args.duration)

    # Stage 2: save WAV
    print()
    print("=" * 50)
    print("STAGE 2: Save to WAV")
    print("=" * 50)
    save_wav(raw, wav_path)

    # Stage 3: VAD (optional)
    if args.vad:
        print()
        print("=" * 50)
        print("STAGE 3: VAD analysis")
        print("=" * 50)
        test_vad(raw)

    # Stage 4: playback (optional)
    if args.playback:
        print()
        print("=" * 50)
        print("STAGE 4: Playback")
        print("=" * 50)
        play_wav(wav_path)

    # Stage 5: ASR (optional)
    if args.asr:
        print()
        print("=" * 50)
        print("STAGE 5: ASR transcription")
        print("=" * 50)
        test_asr(wav_path)

    print()
    print("Done. WAV file: {}".format(wav_path))


if __name__ == "__main__":
    main()
