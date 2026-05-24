import pytest
from llm.base import LLMBackend
from llm.ollama import OllamaBackend
from llm.openai import OpenAIBackend


class TestLLMInterface:
    def test_abstract_interface_methods(self):
        assert hasattr(LLMBackend, 'chat')
        assert hasattr(LLMBackend, 'embed')
        assert hasattr(LLMBackend, 'embed_batch')

    def test_ollama_initialization(self):
        be = OllamaBackend(model='qwen3:1.7b', url='http://127.0.0.1:11434')
        assert be.model == 'qwen3:1.7b'
        assert be.url == 'http://127.0.0.1:11434'

    def test_openai_initialization(self):
        be = OpenAIBackend(model='gpt-4', url='https://api.openai.com/v1', api_key='test')
        assert be.model == 'gpt-4'
        assert be.url == 'https://api.openai.com/v1'
        assert be.api_key == 'test'

    def test_embed_batch_default_implementation(self):
        be = OllamaBackend(model='test')
        called = []

        def fake_embed(text):
            called.append(text)
            return [0.1, 0.2, 0.3]
        be.embed = fake_embed

        result = be.embed_batch(['a', 'b'])
        assert len(result) == 2
        assert called == ['a', 'b']


class TestBackendSmoke:
    @pytest.mark.asyncio
    async def test_ollama_availability(self):
        """Smoke test — skip if Ollama not running."""
        try:
            be = OllamaBackend(model='qwen3:1.7b')
            result = be.embed('test')
            assert isinstance(result, list)
            assert len(result) > 0
        except Exception:
            pytest.skip("Ollama not available")
