# CLAUDE.md

Working notes for this repo. The design of record is `docs/` — start at
`docs/README.md`. This file records how to work here and the traps that cost
real time.

## What this is

A voice-first desktop assistant. It listens, transcribes, reasons, speaks, and
shows an ambient orb. The reasoning backend is selectable: our own loop
(`native`) or the external **pi** coding agent.

## Commands

```sh
./start.sh                  # run (console + orb)
./start.sh --mode console   # headless
./start.sh test             # the whole suite
./.venv/bin/python -m pytest tests/test_voice.py -q    # one file
```

`start.sh` creates the venv, installs the package, and runs. Never call
`run.sh` — it was renamed.

## Layout

```
src/aiassistant/
  agent/       turn loop, memory, embeddings, policy
    harness/   base.py (contract), native.py, pi/ (adapter, process, protocol, events)
  voice/       ASR, TTS, audio device, FSM, chunker, wake
  tools/       discovery, builtin_tools/, skills/
  reasoning/   model providers with streaming
  orb/         native Qt window (separate process)
  bus/         bus.py, topics.py, remote.py (WS server)
  console/ vision/ messaging/ scheduler/ bridge.py main.py config.py
```

Modules talk only over bus topics. `orb/` is a separate process.

## Traps

These are the things that actually bit. They are cheap to re-break.

1. **Topic strings are the interface.** Never write a literal. Import from
   `bus.topics`. Routing used to compare `source == "ears"` inline, so renaming
   a module silently disabled speech.

2. **The harness owns the loop, the provider does not.** `agent.harness`
   (`native` | `pi`) is who reasons. `agent.llm.provider` is which model serves
   tokens, and is used only by `native`. `pi` is a harness, not a provider.

3. **Raw audio never crosses the bus.** `bus.publish` is a synchronous dict
   fan-out with no latency bound. PCM stays on the audio threads.

4. **Providers block.** Never call `chat` / `embed` / `chat_stream` from a
   coroutine. Use `provider.achat*`, or `AgentModule._run_blocking`. A test
   asserts the loop keeps ticking.

5. **Tool-call argument encoding is provider-specific.** Ollama needs a dict,
   OpenAI needs a JSON string. Go through `provider.format_tool_arguments`;
   hardcoding either breaks the other with a validation error at request time.

6. **`asyncio.run` waits for the default executor.** A blocking `input()` in
   `run_in_executor` made Ctrl+C hang forever. The console reads stdin through
   `add_reader` (tty) or a non-blocking poll, and `stop()` cancels the reader.
   Do not reintroduce a blocking read there.

7. **Unit tests must not open audio devices.** It segfaults the host audio
   stack. Call `VoiceModule.disable_audio()` first.

8. **pi's `message_end` fires once per role** (system, user, assistant). Only
   `role: assistant` is the answer. A failed turn arrives as an assistant
   message with `stopReason: "error"`, not a separate error event.

9. **The bus binds loopback by default and a non-loopback bind requires a
   token.** With pi enabled, an open bus is a remote shell.

10. **pi is opt-in and confined at the coding level only.** `pi.enabled: true`
    is required. The tool allowlist excludes shell; `pi_extensions/workspace_guard.ts`
    vetoes out-of-workspace paths. Network access and prompt injection are
    **not** contained. Read `docs/security/threat-model.md`.

## Adding a module

1. Add it to `MODULE_SPECS` in `main.py` with its dotted path and class.
2. Add it to `NON_CRITICAL` if the assistant should survive its failure.
3. Subclass `BaseModule` (`setup` / `start` / `stop` / `health`).
4. Add topic constants to `bus/topics.py`; add a payload schema test.
5. Write the module contract in `docs/architecture/modules/`.

## Commits

Do not commit or push unless asked. When asked, inspect `git status` and
`git diff` first, and stage only intended files. `pi_workspace/` and `.config/`
are ignored runtime data.

## Current state

Refactored and committed in `8b42ab9`. Suite: 341 passed, 1 skipped.

Open, and stated as unverified rather than assumed:

- `abort` during a running pi tool; the adapter falls back to process teardown.
- On-target audio timing; the audio logic is unit tested, not the rig.
- Voice barge-in is off until acoustic echo cancellation exists
  (`docs/architecture/decisions/ADR-0011`).
- The orb draws the painted-circle fallback, not the GLSL shader in `docs/ui/`.
