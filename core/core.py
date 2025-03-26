# system file
import traceback
import time
import threading
import queue

# Local file
from utility.debug import *
from listen.listen import *
from speak.speak import *
from think.think import *

from agent.assistant import AssistantAgent
from llm.llm import *

class Core:
    def __init__(self):
        # def
        self.def_threading_delay = 0.01

        # Flags
        self.flag_core_running = False
        self.flag_heatbeat_running = False
        self.flag_service_running = False

        # Vars
        self.listen_queue = None
        self.speak_queue = None
        self.flag_think = False

        # modules
        self.listen = None
        self.speak = None
        self.think = None

        # Threading
        self.heatbeat_thread = None

        # class
        self.database = None

        ## FIXME, remove me, when it's done.
        self.one_agent = True

    def __initcheck(self):
        # Check env setup is okay or not.
        return True
    def __sanitycheck(self):
        # Check sanity check on heart beat okay or not.
        # dbg_info('Sanity Check.')
        if not self.listen_queue.empty():
            dbg_info(f"Listen Queue: {self.listen_queue.qsize()}")
        if not self.speak_queue.empty():
            dbg_info(f"Speak Queue: {self.speak_queue.qsize()}")
        pass

    def __heatbeat(self):
        self.flag_heatbeat_running = True

        # TODO Impl heatbeat
        heart_beat_interval_time=60
        dbg_info('Heatbeat Start.')
        while self.flag_core_running and self.flag_heatbeat_running:
            try:
                # dbg_trace('heart beatting every {}s'.format(heart_beat_interval_time))
                self.__sanitycheck()
                time.sleep(heart_beat_interval_time)
            except KeyboardInterrupt:
                dbg_warning("Keyboard Interupt.")
                break;
            except Exception as e:
                dbg_error(e)

                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)

            finally:
                # Finalize service thread.
                if self.flag_core_running is False or self.flag_service_running is False:
                    dbg_trace('Finalize service thread.')
                    break

                time.sleep(self.def_threading_delay)

        self.flag_heatbeat_running = False
        dbg_warning('Heatbeat End.')
    def __service(self):

        dbg_info('Service Start.')
        # self.flag_service_running = True
        # TODO, change it to real life settings.
        service_interval_time=5

        # do the evaluation on every service_interval_time.
        while True:
            try:
                dbg_trace('Service running in every {}s'.format(service_interval_time))


                # TODO, Current only one shot test.
                break
                ###############################################################

                # dbg_info("Tracking List: " + tracking_list.__str__())
                time.sleep(service_interval_time)
            except KeyboardInterrupt:
                dbg_warning("Keyboard Interupt.")
                self.flag_service_running = False
            except Exception as e:
                dbg_error(e)

                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)
                self.flag_service_running = False

            finally:
                # Finalize service thread.
                if self.flag_core_running is False or self.flag_service_running is False:
                    dbg_trace('Finalize service thread.')
                    break

                time.sleep(self.def_threading_delay)

        self.flag_service_running = False
        dbg_warning('Service End.')
    def __think_service(self):
        # self.flag_service_running = True
        # TODO, change it to real life settings.
        self.think.start()
        blocking_mode = True
        blocking_mode = False

        dbg_info('Think Service Start.')
        # input_text = "HI, how are u. today"
        while True:
            try:
                if not self.listen_queue.empty():
                    input_text = self.listen_queue.get()
                else:
                    input_text = None

                if input_text is not None:
                    self.flag_think = True
                    dbg_info(f"User: '{input_text}'")
                    if blocking_mode:
                        assistant_message = self.think.think(input_text)
                        # dbg_print(f"Assistant: {assistant_message}")
                        self.speak_queue.put(assistant_message)
                    else:
                        self.think.think(input_text, block=False)

                    self.listen.wait()

                    self.flag_think = False

                if self.think.result_queue.empty() is False and blocking_mode is False :
                    result_text = self.think.result_queue.get()
                    self.speak_queue.put(result_text)
                # input_text = None
                # time.sleep(5)

            except KeyboardInterrupt:
                dbg_warning("Keyboard Interupt.")
                self.flag_service_running = False
            except Exception as e:
                dbg_error(e)

                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)
                self.flag_service_running = False

            finally:
                # Finalize service thread.
                if self.flag_core_running is False or self.flag_service_running is False:
                    dbg_trace('Finalize service thread.')
                    break

                time.sleep(self.def_threading_delay)

        self.flag_service_running = False
        dbg_warning('Think Service End.')
    def __listen_service(self):
        # self.flag_service_running = True
        # TODO, change it to real life settings.
        # service_interval_time=5
        # dbg_trace('start listen hearing')
        self.listen.start()
        # dbg_trace('finished listen hearing')

        dbg_info('Listen Service Start.')
        # do the evaluation on every service_interval_time.
        while True:
            try:
                # dbg_trace('Service running in every {}s'.format(service_interval_time))

                # if self.listen.listen_for_hotword(device_index):
                #     self.listen.listen_for_speech(device_index)

                # dbg_info(f"Listen Queue: {self.listen.listen_queue.qsize()}, {self.listen.listen_queue.empty()}")
                input_text = self.listen.get()
                if input_text is not None:
                    self.listen_queue.put(input_text)

                if self.flag_think is True or self.listen_queue.empty() is False:
                    self.listen.wait()

                # dbg_info("Tracking List: " + tracking_list.__str__())
                # time.sleep(service_interval_time)
            except KeyboardInterrupt:
                dbg_warning("Keyboard Interupt.")
                self.flag_service_running = False
            except Exception as e:
                dbg_error(e)

                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)
                self.flag_service_running = False

            finally:
                # Finalize service thread.
                if self.flag_core_running is False or self.flag_service_running is False:
                    dbg_trace('Finalize service thread.')
                    break

                time.sleep(self.def_threading_delay)

        self.flag_service_running = False
        dbg_warning('Listen Service End.')
    def __speak_service(self):
        # self.flag_service_running = True
        # TODO, change it to real life settings.
        # service_interval_time=5
        # dbg_trace('start listen hearing')
        self.speak.start()
        # dbg_trace('finished listen hearing')

        dbg_info('Speak Service Start.')
        # do the evaluation on every service_interval_time.
        while True:
            try:
                # dbg_trace('Service running in every {}s'.format(service_interval_time))

                # dbg_info(f"Listen Queue: {self.listen.listen_queue.qsize()}, {self.listen.listen_queue.empty()}")
                if self.speak_queue.empty() is False:
                    speach_text = self.speak_queue.get()
                    self.speak.speak(speach_text)

                    self.listen.wait()

                # dbg_info("Tracking List: " + tracking_list.__str__())
                # time.sleep(service_interval_time)
            except KeyboardInterrupt:
                dbg_warning("Keyboard Interupt.")
                self.flag_service_running = False
            except Exception as e:
                dbg_error(e)

                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)
                self.flag_service_running = False

            finally:
                # Finalize service thread.
                if self.flag_core_running is False or self.flag_service_running is False:
                    dbg_trace('Finalize service thread.')
                    break

                time.sleep(self.def_threading_delay)

        self.flag_service_running = False
        dbg_warning('Speak Service End.')
    def input_service(self):

        dbg_info('Input Service Start.')
        while True:
            try:
                input_text = input('User Input: ')
                if input_text is not None:
                    self.listen_queue.put(input_text)

                if self.flag_think is True or self.listen_queue.empty() is False:
                    self.listen.wait()

            except KeyboardInterrupt:
                dbg_warning("Keyboard Interupt.")
                self.flag_service_running = False
            except Exception as e:
                dbg_error(e)

                traceback_output = traceback.format_exc()
                dbg_error(traceback_output)
                self.flag_service_running = False

            finally:
                # Finalize service thread.
                if self.flag_core_running is False or self.flag_service_running is False:
                    dbg_trace('Finalize service thread.')
                    break

                time.sleep(self.def_threading_delay)

        self.flag_service_running = False
        dbg_warning('Input Service End.')
    def initialize(self):
        dbg_info('Core start initialize.')
        try:
            if self.one_agent:
                pass
            else:
                # modules
                self.listen = Listen(device_index=4)
                self.speak = Speak()
                self.think = Think()

                self.listen_queue = queue.Queue()
                self.speak_queue = queue.Queue()

        except Exception as e:
            dbg_error(e)
            traceback_output = traceback.format_exc()
            dbg_error(traceback_output)
            raise
        finally:
            pass

        dbg_info('Core initialized.')
    def start(self):
        dbg_info('Core Start.')
        thread_list = []

        if self.__initcheck() is False:
            dbg_error('Init check fail. Start.')
            return False

        self.flag_core_running = True
        try:
            if self.one_agent:
                dbg_info("One Agent.")
                llm = LLM()
                chat_ins = llm.get_llm()

                assistant = AssistantAgent(chat_ins)
                while True:
                    msg = input("User :")
                    assistant.send_message(msg)
                # Assistant.

            else:
                self.flag_service_running = True
                # self.service_thread = threading.Thread(target=self.__service)
                # self.service_thread.start()
                # thread_list.append(self.service_thread)

                # think
                self.think_service_thread = threading.Thread(target=self.__think_service)
                self.think_service_thread.start()
                thread_list.append(self.think_service_thread)

                # speak
                self.speak_service_thread = threading.Thread(target=self.__speak_service)
                self.speak_service_thread.start()
                thread_list.append(self.speak_service_thread)

                # listen
                user_input_test = False
                if user_input_test:
                    self.input_service()
                else:
                    self.listen_service_thread = threading.Thread(target=self.__listen_service)
                    self.listen_service_thread.start()
                    thread_list.append(self.listen_service_thread)

                # Monitor Thread
                # self.heatbeat_thread = threading.Thread(target=self.__heatbeat, daemon=True)
                self.heatbeat_thread = threading.Thread(target=self.__heatbeat)
                self.heatbeat_thread.start()
                thread_list.append(self.heatbeat_thread)

                # wait for threading.
                for each_thread in thread_list:
                    each_thread.join()

        except KeyboardInterrupt:
            dbg_warning("Keyboard Interupt.")
        except Exception as e:
            dbg_error(e)
            traceback_output = traceback.format_exc()
            dbg_error(traceback_output)

            self.flag_core_running = False

        finally:
            self.flag_service_running = False
            for each_thread in thread_list:
                each_thread.join()

            if self.flag_heatbeat_running and self.heatbeat_thread is not None:
                self.flag_heatbeat_running = False
                self.heatbeat_thread.join()
                self.heatbeat_thread = None

            self.flag_core_running = False

        dbg_warning('Core End.')

    def quit(self):
        dbg_info('Core Quit.')
        # TODO, do final check.

