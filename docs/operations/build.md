# Operations — Build and Run

## Runtime

| Requirement | Version | Notes |
| --- | --- | --- |
| Python | 3.11 or newer | The as-built environment is 3.14.7 |
| OS | macOS 13+ or a current Linux | Both are MVP targets |
| Audio | A working input and output device | Missing devices degrade, they do not crash |

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

System packages:

| OS | Need | Command |
| --- | --- | --- |
| macOS | PortAudio (via `sounddevice` wheels) | usually none; `brew install portaudio` if the wheel fails |
| Linux | PortAudio and Qt runtime libs | `sudo apt install libportaudio2 libgl1 libegl1 libxkbcommon-x11-0` |

## Run

```sh
python main.py                     # default from config: console + orb
python main.py --frontend none     # text only
python main.py --frontend tui      # terminal orb
python main.py --audio             # voice backends on
python main.py -c my_config.yaml   # alternate base config
python main.py -v                  # debug logging
```

## Your config

Every default lives in code, so the assistant runs with no config file.
`config.example.yaml` documents them; copy it to `config.yaml` (git-ignored) and
keep only what you change. It is deep-merged over the defaults, so omitted keys
keep their default. Layers, later winning: code defaults, then `config.yaml`,
then the environment and CLI flags.

The orb is a separate process:

```sh
python -m orb
```

## Config precedence

CLI override > environment > config file > built-in defaults (REQ-CFG-002).

Legacy section names are accepted with a deprecation warning and mapped to the
new keys (REQ-CFG-004). The full nested mapping is in
[contracts/schemas.md § Legacy key migration](../contracts/schemas.md#legacy-key-migration).

## Dependencies to watch

| Dependency | Change | Reason |
| --- | --- | --- |
| `aiohttp` | **Removed** | Imported nowhere |
| `pyaudio` | Replaced by `sounddevice` | Callback streaming for interruptible playback on both OSes |
| `sounddevice` | Added | PortAudio bindings; the same system library, a much harder API to misuse |
| MP3 decoder | Added | edge-tts emits MP3; `sounddevice` needs PCM |
| `PySide6` | Added | The orb |
| `webrtcvad` | Kept | VAD |

## Tests

```sh
pytest                       # host suite
pytest tests/test_voice_queue.py -v
```

On-target audio checks live in `testing/TEST_PLAN.md`; they need a real device
and are not part of the default run.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError: sounddevice` | PortAudio missing | Install the system package above |
| No microphone | Device absent or permission denied (macOS) | Grant access in System Settings; the app degrades, it does not crash |
| orb window does not appear | No display, or Wayland without a compositor supporting it | Run `--frontend none`; see the platform caveats in [ui-stack research](../research/ui-stack.md) |
| Backend-down in the orb | Harness unhealthy | Check `/status` in the console; see [flows (g)](../requirements/flows.md#g-harness-unavailable--model-down) |
| Harness will not start | `agent.harness` names an unknown value, or the provider probe fails | Check the value and the log; see [flows (g)](../requirements/flows.md#g-harness-unavailable--model-down) |
