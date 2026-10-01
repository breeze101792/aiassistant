import tempfile
import os

import pytest

from aiassistant.agent.memory import MemoryManager
from aiassistant.agent.embeddings import EmbeddingsEngine
from aiassistant.agent.persona import Persona
from aiassistant.agent.toolcache import ToolCache


class TestMemoryManager:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(
            conversations_path=os.path.join(self.tmp, 'conversations'),
            facts_path=os.path.join(self.tmp, 'facts'),
            knowledge_path=os.path.join(self.tmp, 'knowledge'),
            embeddings_db_path=os.path.join(self.tmp, 'embeddings.db'),
        )

    def test_save_and_get_turns(self):
        self.mm.save_turn('2026-05-23', '14:30:05', 'user', 'Hello')
        self.mm.save_turn('2026-05-23', '14:30:08', 'assistant', 'Hi!')
        turns = self.mm.get_turns('2026-05-23')
        assert len(turns) == 2
        assert turns[0]['speaker'] == 'user'
        assert turns[0]['content'] == 'Hello'
        assert turns[1]['speaker'] == 'assistant'
        assert turns[1]['content'] == 'Hi!'

    def test_get_turns_nonexistent_date(self):
        turns = self.mm.get_turns('2099-01-01')
        assert turns == []

    def test_get_recent_turns(self):
        self.mm.save_turn('2026-05-20', '10:00:00', 'user', 'Old')
        self.mm.save_turn('2026-05-23', '14:00:00', 'user', 'New')
        recent = self.mm.get_recent_turns(count=1)
        assert len(recent) == 1
        assert recent[0]['content'] == 'New'

    def test_save_and_get_facts(self):
        self.mm.save_fact('user_preferences', 'Prefers dark mode')
        self.mm.save_fact('user_preferences', 'Uses vim')
        facts = self.mm.get_facts('user_preferences')
        assert len(facts) == 2
        assert 'dark mode' in facts[0]
        assert 'vim' in facts[1]

    def test_fact_categories(self):
        self.mm.save_fact('people', 'John is manager')
        self.mm.save_fact('projects', 'Working on aiassistant')
        cats = self.mm.all_fact_categories()
        assert 'people' in cats
        assert 'projects' in cats

    def test_turns_with_tools_and_thinking(self):
        self.mm.save_turn('2026-05-23', '14:30:08', 'assistant', 'Sunny!',
                          thinking='got weather data',
                          tools_used=[{'name': 'weather', 'request_id': 'r1', 'duration_ms': 350}])
        turns = self.mm.get_turns('2026-05-23')
        assert len(turns) == 1


class _FakeEmbedLLM:
    """Deterministic vectors, so ranking is predictable."""

    def embed(self, text):
        return [float(len(text)), 1.0]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


