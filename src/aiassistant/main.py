#!/usr/bin/env python3
"""AI Assistant — voice-first assistant with a swappable agent harness.

Usage:
  start.sh [options]                # recommended launcher (sets up the venv)

Options:
  -c, --config PATH   Local config file (default: config.yaml, optional).
                      Defaults live in code; the file overrides only the keys it
                      names. See config.example.yaml.
  -v, --verbose       Enable debug logging (default: warnings only)
  --frontend SHELL    Visual shell: gui | tui | none | auto (default: auto).
                      auto uses gui when a display is available, none otherwise.
                      Text and audio always run; none means text only.
  --audio             Voice via a self-hosted Whisper server on your LAN
                      (no api key), TTS via edge-tts.
  --offline           Fully offline voice: local faster-whisper ASR, text TTS.
                      Mutually exclusive with --audio.
  -h, --help          Show this help and exit

Examples:
  ./start.sh                        # run with the code defaults
  ./start.sh -c config.yaml         # apply your local overrides
  ./start.sh --frontend none        # text only
  ./start.sh --frontend tui         # terminal orb
  ./start.sh --audio                # voice via a self-hosted Whisper server
  ./start.sh --offline              # fully offline voice in and out
  ./start.sh -v                     # debug logging

Environment:
  AIASSISTANT_DISPLAY_OFF=1  force the none frontend without a config edit

Config:
  Every default lives in code, so the assistant runs with no config file.
  config.example.yaml documents them; copy it to config.yaml (git-ignored) and
  keep only what you change. Precedence: CLI > environment > config.yaml >
  code defaults. See docs/contracts/schemas.md for the full key reference.

  Key sections:
    agent        — persona, model provider, memory, embeddings
    voice        — speech in and out: vad, segmenter, asr, tts (per-stage backends)
    tools        — tool packages, sandbox, timeout
    scheduler    — timed tasks
    console      — terminal interface
    display      — frontend selection (gui/tui/none/auto)
    bus          — bind address, port, auth token
"""

import argparse
import asyncio
import logging
import signal
import sys
from typing import Any

from aiassistant import terminal
from aiassistant.bus import topics
from aiassistant.bus.bus import MessageBus
from aiassistant.bus.remote import RemoteBus
from aiassistant.config import (
    FRONTEND_GUI,
    FRONTEND_NONE,
    FRONTEND_TUI,
    apply_overrides,
    gui_available,
    load_config,
    resolve_frontend,
    tui_available,
)
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


