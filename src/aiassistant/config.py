"""Configuration loading: defaults, precedence, and legacy-key migration.

Defaults live **in code** (``DEFAULTS``), so the assistant runs with no config
file at all. ``config.yaml`` is the user's local override: it is overlaid on the
defaults key by key, so it names only the keys that differ. ``config.example.yaml``
is the tracked, commented example.

Precedence (REQ-CFG-002): CLI override > environment > local config file >
code defaults.

Legacy keys from the pre-refactor config are accepted, mapped to their new
names, and reported once as deprecated (REQ-CFG-004). The mapping lives in
``LEGACY_*`` tables so it is testable in isolation and cannot rot silently.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# The frontend is the visual shell. ``mode`` selects only this; text (the
# console REPL) and audio are always-available capabilities, not modes
# (ADR-0017).
FRONTEND_GUI = "gui"
FRONTEND_TUI = "tui"
FRONTEND_NONE = "none"
FRONTEND_AUTO = "auto"
FRONTENDS = (FRONTEND_GUI, FRONTEND_TUI, FRONTEND_NONE, FRONTEND_AUTO)
_VALID_FRONTENDS = frozenset(FRONTENDS)

# Accepted for back-compat, mapped to a canonical frontend and warned once.
# ``console`` meant "no window, REPL on the tty", which is exactly ``none``.
FRONTEND_ALIASES = {
    "orb": FRONTEND_GUI,
    "ui": FRONTEND_GUI,
    "console": FRONTEND_NONE,
}

# A display server is declared by an environment variable. macOS Aqua sessions
# export neither, so a local Mac is treated as having a GUI (see gui_available).
_DISPLAY_ENV_VARS = ("DISPLAY", "WAYLAND_DISPLAY")
_PROBED_PLATFORM = "linux"

# Set in a remote shell. With no forwarded display, no window can be shown.
_SSH_ENV_VARS = ("SSH_CONNECTION", "SSH_TTY")

# Terminals that cannot do cursor addressing; a full-screen TUI must not start.
_DUMB_TERMS = frozenset({"dumb", "unknown", ""})

# Set when the UI must not be shown. It forces ``none``, but yields to an
# explicit frontend on the command line (REQ-CFG-002).
_DISPLAY_OFF_ENV_VAR = "AIASSISTANT_DISPLAY_OFF"

# Every default, in code, so the assistant runs with no config file. This is the
# single source of truth; config.example.yaml documents the same values for the
# user. A test asserts the example stays in step (tests/test_config.py).
DEFAULTS: dict = {
    "bus": {
        "bind": "127.0.0.1",
        "websocket_port": 8765,
        "remote_auth_token": "",
    },
    "agent": {
        "harness": "native",
        "persona": (
            "You are Jarvis, a conversational voice assistant. Speak the way a "
            "person talks: natural, warm, and direct. Keep every reply to one "
            "short paragraph. Never use more than five sentences, even if the "
            "user asks for more detail; offer to continue instead of writing "
            "more. Never use emoji, markdown, headings, or bullet lists. Do not "
            "read code, URLs, or file paths aloud. Match the user's language. "
            "When a tool is needed, use it and answer with the result in your "
            "own words. If a request is unclear, ask one short question instead "
            "of guessing.\n"
        ),
        "llm": {
            "provider": "ollama",
            "model": "qwen3:latest",
            "url": "http://127.0.0.1:11434",
            "api_key": "",
            "max_tokens": 4096,
            "temperature": 0.7,
        },
        "memory": {
            "conversations_path": ".config/aiassistant/memory/conversations",
            "facts_path": ".config/aiassistant/memory/facts",
            "knowledge_path": ".config/aiassistant/memory/knowledge",
            "embeddings_db": ".config/aiassistant/embeddings.db",
            "context_max_tokens": 4096,
            "context_recent_messages": 20,
        },
        "embeddings": {
            "provider": "ollama",
            "model": "qwen3-embedding:0.6b",
            "url": "",
            "batch_size": 10,
        },
        "thinking": {
            "max_reflect_loops": 3,
        },
    },
    "conversation": {
        "busy": "interrupt",
        "turn_timeout_s": 300,
        "retry_max": 3,
    },
    "scheduler": {
        "storage_path": ".config/aiassistant/schedules.json",
        "max_pending": 100,
    },
    "voice": {
            "listen": {"mode": "open"},
            "hotwords": ["hey jarvis"],
            "endpoint_silence_ms": 2000,
            # After the wake phrase, follow-up utterances are accepted without
            # repeating it, until this much quiet time passes (wake mode only).
            "wake_window_ms": 8000,
            # Keep the mic gated this long after playback, so the speaker's tail
            # is not captured as a new utterance (the assistant hearing itself).
            "echo_guard_ms": 400,
        "speak_text_turns": False,
        "barge_in": {"enabled": False},
        "vad": {"backend": "energy", "energy_threshold": 0.02, "aggressiveness": 3},
        "segmenter": {
            "preroll_ms": 200,
            "min_utterance_ms": 100,
            "max_utterance_ms": 30000,
            # Speech must persist this long to open a segment, so room-noise
            # clicks do not trigger a transcription.
            "onset_ms": 100,
        },
        "asr": {
            "backend": "faster_whisper",
            "model": "base",
            # faster_whisper only. CTranslate2's "auto" can select CUDA and then
            # fail without the CUDA runtime libs, so cpu is the safe default;
            # set device: cuda to opt in.
            "device": "cpu",
            "compute_type": "int8",
            # whisper_server only; generic, not tied to any provider. A
            # self-hosted server ignores the key.
            "base_url": "",
            "api_key": "",
            "api_key_env": "ASR_API_KEY",
            "language": "",
        },
        "tts": {"backend": "edge_tts", "voice": "en-US-AriaNeural", "speed": 1.0},
    },
    "vision": {
        "backend": "stub",
        "camera_index": 0,
        "vision_model": None,
        "vision_model_url": "",
    },
    "tools": {
        "packages": [
            "aiassistant.tools.builtin_tools",
            "aiassistant.tools.skills",
        ],
        "sandbox_default": False,
        "command_timeout": 30,
        "safe_paths": ["./workspace", "/tmp/aiassistant"],
    },
    "console": {
        "backend": "simple",
        "prompt": "> ",
    },
    "messaging": {
        "backends": [],
        "telegram_token": "",
        "telegram_allowed_users": [],
    },
    "display": {
        "mode": FRONTEND_AUTO,
        "always_on_top": True,
        "reduced_motion": False,
    },
}

# Old top-level section -> new top-level section.
LEGACY_SECTIONS = {
    "brain": "agent",
    "ears": "voice",
    "mouth": "voice_tts",
    "hands": "tools",
    "eyes": "vision",
    "chat": "messaging",
    "cli": "console",
}

# Sections that no longer exist at all.
REMOVED_SECTIONS = {"canvas"}

# Old key -> new key, within the mapped section.
LEGACY_KEYS = {
    "voice": {"hotwords": "hotwords"},
}

# Units or names that differ between old and new.
# ears.silence_timeout is seconds; the new key is milliseconds.
LEGACY_SCALE = {
    ("voice", "silence_timeout"): ("endpoint_silence_ms", 1000),
}

# Keys that moved to a different dotted path. Processed after LEGACY_SECTIONS,
# so a section rename and a per-key move compose: ``mouth`` becomes ``voice_tts``
# first, then ``voice_tts.backend`` moves to ``voice.tts.backend``. The old
# value survives verbatim, including ``halasr``, so ``voice.factory`` can report
# the ADR-0018 error rather than a user silently getting the stub.
LEGACY_MOVES = (
    ("voice.backend", "voice.asr.backend"),
    ("voice_tts.backend", "voice.tts.backend"),
    ("voice_tts.voice", "voice.tts.voice"),
    ("voice_tts.speed", "voice.tts.speed"),
)

# Top-level sections that were fully superseded by LEGACY_MOVES and are dropped
# once their keys have moved.
LEGACY_MOVED_SECTIONS = ("voice_tts",)

# Keys with no successor, dropped with one warning. ``voice.recognizer`` was
# meaningful only to the removed halasr backend (ADR-0018).
LEGACY_DROPPED = {
    ("voice", "recognizer"): "halasr-only; use voice.asr.backend (ADR-0018)",
}

# Distinguishes "absent" from a stored None while walking dotted paths.
_MISSING = object()


def _get_dotted(config: dict, path: str):
    target = config
    for part in path.split("."):
        if not isinstance(target, dict) or part not in target:
            return _MISSING
        target = target[part]
    return target


def _set_dotted(config: dict, path: str, value) -> None:
    """Set a dotted path, creating intermediate dicts as needed."""
    parts = path.split(".")
    target = config
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _delete_dotted(config: dict, path: str) -> None:
    parts = path.split(".")
    target = config
    for part in parts[:-1]:
        target = target.get(part)
        if not isinstance(target, dict):
            return
    target.pop(parts[-1], None)


def migrate_legacy(config: dict) -> dict:
    """Rewrite legacy keys in place and return the same dict.

    Unknown legacy sections are dropped with a warning rather than passed
    through, so downstream modules never see a section they do not expect.
    """
    for old, new in LEGACY_SECTIONS.items():
        if old not in config:
            continue
        section = config.pop(old)
        logger.warning("Config section %r is deprecated; use %r", old, new)
        if isinstance(section, dict):
            target = config.setdefault(new, {})
            for key, value in section.items():
                mapped = LEGACY_KEYS.get(new, {}).get(key, key)
                scaled = LEGACY_SCALE.get((new, key))
                if scaled:
                    new_key, factor = scaled
                    value = int(value) * factor
                    mapped = new_key
                target.setdefault(mapped, value)

    for (section, key), reason in LEGACY_DROPPED.items():
        block = config.get(section)
        if isinstance(block, dict) and key in block:
            block.pop(key)
            logger.warning(
                "Config %s.%s is deprecated and was dropped: %s", section, key, reason
            )

    for old_path, new_path in LEGACY_MOVES:
        value = _get_dotted(config, old_path)
        if value is _MISSING:
            continue
        _delete_dotted(config, old_path)
        if _get_dotted(config, new_path) is _MISSING:
            _set_dotted(config, new_path, value)
            logger.warning("Config %s is deprecated; use %s", old_path, new_path)
        else:
            logger.warning("Config %s is deprecated; keeping %s", old_path, new_path)

    for section in LEGACY_MOVED_SECTIONS:
        block = config.get(section)
        if isinstance(block, dict):
            config.pop(section)
            logger.warning("Config section %r is deprecated; use 'voice.tts'", section)

    for removed in REMOVED_SECTIONS:
        if removed in config:
            config.pop(removed)
            logger.warning("Config section %r was removed; ignoring it", removed)

    return config


def apply_overrides(config: dict, overrides: dict) -> None:
    """Apply dotted-key overrides, creating intermediate dicts as needed."""
    for dotted_key, value in overrides.items():
        _set_dotted(config, dotted_key, value)


# The local config file, relative to the working directory. It is ignored by
# git; config.example.yaml is the tracked, commented example.
LOCAL_CONFIG_NAME = "config.yaml"
EXAMPLE_CONFIG_NAME = "config.example.yaml"


def merge_config(base: dict, overlay: dict) -> dict:
    """Deep-merge ``overlay`` onto ``base`` in place and return it.

    Nested mappings merge key by key, so a partial overlay changes only the keys
    it names; a scalar or a list replaces the base value.
    """
    for key, value in overlay.items():
        current = base.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merge_config(current, value)
        else:
            base[key] = value
    return base


def load_config_file(path: str) -> dict:
    """Read one YAML config file. A missing or empty file is an empty dict."""
    import yaml

    try:
        with open(path) as handle:
            raw = yaml.safe_load(handle)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning("Cannot read config %s: %s", path, exc)
        return {}
    except yaml.YAMLError as exc:
        logger.warning("Config %s is not valid YAML: %s", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def load_config(path: str = LOCAL_CONFIG_NAME) -> dict:
    """Return the effective config: ``DEFAULTS`` overlaid by the local file.

    The file is optional. With none present the code defaults apply, so the
    assistant runs on a fresh clone with no setup (REQ-CFG-008). The defaults
    are deep-copied, so loading never mutates them.
    """
    import copy

    config = copy.deepcopy(DEFAULTS)
    raw = load_config_file(path)
    if raw:
        merge_config(config, migrate_legacy(raw))
        logger.debug("Local config applied: %s", path)
    return config


def gui_available() -> bool:
    """True when a window can be shown in this process environment.

    Display variables are checked first, so a forwarded X session (an SSH login
    with a real ``DISPLAY``) still counts as usable. SSH with nothing forwarded
    cannot show a window, which closes the gap where a macOS SSH session wrongly
    reported a GUI. A local macOS Aqua session exports neither variable and is
    treated as having one.
    """
    if any(os.environ.get(var) for var in _DISPLAY_ENV_VARS):
        return True
    if any(os.environ.get(var) for var in _SSH_ENV_VARS):
        return False
    if sys.platform != _PROBED_PLATFORM:
        return True
    return False


def tui_available() -> tuple[bool, str]:
    """Whether a full-screen terminal UI can start here, and why not.

    Checked **before** entering curses: ``curses.initscr()`` can exit the
    interpreter on a bad terminal, and even on a good one it writes escape
    sequences, so a failed start must be decided here. This is safe to call in
    the parent: ``setupterm`` raises, it does not exit.
    """
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return False, "stdin/stdout is not a terminal"
    except (ValueError, AttributeError):
        return False, "stdin/stdout is not a terminal"

    term = os.environ.get("TERM", "")
    if term in _DUMB_TERMS:
        return False, f"TERM is {term or 'unset'}"

    try:
        import curses
    except ImportError:
        return False, "the curses module is not available"

    try:
        curses.setupterm()
        if curses.tigetstr("cup") is None:
            return False, "the terminal lacks cursor addressing"
    except curses.error as exc:
        return False, f"terminfo unavailable: {exc}"
    return True, ""


def canonical_frontend(value: str | None) -> str | None:
    """Map an alias to a canonical frontend. Unknown values pass through."""
    if value is None:
        return None
    return FRONTEND_ALIASES.get(value, value)


def resolve_frontend(config: dict, cli_choice: str | None = None) -> str:
    """Collapse the frontend preference to ``gui``, ``tui``, or ``none``.

    Precedence follows REQ-CFG-002: an explicit CLI choice beats the
    environment, which beats the config file, which beats ``auto``. ``auto``
    (and an unset mode) is ``gui`` when a display is available and ``none``
    otherwise; it never resolves to ``tui``, which is explicit by design.
    """
    choice = canonical_frontend(cli_choice)
    if choice in (FRONTEND_GUI, FRONTEND_TUI, FRONTEND_NONE):
        return choice

    if os.environ.get(_DISPLAY_OFF_ENV_VAR):
        return FRONTEND_NONE

    mode = canonical_frontend(config.get("display", {}).get("mode", FRONTEND_AUTO))
    if mode not in _VALID_FRONTENDS:
        logger.warning("Unknown display.mode %r; falling back to %s", mode, FRONTEND_AUTO)
        mode = FRONTEND_AUTO

    if mode == FRONTEND_AUTO:
        return FRONTEND_GUI if gui_available() else FRONTEND_NONE
    return mode
