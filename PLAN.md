# AI Assistant — Implementation & Verification Plan

Based on [ARCH.md](ARCH.md). Written for Claude to implement and verify.

---

## Phase 1: Scaffolding + Message Bus

### What to create
- `requirements.txt` — update with bus (aiohttp, websockets), llm (ollama, openai), stubs
- `.gitignore` — add data/, __pycache__, *.pyc, .env, config.local.yaml
- `config.yaml` — full config from ARCH.md with stub/text defaults (chat mode)
- `bus/__init__.py` — empty
- `bus/errors.py` — `BusError`, `NoSubscriberError`, `TimeoutError`
- `bus/bus.py` — `MessageBus` class: `publish()`, `subscribe()`, `unsubscribe()`, `request()` (RPC with asyncio.wait_for), `register()`, `unregister()`, `list_modules()`, `user_input()`
- `bus/registry.py` — `ModuleRegistry`: dict of module_name → {status, remote, capabilities, subscription_ids}
- `modules/__init__.py` — empty
- `modules/base.py` — `BaseModule` abstract class (module_name, setup, start, stop, health, register)

### How Claude verifies
```bash
python -c "
import asyncio
from bus.bus import MessageBus
from bus.errors import NoSubscriberError

async def test():
    bus = MessageBus()
    results = []

    # Test subscribe + publish
    async def handler(topic, payload):
        results.append((topic, payload))

    bus.subscribe('test.hello', handler)
    bus.publish('test.hello', {'msg': 'world'})
    await asyncio.sleep(0.01)
    assert results == [('test.hello', {'msg': 'world'})], f'Expected match, got {results}'

    # Test no subscriber
    bus.publish('test.nosub', {})
    await asyncio.sleep(0.01)

    # Test register + list_modules
    class FakeMod:
        module_name = 'test_mod'
    bus.register(FakeMod())
    modules = bus.list_modules()
    assert 'test_mod' in modules, f'Expected test_mod in {modules}'

    # Test unsubscribe
    results.clear()
    sub_id = bus.subscribe('test.hello', handler)
    bus.unsubscribe(sub_id)
    bus.publish('test.hello', {'msg': 'again'})
    await asyncio.sleep(0.01)
    assert results == [], f'Expected empty after unsubscribe, got {results}'

    print('All bus tests passed')

asyncio.run(test())
"
# Expected: All bus tests passed
```

### Tests
- `tests/test_bus.py` — pub/sub delivery, multiple subscribers same topic, unsubscribe stops delivery, RPC timeout raises, register/unregister cycle, user_input publishes to correct topic

---

## Phase 2: LLM Backends

### What to create
- `llm/__init__.py` — empty
- `llm/base.py` — `LLMBackend` abstract class: `chat(messages, tools, temperature, max_tokens) -> dict`, `embed(text) -> list[float]`, `embed_batch(texts) -> list[list[float]]`
- `llm/ollama.py` — `OllamaBackend(LLMBackend)`: wraps `ollama` Python library, `/api/chat` and `/api/embeddings`
- `llm/openai.py` — `OpenAIBackend(LLMBackend)`: wraps `openai` Python library, chat.completions and embeddings

### How Claude verifies
```bash
python -c "
from llm.base import LLMBackend
from llm.ollama import OllamaBackend

# Check interface compliance
assert hasattr(LLMBackend, 'chat'), 'Missing chat method'
assert hasattr(LLMBackend, 'embed'), 'Missing embed method'
assert hasattr(LLMBackend, 'embed_batch'), 'Missing embed_batch method'

# Check concrete class
be = OllamaBackend(model='qwen3:1.7b', url='http://127.0.0.1:11434')
assert be.model == 'qwen3:1.7b'

print('LLM backend interface checks passed')
"
# Expected: LLM backend interface checks passed
```

### Tests
- `tests/test_llm.py` — `OllamaBackend` smoke test if Ollama is running (skip if not), `OpenAIBackend` smoke test if API key set (skip if not), mock-based tests for request/response format, embed() returns correct dimension list

---

## Phase 3: Brain — Core Loop + Input Processing

