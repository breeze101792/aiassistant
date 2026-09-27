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

## External: pi

| Field | Value |
| --- | --- |
| Project | `https://github.com/earendil-works/pi` |
| Package | `@earendil-works/pi-coding-agent` |
| **Pinned version** | `0.87.1` (update here and in `scripts/setup_pi.sh` together) |
| License | MIT |
| Runtime | Node >= 22.19, **or** the standalone darwin/linux binary (preferred) |
| Binaries | darwin-arm64/x64, linux-arm64/x64 |
| Installer | `curl -fsSL https://pi.dev/install.sh \| sh` |
| Config dir | `~/.pi/agent` (override `PI_CODING_AGENT_DIR`) |

**Why not a submodule:** see [ADR-0007](../architecture/decisions/ADR-0007-pin-pi-not-vendor.md).

### Upgrade procedure

1. Bump the pinned version in `scripts/setup_pi.sh` and this file.
2. Re-run `scripts/setup_pi.sh`.
3. Run the adapter fixture tests (`tests/test_pi_events.py`). If any fail, the
   wire format changed and the mapping must be updated against the new docs.
4. Re-run the host spike items listed as unverified in
   [IF-0003](../contracts/protocols.md#if-0003-pi-rpc) — in particular `abort`
   during a running tool.
5. Record any behavior change in the ADR log if it affects a decision.

## Removed repositories

| Item | Why |
| --- | --- |
| `utility` submodule (`pyutility`) | The gitlink was deleted in commit `cf88cfd` and the directory is absent; `.gitmodules` was stale. Verified no code imports it. |

## Models

| Role | Default | Notes |
| --- | --- | --- |
| Chat | `qwen3:latest` via Ollama | No API key needed |
| Embeddings | `qwen3-embedding:0.6b` | Separate config; changing it requires an index rebuild |

pi uses its own model configuration (`~/.pi/agent/models.json`, `auth.json`),
including local and OpenAI-compatible endpoints. The assistant does not read or
manage those files.
