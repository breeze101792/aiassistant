import speech_recognition as sr
import wave
import time
from funasr import AutoModel

# 初始化 FunASR 模型
# model = AutoModel(model="paraformer", model_revision="v2.0.4")

# 🔹 設定 FunASR 模型變數
ASR_MODEL = "paraformer-zh"  # 語音識別模型
VAD_MODEL = "fsmn-vad"       # 語音活動檢測（可選）
PUNC_MODEL = "ct-punc"       # 標點符號模型（可選）

# 🔹 加載 FunASR 模型
model = AutoModel(model=ASR_MODEL, vad_model=VAD_MODEL, punc_model=PUNC_MODEL, disable_update=True, disable_log=True, disable_pbar=True)

def list_microphones():
    """列出可用的麥克風設備"""
    print("可用的音訊設備:")
    for index, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"{index}: {name}")

def save_audio(audio_data, filename="temp.wav"):
    """將 SpeechRecognition 錄製的音訊存為 WAV 檔案"""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)  # 單聲道
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(16000)  # 16kHz 取樣率
        wf.writeframes(audio_data.get_wav_data(convert_rate=16000))

def recognize_speech(device_index):
    """使用 SpeechRecognition 進行 VAD，並傳遞音訊給 FunASR"""
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=device_index)

    print("開始監聽，請說話...")
    with mic as source:
        recognizer.adjust_for_ambient_noise(source)  # 自動調整環境噪音
        while True:
            try:
                # audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)  # 最長錄音 5 秒
                audio = recognizer.listen(source, phrase_time_limit=10)  # 最長錄音 5 秒
                print(f"偵測到語音，開始處理...)")
                
                # 存儲錄製的音訊
                save_audio(audio, "temp.wav")

                # 使用 FunASR 進行語音辨識
                result = model.generate("temp.wav")

                # 輸出辨識結果
                print("辨識結果:", result)

                text = recognizer.recognize_google(audio).lower()
                print(f"Google(Google: {text})")
            except sr.WaitTimeoutError:
                print("Timeout, 未偵測到語音，繼續監聽...")
            except sr.UnknownValueError:
                print("Value, 未偵測到語音，繼續監聽...")
                pass  # 沒有偵測到可辨識的語音
            except sr.WaitTimeoutError:
                print("未偵測到語音，繼續監聽...")
                pass  # 若 3 秒內沒聲音，繼續監聽
            except Exception as e:
                print("發生錯誤:", e)

if __name__ == "__main__":
    list_microphones()
    device_index = int(input("請選擇要使用的麥克風設備索引: "))
    recognize_speech(device_index)
