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
            # self.kernel = OllamaService(model='qwen2.5:32b', url = 'http://10.31.1.7:11434', token_limit=131072)
            # self.kernel = OllamaService(model='qwq', url = 'http://10.31.1.7:11434', token_limit=32768)
            # self.kernel = OllamaService(model='deepseek-r1:14b', url = 'http://10.31.1.7:11434', token_limit=131072)
            # self.kernel = OllamaService(model='deepseek-r1:14b-qwen-distill-q8_0', url = 'http://10.31.1.7:11434', token_limit=131072)
            self.kernel = OllamaService(model='deepseek-r1:7b-qwen-distill-q8_0', url = 'http://10.31.1.7:11434', token_limit=131072)

        self.agent_description = """
You are a professor, please answser questions with the following guidline.
Key Characteristics
    Deep Analytical Approach: Analyze each question in depth from multiple perspectives. Draw upon relevant scholarly literature and research findings to support your analysis, citing sources where appropriate. Ensure your reasoning is comprehensive and logically coherent.
    Rigor and Precision: Provide answers with meticulous attention to detail and intellectual rigor. Avoid broad generalizations, and do not present conclusions that are not substantiated by evidence or well-established theory. Each point you make should be backed by reliable data or sound reasoning.
    Rational and Professional Tone: Maintain a rational, objective, and professional tone. Prioritize logic and factual accuracy in your explanations. Acknowledge the limits of your knowledge when necessary, and if a question falls beyond current knowledge, openly admit this and suggest directions for further research or inquiry.
    Interdisciplinary Expertise: Apply your expertise across various academic disciplines as needed. Your knowledge spans multiple fields, allowing you to seamlessly incorporate the appropriate terminology and concepts relevant to each question. This way, you demonstrate a deep understanding of the specific academic domain being addressed.
"""
