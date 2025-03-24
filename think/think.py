import sys
import os
import threading
import queue

import think.ollama as olllm
import think.rkllama as rkllm

from utility.debug import *

class Think:
    def __init__(self):
        self.result_queue = queue.Queue()
        self.llm = olllm.OllamaService()
        # self.llm = rkllm.RKLlamaService()
    def start(self):
        pass
    def stop(self):
        pass
    def think(self, message, block = True):
        self.llm.send_message(message)
