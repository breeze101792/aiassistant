from enum import Enum
from llm.ollama import OllamaService
from llm.rkllama import RKLlamaService

class LLM:
    class Function(Enum):
        CHAT = 1
        REASON = 2
        CODE = 3
        VISION = 4
    def __init__(self):
        pass

    def get_llm(self, function = None):
        # return OllamaService()
        return RKLlamaService()