class TestEmbeddingsEngine:
    def test_db_creation(self):
        import os
        tmp = os.path.join(tempfile.mkdtemp(), 'test.db')
        engine = EmbeddingsEngine(db_path=tmp)
        assert os.path.exists(tmp)

    def test_search_empty_db(self):
        import os
        tmp = os.path.join(tempfile.mkdtemp(), 'test.db')
        engine = EmbeddingsEngine(db_path=tmp)
        results = engine.search_conversations('test')
        assert results == []
        results = engine.search_facts('test')
        assert results == []

    def test_no_backend_returns_empty_not_raises(self):
        """With no LLM wired, search is a no-op, not an exception."""
        import os
        engine = EmbeddingsEngine(db_path=os.path.join(tempfile.mkdtemp(), 'test.db'))
        assert engine.search_conversations('x') == []
        assert engine.search_facts('x') == []

    def test_indexed_turns_are_searchable(self):
        import os
        engine = EmbeddingsEngine(
            db_path=os.path.join(tempfile.mkdtemp(), 'test.db'),
            llm_backend=_FakeEmbedLLM(),
        )
        engine.index_conversation_turn('2026-05-23', '10:00:00', 'user', 'hello')
        engine.index_conversation_turn('2026-05-23', '10:00:05', 'assistant', 'hi there')
        results = engine.search_conversations('hello')
        assert results, "an indexed turn must be retrievable"
        assert {'date', 'timestamp', 'speaker', 'chunk'} == set(results[0])

    def test_indexed_facts_are_searchable_and_deduplicated(self):
        import os
        engine = EmbeddingsEngine(
            db_path=os.path.join(tempfile.mkdtemp(), 'test.db'),
            llm_backend=_FakeEmbedLLM(),
        )
        engine.index_fact('user_preferences', 'Prefers dark mode')
        engine.index_fact('user_preferences', 'Prefers dark mode')  # same fact again
        rows = engine.search_facts('Prefers dark mode')
        assert len(rows) == 1, "re-indexing the same fact updates, it does not duplicate"

    def test_transient_failure_latches_unavailable(self):
        """A failed provider is remembered, to avoid hammering the endpoint.

        reasoning.md:50-51 owns this "provider unavailable" state, so one
        failure disables further embedding attempts for the process.
        """
        import os

        class Boom:
            def embed(self, text):
                raise RuntimeError("transient")

        engine = EmbeddingsEngine(
            db_path=os.path.join(tempfile.mkdtemp(), 'test.db'),
            llm_backend=Boom(),
        )
        with pytest.raises(RuntimeError):
            engine.embed('x')
        assert engine._embeddings_available() is False

    @pytest.mark.xfail(strict=True,
                       reason="BUG-6: the unavailable latch is never cleared, "
                              "so set_llm() after a transient provider failure "
                              "cannot re-enable embeddings for the process")
    def test_setting_a_new_backend_clears_the_unavailable_latch(self):
        import os

        class Boom:
            def embed(self, text):
                raise RuntimeError("transient")

        engine = EmbeddingsEngine(
            db_path=os.path.join(tempfile.mkdtemp(), 'test.db'),
            llm_backend=Boom(),
        )
        with pytest.raises(RuntimeError):
            engine.embed('x')

        engine.set_llm(_FakeEmbedLLM())
        assert engine.embed('x') == [1.0, 1.0]


class TestPersona:
    def test_custom_prompt(self):
        p = Persona('You are a helpful coding assistant. Be concise.')
        assert 'coding assistant' in p.get_system_prompt()
        assert 'concise' in p.get_system_prompt()

    def test_default_prompt(self):
        p = Persona('')
        prompt = p.get_system_prompt()
        # The default is a conversational voice assistant.
        assert 'conversational' in prompt
        assert 'emoji' in prompt
        assert 'voice' in prompt

    def test_name_extraction(self):
        p = Persona('You are Jarvis. Be helpful.')
        assert p.name == 'Jarvis'


class TestToolCache:
    def test_load_and_retrieve(self):
        tc = ToolCache()
        tc.load([
            {
                'name': 'web_search',
                'description': 'Search the web',
                'parameters': {
                    'type': 'object',
                    'properties': {'query': {'type': 'string'}},
                    'required': ['query']
                }
            },
            {
                'name': 'datetime',
                'description': 'Get time',
                'parameters': {'type': 'object', 'properties': {}}
            },
        ])
        assert tc.lookup('web_search') is not None
        assert tc.lookup('datetime') is not None
        assert tc.lookup('nope') is None
        assert 'web_search' in tc.tool_names
        assert 'datetime' in tc.tool_names

    def test_schema_conversion(self):
        tc = ToolCache()
        tc.load([
            {'name': 'test', 'description': 'Test tool', 'parameters': {'type': 'object', 'properties': {'x': {'type': 'int'}}}}
        ])
        schemas = tc.get_schemas()
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema['name'] == 'test'
        assert schema['description'] == 'Test tool'
        assert 'properties' in schema['parameters']

    def test_empty_cache(self):
        tc = ToolCache()
        assert tc.get_schemas() == []
        assert tc.tool_names == []

    def test_get_formatted_schemas(self):
        tc = ToolCache()
        tc.load([
            {'name': 'test', 'description': 'Test tool', 'parameters': {'type': 'object', 'properties': {'x': {'type': 'int'}}}}
        ])
        formatted = tc.get_formatted_schemas()
        assert len(formatted) == 1
        assert formatted[0]['type'] == 'function'
        assert formatted[0]['function']['name'] == 'test'
        assert formatted[0]['function']['description'] == 'Test tool'
        assert 'parameters' in formatted[0]['function']

    def test_get_tool_list(self):
        tc = ToolCache()
        tc.load([
            {'name': 'test', 'description': 'T', 'parameters': {}},
            {'name': 'other', 'description': 'O', 'parameters': {}},
        ])
        tool_list = tc.get_tool_list()
        assert len(tool_list) == 2
        assert {t['name'] for t in tool_list} == {'test', 'other'}
