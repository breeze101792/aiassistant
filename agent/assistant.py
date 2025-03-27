# from llm.llm import *
from utility.debug import *

class BaseAgent:
    def __init__(self, kernel):
        self.kernel = kernel
        # if your model is 4k, please do 4k - 0.5k. This is for response message.
        # self.token_compress_threshold = 3000
        self.token_compress_target = 600
        self.history = []
        self.agent_description = "You are helpful assistant."
    # Internal API
    def message_compose(self, message):
        msg_buf = []
        rkllama = False
        if rkllama is True:
            msg_buf.append({"role": "user", "content": self.agent_description})
            msg_buf.append({"role": "assistant", "content": "ok"})
        else:
            msg_buf.append({"role": "system", "content": self.agent_description})


        self.history.append({"role": "user", "content": message})

        msg_buf = msg_buf + self.history
        return msg_buf
    def append_history(self, role, message):
        self.history.append({"role": role, "content": message})
    def send_message(self, message):
        pass
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
        self.history.append({"role": "system", "content": compressed_history})
        self.history.append({"role": "assistant", "content": "ok."})
        self.history = self.history + latest_history
        # self.history = [{"role": "system", "content": f"recap for previous chat. self.agent_description"}]

    def check_history(self):
        token_cnt = self.kernel.calculate_token_count(self.history)
        dbg_debug(f"TokenCnt: {token_cnt}")
        if token_cnt > self.kernel.get_token_limit():
            self.compress_history()
    # External API
    def send_message(self, message):
        # conpose message 
        msg_buf = self.message_compose(message)

        # get response 
        result_buf = self.kernel.generate_response(msg_buf)
        # print(f"asstant: {result_buf}")

        # save history.
        self.append_history('assistant',result_buf)

        self.check_history()
        return result_buf

class AssistantAgent(BaseAgent):
    def __init__(self, kernel):
        super().__init__(kernel)
        self.agent_description = """
You are a smart, detail-oriented assistant. Always think before answering, never say “I don’t know” too quickly. Focus on solving problems with clear, organized responses — not raw data. Proactively point out anything I may have missed. Match my language (English or Traditional Chinese), and always speak concisely.
"""


if __name__ == "__main__":
    llm = LLM()
    chat_ins = llm.get_llm()

    assistant = AssistantAgent(chat_ins)
    while true:
        msg = input("test")
        assistant.send_message(msg)
    # Assistant.

