import re
import traceback
from api.base import *
from api.system import *
from api.websearch import *
from utility.debug import *

class APIManager:
    def __init__(self):
        # self.api_table = {}
        self.api_function_table = {}

        self.register_api(WeatherAPI)
        self.register_api(CurrentDateTimeAPI)
        self.register_api(SysCmdAPI)
        self.register_api(WebSearchAPI)

    def register_api(self, api_ins):
        if self.api_function_table.get(api_ins.NAME, None) is None:
            # self.api_table[api_ins.NAME] = api_ins

            self.api_function_table[api_ins.NAME] = {
                "func_ptr": api_ins,
                "description": api_ins.DESCRIPTION,
                "parameters": api_ins.PARAMETERS
            }
    def generate_api_doc(self):
        doc = "📌 Available APIs:\n"
        # print(self.api_function_table.items())
        for api_name, detail in self.api_function_table.items():
            doc += f"{api_name}\n"
            doc += f"  - Description: {detail['description']}\n"
            doc += f"  - Parameters:\n"
            if len(detail["parameters"]) > 0:
                for param, desc in detail["parameters"].items():
                    doc += f"    - {param}: {desc}\n"
            else:
                doc += "Not accept any parameters.\n"
            doc += "\n"
        return doc

    def get_prompt(self):
        return f"""
You have access to the following APIs with system. All returns need to process by you, excuete once at a time.
[Usage]
To call an API, just output only one line:  
APIName(param1=value1, param2=value2)

* example usages:
WeatherAPI(location="New York")
* example wihout param:
CurrentDateTimeAPI()

[API Documents]
{self.generate_api_doc()}

!If no API is needed, just reply normally. DO NOT reveal API use to user.
"""

    def parse_ai_message(self, message: str):
        # 用正則表達式或 LLM 提取 API 名與參數
        # match = re.search(r"\[(\w+)\((.*?)\)\]", message)
        match = re.search(r"(\w+)\((.*?)\)", message)
        if not match:
            return None, {}

        api_name = match.group(1)
        param_str = match.group(2)
        params = {}
        if param_str:
            for item in param_str.split(","):
                key, val = item.split("=")
                params[key.strip()] = eval(val.strip())
        return api_name, params
    def handle_ai_message(self, message):
        api_name, params = self.parse_ai_message(message)
        if not api_name:
            dbg_trace( "No API call detected.")
            return ""

        # api_class = self.api_table.get(api_name)
        api_class = self.api_function_table.get(api_name)['func_ptr']

        if not api_class:
            dbg_warning(f"API '{api_name}' not found.")
            return ""

        respone = ""
        try:
            api_instance = api_class()
            respone = api_instance.execute(**params)
        except Exception as e:
            dbg_error(f"Message: {message}")
            dbg_error(e)

            traceback_output = traceback.format_exc()
            dbg_error(traceback_output)
        return respone
