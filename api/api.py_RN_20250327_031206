import re

class BaseAPI:
    def execute(self, **kwargs):
        raise NotImplementedError("You must implement the execute method.")

# from .base import BaseAPI
class WeatherAPI(BaseAPI):
    def execute(self, location="Taipei"):
        return f"The weather in {location} is sunny and 25°C."

def parse_ai_message(message: str):
    # 用正則表達式或 LLM 提取 API 名與參數
    match = re.search(r"\[(\w+)\((.*?)\)\]", message)
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

# from api.weather_api import WeatherAPI
# from api.math_api import MathAPI
# from utils.parser import parse_ai_message

api_registry = {
    "WeatherAPI": WeatherAPI,
    "MathAPI": MathAPI,
}

api_docs = {
    "WeatherAPI": {
        "description": "Get weather information for a specific location.",
        "parameters": {
            "location": "string – Name of the city or area."
        }
    },
    "MathAPI": {
        "description": "Perform a basic math operation.",
        "parameters": {
            "operation": "string – Type of operation. Options: 'add', 'multiply'.",
            "a": "number – First number.",
            "b": "number – Second number."
        }
    }
}

def generate_api_doc():
    doc = "📌 Available APIs:\n"
    for api_name, detail in api_docs.items():
        doc += f"{api_name}\n"
        doc += f"  - Description: {detail['description']}\n"
        doc += f"  - Parameters:\n"
        for param, desc in detail["parameters"].items():
            doc += f"    - {param}: {desc}\n"
        doc += "\n"
    return doc

def get_prompt_template():
    return f"""
You have access to the following APIs.  
To call an API, use this format(Start with '[', end with ']'):  
[APIName(param1=value1, param2=value2)]

{generate_api_doc()}

✳️ Example usages:
- [WeatherAPI(location="New York")]
- [MathAPI(operation="multiply", a=4, b=6)]

❗If no API is needed, just reply normally.
"""

def handle_ai_message(message):
    api_name, params = parse_ai_message(message)
    if not api_name:
        return "No API call detected."

    api_class = api_registry.get(api_name)
    if not api_class:
        return f"API '{api_name}' not found."

    api_instance = api_class()
    return api_instance.execute(**params)

# Example usage
# if __name__ == "__main__":
#     msg = "Tell me the result of [MathAPI(operation='add', a=5, b=3)]."
#     print(handle_ai_message(msg))
#     print("\nGenerated Prompt for AI:\n")
#     print(get_prompt_template())
#


if __name__ == "__main__":
    input_text = '[WeatherAPI(location="Taipei")]'
    result = parse_ai_message(input_text)
    print("Result:", result)

