import speech_recognition as sr
import queue
import time
import threading

from utility.debug import *

class Listen:
    HOTWORDS = ["hey assistant", "hi mark", "hey mark"]
    SILENCE_TIMEOUT = 20  # 若超過 n 秒沒偵測到語音，則回到 Hotword 偵測模式
    def __init__(self, device_idx = 0):
        self.device_idx = device_idx

        self.listen_queue = queue.Queue()
        self.flag_run = False
        self.service_thread = None
        self.is_waiting = False

        self.last_speech_time = time.time()  # 記錄最後一次辨識成功的時間

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
        self.service_thread = threading.Thread(target=self.__service, daemon=True)
        self.service_thread.start()

    def __service(self):
        dbg_info("Listen Module Service thread start")
        self.flag_run = True
        """主迴圈，持續等待喚醒詞並進入語音模式"""
        while self.flag_run:
            if self.listen_for_hotword(self.device_idx):
                self.listen_for_speech(self.device_idx)
        dbg_info("Listen Module Service thread end")

    def listen_for_hotword(self, device_index=0):
        """Listen for a wake word from the list of HOTWORDS"""
        recognizer = sr.Recognizer()
        mic = sr.Microphone(device_index=device_index)

        with mic as source:
            dbg_info(f"Waiting for hotword at device {device_index}...")
            recognizer.adjust_for_ambient_noise(source)

            while True:
                try:
                    audio = recognizer.listen(source)
                    text = recognizer.recognize_google(audio).lower()
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


    def listen_for_speech(self, device_index=0):
        """在 Hotword 被觸發後，開始持續監聽語音"""
        recognizer = sr.Recognizer()
        mic = sr.Microphone(device_index=device_index)

        self.last_speech_time = time.time()  # 記錄最後一次辨識成功的時間

        with mic as source:
            recognizer.adjust_for_ambient_noise(source)  # 降低背景雜音
            dbg_info("🔊 Enter listen mode, please speak...")

            while True:
                try:
                    audio = recognizer.listen(source, timeout=3)  # 限制錄音時間
                    text = recognizer.recognize_google(audio).lower()

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
