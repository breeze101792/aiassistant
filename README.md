# AI Assistant

A voice-first desktop assistant with a native orb UI and a swappable agent
harness.

You speak; it transcribes, reasons, and answers out loud, while an ambient orb
shows what it is doing. The reasoning backend is selectable in config: the
built-in loop with a local model, or the external **pi** coding agent.

- **Voice in, audio out** — speech recognition, streaming text-to-speech, and an
  interrupt that actually stops the audio.
- **Native orb** — a PySide6/Qt window on macOS and Linux. No browser, no
  terminal as the primary interface.
- **Swappable harness** — `native` (our loop plus a model provider) or `pi`
  (an external coding agent over JSONL RPC).
- **Console fallback** — stays usable headless and in text.

## Quick start

```sh
./start.sh
```

`start.sh` creates the virtual environment if needed, installs the package, and
starts the assistant.

```sh
./start.sh --frontend none  # text only
./start.sh --frontend tui   # terminal orb
./start.sh --audio          # voice in and out
./start.sh test             # run the test suite
./start.sh -h               # options
```

## Your config

Every default lives in code, so the assistant runs with no config file. To
change something, copy the example and keep only what you want to differ:

```sh
cp config.example.yaml config.yaml   # config.yaml is git-ignored
```

```yaml
# config.yaml — only your overrides
agent:
  llm:
    model: qwen3:latest      # your model
console:
  prompt: "you> "
```

It is deep-merged over the defaults, so anything you omit keeps its default.
Precedence: CLI flag > environment > `config.yaml` > code defaults.

## Requirements

| | |
| --- | --- |
| Python | 3.11 or newer |
| OS | macOS or Linux |
| Model | A local [Ollama](https://ollama.com) model, or an OpenAI-compatible endpoint |
| Optional | `pi` for the external harness (`./scripts/setup_pi.sh`) |

```sh
# The default model, if you do not have it yet
ollama pull qwen3:latest
```

## Configuration

One file selects every backend: `config.yaml`. See
[docs/contracts/schemas.md](docs/contracts/schemas.md) for the full reference.

```yaml
agent:
  harness: native            # native | pi
  llm:
    provider: ollama         # ollama | openai
    model: qwen3:latest

voice:
  listen:
    mode: open               # ptt | open | wake
  backend: stub              # stub | whisper | funasr
  hotwords: ["hey jarvis"]

voice_tts:
  backend: text              # text | edge_tts
```

### Switching the reasoning backend

Two independent choices, which are easy to confuse:

| Layer | What it is | Config |
| --- | --- | --- |
| Model provider | Serves an LLM over an API | `agent.llm.provider` |
| Model | The weights | `agent.llm.model` |
| **Agent harness** | Owns the reasoning loop, tool calls, and context | `agent.harness` |

`pi` is a **harness**, not a provider: it runs its own loop and calls its own
model. Swapping `harness` changes who owns the loop.

To use it:

```sh
./scripts/setup_pi.sh
```

```yaml
agent:
  harness: pi
  pi:
    enabled: true
    workspace: "~/.config/aiassistant/pi_workspace"
```

> **Read [docs/security/threat-model.md](docs/security/threat-model.md) first.**
> pi runs with your permissions and has no permission system of its own. The
> tool allowlist and workspace guard reduce the blast radius; they are not an OS
> sandbox.

## Layout

```
src/aiassistant/
  agent/        the turn loop, memory, embeddings, and the harness contract
    harness/    native (our loop) and pi (external process)
  voice/        speech in and out: ASR, TTS, audio device, wake detection
  tools/        tool discovery, built-ins, and skills
  reasoning/    model providers (ollama, openai) with streaming
  orb/          the native Qt window
  bus/          the in-process bus, topics, and the WebSocket bridge
  console/  vision/  messaging/  scheduler/  bridge.py
```

Modules talk to each other only over bus topics. `orb/` is a separate process,
so a GUI crash cannot take the assistant down.

## Documentation

The design docs are the reference; start at [docs/README.md](docs/README.md).

| | |
| --- | --- |
| [requirements/](docs/requirements/) | what it must do, with testable criteria |
| [architecture/](docs/architecture/) | components, module contracts, decisions |
| [contracts/](docs/contracts/) | bus topics, the pi protocol, the orb API |
| [testing/](docs/testing/) | test plan and the requirement-to-test trace |
| [security/](docs/security/) | threat model and the pi confinement story |

## Tests

```sh
./start.sh test
```

On-target audio checks are described in
[docs/testing/TEST_PLAN.md](docs/testing/TEST_PLAN.md); they need a real device
and are not part of the default run.

## License

See [LICENSE](LICENSE). The orb uses PySide6 under LGPLv3; distribution
obligations are noted in [docs/operations/deploy.md](docs/operations/deploy.md).
