import queue

from llm.base import BaseService
from utility.debug import *

from openai import OpenAI


class OpenaiService(BaseService):
    ServiceProvider = 'openai'
    # def __init__(self, model = None, url = None, api_key = "", token_limit = 10000):
    #     super().__init__(model, url, api_key, token_limit)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # Function to send a chat message
    def generate_response(self, message, hidden = False, name = "AI"):

        dbg_trace(f"Message: {message}")
        try:

            client = OpenAI(
                base_url=self.server_url,
                api_key=self.api_key,
            )

            completion = client.chat.completions.create(
                model=self.model,
                messages = message
            )
            replay_message = completion.choices[0].message.content
            print(f"{name}: ", replay_message)
            return replay_message
        except Exception as e:
            print("Error:", e)
            self.connect()
            return None
