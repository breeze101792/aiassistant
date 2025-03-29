import traceback
from utility.debug import *
from utility.cli import *

from agent.assistant import *
from llm.llm import *

class AICLI(CommandLineInterface):
    def __init__(self):
        super().__init__(promote='LLM')
        self.llm = LLM()
        self.current_agent = AssistantAgent

        # self.regist_cmd("chat", self.cmd_chat, description="Start to chat.", arg_list=['project', 'task', 'name', 'description']  )
        self.regist_cmd("chat", self.cmd_chat, description="Start to chat.")
        self.regist_cmd("connect", self.cmd_connect, description="Reconnect llm model.")
        self.total_agent_list = ['assistant', 'simple', 'professor']
        self.regist_cmd("agent", self.cmd_agent, description="Switch agent.", arg_list = self.total_agent_list)
        # self.total_agent_list = ['assistant', 'simple']
        # self.regist_cmd("llm", self.cmd_llm, description="Switch llm.", arg_list = self.total_agent_list)
        self.regist_cmd("test", self.cmd_test, description="Auto test current agent.")

    def cmd_connect(self, args):
        pass
        # chat_ins = self.llm.get_llm()
        # chat_ins.connect()
    def cmd_llm(self, args):
        llm_list = self.total_llm_list

        if args['#'] == 1 and args['1'] in llm_list:
            if args['1'] == 'assistant':
                self.current_agent = AssistantAgent
                dbg_info(f"Switch to {args['1']} agent")
                return True
            elif args['1'] == 'simple':
                self.current_agent = SimpleAgent
                dbg_info(f"Switch to {args['1']} agent")
                return True
        return False
    def cmd_agent(self, args):
        agent_list = self.total_agent_list

        if args['#'] == 1 and args['1'] in agent_list:
            if args['1'] == 'assistant':
                self.current_agent = AssistantAgent
                dbg_info(f"Switch to {args['1']} agent")
                return True
            elif args['1'] == 'simple':
                self.current_agent = SimpleAgent
                dbg_info(f"Switch to {args['1']} agent")
                return True
            elif args['1'] == 'professor':
                self.current_agent = ProfessorAgent
                dbg_info(f"Switch to {args['1']} agent")
                return True

        return False
    def cmd_test(self, args):
        test_question = ['Who will host the next Olympics game?']
        assistant = self.current_agent()

        for each_question in test_question:
            dbg_info(f"Question: {each_question}")
            assistant.send_message(each_question)

    def cmd_chat(self, args):
        assistant = self.current_agent()

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

