# from llm.llm import *
from utility.debug import *
from llm.ollama import OllamaService
from llm.rkllama import RKLlamaService,RKOllamaService
from agent.base import ConversationalAgent

class AssistantAgent(ConversationalAgent):
    def __init__(self, kernel = None):
        super().__init__(kernel)
        # if kernel is None:
        #     # default we use qwen3:1.7b, it's fast and smart enough.
        #     self.kernel = OllamaService(model='qwen3:1.7b', url = 'http://127.0.0.1:11434', token_limit=131072)

        self.agent_description = """
You are a smart, detail-oriented assistant. Always think before answering, never say “I don’t know” too quickly. Focus on solving problems with clear, organized responses — not raw data. Proactively point out anything I may have missed. Match my language (English or Traditional Chinese), and always speak concisely.
1. list reference link, if it's an online search.
2. All you news is out-dated. if request with time realted things, please use api or internet to check.
3. Use Web search only if there is no API to check.
4. User api to get date/time, if you are process time related task.
5. Don't use markdown syntax/bold text, use plain text with space/indention instead.
"""

class SimpleAgent(ConversationalAgent):
    def __init__(self, kernel):
        super().__init__(kernel)
        local_model = 'Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0'
        if kernel is None:
            # system support, token 1024
            # local_model = "gemma-2-2b-it-rk3588-w8a8-opt-1-hybrid-ratio-0.0"
            local_model = 'Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0'
            self.kernel = RKOllamaService(model=local_model,url = local_url)
            self.kernel.connect()

        self.agent_description = f"""
You are a personal assistant responsible for responding to user requests clearly and accurately.

## Workflow:
1. The user gives you a request.
2. If an API call is required, respond directly with the API call command
3. If the user's request lacks necessary details, ask the user directly for clarification.
4. If no API is needed, respond directly in natural language.

{self.apimgr.get_prompt()}

Please follow these rules and examples below to handle user requests.
"""
    def message_compose(self, message):
        msg_buf = []
        if self.kernel.ServiceProvider == 'rkllama':
            msg_buf.append({"role": "user", "content": self.agent_description})
            msg_buf.append({"role": "assistant", "content": "ok"})
        else:
            msg_buf.append({"role": "system", "content": self.agent_description})
            msg_buf.append({"role": "system", "content": self.apimgr.get_prompt()})

        self.history.append({"role": "user", "content": message})

        msg_buf = msg_buf + self.history
        return msg_buf


if __name__ == "__main__":
    llm = LLM()
    chat_ins = llm.get_llm()

    assistant = AssistantAgent(chat_ins)
    while true:
        msg = input("test")
        assistant.send_message(msg)
    # Assistant.