### What to create
- `modules/brain/__init__.py` — empty
- `modules/brain/brain.py` — `BrainModule(BaseModule)`: 7-stage thinking loop orchestration (PERCEIVE → UNDERSTAND → REASON → PLAN → ACT → REFLECT → RESPOND), subscribes to all input topics from ARCH.md, publishes response/action topics, `max_reflect_loops` guard
- `modules/brain/perceive.py` — `Perceiver`: classifies input type (text/speech/vision/tool_result/schedule), hotword check, noise filter, fast-tracks tool results to REFLECT
- `modules/brain/understand.py` — `Understander`: intent classification, disambiguation flag, urgency check

### How Claude verifies
```bash
python -c "
import asyncio
from bus.bus import MessageBus
from modules.brain.brain import BrainModule
from modules.brain.perceive import Perceiver
from modules.brain.understand import Understander

# Brain module structure
bus = MessageBus()
brain = BrainModule(bus, {
    'persona': 'You are a helpful assistant.',
    'llm': {'provider': 'ollama', 'model': 'qwen3:1.7b', 'url': 'http://127.0.0.1:11434'},
    'memory': {'conversations_path': './data/memory/conversations', 'facts_path': './data/memory/facts', 'knowledge_path': './data/memory/knowledge', 'embeddings_db': './data/embeddings.db', 'context_max_tokens': 4096, 'context_recent_messages': 20},
    'embeddings': {'provider': 'same', 'model': ''},
    'thinking': {'max_reflect_loops': 3}
})
assert brain.module_name == 'brain'
assert brain.max_reflect_loops == 3

# Perceiver
p = Perceiver()
result = p.classify({'topic': 'user.input.text', 'payload': {'text': 'hello'}})
assert result.input_type == 'text'
assert not result.is_noise

result2 = p.classify({'topic': 'status.hand.done', 'payload': {'request_id': 'r1', 'result': 'ok'}})
assert result2.is_tool_result

# Understander
u = Understander()
intent = u.classify('What is the weather tomorrow?')
assert intent.type in ('question', 'command', 'chat')

print('Brain core tests passed')
"
# Expected: Brain core tests passed
```

### Tests
- `tests/test_brain_core.py` — BrainModule subscribes to all required topics, publishes response.text on input, max_reflect_loops terminates infinite tool loops, Perceiver correctly classifies all input types, Understander handles ambiguous input

---

## Phase 4: Brain — Reasoning + Response

### What to create
- `modules/brain/reason.py` — `Reasoner`: builds LLM prompt with persona + memory context + tool schemas, calls LLM, returns chain-of-thought + decision
- `modules/brain/plan.py` — `Planner`: decides simple answer vs tool needed vs multi-step, identifies which tool(s) to call, orders execution
- `modules/brain/reflect.py` — `Reflector`: evaluates tool results — sufficient? need more? failed? retry? fallback? Returns `ReflectDecision` (proceed/loop/abort)
- `modules/brain/respond.py` — `Responder`: synthesizes final response, publishes `response.text` + `action.speak`, appends turn to conversation markdown file, generates embedding for turn

### How Claude verifies
```bash
python -c "
from modules.brain.reason import Reasoner
from modules.brain.plan import Planner
from modules.brain.reflect import Reflector, ReflectDecision
from modules.brain.respond import Responder

# Planner
planner = Planner()
decision = planner.decide(intent='question', complexity='simple', has_tools=False)
assert decision.action == 'direct_answer'

decision2 = planner.decide(intent='question', complexity='needs_data', has_tools=True)
assert decision2.action in ('call_tool', 'multi_step')

# Reflector
reflector = Reflector()
d = reflector.evaluate(tool_result='sunny, 26°C', goal='get weather')
assert d.verdict == 'proceed'

d2 = reflector.evaluate(tool_result=None, error='timeout', goal='get weather')
assert d2.verdict in ('retry', 'fallback', 'abort')

print('Brain reasoning tests passed')
"
# Expected: Brain reasoning tests passed
```

### Tests
- `tests/test_brain_reasoning.py` — Reasoner includes persona in prompt, Planner routes simple questions to direct_answer, Reflector loops on insufficient data (max 3), Responder publishes response.text with conversation_id, Responder appends to today's conversation file

---

