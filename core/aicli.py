import traceback
from utility.debug import *
from utility.cli import *

from agent.assistant import AssistantAgent
from llm.llm import *

class AICLI(CommandLineInterface):
    def __init__(self):
        super().__init__(promote='LLM')
        self.llm = LLM()

        # self.regist_cmd("chat", self.cmd_chat, description="Start to chat.", arg_list=['project', 'task', 'name', 'description']  )
        self.regist_cmd("chat", self.cmd_chat, description="Start to chat.")
        self.regist_cmd("connect", self.cmd_connect, description="Reconnect llm model.")
    def cmd_connect(self, args):
        chat_ins = self.llm.get_llm()
        chat_ins.connect()
    def cmd_chat(self, args):
        dbg_info("One Agent.")
        chat_ins = self.llm.get_llm()
        assistant = AssistantAgent(chat_ins)

        while True:
            try:
                msg = input("User :")
                assistant.send_message(msg)
            except Exception as e:
                dbg_error(e)
                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)
            except KeyboardInterrupt:
                dbg_info("Keyboard Interupt.")
                break