class PromptAwareHandler(logging.StreamHandler):
    """Log handler that keeps an interactive prompt intact.

    A WARNING can arrive while the user is at an empty prompt. Writing straight
    to the stream appends to the prompt line and destroys it. When a prompt
    owner is registered, the record goes through ``terminal.write_above`` so the
    console erases the prompt, prints the record on its own line, and redraws
    the prompt.

    With no prompt owner (a pipe, a log file, a non-interactive run) it defers
    to the plain ``StreamHandler``, so the record still goes to this handler's
    own stream — stderr by default — exactly as before.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if not terminal.has_prompt_writer():
                super().emit(record)
                return
            terminal.write_above(self.format(record) + self.terminator)
        except Exception:
            self.handleError(record)


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

# A visual frontend is a separate process; restart it bounded, then give up
# quietly. A child that dies within the startup grace is not retried: the host
# cannot run it, so retrying three times only delays the fallback.
FRONTEND_MAX_RESTARTS = 3
FRONTEND_RESTART_DELAY_S = 2.0
FRONTEND_STARTUP_GRACE_S = 5.0


def frontend_plan(frontend: str, tui_ok: bool) -> tuple[str, str]:
    """Decide what to spawn and why, without spawning anything.

    Returns ``(kind, note)`` where kind is ``gui``, ``tui``, or ``none``. An
    explicit ``gui`` that cannot be shown degrades to the TUI when a terminal is
    usable, else to text-only, so the assistant always runs (REQ-FRONTEND-004).
    Pure, so the decision is unit-testable without a display or a terminal.
    """
    if frontend == FRONTEND_GUI:
        if gui_available():
            return FRONTEND_GUI, ""
        if tui_ok:
            return FRONTEND_TUI, "no display server; using the terminal UI"
        return FRONTEND_NONE, "no display server and no usable terminal; text only"
    if frontend == FRONTEND_TUI:
        if tui_ok:
            return FRONTEND_TUI, ""
        return FRONTEND_NONE, "no usable terminal; text only"
    return FRONTEND_NONE, ""


def frontend_inherits_terminal(kind: str) -> bool:
    """Whether a frontend child must inherit this process's stdin/stdout.

    The TUI draws on the terminal, so a piped stdout makes it report "not a
    terminal" and exit. The GUI orb opens its own window and does not touch the
    terminal, so its output is discarded.
    """
    return kind == FRONTEND_TUI


def import_module_class(module_path: str, class_name: str):
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class AssistantRunner:
    def __init__(self, config_path: str = "config.yaml", config_overrides: dict | None = None,
                 display_choice: str | None = None):
        self.config = load_config(config_path)
        if config_overrides:
            apply_overrides(self.config, config_overrides)
        self._config_path = config_path
        self._display_choice = display_choice
        self.bus = MessageBus()
        self.modules: dict[str, Any] = {}
        self.remote_bus: RemoteBus | None = None
        self._shutdown_event = asyncio.Event()
        self._frontend: str = FRONTEND_NONE
        self._frontend_process = None
        self._frontend_restarts = 0
        self._frontend_spawning = False
        # Bumped on every spawn request. A watcher only owns the tty and the
        # console flag while its generation is current, so a replaced child
        # cannot tear down its successor's terminal.
        self._frontend_generation = 0
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
        await self._maybe_start_frontend()

        # Commands from a frontend (TUI) arrive over the remote bus.
        self.bus.subscribe(topics.COMMAND_ASSISTANT_SHUTDOWN,
                           self._handle_shutdown_command)
        self.bus.subscribe(topics.COMMAND_FRONTEND_OPEN,
                           self._handle_frontend_open)

        # Wait for shutdown
        await self._shutdown_event.wait()

    def _handle_shutdown_command(self, topic: str, payload: dict) -> None:
        """End the whole assistant, the same path as SIGINT. Never raises."""
        logger.info("Shutdown requested by a frontend")
        self._shutdown_event.set()

    def _handle_frontend_open(self, topic: str, payload: dict) -> None:
        """Open a frontend on request. Called synchronously from bus.publish."""
        kind = payload.get("kind")
        if kind not in (FRONTEND_TUI, FRONTEND_GUI):
            logger.warning("Ignoring frontend open with unknown kind: %r", kind)
            return
        if self._frontend_spawning:
            # A spawn is already in flight; the process is not assigned yet, so
            # the process check alone would let a second request through.
            logger.info("A frontend is already opening; ignoring %s request", kind)
            return
        proc = self._frontend_process
        if proc is not None and proc.returncode is None:
            logger.info("A frontend is already open; ignoring %s request", kind)
            return
        asyncio.ensure_future(self._open_frontend(kind))

    async def _maybe_start_frontend(self) -> None:
        """Spawn the chosen visual frontend, if any.

        Text (the console) and audio always run; this only starts the extra
        visual shell (ADR-0017). A frontend failure must never stop the
        assistant, so every path here degrades (REQ-CONSOLE-001).
        """
        frontend = resolve_frontend(self.config, cli_choice=self._display_choice)
        tui_ok, _ = tui_available()
        kind, note = frontend_plan(frontend, tui_ok)
        if note:
            logger.warning("Frontend %r: %s", frontend, note)
        self._frontend = kind
        if kind in (FRONTEND_GUI, FRONTEND_TUI):
            await self._open_frontend(kind)

    async def _open_frontend(self, kind: str) -> None:
        """Open one explicit frontend kind, shared by startup and /tui //gui.

        Degrades instead of failing: a missing PySide6 falls back to the TUI,
        and an unusable terminal to text only, so the assistant always runs.
        The in-flight flag and the generation are set before the first await,
        so a second request cannot slip past while the process is unassigned
        and a replaced child's watcher cannot release the new child's tty.
        """
        if self._frontend_spawning:
            logger.info("A frontend is already opening; ignoring %s request", kind)
            return
        self._frontend_spawning = True
        self._frontend_generation += 1
        generation = self._frontend_generation
        try:
            await self._do_open_frontend(kind, generation)
        finally:
            self._frontend_spawning = False

    async def _do_open_frontend(self, kind: str, generation: int) -> None:
        if kind == FRONTEND_GUI and not self._pyside_available():
            logger.warning(
                "PySide6 is not installed; not starting the orb. "
                "Install it with: pip install 'aiassistant[ui]'"
            )
            kind = FRONTEND_TUI
        console = self.modules.get("console")
        if kind == FRONTEND_TUI:
            tui_ok, reason = tui_available()
            if not tui_ok:
                logger.warning("Terminal UI unavailable: %s", reason)
                self._frontend = FRONTEND_NONE
                return
            # The TUI owns the tty, so yield it before the child starts. A spawn
            # failure resumes it again in _spawn_frontend.
            if console is not None:
                console.suspend_terminal()
        argv = ("aiassistant.orb",) if kind == FRONTEND_GUI else ("aiassistant.tui",)
        if await self._spawn_frontend(kind, argv, initial=True):
            self._frontend = kind
            if console is not None:
                console.frontend_started(kind)
            asyncio.ensure_future(self._watch_frontend(kind, generation))

    @staticmethod
    def _pyside_available() -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("PySide6") is not None
        except Exception:
            return False

    async def _spawn_frontend(self, kind: str, argv: tuple[str, ...], *, initial: bool) -> bool:
        """Spawn a frontend child. Returns False if it could not be started.

        Only the initial spawn resets the restart counter; a respawn from
        ``_watch_frontend`` keeps it, so the restart budget is real.
        """
        try:
            if frontend_inherits_terminal(kind):
                self._frontend_process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", *argv, "-c", self._config_path,
                )
            else:
                self._frontend_process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", *argv, "-c", self._config_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
        except Exception as exc:
            logger.warning("Could not start the %s frontend: %s", kind, exc)
            self._frontend = FRONTEND_NONE
            self._release_terminal(kind)
            return False
        if initial:
            self._frontend_restarts = 0
        logger.info("%s started (pid=%s)", kind, self._frontend_process.pid)
        return True

    async def _watch_frontend(self, kind: str, generation: int) -> None:
        """Supervise a frontend child. A crash changes only the UI.

        The sole owner of respawns, so the restart budget holds and no second
        watcher can spawn a duplicate process. A clean exit (code 0) means the
        user closed the UI, so it is not a crash and is not respawned. A child
        that dies within the startup grace cannot run on this host, so it is not
        retried — retrying only delays the fallback.

        A watcher only acts while its generation is current: a replacement
        frontend bumps the generation, and the old watcher then returns without
        releasing the tty or clearing the console flag, which would tear down
        the successor's terminal.
        """
        proc = self._frontend_process
        started = asyncio.get_running_loop().time()
        while proc is not None:
            code = await proc.wait()
            alive_for = asyncio.get_running_loop().time() - started
            if self._shutting_down or generation != self._frontend_generation:
                return
            if code == 0:
                logger.info("%s closed by the user", kind)
                self._frontend = FRONTEND_NONE
                self._release_terminal(kind)
                return
            logger.warning("%s exited (code=%s)", kind, code)
            if alive_for < FRONTEND_STARTUP_GRACE_S:
                logger.error(
                    "%s failed to start; not retrying. Text mode continues.",
                    kind,
                )
                self._frontend = FRONTEND_NONE
                self._release_terminal(kind)
                return
            self._frontend_restarts += 1
            if self._frontend_restarts > FRONTEND_MAX_RESTARTS:
                logger.error("%s failed %d times; not restarting.", kind, self._frontend_restarts)
                self._release_terminal(kind)
                return
            await asyncio.sleep(FRONTEND_RESTART_DELAY_S)
            argv = ("aiassistant.orb",) if kind == FRONTEND_GUI else ("aiassistant.tui",)
            if not await self._spawn_frontend(kind, argv, initial=False):
                return
            proc = self._frontend_process
            started = asyncio.get_running_loop().time()

    def _release_terminal(self, kind: str) -> None:
        """Give the tty back to the console after a TUI child exits."""
        console = self.modules.get("console")
        if console is not None:
            console.frontend_stopped()
        if kind != FRONTEND_TUI:
            return
        if console is not None:
            console.resume_terminal()

    async def _stop_frontend(self) -> None:
        proc = self._frontend_process
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        except Exception:
            logger.debug("stopping the frontend raised", exc_info=True)

    async def shutdown(self):
        logger.info("Shutting down...")
        self._shutting_down = True
        # Cancel any in-flight turn before tearing modules down, so no task is
        # left holding a provider call or waiting on the bus.
        await self._stop_frontend()
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
                        metavar="PATH", help="Local config file (default: config.yaml; optional)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging (default: warnings only)")
    parser.add_argument("--frontend", choices=("gui", "tui", "none", "auto"),
                        default="auto",
                        help="Visual shell: gui (orb window), tui (terminal orb), "
                             "none (text only), auto (default: gui when a display "
                             "is available). Text and audio always run.")
    parser.add_argument("--mode", choices=("console", "audio", "ui", "orb", "tui",
                                           "gui", "none", "auto"), default=None,
                        help=argparse.SUPPRESS)  # deprecated alias for --frontend
    parser.add_argument("--audio", action="store_true",
                        help="Self-hosted LAN Whisper ASR (no api key), edge-tts")
    parser.add_argument("--offline", action="store_true",
                        help="Offline voice preset (faster-whisper ASR, text TTS)")
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

    handler = PromptAwareHandler()
    handler.setFormatter(ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        handlers=[handler],
    )

    # `--frontend` selects the visual shell. `--mode` is the deprecated alias
    # that also carried the `audio` voice preset; that preset now lives on
    # `--audio` only. The frontend choice is passed separately from the config
    # overrides so it outranks the environment and the config file, matching the
    # documented precedence (REQ-CFG-002).
    requested = args.frontend if args.frontend != "auto" else None
    if args.mode is not None and requested is None:
        logger.warning("--mode is deprecated; use --frontend")
        requested = None if args.mode == "audio" else args.mode

    self_hosted = args.audio or args.mode == "audio"
    if self_hosted and args.offline:
        parser.error("--audio and --offline are mutually exclusive")

    overrides = {}
    if self_hosted:
        # The self-hosted preset is a documented value set materialized into
        # per-stage keys; there is no separate "preset" switch (ADR-0018).
        overrides["voice.asr.backend"] = "whisper_server"
        overrides["voice.tts.backend"] = "edge_tts"
    elif args.offline:
        overrides["voice.asr.backend"] = "faster_whisper"
        overrides["voice.tts.backend"] = "text"

    runner = AssistantRunner(
        args.config,
        config_overrides=overrides if overrides else None,
        display_choice=requested,
    )

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