## Phase 5: Brain — Memory + Embeddings + Persona + Tool Cache

### What to create
- `modules/brain/memory.py` — `MemoryManager`: reads/writes conversation markdown files (`data/memory/conversations/YYYY-MM-DD.md`), reads/writes fact markdown files, loads knowledge base markdown files, assembles working memory context (recency + semantic search via embeddings.db)
- `modules/brain/embeddings.py` — `EmbeddingsEngine`: calls LLM embed()/embed_batch(), SQLite cache for conversation_embeddings + fact_embeddings + knowledge_embeddings, cosine similarity search, rebuild_index() from markdown files
- `modules/brain/persona.py` — `Persona`: loads system prompt from config, injects language preference + behavior rules
- `modules/brain/tools.py` — `ToolCache`: receives tool list from `status.hands.ready`, converts to OpenAI function-calling format schemas, provides `get_schemas()` and `lookup(name)`

### How Claude verifies
```bash
python -c "
import os, tempfile, json
from modules.brain.memory import MemoryManager
from modules.brain.embeddings import EmbeddingsEngine
from modules.brain.persona import Persona
from modules.brain.tools import ToolCache

# MemoryManager
tmpdir = tempfile.mkdtemp()
mm = MemoryManager(conversations_path=os.path.join(tmpdir, 'conversations'),
                   facts_path=os.path.join(tmpdir, 'facts'),
                   knowledge_path=os.path.join(tmpdir, 'knowledge'))
# Save a conversation turn
mm.save_turn('2026-05-22', '14:30:05', 'user', 'Hello')
mm.save_turn('2026-05-22', '14:30:08', 'assistant', 'Hi there!', thinking='greeting')
# Read back
turns = mm.get_turns('2026-05-22')
assert len(turns) == 2
assert turns[0]['speaker'] == 'user'
assert turns[0]['content'] == 'Hello'

# Fact management
mm.save_fact('user_preferences', 'User prefers Celsius')
facts = mm.get_facts('user_preferences')
assert 'Celsius' in facts[0]

# Persona
p = Persona('You are a helpful assistant. Be concise.')
prompt = p.get_system_prompt()
assert 'helpful assistant' in prompt
assert 'concise' in prompt

# ToolCache
tc = ToolCache()
tc.load([{'name': 'web_search', 'description': 'Search the web', 'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}}])
schemas = tc.get_openai_schemas()
assert len(schemas) == 1
assert schemas[0]['function']['name'] == 'web_search'

print('Memory + embeddings + persona + tools tests passed')
"
# Expected: Memory + embeddings + persona + tools tests passed
```

### Tests
- `tests/test_memory.py` — conversation markdown round-trip, fact CRUD operations, knowledge base chunk loading, working memory context assembly within token budget, recency + semantic merge
- `tests/test_embeddings.py` — SQLite schema creation, embed + cache cycle, cosine similarity search returns expected ranking, rebuild_index from markdown files

---

## Phase 6: Hands — Tool Executor + Built-in Tools

### What to create
- `modules/hands/__init__.py` — empty
- `modules/hands/hands.py` — `HandsModule(BaseModule)`: subscribes to `action.execute`, looks up tool by name, calls `execute(**params)`, publishes `status.hand.done` or `status.hand.error`, scans tool_paths at startup, publishes `status.hands.ready` with tool list, handles `sandbox` flag
- `modules/hands/sandbox.py` — `Sandbox`: restricted subprocess (no network, limited paths, timeout), wraps tool execution
- `modules/hands/builtin_tools/__init__.py` — empty
- `modules/hands/builtin_tools/base.py` — `ToolBase` abstract class: `name`, `description`, `parameters` (JSON Schema dict), `execute(**kwargs) -> Any`
- `modules/hands/builtin_tools/shell.py` — `ShellTool`: execute shell command, returns stdout/stderr/returncode
- `modules/hands/builtin_tools/datetime_tool.py` — `DateTimeTool`: returns current date/time/timezone
- `modules/hands/builtin_tools/file_ops.py` — `FileReadTool` + `FileWriteTool`: read/write files within safe_paths

