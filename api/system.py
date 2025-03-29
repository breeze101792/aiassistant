from api.base import BaseAPI
class SysCmdAPI(BaseAPI):
    NAME = "SysCmdAPI"
    DESCRIPTION = "Get weather information for a specific location."
    PARAMETERS = {
        "cmd": """Execute limit commands to get system info.
        [support command]
        ls: list file in the current working dir.
        uname: get the kernel name of current running kernel info.
        """
        }
    def execute(self, cmd=""):
        return f"Empty."

class ScheduleAPI(BaseAPI):
    NAME = "ScheduleAPI"
    DESCRIPTION = "Add a todo job/things on scheduler for AI. when the time come, it'll callback to ai to do the task."
