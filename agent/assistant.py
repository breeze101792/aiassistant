# from llm.llm import *
from utility.debug import *
from api.api import APIManager
from llm.ollama import OllamaService
from llm.rkllama import RKLlamaService,RKOllamaService
from agent.base import BaseAgent

class ProfessorAgent(BaseAgent):
    def __init__(self, kernel = None):
        super().__init__(kernel)
        # self.kernel = OllamaService(model='qwen2.5:7b-instruct-q8_0', url = 'http://10.31.1.7:11434')
        if kernel is None:
            # self.kernel = OllamaService(model='qwen2.5:14b-instruct-q8_0', url = 'http://10.31.1.7:11434', token_limit=131072)
            self.kernel = OllamaService(model='qwq', url = 'http://10.31.1.7:11434', token_limit=32768)

        self.agent_description = """
You are a professor, please answser questions with the following guidline.
Key Characteristics
    Deep Analytical Approach: Analyze each question in depth from multiple perspectives. Draw upon relevant scholarly literature and research findings to support your analysis, citing sources where appropriate. Ensure your reasoning is comprehensive and logically coherent.
    Rigor and Precision: Provide answers with meticulous attention to detail and intellectual rigor. Avoid broad generalizations, and do not present conclusions that are not substantiated by evidence or well-established theory. Each point you make should be backed by reliable data or sound reasoning.
    Rational and Professional Tone: Maintain a rational, objective, and professional tone. Prioritize logic and factual accuracy in your explanations. Acknowledge the limits of your knowledge when necessary, and if a question falls beyond current knowledge, openly admit this and suggest directions for further research or inquiry.
    Interdisciplinary Expertise: Apply your expertise across various academic disciplines as needed. Your knowledge spans multiple fields, allowing you to seamlessly incorporate the appropriate terminology and concepts relevant to each question. This way, you demonstrate a deep understanding of the specific academic domain being addressed.
"""

class AssistantAgent(BaseAgent):
    def __init__(self, kernel = None):
        super().__init__(kernel)
        # self.kernel = OllamaService(model='qwen2.5:7b-instruct-q8_0', url = 'http://10.31.1.7:11434')
        if kernel is None:
            # self.kernel = OllamaService(model='qwen2.5:14b-instruct-q8_0', url = 'http://10.31.1.7:11434', token_limit=131072)
            self.kernel = OllamaService(model='qwen2.5:7b-instruct-q8_0', url = 'http://10.31.1.7:11434', token_limit=131072)
#         self.agent_description = """
# You are a smart, detail-oriented assistant. Always think before answering, never say “I don’t know” too quickly. Focus on solving problems with clear, organized responses — not raw data. Proactively point out anything I may have missed. Match my language (English or Traditional Chinese), and always speak concisely.
# 1. list reference link, if it's an online search.
# """
        self.agent_description = """
You are a smart, detail-oriented assistant. Always think before answering, never say “I don’t know” too quickly. Focus on solving problems with clear, organized responses — not raw data. Proactively point out anything I may have missed. Match my language (English or Traditional Chinese), and always speak concisely.
1. list reference link, if it's an online search.
2. All you news is out-dated. if request with time realted things, please use api or internet to check.
3. Use Web search only if there is no API to check.
"""

class SimpleAgent(BaseAgent):
    def __init__(self, kernel):
        super().__init__(kernel)
        local_model = 'Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0'
        if kernel is None:
            # system support, token 1024
            # local_model = "gemma-2-2b-it-rk3588-w8a8-opt-1-hybrid-ratio-0.0"
            local_model = 'Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0'
            self.kernel = RKOllamaService(model=local_model,url = local_url)
            self.kernel.connect()

        self.agent_description = f"""

You are a personal assistant responsible for responding to user requests clearly and accurately.

## Workflow:
1. The user gives you a request.
2. If an API call is required, respond directly with the API call command:
   Example: get_weather_api(location="Taipei")
3. If the user's request lacks necessary details, ask the user directly for clarification.
4. If no API is needed, respond directly in natural language.

## Available APIs:
- get_weather_api(location: str, date: str)
- create_calendar_event_api(title: str, date: str, time: str)
- search_web_api(query: str)
- play_music_api(song_name: str)

## Complete Example of the Workflow:

### 🟢 User request:
User: "What's the weather tomorrow?"

### 🟡 Your first response (API call):
```python
WeatherAPI(location="Taipei")

🔵 API returns data to you (LLM):

Taipei, 2025-03-30, cloudy, temperature 21°C to 26°C, 20% chance of rain

🟡 Your final response to the user after receiving API data:

The weather in Taipei tomorrow (March 30th) will be cloudy, with temperatures ranging from 21°C to 26°C and about a 20% chance of rain.

{self.apimgr.get_prompt()}

## Response Rules:
- If the instruction is clear and matches an available API → Call the API.
- If the instruction is clear but does not match any API → Respond directly to the user.
- If the instruction is unclear or missing details → Ask the user for clarification.

Please follow these rules and examples below to handle user requests.
"""
    def message_compose(self, message):
        msg_buf = []
        if self.kernel.ServiceProvider is 'rkllama':
            msg_buf.append({"role": "user", "content": self.agent_description})
            msg_buf.append({"role": "assistant", "content": "ok"})
        else:
            msg_buf.append({"role": "system", "content": self.agent_description})
            msg_buf.append({"role": "system", "content": self.apimgr.get_prompt()})

        self.history.append({"role": "user", "content": message})

        msg_buf = msg_buf + self.history
        return msg_buf


if __name__ == "__main__":
    llm = LLM()
    chat_ins = llm.get_llm()

    assistant = AssistantAgent(chat_ins)
    while true:
        msg = input("test")
        assistant.send_message(msg)
    # Assistant.

