# AI Assistant

Modular AI assistant with message bus architecture. All modules communicate through a central pub/sub bus. Backends control behavior — set to `stub` to disable hardware-dependent modules.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Make sure Ollama is running and has the model
ollama pull qwen3:latest
ollama pull qwen3-embedding:0.6b

# Start the assistant
./run.sh                              # text chat mode
./run.sh python main.py --audio       # audio chat mode (mic + TTS)
./run.sh python main.py -v            # debug logging
./run.sh python main.py --help        # full options

# Run tests
./run.sh python -m pytest tests/ -v
```

## CLI Commands

When the assistant is running:

| Command | Action |
|---------|--------|
| `/exit` | Quit the assistant |
| `/help` | Show available commands |
| `/status` | Show module status and health |
| `/log [level]` | Show or set log level (debug/info/warning/error/off) |
| `/clear` | Clear the terminal |

## Architecture

```
main.py ── starts all modules
    │
    ├── brain/     Central intelligence, 7-stage thinking loop
    ├── hands/     Tool execution (shell, web search, file ops, etc.)
    ├── ears/      Speech recognition (stub/funasr/whisper)
    ├── mouth/     Text-to-speech (text/edge_tts)
    ├── eyes/      Computer vision (stub/opencv)
    ├── canvas/    Image/file output (file/web)
    ├── scheduler/ Recurring task scheduling
    ├── cli/       Terminal REPL
    └── chat/      Messaging backends (Telegram, etc.)
```

All modules communicate through `bus/` — a pub/sub + RPC message bus.

## Config

See `config.yaml` for all options. Key sections:

| Section | Controls |
|---------|----------|
| `brain.llm` | LLM provider (ollama/openai), model, temperature |
| `brain.embeddings` | Embedding model for memory search |
| `brain.memory` | Conversation/fact/knowledge storage paths |
| `ears` | Speech backend, hotwords, silence timeout |
| `mouth` | TTS backend, voice, speed |
| `hands` | Tool directories, sandbox, command timeout |
| `scheduler` | Task storage, max pending |

Set hardware backends to `stub` if you don't have the hardware:

```yaml
ears:  {backend: stub}    # no microphone
mouth: {backend: text}    # TTS prints to stdout
eyes:  {backend: stub}    # no camera
```

## Tools

Built-in tools in `modules/hands/builtin_tools/`:

| Tool | Description |
|------|-------------|
| `datetime` | Current date/time/timezone |
| `shell` | Execute shell commands |
| `file.read` | Read file contents |
| `file.write` | Write to a file |
| `file.list` | List directory contents |
| `web_search` | Search the web (DuckDuckGo) |
| `web_fetch` | Fetch and extract URL content |
| `weather` | Get weather for a location (wttr.in) |
| `browser` | Open URL in browser |

Skills in `modules/hands/skills/`:

| Skill | Description |
|-------|-------------|
| `daily_briefing` | Date + weather → formatted summary |
| `research_topic` | Search → fetch → summarize → save |

## Memory

- **Conversations** stored as markdown: `.config/aiassistant/memory/conversations/YYYY-MM-DD.md`
- **Facts** stored by category: `.config/aiassistant/memory/facts/*.md`
- **Knowledge base**: `.config/aiassistant/memory/knowledge/*.md`
- **Embeddings cache**: SQLite database at `.config/aiassistant/embeddings.db` (rebuildable from markdown)

## Remote Modules

Run hardware modules on separate machines:

```bash
python main_remote.py --module ears --bus ws://192.168.1.100:8765
python main_remote.py --help  # full options
```

## Project Structure

```
├── bus/           Message bus, registry, remote WebSocket server
├── llm/           LLM backends (ollama, openai)
├── modules/       All assistant modules
│   ├── base.py    BaseModule abstract class
│   ├── brain/     7-stage thinking + memory + embeddings
│   ├── hands/     Tools + skills + sandbox
│   ├── ears/      Speech recognition + backends
│   ├── mouth/     TTS + backends
│   ├── eyes/      Vision + backends
│   ├── canvas/    File/web output
│   ├── scheduler/ Task scheduling
│   ├── cli/       Terminal interface
│   └── chat/      Messaging backends
├── tests/         pytest test suite
├── main.py        Entry point
├── main_remote.py Remote module launcher
├── config.yaml    Configuration
├── run.sh         Venv wrapper (defaults to main.py)
└── requirements.txt
```

## Tests

```bash
# All tests (fast, no Ollama needed for most)
python -m pytest tests/ -v

# Integration tests only (requires Ollama running)
python -m pytest tests/test_integration.py -v -s

# Unit tests only (no external deps)
python -m pytest tests/ -v --ignore=tests/test_integration.py
```

## Audio Chat

To use voice input, set `ears.backend: halasr` and `mouth.backend: edge_tts` in `config.yaml`.
The assistant records from the default microphone and transcribes with FunASR.

Recorded audio is saved at `/tmp/aiassistant_asr.wav` during live sessions — play it back to verify mic capture.