### How Claude verifies
```bash
python -c "
import asyncio, tempfile, os
from bus.bus import MessageBus
from modules.hands.builtin_tools.base import ToolBase
from modules.hands.builtin_tools.datetime_tool import DateTimeTool
from modules.hands.builtin_tools.file_ops import FileReadTool, FileWriteTool
from modules.hands.sandbox import Sandbox

# ToolBase interface check
dt = DateTimeTool()
assert dt.name == 'datetime'
assert 'description' in dir(dt)
assert 'parameters' in dir(dt)
result = dt.execute()
assert 'datetime' in result or 'timezone' in result or 'iso' in result

# File ops
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, 'test.txt')
fw = FileWriteTool()
fw.execute(path=path, content='hello world')
fr = FileReadTool()
content = fr.execute(path=path)
assert content == 'hello world'

# Tool schema is valid JSON Schema
schema = dt.parameters
assert schema['type'] == 'object'

# Sandbox
sb = Sandbox(safe_paths=[tmp], timeout=5)
result = sb.run('echo hello')
assert result['returncode'] == 0
assert 'hello' in result['stdout']

print('Hands + tools tests passed')
"
# Expected: Hands + tools tests passed
```

### Tests
- `tests/test_hands.py` — HandsModule loads tools from directory, publishes status.hands.ready with correct schemas, executes tool and returns result with request_id, sandbox blocks unsafe paths, sandbox enforces timeout

---

## Phase 7: Hands — Web Tools + Remaining Built-ins

### What to create
- `modules/hands/builtin_tools/websearch.py` — `WebSearchTool`: uses ddgs (duckduckgo-search) to search web, returns list of {title, url, snippet}
- `modules/hands/builtin_tools/webfetch.py` — `WebFetchTool`: fetches URL, extracts text content (html2text or bs4)
- `modules/hands/builtin_tools/weather.py` — `WeatherTool`: gets weather for location via free API (wttr.in)
- `modules/hands/builtin_tools/browser.py` — `BrowserTool`: stub only in this phase (requires playwright, defer full impl)

### How Claude verifies
```bash
python -c "
from modules.hands.builtin_tools.websearch import WebSearchTool
from modules.hands.builtin_tools.webfetch import WebFetchTool
from modules.hands.builtin_tools.weather import WeatherTool

# WebSearch
ws = WebSearchTool()
results = ws.execute(query='Python programming', max_results=3)
assert isinstance(results, list)
if len(results) > 0:
    assert 'title' in results[0]
    assert 'url' in results[0]

# WebFetch
wf = WebFetchTool()
content = wf.execute(url='https://httpbin.org/get')
assert content is not None

# Weather
wt = WeatherTool()
result = wt.execute(location='London')
assert result is not None

print('Web tools tests passed')
"
# Expected: Web tools tests passed (may skip if offline — mark as SKIP)
```

### Tests
- `tests/test_web_tools.py` — search returns list with expected keys, fetch returns text content, weather returns string with location, mock-based tests for offline reliability

---

## Phase 8: Scheduler

### What to create
- `modules/scheduler/__init__.py` — empty
- `modules/scheduler/scheduler.py` — `SchedulerModule(BaseModule)`: clock watcher loop (1s tick), subscribes to `action.schedule.add/list/delete`, publishes `schedule.triggered` when time arrives, handles recurring tasks (daily/weekly/hourly), enforces max_pending limit
- `modules/scheduler/storage.py` — `ScheduleStorage`: load/save `data/schedules.json`, atomic writes (write to temp + rename)

### How Claude verifies
```bash
python -c "
import asyncio, tempfile, os, json
from modules.scheduler.storage import ScheduleStorage
from datetime import datetime, timezone, timedelta

tmpdir = tempfile.mkdtemp()
path = os.path.join(tmpdir, 'schedules.json')
st = ScheduleStorage(path)

# Add a task
task = {
    'id': 'sched_1',
    'task': 'Test reminder',
    'time': (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
    'repeat': None,
    'description': 'Test'
}
st.add(task)
tasks = st.list_all()
assert len(tasks) == 1
assert tasks[0]['id'] == 'sched_1'

# Delete
st.delete('sched_1')
assert len(st.list_all()) == 0

# Persistence
st.add(task)
st2 = ScheduleStorage(path)
assert len(st2.list_all()) == 1

print('Scheduler tests passed')
"
# Expected: Scheduler tests passed
```

