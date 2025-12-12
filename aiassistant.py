#!/usr/bin/env python3
# system function
from optparse import OptionParser
import os
import subprocess as sp
import time

from utility.cli import CommandLineInterface as cli 
from utility.debug import *

# Core
from core.core import *
from core.config import *

def main():
    parser = OptionParser(usage='Usage: aiassistant [options] ......')
    parser.add_option("-d", "--debug", dest="debug",
                    help="debug mode on!!", action="store_true")
    parser.add_option("-m", "--model", dest="model_name",
                    help="Specify model name.", action="store")
    parser.add_option("-s", "--server", dest="server_ip",
                    help="Specify server ip.", action="store")

    (options, args) = parser.parse_args()

    cfmgr = AIConfigManager()
    cfmgr.load()

    if options.debug:
        DebugSetting.setDbgLevel("all")
        dbg_info('Enable Debug mode')
    # else:
    #     DebugSetting.setDbgLevel("information")

    # open file


    try:
        dbg_info(f"Starting {cfmgr.config.about.program_name} v{cfmgr.config.about.version}")
        core = Core()
        core.initialize()
        core.start()

    except (OSError, KeyboardInterrupt):
        dbg_error("Bye")
    except:
        raise
if __name__ == '__main__':
    main()
