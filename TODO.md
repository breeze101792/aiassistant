# TODO

## Known Issues

### Tab Auto-Complete
- [ ] Fix tab auto-complete for slash commands on macOS (libedit) — current approach inserts stray `/` character or doesn't work
- [ ] Test tab completion on Linux (GNU readline) to confirm it works there

## Module Tests

Each module needs its own test file so we can develop and test modules independently.

### Tests still needed
- [ ] `tests/test_chat.py` — Telegram and other chat backends

### Existing tests
- `tests/test_bus.py` — MessageBus pub/sub, RPC, module registry
- `tests/test_brain_core.py` — Perceiver, understander, reasoner, planner, reflector, responder
- `tests/test_cli.py` — Command parsing, log level switching, tab completion logic
- `tests/test_ears_mouth.py` — ASR backends, TTS backends
- `tests/test_eyes_canvas.py` — Vision backends, canvas output
- `tests/test_hands.py` — Tool execution, sandbox, builtin tools
- `tests/test_llm.py` — LLM backend interface and smoke tests
- `tests/test_memory.py` — Memory manager, embeddings, persona, tool cache
- `tests/test_scheduler.py` — Schedule storage (add, list, delete, persistence)
- `tests/test_integration.py` — End-to-end flow tests (requires Ollama)
