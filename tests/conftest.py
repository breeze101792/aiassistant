"""Shared pytest fixtures for all tests."""
import pytest


@pytest.fixture
def message_bus():
    """Fresh MessageBus for each test."""
    from bus.bus import MessageBus
    return MessageBus()


@pytest.fixture
def temp_dir():
    """Temporary directory, auto-cleaned after test."""
    import tempfile
    import shutil
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


class _MockLLMBackend:
    """Configurable mock LLM for testing brain pipeline without real API calls.

    Set .chat_response and .embed_response before use.
    """

    def __init__(self, model="mock", url=""):
        self.model = model
        self.url = url
        self.api_key = ""
        self.chat_response = {"content": "mock assistant response", "tool_calls": None, "usage": {"total_tokens": 10}}
        self.embed_response = [0.1, 0.2, 0.3]
        self.chat_calls: list[dict] = []
        self.embed_calls: list[list[str]] = []

    def chat(self, messages, tools=None, max_tokens=4096, temperature=0.7):
        self.chat_calls.append({"messages": list(messages), "tools": tools})
        return dict(self.chat_response)

    def embed(self, text):
        self.embed_calls.append(text)
        return list(self.embed_response)

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

    def token_count(self, messages):
        return 100  # small enough not to trigger compression by default


@pytest.fixture
def mock_llm():
    """A mock LLM backend returning canned responses. Tweak .chat_response for specific tests."""
    return _MockLLMBackend()
