# system file
import traceback
import time
import threading
import queue

# Local file
from utility.debug import *
from listen.listen import *

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
        dbg_info('Heatbeat Start.')
        self.flag_heatbeat_running = True

        # TODO Impl heatbeat
        heart_beat_interval_time=60
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

        dbg_info('Think Service Start.')
        # self.flag_service_running = True
        # TODO, change it to real life settings.

        while True:
            try:

                self.flag_think = True
                input_text = self.listen_queue.get()
                dbg_info(f"User: {input_text}")
                # TODO, We will thinkg here.
                ###############################################################
                time.sleep(2)

                self.flag_think = False
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
        dbg_info('Listen Service Start.')
        # self.flag_service_running = True
        # TODO, change it to real life settings.
        # service_interval_time=5
        # dbg_trace('start listen hearing')
        self.listen.start()
        # dbg_trace('finished listen hearing')

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
        dbg_warning('Service End.')
    def initialize(self):
        dbg_info('Core start initialize.')
        try:
            # modules
            self.listen = Listen(device_idx=5)
            self.speak = None
            self.think = None

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
            self.flag_service_running = True
            # self.service_thread = threading.Thread(target=self.__service)
            # self.service_thread.start()
            # thread_list.append(self.service_thread)

            # think
            self.think_service_thread = threading.Thread(target=self.__think_service)
            self.think_service_thread.start()
            thread_list.append(self.think_service_thread)

            # listen
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

