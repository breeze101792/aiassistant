from listen.halasr import *
from utility.debug import *

class Listen:
    SILENCE_TIMEOUT = 20  # 若超過 n 秒沒偵測到語音，則回到 Hotword 偵測模式
    def __init__(self, device_index = 0, hot_words = ["Hello."]):
        self.last_speech_time = time.time()  # 記錄最後一次辨識成功的時間

        self.asr = ASRService(device_index = device_index, hot_words = hot_words)
    def wait(self):
        self.last_speech_time = time.time()

    def get(self):
        # if time.time() - self.last_speech_time > self.SILENCE_TIMEOUT:
        #     dbg_info("🛑 listen tiemout, go back to hot word mode...")
        #     self.asr.set_pause(True)
        #     return None
        return self.asr.get()
    def start(self):
        self.asr.start()
