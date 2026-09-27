"""Entry point for the TUI orb process.

A separate process (ADR-0017), started by ``main.py`` as a child, or directly:

    python -m aiassistant.tui [-c config.yaml] [-v] [--url ws://...]

Terminal preconditions are checked **before** entering curses: ``initscr()``
can hard-exit the interpreter on a bad terminal, so a failure here is reported
as text and exit code 3 instead.
"""

import argparse
import asyncio
import logging
import sys

from aiassistant import config as assistant_config

DEFAULT_CONFIG_PATH = "config.yaml"

# Exit codes. 3 mirrors "cannot start here"; 0 is a clean exit.
EXIT_OK = 0
EXIT_BAD_TERMINAL = 3


def parse_args(argv=None):
    from . import tokens

    parser = argparse.ArgumentParser(
        prog=tokens.PROGRAM_NAME, description="AI Assistant terminal orb")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG_PATH,
                        help="Local config file (default: config.yaml; optional)")
    parser.add_argument("--url", default=None,
                        help="Override the bus WebSocket URL")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def load_tui_config(path: str, url_override: str | None) -> tuple[str, str, str, list[str]]:
    """Read only the keys the TUI needs: bus, identity, and wake phrases.

    Uses the same defaults-plus-local loader, so a bus port or identity set in
    config.yaml reaches this process too; the read stays narrow, so a config
    error elsewhere cannot stop the UI. A missing file yields the defaults.
    """
    raw: dict = {}
    try:
        from aiassistant.config import load_config
        loaded = load_config(path)
        if isinstance(loaded, dict):
            raw = loaded
    except Exception:
        logging.getLogger(__name__).debug("config read failed; using defaults",
                                          exc_info=True)

    bus_cfg = raw.get("bus", {}) if isinstance(raw.get("bus"), dict) else {}
    bind = bus_cfg.get("bind") or "127.0.0.1"
    # A wildcard bind is not reachable as a client address; use loopback.
    host = "127.0.0.1" if bind in ("0.0.0.0", "::", "") else bind
    port = bus_cfg.get("websocket_port") or 8765
    url = url_override or f"ws://{host}:{port}"

    token = bus_cfg.get("remote_auth_token") or ""
    identity = _active_identity(raw)
    return url, str(token), identity, _hotwords(raw)


def _hotwords(raw: dict) -> list[str]:
    """The configured wake phrases, for the help overlay.

    Read from ``voice.hotwords`` so the overlay names the phrase the voice
    pipeline listens for. Never hard-coded.
    """
    voice = raw.get("voice")
    if not isinstance(voice, dict):
        return []
    phrases = voice.get("hotwords")
    if not isinstance(phrases, list):
        return []
    return [str(p) for p in phrases if str(p).strip()]


def _active_identity(raw: dict) -> str:
    """The display name for the transcript gutter.

    From ``agents.<active>.identity.name`` (schemas.md); never hard-coded.
    Falls back to the only entry, then to the shipped default.
    """
    from . import tokens

    agents = raw.get("agents")
    if not isinstance(agents, dict) or not agents:
        return tokens.DEFAULT_IDENTITY
    active = agents.get("active")
    entry = agents.get(active) if isinstance(active, str) else None
    if not isinstance(entry, dict):
        candidates = [v for k, v in agents.items() if k != "active"
                      and isinstance(v, dict)]
        entry = candidates[0] if len(candidates) == 1 else None
    if isinstance(entry, dict):
        name = entry.get("identity", {}).get("name") \
            if isinstance(entry.get("identity"), dict) else None
        if isinstance(name, str) and name:
            return name
    return tokens.DEFAULT_IDENTITY


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    ok, reason = assistant_config.tui_available()
    if not ok:
        print(f"cannot start the TUI: {reason}", file=sys.stderr)
        return EXIT_BAD_TERMINAL

    url, token, identity, hotwords = load_tui_config(args.config, args.url)

    from .app import TuiApp

    try:
        return asyncio.run(TuiApp(url=url, token=token, identity=identity,
                                  hotwords=hotwords).run())
    except KeyboardInterrupt:
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
