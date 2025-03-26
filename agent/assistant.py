# from llm.llm import *

class BaseAgent:
    def __init__(self, kernel):
        self.kernel = kernel

class AssistantAgent(BaseAgent):
    def __init__(self, kernel):
        super().__init__(kernel)
        self.agent_description = "You a helpful assistant."
        self.history = []

    def send_message(self, message):

        msg_buf = []

        # msg_buf.append({"role": "system", "content": agent_description})

        msg_buf.append({"role": "user", "content": self.agent_description})
        msg_buf.append({"role": "assistant", "content": "ok"})

        self.history.append({"role": "user", "content": message})

        msg_buf = msg_buf + self.history

        result_buf = self.kernel.generate_response(msg_buf)
        # print(f"asstant: {result_buf}")

        self.history.append({"role": "assistant", "content": result_buf})


if __name__ == "__main__":
    llm = LLM()
    chat_ins = llm.get_llm()

    assistant = AssistantAgent(chat_ins)
    while true:
        msg = input("test")
        assistant.send_message(msg)
    # Assistant.

