import json
import re

from api.base import *
from api.system import *
from api.schedule import *
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

        self.register_api(AddScheduleAPI)
        self.register_api(ListSchedulesAPI)
        self.register_api(DeleteScheduleAPI)

    def register_api(self, api_ins):
        if self.api_function_table.get(api_ins.NAME, None) is None:
            # self.api_table[api_ins.NAME] = api_ins

            self.api_function_table[api_ins.NAME] = {
                "func_ptr": api_ins,
                "description": api_ins.DESCRIPTION,
                "parameters": api_ins.PARAMETERS
            }
    def generate_api_doc(self):
        doc = ""
        # doc = "## Available APIs:\n"
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
        api_planner = False
        if api_planner:
            promote = """
    You are an intelligent API planner. Based on the user's input, if an API call is needed, return a JSON object with a "tool_calls" list containing all required tool invocations. If no tool is needed, return {"tool_calls": []}.

    Each tool call should follow this structure:
    {
    "tool": "tool_name",
    "parameters": {
        "param1": "value1",
        "param2": "value2"
    }
    }
            """
        else:
            promote = """
You are an intelligent API planner. Based on the user's input, if an API call is needed, return a JSON object with a "tool_calls" list containing all required tool invocations(If needed, you could ask several times.). If no tool is needed, respone normally.

Each tool call should follow this structure:
{
  "tool_calls": [
    {
        "tool": "tool_name",
        "parameters": {
            "param1": "value1",
            "param2": "value2"
        }
    }
  ]
}
"""
        # avaliable tools
        promote += f"""
## Available tools:
{self.generate_api_doc()}
"""
        # Tips.
#         promote += """
# ## API Tips:
# - Doing CurrentDateTimeAPI before doing AddScheduleAPI.
# """
        # Rules.
        promote += """
## Response Rules:
- If the instruction is clear and matches an available API → Call the API. Your output should be valid JSON and nothing else.
- If the instruction is clear but does not match any API → Respond directly to the user.
- If the instruction is unclear or missing details → Ask the user for clarification.
"""
        return promote
    def fix_common_json_errors(self, raw: str) -> str:
        """
        Try to fix common JSON issues from LLM outputs.
        """
        fixed = raw.strip()

        # Replace single quotes with double quotes
        fixed = fixed.replace("'", '"')

        # Remove trailing commas (before } or ])
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

        return fixed

    def parse_ai_message(self, message: str) -> list:
        """
        Parse tool_calls from LLM response. Try to fix bad JSON if needed.
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            dbg_trace("Original message is not valid JSON. Trying to fix...")
            try:
                fixed_message = self.fix_common_json_errors(message)
                data = json.loads(fixed_message)
            except json.JSONDecodeError:
                dbg_trace("Failed to parse even after fix.")
                return []

        if isinstance(data, dict) and "tool_calls" in data:
            tool_calls = data["tool_calls"]
            if isinstance(tool_calls, list):
                dbg_trace(f"Parsed tool_calls: {tool_calls}")
                return tool_calls

        dbg_warning("JSON does not contain valid 'tool_calls' list.")
        return []

    def handle_ai_message(self, message: str) -> dict:
        """
        Parses an LLM message, calls an API if needed, and returns structured result for LLM to consume.
        """
        try:
            # Step 1: Parse tool calls from AI output
            tool_calls = self.parse_ai_message(message)
            if not tool_calls:
                dbg_trace("No tool calls detected.")
                return {
                    "tool_results": [],
                    "reasoning": "No API call needed. Pure LLM response."
                }

            # Step 2: Execute tool calls
            tool_results = []

            for call in tool_calls:
                api_name = call.get("tool")
                params = call.get("parameters", {})

                if not api_name:
                    dbg_warning("Missing tool name in call.")
                    continue

                api_entry = self.api_function_table.get(api_name)
                if not api_entry:
                    dbg_warning(f"API '{api_name}' not found.")
                    tool_results.append({
                        "tool": api_name,
                        "error": f"Tool '{api_name}' not found."
                    })
                    continue

                func_ptr = api_entry.get("func_ptr")
                if not func_ptr:
                    dbg_warning(f"No function pointer for '{api_name}'.")
                    continue

                try:
                    api_instance = func_ptr()
                    result = api_instance.execute(**params)
                    tool_results.append({
                        "tool": api_name,
                        "result": result
                    })
                except Exception as e:
                    dbg_error(f"Failed to execute '{api_name}' with params {params}")
                    dbg_error(e)
                    traceback_output = traceback.format_exc()
                    dbg_error(traceback_output)

                    tool_results.append({
                        "tool": api_name,
                        "error": str(e),
                        "traceback": traceback_output
                    })

            return {
                "tool_results": tool_results,
                "reasoning": "Executed tool calls based on AI intent."
            }

        except Exception as outer_error:
            dbg_error("Exception in handle_ai_message")
            dbg_error(outer_error)
            traceback_output = traceback.format_exc()
            dbg_error(traceback_output)
            return {
                "tool_results": [],
                "error": str(outer_error),
                "traceback": traceback_output
            }
