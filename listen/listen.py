import speech_recognition as sr
import queue
import time
import threading

from utility.debug import *

###################################################
import wave
from funasr import AutoModel

# 🔹 設定 FunASR 模型變數
ASR_MODEL = "paraformer-zh"  # 語音識別模型
VAD_MODEL = "fsmn-vad"       # 語音活動檢測（可選）
PUNC_MODEL = "ct-punc"       # 標點符號模型（可選）

def save_audio(audio_data, filename="temp.wav"):
    """將 SpeechRecognition 錄製的音訊存為 WAV 檔案"""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)  # 單聲道
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(16000)  # 16kHz 取樣率
        wf.writeframes(audio_data.get_wav_data(convert_rate=16000))
###################################################

class Listen:
    HOTWORDS = ["hey assistant", "hi mark", "hey mark", "ok google", "hi ducky"]
    SILENCE_TIMEOUT = 20  # 若超過 n 秒沒偵測到語音，則回到 Hotword 偵測模式
    def __init__(self, device_index = 0):
        self.device_index = device_index
        self.listen_queue = queue.Queue()
        self.flag_run = False
        self.service_thread = None
        self.is_waiting = False

        self.last_speech_time = time.time()  # 記錄最後一次辨識成功的時間

        self.recognizer = None
        self.microphone = None

        # self.model = AutoModel(model=ASR_MODEL, vad_model=VAD_MODEL, punc_model=PUNC_MODEL, disable_update=True, disable_log=True, disable_pbar=True)
        self.model = None

    def wait(self):
        self.last_speech_time = time.time()

    def get(self):
        # print(f"Listen Queue: {self.listen_queue.qsize()}, {self.listen_queue.empty()}")
        if not self.listen_queue.empty():
            return self.listen_queue.get()
        else:
            return None

    def list_dev(self):
        for index, name in enumerate(s_r.Microphone.list_microphone_names()):
            dbg_info("Microphone with name \"{1}\" found for `Microphone(device_index={0})`".format(index, name))

    def start(self):
        self.model = AutoModel(model=ASR_MODEL, vad_model=VAD_MODEL, punc_model=PUNC_MODEL, disable_update=True, disable_log=True, disable_pbar=True)
        
        self.service_thread = threading.Thread(target=self.__service, daemon=True)
        self.service_thread.start()

    def __service(self):
        dbg_info("Listen Module Service thread start")
        self.flag_run = True

        # init sr
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=self.device_index)
        """主迴圈，持續等待喚醒詞並進入語音模式"""
        while self.flag_run:
            if self.listen_for_hotword():
                self.listen_for_speech()
        dbg_info("Listen Module Service thread end")

    def listen_for_hotword(self):
        """Listen for a wake word from the list of HOTWORDS"""
        # recognizer = sr.Recognizer()
        # mic = sr.Microphone(device_index=device_index)

        with self.microphone as source:
            dbg_info(f"Waiting for hotword")
            self.recognizer.adjust_for_ambient_noise(source)

            while True:
                try:
                    audio = self.recognizer.listen(source)
                    text = self.recognizer.recognize_google(audio).lower()
                    dbg_trace(f"Recognized: {text}")

                    # ✅ Check if any hotword is detected
                    if any(word in text for word in self.HOTWORDS):
                        dbg_info("✅ Hotword detected! Activating assistant...")
                        return text
                except sr.UnknownValueError:
                    pass  # No speech detected, continue listening
                except sr.RequestError:
                    dbg_error("❌ Speech recognition service error")
                    return False


    def listen_for_speech(self):
        """在 Hotword 被觸發後，開始持續監聽語音"""
        # recognizer = sr.Recognizer()
        # mic = sr.Microphone(device_index=device_index)

        self.last_speech_time = time.time()  # 記錄最後一次辨識成功的時間

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)  # 降低背景雜音
            dbg_info("🔊 Enter listen mode, please speak...")

            while True:
                try:
                    # audio = self.recognizer.listen(source, timeout=3)  # 限制錄音時間
                    audio = self.recognizer.listen(source, phrase_time_limit=10)  # 限制錄音時間

                    # 存儲錄製的音訊
                    save_audio(audio, "temp.wav")

                    # 使用 FunASR 進行語音辨識
                    result = self.model.generate("temp.wav")
                    # 如果成功辨識到語音
                    text = result[0]['text']

                    # text = self.recognizer.recognize_google(audio).lower()

                    # 如果成功辨識到語音
                    if text:
                        dbg_trace(f"📝 Result: {text}")
                        self.listen_queue.put(text)  # 放入 queue
                        self.last_speech_time = time.time()  # 更新時間

                except sr.UnknownValueError:
                    pass  # 沒有偵測到可辨識的語音
                except sr.WaitTimeoutError:
                    pass  # 若 3 秒內沒聲音，繼續監聽
                except sr.RequestError:
                    dbg_error("❌ Service error")
                    return

                # 如果超過 SILENCE_TIMEOUT 秒沒有語音輸入，則返回 hotword 偵測模式
                if time.time() - self.last_speech_time > self.SILENCE_TIMEOUT and self.listen_queue.empty():
                    dbg_info("🛑 listen tiemout, go back to hot word mode...")
                    return