### Tests
- `tests/test_scheduler.py` — storage CRUD, recurring tasks re-schedule correctly, max_pending enforcement, atomic writes don't corrupt on crash, scheduler triggers on time (fast-forward mock clock)

---

## Phase 9: CLI Module + End-to-End Chat Mode

### What to create
- `modules/cli/__init__.py` — empty
- `modules/cli/cli.py` — `CLIModule(BaseModule)`: reads stdin line by line, publishes `user.input.text`, subscribes to `response.text` and prints to stdout, special commands `/exit`, `/verbose`, `/clear`, `/agent <name>`, multi-line input (line ending with `\`)
- `main.py` — entry point: loads config.yaml, creates MessageBus, instantiates all modules (brain, hands, scheduler, cli), calls setup() → start() for each, handles graceful shutdown on SIGINT/SIGTERM, fatal exit on brain/bus crash, disable non-core modules on crash

### How Claude verifies
```bash
# Start the assistant in background
python main.py &
PID=$!
sleep 3

# Send a test message via a quick script
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from bus.bus import MessageBus
async def test():
    bus = MessageBus()
    result = None
    async def on_response(topic, payload):
        nonlocal result
        result = payload
    bus.subscribe('response.text', on_response)
    bus.user_input('Hello, what is your name?')
    await asyncio.sleep(5)
    if result:
        print(f'GOT RESPONSE: {result[\"text\"][:80]}')
    else:
        print('NO RESPONSE (timeout or LLM not available)')
asyncio.run(test())
"

# Cleanup
kill $PID 2>/dev/null

# Expected: either GOT RESPONSE with text, or NO RESPONSE if no LLM available
echo "CLI module integration check complete"
```

### Tests
- `tests/test_cli.py` — CLI module publishes user.input.text on stdin input, CLI prints response.text to stdout, `/exit` command triggers shutdown, multi-line input aggregation

---

## Phase 10: Ears Module (Stub)

### What to create
- `modules/ears/__init__.py` — empty
- `modules/ears/ears.py` — `EarsModule(BaseModule)`: subscribes to `command.ears.start/stop/pause/resume`, publishes `sensory.speech.heard` and `sensory.speech.hotword`, manages listening state machine (idle → listening → paused)
- `modules/ears/asr_backends/__init__.py` — empty
- `modules/ears/asr_backends/base.py` — `ASRBackend` abstract class: `transcribe(audio_bytes) -> {text, confidence, language}`
- `modules/ears/asr_backends/stub.py` — `StubASR`: returns "no microphone available"

### How Claude verifies
```bash
python -c "
import asyncio
from bus.bus import MessageBus
from modules.ears.ears import EarsModule
from modules.ears.asr_backends.stub import StubASR

bus = MessageBus()
ears = EarsModule(bus, {'backend': 'stub', 'device_index': 0, 'sample_rate': 48000, 'hotwords': ['hey'], 'silence_timeout': 20})
assert ears.module_name == 'ears'

# Stub backend returns expected message
stub = StubASR()
result = stub.transcribe(b'fake_audio')
assert 'no microphone' in result['text'].lower() or 'not available' in result['text'].lower()

print('Ears stub tests passed')
"
# Expected: Ears stub tests passed
```

### Tests
- `tests/test_ears.py` — EarsModule state machine transitions, start/stop/pause/resume commands, stub backend contract, hotword detection publishes sensory.speech.hotword

---

## Phase 11: Mouth Module (Text Backend)

### What to create
- `modules/mouth/__init__.py` — empty
- `modules/mouth/mouth.py` — `MouthModule(BaseModule)`: subscribes to `action.speak`, manages speech queue, handles `interrupt` flag (flush queue + stop current), publishes `status.mouth.started/done/ready/error`
- `modules/mouth/tts_backends/__init__.py` — empty
- `modules/mouth/tts_backends/base.py` — `TTSBackend` abstract class: `speak(text, voice, speed) -> None`, `stop() -> None`
- `modules/mouth/tts_backends/text.py` — `TextTTS`: prints text to stdout with prefix (no audio)

### How Claude verifies
```bash
python -c "
import asyncio
from bus.bus import MessageBus
from modules.mouth.mouth import MouthModule
from modules.mouth.tts_backends.text import TextTTS

bus = MessageBus()
mouth = MouthModule(bus, {'backend': 'text', 'voice': 'default', 'speed': 1.0})
assert mouth.module_name == 'mouth'

# Text backend
tts = TextTTS()
tts.speak('Hello world', voice=None, speed=1.0)
# Expected: prints [Assistant] Hello world

# Queue behavior
events = []
async def on_started(topic, payload):
    events.append(('started', payload))

bus.subscribe('status.mouth.started', on_started)
bus.publish('action.speak', {'text': 'Test', 'voice': None, 'speed': 1.0, 'interrupt': False})
# async processing...

print('Mouth text backend tests passed')
"
# Expected: Mouth text backend tests passed
# Expected stdout: [Assistant] Hello world (from tts.speak)
```

### Tests
- `tests/test_mouth.py` — MouthModule queues multiple speak requests, interrupt flag flushes queue, publishes started/done events, text backend outputs expected format

---

## Phase 12: Eyes Module (Stub) + Canvas Module (File Backend)

### What to create
- `modules/eyes/__init__.py` — empty
- `modules/eyes/eyes.py` — `EyesModule(BaseModule)`: subscribes to `command.eyes.capture/stream.start/stream.stop`, publishes `sensory.vision.frame`, RPC endpoint `eyes.analyze`
- `modules/eyes/vision_backends/__init__.py` — empty
- `modules/eyes/vision_backends/base.py` — `VisionBackend` abstract class
- `modules/eyes/vision_backends/stub.py` — `StubVision`: returns "no camera available"
- `modules/canvas/__init__.py` — empty
- `modules/canvas/canvas.py` — `CanvasModule(BaseModule)`: subscribes to `action.canvas.show/generate/clear/draw/update`, publishes `sensory.canvas.click/input/draw` and `status.canvas.*`, RPC `canvas.screenshot`
- `modules/canvas/renderer.py` — `ImageRenderer`: stub image generation (returns placeholder/error until a real model is configured)
- `modules/canvas/backends/__init__.py` — empty
- `modules/canvas/backends/base.py` — `CanvasBackend` abstract class
- `modules/canvas/backends/file.py` — `FileCanvas`: writes output to files in `data/canvas_output/`

### How Claude verifies
```bash
python -c "
from bus.bus import MessageBus
from modules.eyes.eyes import EyesModule
from modules.eyes.vision_backends.stub import StubVision
from modules.canvas.canvas import CanvasModule
from modules.canvas.backends.file import FileCanvas
import tempfile, os

bus = MessageBus()

# Eyes stub
eyes = EyesModule(bus, {'backend': 'stub', 'camera_index': 0, 'vision_model': None})
assert eyes.module_name == 'eyes'

stub = StubVision()
result = stub.capture()
assert 'not available' in result.get('description', '').lower() or 'no camera' in result.get('description', '').lower()

# Canvas file backend
tmpdir = tempfile.mkdtemp()
fc = FileCanvas(output_dir=tmpdir)
fc.show(content_type='text', data='Hello canvas', title='Test')
files = os.listdir(tmpdir)
assert len(files) > 0, f'Expected output file in {tmpdir}'

print('Eyes stub + Canvas file backend tests passed')
"
# Expected: Eyes stub + Canvas file backend tests passed
```

### Tests
- `tests/test_eyes.py` — stub backend contract, capture command publishes frame, stream start/stop lifecycle
- `tests/test_canvas.py` — file backend writes content to disk, generate stub returns placeholder, clear removes content, draw creates expected output

---

## Phase 13: Chat Module + Remote WebSocket

### What to create
- `modules/chat/__init__.py` — empty
- `modules/chat/chat.py` — `ChatModule(BaseModule)`: manages multiple chat backends, each backend publishes `user.input.text`, subscribes to `response.text` and sends back
- `modules/chat/backends/__init__.py` — empty
- `modules/chat/backends/base.py` — `ChatBackend` abstract class: `start()`, `stop()`, `send_message(text)`, callback `on_message(handler)`
- `modules/chat/backends/telegram.py` — `TelegramBackend`: stub in this phase (requires telegram bot token), structure for future
- `bus/remote.py` — `RemoteBus`: WebSocket server (aiohttp or websockets), accepts remote module connections, authenticates via token, relays pub/sub messages bidirectionally, tracks remote modules in registry
- `main_remote.py` — Entry point for remote modules: connects to remote bus WebSocket, creates module instance, bridges local bus calls to remote

### How Claude verifies
```bash
python -c "
from bus.remote import RemoteBus
from modules.chat.backends.base import ChatBackend

# Chat backend interface
assert hasattr(ChatBackend, 'start')
assert hasattr(ChatBackend, 'stop')
assert hasattr(ChatBackend, 'send_message')

# RemoteBus has expected structure
import inspect
from bus.remote import RemoteBus
assert hasattr(RemoteBus, 'start')
assert hasattr(RemoteBus, 'stop')

print('Chat + remote interface tests passed')
"
# Expected: Chat + remote interface tests passed
```

### Tests
- `tests/test_chat.py` — ChatBackend abstract interface, multiple backends don't interfere, ChatModule routes response.text to all active backends
- `tests/test_remote.py` — WebSocket server starts/stops cleanly, module connect/disconnect updates registry, message relay works bidirectionally

---

## Phase 14: Skills System

### What to create
- `modules/hands/skills/__init__.py` — empty
- `modules/hands/skills/base.py` — `SkillBase(ToolBase)`: adds `call_tool(name, **params)` (publishes action.execute, waits for status.hand.done, returns result) and `call_llm(prompt, context)` (calls brain.ask RPC)
- `modules/hands/skills/research.py` — `ResearchSkill`: chains web_search → web_fetch → summarize → file.write, demonstrates the pattern
- `modules/hands/skills/daily_briefing.py` — `DailyBriefingSkill`: chains datetime + weather + calendar.list → formatted summary

### How Claude verifies
```bash
python -c "
from modules.hands.builtin_tools.base import ToolBase
from modules.hands.skills.base import SkillBase

# SkillBase extends ToolBase
assert issubclass(SkillBase, ToolBase)

# Check SkillBase adds call_tool and call_llm
assert hasattr(SkillBase, 'call_tool')
assert hasattr(SkillBase, 'call_llm')

# Skill has same interface as tool
skill = SkillBase()
skill.name = 'test_skill'
skill.description = 'A test skill'
skill.parameters = {'type': 'object', 'properties': {}}
assert hasattr(skill, 'execute')

print('Skills interface tests passed')
"
# Expected: Skills interface tests passed
```

### Tests
- `tests/test_skills.py` — SkillBase has same interface as ToolBase (LLM sees them identically), ResearchSkill execute() calls dependencies in order, call_tool timeout handling, call_llm fallback on brain unavailable

---

## Phase 15: Integration — Full System

### What to create
- `main.py` — update with proper startup ordering (bus → brain → hands → scheduler → cli → ears → mouth → eyes → canvas → chat), crash isolation (non-core module crash → disable + log, brain/bus crash → exit), signal handling
- `config.yaml` — finalize with all defaults
- `tests/fixtures/` — test config, test memory files, mock LLM responses
- `tests/test_integration.py` — end-to-end: user_input → brain → response.text flow, tool call lifecycle (action.execute → status.hand.done → reflect → respond), scheduled task fires and brain responds, module crash doesn't kill system

### How Claude verifies
```bash
# Full integration test
python -c "
import asyncio, sys, json
sys.path.insert(0, '.')
from bus.bus import MessageBus
from bus.registry import ModuleRegistry

# Verify all modules can be instantiated
from modules.brain.brain import BrainModule
from modules.hands.hands import HandsModule
from modules.scheduler.scheduler import SchedulerModule
from modules.cli.cli import CLIModule
from modules.ears.ears import EarsModule
from modules.mouth.mouth import MouthModule
from modules.eyes.eyes import EyesModule
from modules.canvas.canvas import CanvasModule
from modules.chat.chat import ChatModule

modules = {
    'brain': BrainModule,
    'hands': HandsModule,
    'scheduler': SchedulerModule,
    'cli': CLIModule,
    'ears': EarsModule,
    'mouth': MouthModule,
    'eyes': EyesModule,
    'canvas': CanvasModule,
    'chat': ChatModule,
}
print(f'All {len(modules)} modules importable')
print('Integration check passed')
"
# Expected: All 9 modules importable, Integration check passed
```

### Tests
- `tests/test_integration.py` — full message flow from user input to response, tool call + result cycle, scheduler triggers brain response, module crash isolation, config-driven backend selection

---

## Phase 16: Ear + Mouth Real Backends (FunASR + Edge TTS)

### What to create
- `modules/ears/asr_backends/funasr.py` — `FunASRBackend`: wraps existing funasr code, real microphone + ASR
- `modules/ears/asr_backends/whisper.py` — `WhisperBackend`: wraps OpenAI Whisper (optional, depends on whisper package)
- `modules/mouth/tts_backends/edge_tts.py` — `EdgeTTSBackend`: Microsoft Edge TTS, generates audio, plays via pyaudio or pygame
- `modules/mouth/tts_backends/piper.py` — `PiperBackend`: local Piper TTS (optional, depends on piper-tts)

### How Claude verifies
```bash
python -c "
from modules.ears.asr_backends.funasr import FunASRBackend
from modules.mouth.tts_backends.edge_tts import EdgeTTSBackend

# Check interface compliance
from modules.ears.asr_backends.base import ASRBackend
from modules.mouth.tts_backends.base import TTSBackend

assert issubclass(FunASRBackend, ASRBackend)
assert issubclass(EdgeTTSBackend, TTSBackend)

print('Real backend interface checks passed')
"
# Expected: Real backend interface checks passed
```

### Tests
- Manual: switch config to `ears: {backend: funasr}` + `mouth: {backend: edge_tts}`, speak to assistant, verify voice response

---

## Phase Summary

| Phase | Files | Cumulative capability |
|--------|-------|----------------------|
| 1 | 8 | Bus + scaffolding |
| 2 | 3 | LLM backends |
| 3 | 3 | Brain loop skeleton |
| 4 | 4 | Brain reasoning complete |
| 5 | 4 | Memory + embeddings + persona |
| 6 | 8 | Hands + sandbox + core builtins |
| 7 | 4 | Web tools (search, fetch, weather) |
| 8 | 2 | Scheduler |
| 9 | 2 | **MVP: CLI chat mode works** |
| 10 | 4 | Ears stub |
| 11 | 4 | Mouth text backend |
| 12 | 10 | Eyes stub + Canvas file backend |
| 13 | 6 | Chat module + remote WebSocket |
| 14 | 4 | Skills system |
| 15 | 3 | Full integration tests |
| 16 | 4 | Real ASR + TTS backends |

**MVP at Phase 9**: CLI text chat with brain reasoning loop, tools (shell, datetime, file, web), scheduler, and full memory system. You can type to the assistant and it thinks, uses tools, remembers, and responds.

**Full system at Phase 15**: All modules integrated with crash isolation, remote module support, and skills.

---

## Dependency Graph

```
Phase 1 (Bus)
    │
    ▼
Phase 2 (LLM)
    │
    ▼
Phase 3 (Brain core)
    │
    ├──► Phase 4 (Brain reasoning)
    │        │
    │        ▼
    │    Phase 5 (Memory)
    │        │
    │        ▼
    │    Phase 6 (Hands + core tools)
    │        │
    │        ├──► Phase 7 (Web tools)
    │        │
    │        ▼
    │    Phase 8 (Scheduler)
    │        │
    │        ▼
    │    Phase 9 (CLI) ◄── MVP
    │        │
    │        ├──► Phase 10 (Ears stub)
    │        ├──► Phase 11 (Mouth text)
    │        ├──► Phase 12 (Eyes + Canvas)
    │        ├──► Phase 13 (Chat + Remote)
    │        ├──► Phase 14 (Skills)
    │        │
    │        ▼
    │    Phase 15 (Integration)
    │        │
    │        ▼
    │    Phase 16 (Real backends)
```
