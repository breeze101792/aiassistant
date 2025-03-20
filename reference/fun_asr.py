import wave
import queue
import numpy as np
import librosa
import pyaudio
import time
import threading
from funasr import AutoModel
import webrtcvad

# 🔹 設定 FunASR 模型變數
ASR_MODEL = "paraformer-zh"  # 語音識別模型
VAD_MODEL = "fsmn-vad"       # 語音活動檢測（可選）
PUNC_MODEL = "ct-punc"       # 標點符號模型（可選）

# 🔹 加載 FunASR 模型
model = AutoModel(model=ASR_MODEL, vad_model=VAD_MODEL, punc_model=PUNC_MODEL)

# 🔍 設定音訊參數
CHUNK = 1024  # 每次讀取的音訊大小
FORMAT = pyaudio.paInt16  # 16-bit PCM
CHANNELS = 1  # 單聲道
RATE = 48000  # FunASR 需要 16kHz
TARGET_RATE = 16000  # FunASR 需要 16kHz
DEVICE_INDEX = 5  # 手動設定裝置 ID（可用 list_audio_devices() 查詢）
SILENCE_DURATION = 3  # 若無聲音超過 3 秒則結束錄音
CHUNK = int(RATE * 20 / 1000)

# 🎤 初始化錄音
audio = pyaudio.PyAudio()

def list_audio_devices():
    print("🔍 可用音訊裝置列表：")
    for i in range(audio.get_device_count()):
        dev = audio.get_device_info_by_index(i)
        print(f"🎤 裝置 {i}: {dev['name']} (ID: {dev['index']})")
        print(f"   - 最高取樣率: {dev['defaultSampleRate']} Hz")
        print(f"   - 頻道數: {dev['maxInputChannels']}")

def save_wave(filename, audio_data, sample_rate):
    audio_np = np.frombuffer(audio_data, dtype=np.int16)
    if sample_rate != TARGET_RATE:
        audio_np = librosa.resample(audio_np.astype(np.float32), orig_sr=sample_rate, target_sr=TARGET_RATE)
        sample_rate = TARGET_RATE

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_np.astype(np.int16).tobytes())

    print(f"✅ 音檔已儲存: {filename} (取樣率: {sample_rate} Hz)")

def recognize_audio(filename):
    result = model.generate(input=filename)
    print(f"📝 辨識結果: {result}")

def listen_continuous():
    # 初始化 VAD
    vad_mode=3
    vad = webrtcvad.Vad()
    vad.set_mode(vad_mode)

    print("🎤 持續監聽中，請開始說話...")
    
    stream = audio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK,
                        input_device_index=DEVICE_INDEX)
    
    while True:
        # audio_queue = queue.Queue()
        audio_list = []
        is_recording = False
        start_time = time.time()
        silence_start_time = time.time()

        try:
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                is_speech = vad.is_speech(data, RATE)

                if is_speech is True and is_recording is False:
                    # Start recording
                    print("🎙️ 偵測到語音，開始錄音...")
                    is_recording = True
                    start_time = time.time()
                    silence_start_time = time.time()

                # record data.
                if is_recording is True:
                    # audio_queue.put(data)
                    audio_list.append(data)
                
                # 偵測停止（若無聲音超過 SILENCE_DURATION 秒則結束錄音）
                silence_duration = time.time() - silence_start_time
                if is_recording and silence_duration > SILENCE_DURATION:
                    print("🛑 語音結束，開始辨識...")
                    break
        except KeyboardInterrupt:
            print("\n🛑 停止錄音")
            break
        
        # 組合音訊數據
        # audio_data = b''.join(list(audio_queue.queue))
        audio_data = b''.join(audio_list)
        filename = "output.wav"
        save_wave(filename, audio_data, RATE)
        recognize_audio(filename)
        
    stream.stop_stream()
    stream.close()
    audio.terminate()

# 🏁 主程式
if __name__ == "__main__":
    list_audio_devices()
    listener_thread = threading.Thread(target=listen_continuous, daemon=True)
    listener_thread.start()
    input("按 Enter 鍵停止程式...\n")

