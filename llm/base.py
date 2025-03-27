
import traceback
import tiktoken

from utility.debug import *

class BaseService:
    def __init__(self, model = None, url = None, token_limit = 8000):
        if model is not None:
            self.server_url = url
        else:
            self.server_url = "http://127.0.0.1:8080/"
        if model is not None:
            self.model=model
        else:
            self.model = "deepseek-r1"
        self.token_limit = token_limit

        # Checking status.
        # self.check_status
    def check_status(self):
        try:
            response = requests.get(self.server_url)
            dbg_debug(f'Respone code from {self.server_url}:{response.status_code}')
            return True
        except:
            return 500
            return False
    def get_token_limit(self):
        return self.token_limit

    def calculate_token_count(self, messages, model_name='gpt-4'):
        """
        Calculate the total token count for a list of messages using tiktoken.

        Args:
        - messages (list): List of dictionaries with 'role' and 'content'.
        - model_name (str): The model name to select the correct tokenizer. Default is 'gpt-4'.

        Returns:
        - int: Total number of tokens in the messages.
        """
        try:
            # Initialize tokenizer based on the selected model
            encoding = tiktoken.encoding_for_model(model_name)

            total_tokens = 0

            # Loop through each message and calculate token count
            for message in messages:
                content = message.get("content", "")
                tokens = encoding.encode(content)
                total_tokens += len(tokens)

            return total_tokens

        except Exception as e:
            dbg_error(e)

            traceback_output = traceback.format_exc()
            dbg_error(traceback_output)
            return -1
