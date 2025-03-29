from enum import Enum
from llm.ollama import OllamaService
from llm.rkllama import RKLlamaService,RKOllamaService
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

        # FIXME, RKLlamaService, need to check / at the end of url.
        # only use one llm in the same time.
        local_url = 'http://10.31.1.13:8080/'
        # Tested
        local_model = 'Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0'
        # system support, token 1024
        # local_model = "gemma-2-2b-it-rk3588-w8a8-opt-1-hybrid-ratio-0.0"

        local_chat = RKOllamaService(model=local_model,url = local_url)
        # local_chat.ServiceProvider = 'rkllama'
        # local_chat.ServiceProvider = 'ollama'

        if remote_chat.check_status():
            dbg_info(f'Using {remote_chat.server_url}')
            self.model_list[LLM.Function.CHAT] = remote_chat
            self.model_list[LLM.Function.REASON] = remote_reason
            remote_chat.connect()
        elif local_chat.check_status():
            dbg_info(f'Using {local_chat.server_url}')
            self.model_list[LLM.Function.CHAT] = local_chat
            self.model_list[LLM.Function.REASON] = local_chat
            local_chat.connect()

    def get_llm(self, function = None):
        return self.model_list[LLM.Function.CHAT]
