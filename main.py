#!/usr/bin/env python3
"""AI Assistant — modular agent with message bus architecture.

Usage:
  python main.py [options]

Options:
  -c, --config PATH   Config file path (default: config.yaml)
  -v, --verbose       Enable verbose logging (DEBUG level)
  -h, --help          Show this help and exit

Examples:
  python main.py                       # Start with config.yaml, INFO logging
  python main.py -c my_config.yaml     # Use custom config file
  python main.py -v                    # Start with debug logging
  python main.py -c prod.yaml -v       # Custom config + debug mode

Config:
  config.yaml controls all modules. Each module has its own section.
  All modules are always loaded; backends control behavior.
  Set backend to "stub" to disable hardware-dependent modules.

  Key config sections:
    brain      — persona, LLM provider/model, memory, embeddings
    ears       — speech recognition backend (stub/funasr/whisper)
    mouth      — TTS backend (text/edge_tts)
    hands      — tool paths, sandbox, command timeout
    scheduler  — task scheduling, max pending
    cli        — terminal interface, prompt style
    bus        — websocket port, remote auth

  See config.yaml for full options with defaults.
"""

import argparse
import asyncio
import logging
import signal
import sys
import yaml

from bus.bus import MessageBus
from bus.remote import RemoteBus

# ── Colored Logging ─────────────────────────────────────────────

COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[1;31m",  # bold red
}
RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    def format(self, record):
        color = COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{RESET}"
        record.msg = f"{color}{record.msg}{RESET}"
        return super().format(record)


logger = logging.getLogger("main")

# Module registry — name → (module_path, class_name)
MODULE_SPECS = [
    ("brain", "brain.brain", "BrainModule"),
    ("hands", "modules.hands.hands", "HandsModule"),
    ("scheduler", "modules.scheduler.scheduler", "SchedulerModule"),
    ("cli", "modules.cli.cli", "CLIModule"),
    ("ears", "modules.ears.ears", "EarsModule"),
    ("mouth", "modules.mouth.mouth", "MouthModule"),
    ("eyes", "modules.eyes.eyes", "EyesModule"),
    ("canvas", "modules.canvas.canvas", "CanvasModule"),
    ("chat", "modules.chat.chat", "ChatModule"),
]

NON_CRITICAL = {"ears", "mouth", "eyes", "canvas", "hands", "cli", "chat"}


def load_config(path: str) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Config not found: {path}, using defaults")
        return {}


def import_module_class(module_path: str, class_name: str):
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class AssistantRunner:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        self.bus = MessageBus()
        self.modules: dict[str, object] = {}
        self.remote_bus: RemoteBus | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self):
        logger.info("Starting AI Assistant...")

        # Start remote bus
        bus_cfg = self.config.get("bus", {})
        self.remote_bus = RemoteBus(
            self.bus,
            port=bus_cfg.get("websocket_port", 8765),
            auth_token=bus_cfg.get("remote_auth_token", ""),
        )
        await self.remote_bus.start()

        # Setup all modules
        for module_name, module_path, class_name in MODULE_SPECS:
            try:
                cls = import_module_class(module_path, class_name)
                instance = cls(self.bus, self.config)
                ok = await instance.setup()
                if not ok:
                    logger.error(f"Module {module_name} setup failed — disabling")
                    continue
                self.modules[module_name] = instance
                logger.info(f"Module {module_name} setup OK")
            except Exception as e:
                logger.exception(f"Module {module_name} setup crashed: {e}")
                if module_name not in NON_CRITICAL:
                    logger.critical(f"Critical module {module_name} failed — exiting")
                    sys.exit(1)

        # Start all modules
        for name, mod in self.modules.items():
            try:
                await mod.start()
                logger.info(f"Module {name} started")
            except Exception as e:
                logger.exception(f"Module {name} start crashed: {e}")
                if name not in NON_CRITICAL:
                    logger.critical(f"Critical module {name} start failed — exiting")
                    sys.exit(1)
                else:
                    self.bus.publish("bus.module.disconnected", {
                        "module_name": name,
                        "reason": str(e),
                    })
                    logger.warning(f"Non-critical module {name} disabled")

        logger.info("All modules started. Assistant ready.")

        # Wait for shutdown
        await self._shutdown_event.wait()

    async def shutdown(self):
        logger.info("Shutting down...")
        for name, mod in reversed(list(self.modules.items())):
            try:
                await mod.stop()
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

        if self.remote_bus:
            await self.remote_bus.stop()

        logger.info("Assistant stopped.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI Assistant — modular agent with message bus architecture.",
        add_help=False,
    )
    parser.add_argument("-c", "--config", default="config.yaml",
                        metavar="PATH", help="Config file path (default: config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable DEBUG logging")
    parser.add_argument("-h", "--help", action="store_true",
                        help="Show help message and exit")
    return parser


async def main():
    parser = parse_args()
    args = parser.parse_args()

    if args.help:
        parser.print_help()
        print()
        print(__doc__)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        handlers=[handler],
    )

    runner = AssistantRunner(args.config)

    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        runner._shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    await runner.start()
    await runner.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
