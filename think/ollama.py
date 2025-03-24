
import queue

import ollama 

class OllamaService:
    OLLAMA_SERVER = 'http://10.31.1.7:11434'
    def __init__(self):
        self.result_queue = queue.Queue()
        self.system_prompt = "You are a help full assistant"
        # self.model='deepseek-r1:latest'
        # self.model='qwen2.5:1.5b'
        self.model='mistral:latest'

        self.history = []
        self.history.append({"role": "system", "content": self.system_prompt})
        # self.history.append({"role": "assistant", "content": "ok"})
    def start(self):
        pass

    # Function to send a chat message
    def send_message(self, message, agent = None):
        url = f"{self.OLLAMA_SERVER}/api/chat"
        self.history.append({"role": "user", "content": message})
        # messages = [
        #     {"role": "user", "content": message}
        # ]
        messages = self.history
        try:
            client = ollama.Client(host=self.OLLAMA_SERVER)
            stream = client.chat(
                model=self.model,
                messages=messages,
                stream=True
            )

            replay_message = ''
            for chunk in stream:
                print(chunk['message']['content'], end='', flush=True)
                replay_message +=chunk['message']['content']

                if '.' in replay_message or '?' in replay_message or '!' in replay_message or "。" in replay_message:
                    self.result_queue.put(replay_message)
                    replay_message = ""
            print("")
            self.history.append({"role": "assistant", "content": replay_message})
            return replay_message
        except Exception as e:
            print("Error:", e)
            return None
