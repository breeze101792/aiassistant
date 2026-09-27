# ADR-0003 — Delete the canvas module; the orb is the display

**Status:** accepted · **Date:** 2026-09-26

## Decision

Delete `modules/canvas/` entirely — all five files. Do not rename it to
`display`. The orb is the display. Generated artifacts are written by tools.

## Why

The module is dead. Verified:

| Artifact | Evidence |
| --- | --- |
| `backends/web.py` | Every method is `pass` (`web.py:7-21`); `start()` is `pass  # Web server started in main process`, and no such server exists |
| `config.yaml:65` `web_port: 8081` | Never bound |
| `requirements.txt:2` `aiohttp>=3.9` | Imported nowhere |
| `backends/file.py` | Writes HTML/text wrappers to disk; a thin `open().write()` |
| `renderer.py` | Only wraps image generation behind an unconfigured `image_model` |

The user believed there was a web frontend and asked to drop it in favor of a
native UI. There is no frontend: the web backend was a stub. So "drop it" is a
deletion, not a migration.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Rename `canvas` → `display` | Creates a name collision: the orb is the real display. Two things called display is worse than none. |
| Keep the file backend for artifact output | `tools/file.write` already writes files. A second path is duplication. |
| Keep the web backend and finish it | Explicitly out of scope; the user wants native, not web. |

## Consequences

- `config.yaml` loses the `canvas` section; `requirements.txt` loses `aiohttp`.
- `tests/test_canvas.py` is deleted.
- Artifacts go to a configurable `tools.artifacts_path`.
- `sensory.canvas.*` topics are removed from `perceive.py`.
