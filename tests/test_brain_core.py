import tempfile
import os

from brain.perceive import Perceiver
from brain.understand import Understander
from brain.plan import Planner
from brain.reflect import Reflector, ReflectVerdict


class TestPerceiver:
    def test_classify_text(self):
        p = Perceiver()
        result = p.classify('user.input.text', {'text': 'hello'})
        assert result.input_type == 'text'
        assert not result.is_noise
        assert not result.is_tool_result

    def test_classify_speech(self):
        p = Perceiver()
        result = p.classify('sensory.speech.heard', {'text': 'hello', 'confidence': 0.95})
        assert result.input_type == 'speech'

    def test_classify_tool_result(self):
        p = Perceiver()
        result = p.classify('status.hand.done', {'request_id': 'r1', 'result': 'ok'})
        assert result.is_tool_result
        assert result.tool_request_id == 'r1'

    def test_classify_vision(self):
        p = Perceiver()
        result = p.classify('sensory.vision.frame', {'description': 'a desk'})
        assert result.input_type == 'vision'

    def test_noise_empty_text(self):
        p = Perceiver()
        result = p.classify('user.input.text', {'text': ''})
        assert result.is_noise

    def test_noise_low_confidence_speech(self):
        p = Perceiver()
        result = p.classify('sensory.speech.heard', {'text': 'mm', 'confidence': 0.1})
        assert result.is_noise

    def test_hotword_detection(self):
        p = Perceiver(hotwords=['hey assistant'])
        result = p.classify('sensory.speech.heard', {'text': 'hey assistant what time is it', 'confidence': 0.9})
        assert result.is_addressed_to_assistant

    def test_unknown_topic(self):
        p = Perceiver()
        result = p.classify('some.random.topic', {})
        assert result.input_type == 'unknown'


class TestUnderstander:
    def test_question_intent(self):
        u = Understander()
        assert u.classify('What is the weather?').type == 'question'
        assert u.classify('how do I code?').type == 'question'
        assert u.classify('why is the sky blue').type == 'question'

    def test_command_intent(self):
        u = Understander()
        assert u.classify('search for cats').type == 'command'
        assert u.classify('create a file').type == 'command'
        assert u.classify('remind me at 3pm').type == 'command'

    def test_chat_intent(self):
        u = Understander()
        assert u.classify('hello there').type == 'chat'
        assert u.classify('thanks').type == 'chat'

    def test_urgency(self):
        u = Understander()
        assert u.classify('urgent: what is the server status').urgency == 'high'
        assert u.classify('hello').urgency == 'normal'

    def test_empty_input(self):
        u = Understander()
        intent = u.classify('')
        assert intent.type == 'unknown'
        assert intent.needs_clarification


class TestPlanner:
    def test_direct_answer(self):
        p = Planner()
        result = p.decide('question', {'content': 'The answer is 42', 'tool_calls': None}, has_tools=True)
        assert result.action == 'direct_answer'

    def test_call_tool(self):
        p = Planner()
        result = p.decide('command', {
            'content': '',
            'tool_calls': [{'name': 'weather', 'arguments': {'location': 'Taipei'}}]
        }, has_tools=True)
        assert result.action == 'call_tool'
        assert result.tool_name == 'weather'

    def test_call_tool_no_tools_available(self):
        p = Planner()
        result = p.decide('command', {
            'content': '',
            'tool_calls': [{'name': 'weather', 'arguments': {}}]
        }, has_tools=False)
        assert result.action == 'direct_answer'

    def test_ask_clarification_unknown(self):
        p = Planner()
        result = p.decide('unknown', {'content': '...'}, has_tools=False)
        assert result.action == 'ask_clarification'


class TestReflector:
    def test_proceed_on_success(self):
        r = Reflector(max_loops=3)
        d = r.evaluate(tool_result='sunny, 26C', goal='get weather')
        assert d.verdict == ReflectVerdict.PROCEED

    def test_retry_on_error(self):
        r = Reflector(max_loops=3)
        d = r.evaluate(tool_result=None, error='timeout', goal='get weather')
        assert d.verdict == ReflectVerdict.RETRY

    def test_abort_after_max_retries(self):
        r = Reflector(max_loops=2)
        r.evaluate(tool_result=None, error='fail1', goal='x')
        r.evaluate(tool_result=None, error='fail2', goal='x')
        d = r.evaluate(tool_result=None, error='fail3', goal='x')
        assert d.verdict == ReflectVerdict.ABORT

    def test_fallback_on_none_result(self):
        r = Reflector(max_loops=3)
        d = r.evaluate(tool_result=None, goal='x')
        assert d.verdict == ReflectVerdict.FALLBACK

    def test_reset(self):
        r = Reflector(max_loops=3)
        r.evaluate(tool_result=None, error='fail', goal='x')
        r.reset()
        d = r.evaluate(tool_result='ok', goal='x')
        assert d.verdict == ReflectVerdict.PROCEED
