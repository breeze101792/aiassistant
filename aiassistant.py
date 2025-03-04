#!/usr/bin/env python3
# system function
from optparse import OptionParser
import os
import subprocess as sp
import time

from utility.cli import CommandLineInterface as cli 
from utility.debug import *

# Core
from core.settings import *

psettings = Setting()

def main():
    parser = OptionParser(usage='Usage: LlamaAgent [options] ......')
    parser.add_option("-d", "--debug", dest="debug",
                    help="debug mode on!!", action="store_true")
    parser.add_option("-m", "--model", dest="model_name",
                    help="Specify model name.", action="store")
    parser.add_option("-s", "--server", dest="server_ip",
                    help="Specify server ip.", action="store")

    (options, args) = parser.parse_args()

    if options.debug:
        DebugSetting.setDbgLevel("all")
        dbg_info('Enable Debug mode')
        psettings.Info.Debug = True
    else:
        DebugSetting.setDbgLevel("information")

    # open file
    try:
        dbg_print("Hello. It's your ai assistant.")

        dbg_print(psettings.Message.Exit)
    except (OSError, KeyboardInterrupt):
        dbg_error(psettings.Message.Exit)
    except:
        raise
if __name__ == '__main__':
    main()
