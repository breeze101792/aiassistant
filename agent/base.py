from utility.debug import *
from api.api import APIManager
from api.apijson import APIManager

class BaseAgent:
    def __init__(self, kernel = None):
        if kernel is not None:
            self.kernel = kernel
        # if your model is 4k, please do 4k - 0.5k. This is for response message.
        # self.token_compress_threshold = 3000
        self.token_compress_target = 600
        self.history = []
        self.agent_description = "You are helpful assistant."
        self.apimgr = APIManager()
    def set_kernel(self, kernel):
        self.kernel = kernel
    # Internal API
    def message_compose(self, message):
        msg_buf = []
        if self.kernel.ServiceProvider == 'rkllama':
            msg_buf.append({"role": "user", "content": self.agent_description + self.apimgr.get_prompt()})
            msg_buf.append({"role": "assistant", "content": "ok"})
        else:
            msg_buf.append({"role": "system", "content": self.agent_description})
            msg_buf.append({"role": "system", "content": self.apimgr.get_prompt()})

        self.history.append({"role": "user", "content": message})

        msg_buf = msg_buf + self.history
        return msg_buf
    def append_history(self, role, message):
        self.history.append({"role": role, "content": message})
    def compress_history(self):
        dbg_info(f"Compressing chat history.")
        latest_history = self.history[-2:]
        msg_buf = self.history[:-2]
        tokens_for_each_part = int(self.token_compress_target / 3)
        compress_promote = f"""
Summarize the previous conversation with the following things:
- The user's main questions, goals, and requests, use {tokens_for_each_part} words to explain it.
- The AI's key responses, explanations, and suggestions, use {tokens_for_each_part} words to explain it.
- Any important decisions or conclusions reached, use {tokens_for_each_part} words to explain it.
And show the last user question for keeping dialogue go smoothly.
"""
        # Please help me summarize coversation above to whitin {self.token_compress_target} words."
        msg_buf.append({"role": "user", "content": compress_promote})
        result_buf = self.kernel.generate_response(msg_buf, hidden = True)

        compressed_history = """
We have had previous conversations that are relevant to our ongoing discussion. To maintain context and continuity, I am providing a summarized version of our prior conversation:
{result_buf}
This summarized history contains the key points and context of our previous interactions. Please use this information as context for any future responses.
"""
        self.history = []
        if self.kernel.ServiceProvider == 'rkllama':
            self.history.append({"role": "user", "content": compressed_history})
        else:
            self.history.append({"role": "system", "content": compressed_history})
        self.history.append({"role": "assistant", "content": "ok."})
        self.history = self.history + latest_history
        # self.history = [{"role": "system", "content": f"recap for previous chat. self.agent_description"}]

    def check_history(self):
        token_cnt = self.kernel.calculate_token_count(self.history)
        dbg_debug(f"TokenCnt: {token_cnt}")
        if token_cnt > self.kernel.get_token_limit() - self.token_compress_target:
            self.compress_history()
    # External API
    def send_message(self, message):
        # conpose message 
        msg_buf = self.message_compose(message)

        # get response 
        response_buf = self.kernel.generate_response(msg_buf)
        # print(f"asstant: {response_buf}")
        api_result = self.apimgr.handle_ai_message(response_buf)
        # if api_result != "":
        dbg_trace(api_result['tool_results'])
        while api_result != "" and len(api_result['tool_results']) != 0:
            result_buf = f"""
API Result: {api_result}
"""
            msg_buf.append({"role": "assistant", "content": response_buf})
            if self.kernel.ServiceProvider == 'rkllama':
                msg_buf.append({"role": "user", "content": result_buf})
            else:
                msg_buf.append({"role": "system", "content": result_buf})

            response_buf = self.kernel.generate_response(msg_buf)

            api_result = self.apimgr.handle_ai_message(response_buf)

        # save history.
        self.append_history('assistant',response_buf)

        self.check_history()
        return response_buf
