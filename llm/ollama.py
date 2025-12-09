import queue
import ollama 

from llm.base import BaseService
from utility.debug import *

class OllamaService(BaseService):
    ServiceProvider = 'ollama'
    def __init__(self, model = None, url = None, token_limit = 10000):
        super().__init__(model, url, token_limit)
        # self.server_url = 'http://10.31.1.7:11434'
        # if model is not None:
        #     self.model=model
        # else:
        #     self.model='mistral:latest'

        # self.model='deepseek-r1:latest'
        # self.model='qwen2.5:1.5b'

    # Function to send a chat message
    def generate_response(self, message, hidden = False, name = "AI"):
        dbg_trace(f"Message: {message}")
        # self.history = []
        # self.system_prompt = "You are a help full assistant"
        # self.history.append({"role": "system", "content": self.system_prompt})
        # self.history.append({"role": "user", "content": message})
        # messages = [
        #     {"role": "user", "content": message}
        # ]
        # messages = self.history
        try:
            client = ollama.Client(host=self.server_url)
            stream = client.chat(
                model=self.model,
                messages=message,
                stream=True
            )

            replay_message = ''
            print(f"{name}: ", end = '')
            for chunk in stream:
                # for the first chunk, we print then ai name.

                if not hidden:
                    print(chunk['message']['content'], end='', flush=True)
                replay_message +=chunk['message']['content']

                # if '.' in replay_message or '?' in replay_message or '!' in replay_message or "。" in replay_message:
                #     self.result_queue.put(replay_message)
                #     replay_message = ""
            if not hidden:
                print("")
            # self.history.append({"role": "assistant", "content": replay_message})
            return replay_message
        except Exception as e:
            print("Error:", e)
            self.connect()
            return None
