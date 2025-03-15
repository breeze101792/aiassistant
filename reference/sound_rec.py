import speech_recognition as s_r

def list_dev():
    for index, name in enumerate(s_r.Microphone.list_microphone_names()):
        print("Microphone with name \"{1}\" found for `Microphone(device_index={0})`".format(index, name))

HOTWORD = "hey jack"  # 你可以改成自己的喚醒詞

def listen_for_hotword(device_index = 0):
    """監聽麥克風，等待喚醒詞"""
    recognizer = s_r.Recognizer()
    mic = s_r.Microphone(device_index=device_index)

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)  # 降低背景雜音
        print(f"正在使用裝置 {device_index}，等待喚醒詞...")

        while True:
            try:
                audio = recognizer.listen(source)
                text = recognizer.recognize_google(audio).lower()  # 轉為小寫
                print(f"辨識結果: {text}")

                if HOTWORD in text:
                    print("✅ 偵測到熱詞，啟動助理！")
                    return text  # 返回語音內容，可用於後續處理
            except s_r.UnknownValueError:
                print("未偵測到語音")
            except s_r.RequestError:
                print("語音辨識服務錯誤")

def recon(device_index = 0):
    r = s_r.Recognizer()
    my_mic = s_r.Microphone(device_index=device_index) #my device index is 1, you have to put your device index
    with my_mic as source:
        print("Say now!!!!")
        r.adjust_for_ambient_noise(source) #reduce noise
        audio = r.listen(source) #take voice input from the microphone
    # print(r.recognize_google(audio)) #to print voice into text
    # print(r.recognize_google(audio).__str__()) #to print voice into text

    # Recognize speech using Google Web Speech API (offline mode)
    try:
        print("You said: " + r.recognize_google(audio, show_all=False))
    except s_r.UnknownValueError:
        print("Sorry, I could not understand the audio.")
    except s_r.RequestError:
        print("Could not request results from the service.")

def main():
    print(s_r.__version__) # just to print the version not required
    list_dev()
    # recon(5)
    listen_for_hotword(5)

if __name__ == "__main__":
    main()
