import speech_recognition as sr
import queue
import time

import os
import sys

# sys.stderr = open(os.devnull, "w")  # 抑制所有 stderr 輸出
# sys.stderr = sys.__stderr__
sys.stderr = None


# HOTWORD = "hey assistant"  # 你的喚醒詞
HOTWORDS = ["hey assistant", "hi mark", "hey mark"]
SILENCE_TIMEOUT = 20  # 若超過 n 秒沒偵測到語音，則回到 Hotword 偵測模式

# 創建一個 Queue 存放語音辨識結果
speech_queue = queue.Queue()

def listen_for_hotword(device_index=0):
    """Listen for a wake word from the list of HOTWORDS"""
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=device_index)

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)
        print("Waiting for hotword...")

        while True:
            try:
                audio = recognizer.listen(source)
                text = recognizer.recognize_google(audio).lower()
                print(f"Recognized: {text}")

                # ✅ Check if any hotword is detected
                if any(word in text for word in HOTWORDS):
                    print("✅ Hotword detected! Activating assistant...")
                    return text
            except sr.UnknownValueError:
                pass  # No speech detected, continue listening
            except sr.RequestError:
                print("❌ Speech recognition service error")
                return False


def listen_for_speech(device_index=0):
    """在 Hotword 被觸發後，開始持續監聽語音"""
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=device_index)
    
    last_speech_time = time.time()  # 記錄最後一次辨識成功的時間

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)  # 降低背景雜音
        print("🔊 進入語音辨識模式，請開始說話...")

        while True:
            try:
                audio = recognizer.listen(source, timeout=3)  # 限制錄音時間
                text = recognizer.recognize_google(audio).lower()
                
                # 如果成功辨識到語音
                if text:
                    print(f"📝 辨識結果: {text}")
                    speech_queue.put(text)  # 放入 queue
                    last_speech_time = time.time()  # 更新時間
                
            except sr.UnknownValueError:
                pass  # 沒有偵測到可辨識的語音
            except sr.WaitTimeoutError:
                pass  # 若 3 秒內沒聲音，繼續監聽
            except sr.RequestError:
                print("❌ 語音辨識服務錯誤")
                return

            # 如果超過 SILENCE_TIMEOUT 秒沒有語音輸入，則返回 hotword 偵測模式
            if time.time() - last_speech_time > SILENCE_TIMEOUT:
                print("🛑 太久沒說話，回到喚醒詞監聽模式...")
                return

def main_loop(device_index=0):
    """主迴圈，持續等待喚醒詞並進入語音模式"""
    while True:
        if listen_for_hotword(device_index):
            listen_for_speech(device_index)

if __name__ == "__main__":
    main_loop(device_index=5)  # 設定麥克風索引

