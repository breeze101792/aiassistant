# Operations — Dependencies and Repositories

## Python dependencies

| Package | Purpose | Notes |
| --- | --- | --- |
| `websockets` | Bridge server and client | **Pin it.** Version 16.0 changed the handler signature, which broke `bus/remote.py:45` |
| `ollama` | Local model provider | |
| `openai` | OpenAI-compatible provider | Also works with vLLM and LM Studio |
| `tiktoken` | Token counting | Optional; degrades to a word estimate |
| `sounddevice` | Audio capture and playback | Replaces `pyaudio`; PortAudio bindings |
| `webrtcvad` | Voice activity detection | |
| `edge-tts` | Text to speech | Emits MP3; needs a decoder to reach PCM |
| `PySide6` | The orb | LGPLv3; see [deploy.md](deploy.md) |
| `pyyaml`, `tzlocal` | Config and time | |
| ASR backends | `openai-whisper`, `funasr` (needs `torch`) | Install separately; heavy |
| `duckduckgo-search`, `beautifulsoup4` | Web tools | |

Removed: `aiohttp` (imported nowhere).

## Removed repositories

| Item | Why |
| --- | --- |
| `utility` submodule (`pyutility`) | The gitlink was deleted in commit `cf88cfd` and the directory is absent; `.gitmodules` was stale. Verified no code imports it. |

## Models

| Role | Default | Notes |
| --- | --- | --- |
| Chat | `qwen3:latest` via Ollama | No API key needed |
| Embeddings | `qwen3-embedding:0.6b` | Separate config; changing it requires an index rebuild |

The native harness uses these providers through `agent.llm.*` and `embeddings.*`.
