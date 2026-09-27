#!/usr/bin/env python3
"""AI Assistant — voice-first assistant with a swappable agent harness.

Usage:
  start.sh [options]                # recommended launcher (sets up the venv)

Options:
  -c, --config PATH   Config file path (default: config.yaml)
  -v, --verbose       Enable debug logging (default: warnings only)
  --mode MODE         Interface mode: console | audio | ui | auto (default: auto)
  -h, --help          Show this help and exit

Examples:
  ./start.sh                        # start with config.yaml
  ./start.sh --mode console         # headless
  ./start.sh --mode audio           # voice in and out
  ./start.sh -v                     # debug logging

Config:
  config.yaml controls every module. See docs/contracts/schemas.md for the
  full key reference. Set a backend to "stub" to run without that hardware.

  Key sections:
    agent        — persona, model provider, memory, embeddings
    voice        — speech in and out (stub/whisper/funasr/halasr + text/edge_tts)
    tools        — tool packages, sandbox, timeout
    scheduler    — timed tasks
    console      — terminal interface
    bus          — bind address, port, auth token
"""

import argparse
import asyncio
import logging
import signal
import sys
import yaml

from aiassistant.bus import topics
from aiassistant.bus.bus import MessageBus
from aiassistant.bus.remote import RemoteBus
from aiassistant.config import apply_overrides, migrate_legacy

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

# Module registry — name → (module_path, class_name).
# Keep in sync with the module map in docs/architecture/overview.md.
MODULE_SPECS = [
    ("agent", "aiassistant.agent.module", "AgentModule"),
    ("tools", "aiassistant.tools.module", "ToolsModule"),
    ("scheduler", "aiassistant.scheduler.module", "SchedulerModule"),
    ("console", "aiassistant.console.module", "ConsoleModule"),
    ("voice", "aiassistant.voice.module", "VoiceModule"),
    ("vision", "aiassistant.vision.module", "VisionModule"),
    ("messaging", "aiassistant.messaging.module", "MessagingModule"),
]

NON_CRITICAL = {"voice", "vision", "messaging", "tools", "console"}

# The orb is a separate process; restart it bounded, then give up quietly.
ORB_MAX_RESTARTS = 3
ORB_RESTART_DELAY_S = 2.0


def load_config(path: str) -> dict:
    """Read the config file and migrate any legacy keys (REQ-CFG-004)."""
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Config not found: {path}, using defaults")
        raw = {}
    return migrate_legacy(raw)


def import_module_class(module_path: str, class_name: str):
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class AssistantRunner:
    def __init__(self, config_path: str = "config.yaml", config_overrides: dict | None = None):
        self.config = load_config(config_path)
        if config_overrides:
            apply_overrides(self.config, config_overrides)
        self._config_path = config_path
        self.bus = MessageBus()
        self.modules: dict[str, object] = {}
        self.remote_bus: RemoteBus | None = None
        self._shutdown_event = asyncio.Event()
        self._orb_process = None
        self._orb_restarts = 0
        self._shutting_down = False

    async def start(self):
        logger.info("Starting AI Assistant...")

        # Capture the event loop so daemon threads can schedule coroutines
        self.bus._loop = asyncio.get_running_loop()

        # Start remote bus
        bus_cfg = self.config.get("bus", {})
        self.remote_bus = RemoteBus(
            self.bus,
            port=bus_cfg.get("websocket_port", 8765),
            auth_token=bus_cfg.get("remote_auth_token", ""),
            host=bus_cfg.get("bind", "127.0.0.1"),
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
        self.bus.publish(topics.STATUS_ASSISTANT_READY, {})

        # Launch the orb unless console mode is configured. A GUI failure must
        # not stop the assistant: console is the permanent fallback
        # (REQ-CONSOLE-001).
        await self._maybe_start_orb()

        # Wait for shutdown
        await self._shutdown_event.wait()

    async def _maybe_start_orb(self) -> None:
        """Spawn the orb process, if the display mode calls for one."""
        display = self.config.get("display", {})
        mode = display.get("mode", "orb")
        if mode == "console":
            logger.info("Display mode is console; not starting the orb")
            return

        try:
            import importlib.util
            if importlib.util.find_spec("PySide6") is None:
                logger.warning(
                    "PySide6 is not installed; running without the orb. "
                    "Install it with: pip install 'aiassistant[ui]'"
                )
                return
        except Exception:
            return

        try:
            self._orb_process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "aiassistant.orb",
                "-c", self._config_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._orb_restarts = 0
            logger.info("Orb started (pid=%s)", self._orb_process.pid)
            asyncio.ensure_future(self._watch_orb())
        except Exception as exc:
            logger.warning("Could not start the orb: %s", exc)

    async def _watch_orb(self) -> None:
        """Restart the orb if it dies, bounded, then give up quietly.

        The orb holds no state the assistant needs, so a crash changes nothing
        except the UI (REQ-ORB-001).
        """
        while self._orb_process is not None:
            code = await self._orb_process.wait()
            if self._shutting_down:
                return
            logger.warning("Orb exited (code=%s)", code)
            self._orb_restarts += 1
            if self._orb_restarts > ORB_MAX_RESTARTS:
                logger.error(
                    "Orb failed %d times; not restarting. Run --mode console, "
                    "or check the Qt install.", self._orb_restarts,
                )
                return
            await asyncio.sleep(ORB_RESTART_DELAY_S)
            await self._maybe_start_orb()

    async def _stop_orb(self) -> None:
        proc = self._orb_process
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        except Exception:
            logger.debug("stopping the orb raised", exc_info=True)

    async def shutdown(self):
        logger.info("Shutting down...")
        self._shutting_down = True
        # Cancel any in-flight turn before tearing modules down, so no task is
        # left holding a provider call or waiting on the bus.
        await self._stop_orb()
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
        description="AI Assistant — voice-first assistant with a swappable agent harness.",
        add_help=False,
    )
    parser.add_argument("-c", "--config", default="config.yaml",
                        metavar="PATH", help="Config file path (default: config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging (default: warnings only)")
    parser.add_argument("--mode", choices=("console", "audio", "ui", "auto"),
                        default="auto", help="Interface mode (default: auto from config)")
    parser.add_argument("--audio", action="store_true",
                        help="Deprecated alias for --mode audio")
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
        return 0

    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        handlers=[handler],
    )

    mode = args.mode
    if args.audio and mode == "auto":
        mode = "audio"

    overrides = {}
    if mode == "audio":
        overrides["voice.backend"] = "halasr"
        overrides["voice.tts.backend"] = "edge_tts"

    runner = AssistantRunner(args.config, config_overrides=overrides if overrides else None)

    loop = asyncio.get_running_loop()

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
    return 0


def cli() -> int:
    """Console entry point (``aiassistant`` script)."""
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(cli())
