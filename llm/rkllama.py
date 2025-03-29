import requests
import json
import sys
import os
import threading
import queue

from utility.debug import *
from llm.base import BaseService
from llm.ollama import OllamaService

class RKLlamaService(BaseService):
    ServiceProvider = 'rkllama'
    def __init__(self, model = None, url = None):
        if model is not None:
            self.model=model
        else:
            self.model = "Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0"

        super().__init__(model, url)
        # self.server_url = "http://127.0.0.1:8080/"

        self.verbose = False

        # init
        # self.switch_model(self.model)
        # if self.check_status() is False:
        #     self.switch_model(self.model)

    # Sends a message to the loaded model and displays the response.
    def generate_response(self, message, hidden = False):
        dbg_trace(f"Message: {message}")
        stream_mode = True

        # self.history.append({"role": "user", "content": message})

        # if self.verbose == True:
        #     print(self.history)

        payload = {
            "messages": message,
            "stream": stream_mode
        }

        assistant_message = None

        try:
            if stream_mode:
                with requests.post(self.server_url + "generate", json=payload, stream=True) as response:

                    if response.status_code == 200:
                        dbg_print(f"Assistant: ", end="")
                        assistant_message = ""
                        final_json        = {
                            "usage": {
                                "tokens_per_second": 0,
                                "completion_tokens": 0
                            }
                        }

                        tmp_buf = ""
                        for line in response.iter_lines(decode_unicode=True):
                            if line:
                                try:
                                    response_json = json.loads(line)
                                    final_json = response_json

                                    content_chunk = response_json["choices"][0]["content"]
                                    sys.stdout.write(content_chunk)
                                    sys.stdout.flush()
                                    assistant_message += content_chunk
                                    tmp_buf += content_chunk
                                    if '.' in tmp_buf or '?' in tmp_buf or '!' in tmp_buf or "。" in tmp_buf:
                                        # dbg_print(f"{tmp_buf}")
                                        tmp_buf = ""

                                except json.JSONDecodeError:
                                    dbg_error(f"Error detecting JSON response.")

                        if self.verbose == True:
                            tokens_per_second = final_json["usage"]["tokens_per_second"]
                            completion_tokens = final_json["usage"]["completion_tokens"]
                            dbg_debug(f"\n\nTokens per second: {tokens_per_second}")
                            dbg_debug(f"Number of tokens  : {completion_tokens}")

                        # self.history.append({"role": "assistant", "content": assistant_message})

                        # Return to line after last token
                        # dbg_print("\n")

                    else:
                        dbg_error(f"Streaming error: {response.status_code} - {response.text}")

            else:
                response = requests.post(self.server_url + "generate", json=payload)
                if response.status_code == 200:
                    response_json = response.json()
                    assistant_message = response_json["choices"][0]["content"]

                    dbg_print(f"Assistant: {assistant_message}")

                    if self.verbose == True:
                            tokens_per_second = final_json["usage"]["tokens_per_second"]
                            completion_tokens = final_json["usage"]["completion_tokens"]
                            dbg_debug(f"\n\nTokens per second: {tokens_per_second}")
                            dbg_debug(f"Number of Tokens  : {completion_tokens}")

                    self.history.append({"role": "assistant", "content": assistant_message})
                else:
                    dbg_error(f"Query error: {response.status_code} - {response.text}")

            # dbg_info("Finished generation.")
            print("")
        except requests.RequestException as e:
            dbg_error(f"Query error: {e}")

        return assistant_message

    def connect(self):
        self.switch_model(self.model)
    # Function to change model if the old model loaded is not the same one to execute
    def switch_model(self, new_model):
        response = requests.get(self.server_url + "current_model")
        if response.status_code == 200:
            current_model = response.json().get("model_name")

            if current_model:
                dbg_info(f"Unloading the current model: {current_model}")
                self.unload_model()

        if not self.load_model(new_model):
            dbg_info(f"Unable to load model {new_model}.")
            return False

        return True
    # Loads a specific template on the server.
    def load_model(self, model_name, From=None, huggingface_path=None):

        if From != None and huggingface_path != None:
            payload = {"model_name": model_name, "huggingface_path": huggingface_path, "from": From}
        else:
            payload = {"model_name": model_name}

        try:
            response = requests.post(self.server_url + "load_model", json=payload)
            if response.status_code == 200:
                dbg_info(f"Model {model_name} loaded successfully.")
                return True
            else:
                dbg_error(f"Error loading model: {response.status_code} - {response.json().get('error', response.text)}")
            return False
        except requests.RequestException as e:
            dbg_error(f"Query error: {e}")
            return False

    # Unloads the currently loaded model.
    def unload_model(self):
        try:
            response = requests.post(self.server_url + "unload_model")
            if response.status_code == 200:
                dbg_info(f"Model successfully unloaded.")
            else:
                dbg_error(f"Error when unloading model: {response.status_code} - {response.json().get('error', response.text)}")
        except requests.RequestException as e:
            dbg_error(f"Query error: {e}")

class RKOllamaService(OllamaService):
    ServiceProvider = 'rkllama'
    def __init__(self, model = None, url = None):
        super().__init__(model, url)
        # init
        self.rksvc = RKLlamaService(self.model, self.server_url)
        # self.rksvc.switch_model(self.model)

        self.ServiceProvider = self.rksvc.ServiceProvider
        self.token_limit = 900
    def connect(self):
        dbg_info(f'Connect to model: {self.model}')
        self.rksvc.switch_model(self.model)
