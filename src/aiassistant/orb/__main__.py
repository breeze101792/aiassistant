"""Entry point for the orb process.

Runs only the Qt event loop. Started by ``main.py`` as a child process, or
directly with ``python -m aiassistant.orb`` for development.

    python -m aiassistant.orb [--config config.yaml] [--no-on-top]
"""

import argparse
import logging
import sys

from aiassistant.orb.app import OrbConfig, OrbWindow
from aiassistant.orb.model import OrbViewModel


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="AI Assistant orb UI")
    parser.add_argument("-c", "--config", default="config.yaml",
                        help="Config file path (default: config.yaml)")
    parser.add_argument("--url", default=None,
                        help="Override the bus WebSocket URL")
    parser.add_argument("--no-on-top", action="store_true",
                        help="Do not keep the window above other windows")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def load_orb_config(path: str, url_override: str | None, no_on_top: bool) -> OrbConfig:
    """Read only the keys the orb needs.

    Deliberately avoids importing the assistant's config machinery: this process
    has no business loading the whole application configuration, and keeping it
    narrow means a config error elsewhere cannot stop the UI.
    """
    try:
        import yaml
        with open(path) as handle:
            raw = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        raw = {}
    except Exception:
        raw = {}

    cfg = OrbConfig.from_config(raw)
    if url_override:
        cfg.url = url_override
    if no_on_top:
        cfg.always_on_top = False
    return cfg


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print(
            "PySide6 is required for the orb: pip install 'aiassistant[ui]'\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 2

    cfg = load_orb_config(args.config, args.url, args.no_on_top)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("AI Assistant")
    model = OrbViewModel()
    window = OrbWindow(model, cfg.url, cfg.token, cfg.always_on_top)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
