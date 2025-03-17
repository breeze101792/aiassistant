import requests
import json
import sys
import os
import threading
import queue

from utility.debug import *

class Think:
    def __init__(self, agent_description = None):

        self.history = []
        self.stream_mode = True
        self.verbose = False

        self.result_queue = queue.Queue()
        self.service_thread = None

        port = "8080"
        self.api_url = f"http://127.0.0.1:{port}/"
        self.model = "Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0"

        if agent_description is None:
            agent_description = """
Your name is Mark, a real word helpful assistant. Replay user only with English or Chinese Traditional, don't do it both.

                            """
        self.history.append({"role": "user", "content": agent_description})
        self.history.append({"role": "assistant", "content": "ok"})
    def start(self):
        if self.check_status() != 200 and command not in ['serve', 'update']:
            dbg_error(f"Error: Server not started!")
            raise
        self.switch_model(self.model)

    def check_status(self):
        try:
            response = requests.get(self.api_url)
            return response.status_code
        except:
            return 500

    def think(self, message, block = True):
        self.result_queue = queue.Queue()

        if block is False:
            service_thread = threading.Thread(target=self.send_message, args=(message, ), daemon=True)
            service_thread.start()
            return None
        else:
            return self.send_message(message)

    # Sends a message to the loaded model and displays the response.
    def send_message(self, message):
        # dbg_info(f"User: {message}")

        self.history.append({"role": "user", "content": message})

        # if self.verbose == True:
        #     print(self.history)

        payload = {
            "messages": self.history,
            "stream": self.stream_mode
        }

        assistant_message = None
        if not self.result_queue.empty():
            self.result_queue.queue.clear()

        try:
            if self.stream_mode:
                with requests.post(self.api_url + "generate", json=payload, stream=True) as response:

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
                                        self.result_queue.put(tmp_buf)
                                        tmp_buf = ""

                                except json.JSONDecodeError:
                                    dbg_error(f"Error detecting JSON response.")
                        self.result_queue.put(tmp_buf)

                        if self.verbose == True:
                            tokens_per_second = final_json["usage"]["tokens_per_second"]
                            completion_tokens = final_json["usage"]["completion_tokens"]
                            dbg_debug(f"\n\nTokens per second: {tokens_per_second}")
                            dbg_debug(f"Number of tokens  : {completion_tokens}")

                        self.history.append({"role": "assistant", "content": assistant_message})

                        # Return to line after last token
                        dbg_print("\n")

                    else:
                        dbg_error(f"Streaming error: {response.status_code} - {response.text}")

            else:
                response = requests.post(self.api_url + "generate", json=payload)
                if response.status_code == 200:
                    response_json = response.json()
                    assistant_message = response_json["choices"][0]["content"]
                    self.result_queue.get(response_json["choices"][0]["content"])

                    dbg_print(f"Assistant: {assistant_message}")

                    if self.verbose == True:
                            tokens_per_second = final_json["usage"]["tokens_per_second"]
                            completion_tokens = final_json["usage"]["completion_tokens"]
                            dbg_debug(f"\n\nTokens per second: {tokens_per_second}")
                            dbg_debug(f"Number of Tokens  : {completion_tokens}")

                    self.history.append({"role": "assistant", "content": assistant_message})
                else:
                    dbg_error(f"Query error: {response.status_code} - {response.text}")

            dbg_info("Finished generation.")
        except requests.RequestException as e:
            dbg_error(f"Query error: {e}")

        return assistant_message

    # Function to change model if the old model loaded is not the same one to execute
    def switch_model(self, new_model):
        response = requests.get(self.api_url + "current_model")
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
            response = requests.post(self.api_url + "load_model", json=payload)
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
            response = requests.post(self.api_url + "unload_model")
            if response.status_code == 200:
                dbg_info(f"Model successfully unloaded.")
            else:
                dbg_error(f"Error when unloading model: {response.status_code} - {response.json().get('error', response.text)}")
        except requests.RequestException as e:
            dbg_error(f"Query error: {e}")
