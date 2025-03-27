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
        remote_reason = OllamaService(model='deepseek-r1', url = 'http://10.31.1.7:11434')

        local_chect = OllamaService(model="Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0",url = 'http://10.31.1.13:11434')
        local_reason = OllamaService(model="deepseek-coder-7b-instruct-v1.5-rk3588-w8a8_g256-opt-1-hybrid-ratio-0.5",url = 'http://10.31.1.13:11434')

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
