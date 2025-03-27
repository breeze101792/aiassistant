from enum import Enum
from llm.ollama import OllamaService
from llm.rkllama import RKLlamaService
from utility.debug import *

class LLM:
    class Function(Enum):
        CHAT = 1
        REASON = 2
        CODE = 3
        VISION = 4
    def __init__(self):
        self.model_list = {}

        # FIXME, remove hard coded.
        remote_chat = OllamaService(model='qwen2.5', url = 'http://10.31.1.7:11434')
        # remote_chat = OllamaService(model='phi4-mini', url = 'http://10.31.1.7:11434')
        # remote_chat = OllamaService(model='llama3.2', url = 'http://10.31.1.7:11434')
        # remote_chat = OllamaService(model='qwq', url = 'http://10.31.1.7:11434')
        # remote_chat = OllamaService(model='mistral', url = 'http://10.31.1.7:11434')
        remote_reason = OllamaService(model='deepseek-r1', url = 'http://10.31.1.7:11434')

        # FIXME, RKLlamaService, need to check / at the end of url.
        # local_chect = RKLlamaService(model="Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0",url = 'http://10.31.1.13:8080/')
        local_chect = RKLlamaService(model="TinyLlama-1.1B-Chat-v1.0-rk3588-w8a8-opt-0-hybrid-ratio-0.5",url = 'http://10.31.1.13:8080/')
        local_reason = RKLlamaService(model="deepseek-coder-7b-instruct-v1.5-rk3588-w8a8_g256-opt-1-hybrid-ratio-0.5",url = 'http://10.31.1.13:8080/')

        if remote_chat.check_status():
            dbg_info(f'Using {remote_chat.server_url}')
            self.model_list[LLM.Function.CHAT] = remote_chat
            self.model_list[LLM.Function.REASON] = remote_reason
        elif local_chect.check_status():
            dbg_info(f'Using {local_chect.server_url}')
            self.model_list[LLM.Function.CHAT] = local_chect
            self.model_list[LLM.Function.REASON] = local_reason

    def get_llm(self, function = None):
        return self.model_list[LLM.Function.CHAT]
