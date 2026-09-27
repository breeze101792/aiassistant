import asyncio
import logging
import os
import readline
import signal
import sys

from aiassistant.base import BaseModule

logger = logging.getLogger(__name__)

HISTORY_FILE = ".config/aiassistant/history"
HISTORY_MAX = 1000

# Poll interval for stdin readability when no tty reader is available.
_POLL_INTERVAL_S = 0.2

# Returned by the poll helper when no complete line is ready yet.
_NO_LINE = object()


class ConsoleModule(BaseModule):
    """Terminal interface — reads stdin, prints response.text to stdout."""

    module_name = "console"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        console_cfg = config.get("console", {})
        self.prompt = console_cfg.get("prompt", "> ")
        self._running = False
        self._show_thinking = False
        self._read_task: asyncio.Task | None = None
        self._reader_added = False

    async def setup(self) -> bool:
        logger.info("CLI setup complete")
        return True

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("response.text", self._handle_response)
        self.bus.subscribe("status.ears.listening", self._handle_listening)
        self.bus.subscribe("status.ears.processing", self._handle_processing)
        self.bus.subscribe("status.ears.transcribed", self._handle_transcribed)
        self.bus.subscribe("status.ears.error", self._handle_error)
        self.bus.subscribe("status.mouth.error", self._handle_error)
        self.bus.subscribe("status.assistant.ready", self._handle_ready)

        readline.set_completer(self._complete)
        if "libedit" in (readline.__doc__ or ""):
            readline.parse_and_bind("bind -s ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass

        logger.info("CLI started — reading stdin")
        self._read_task = asyncio.ensure_future(self._read_loop())

    async def stop(self) -> None:
        self._running = False
        # Cancel the reader rather than waiting for it. It may be parked on a
        # blocking stdin read, and waiting would stall shutdown — which is why
        # Ctrl+C used to hang (see _read_loop).
        task = self._read_task
        self._read_task = None
        self._remove_reader()
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            readline.set_history_length(HISTORY_MAX)
            readline.write_history_file(HISTORY_FILE)
        except Exception:
            pass
        logger.info("CLI stopped")

    async def health(self) -> dict:
        return {"status": "ok" if self._running else "stopped"}

    # ── Stdin reading ────────────────────────────────────────

    def _remove_reader(self) -> None:
        if not self._reader_added:
            return
        try:
            asyncio.get_running_loop().remove_reader(sys.stdin.fileno())
        except (RuntimeError, ValueError, OSError):
            pass
        self._reader_added = False

    async def _read_loop(self) -> None:
        """Read lines without ever blocking loop shutdown.

        The previous implementation ran ``input()`` in the default executor.
        That call blocks until a line arrives, and ``asyncio.run`` waits for the
        default executor to finish at shutdown — so Ctrl+C set the shutdown
        event and then hung forever. Here the read is cancellable instead:

        * On a tty, the loop registers a reader on stdin, so a line arrives as a
          callback and nothing blocks.
        * Otherwise (a pipe or a redirected file), a short non-blocking poll is
          used, which also lets an EOF end the loop promptly.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_stdin_ready() -> None:
            # Called by the loop when stdin is readable. A readline() here is
            # safe: it only runs when a full line is already available.
            line = sys.stdin.readline()
            queue.put_nowait(line)

        try:
            if sys.stdin.isatty():
                loop.add_reader(sys.stdin.fileno(), on_stdin_ready)
                self._reader_added = True
        except (ValueError, OSError, NotImplementedError):
            self._reader_added = False

        prompt_shown = False
        try:
            while self._running:
                if not prompt_shown:
                    print(self.prompt, end="", flush=True)
                    prompt_shown = True

                if self._reader_added:
                    line = await queue.get()
                else:
                    line = await self._poll_stdin()
                    if line is _NO_LINE:
                        continue

                if line == "":  # EOF
                    logger.info("stdin closed")
                    break

                print("\r\x1b[K", end="")
                prompt_shown = False
                if not await self._handle_line(line.strip()):
                    break
        except asyncio.CancelledError:
            raise
        finally:
            self._remove_reader()

    async def _poll_stdin(self) -> str:
        """Non-blocking read for a non-tty stdin, yielding to the loop."""
        import select

        await asyncio.sleep(_POLL_INTERVAL_S)
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
        except (ValueError, OSError):
            return _NO_LINE
        if not ready:
            return _NO_LINE
        # A full line is available, so readline() will not block.
        return sys.stdin.readline()

    async def _handle_line(self, line: str) -> bool:
        """Handle one input line. Returns False to end the read loop."""
        if not line:
            return True
        readline.add_history(line)

        if line == "/exit":
            logger.info("Exit command received")
            self._running = False
            signal.raise_signal(signal.SIGINT)
            return False
        if line == "/help":
            self._print_help()
            return True
        if line == "/status":
            self._print_status()
            return True
        if line.startswith("/log"):
            self._set_log_level(line)
            return True
        if line == "/thinking":
            self._show_thinking = not self._show_thinking
            state = "ON" if self._show_thinking else "OFF"
            print(f"Thinking display: {state}")
            return True
        if line == "/clear":
            print("\033[2J\033[H", end="")
            return True
        if line.startswith("/"):
            print(f"Unknown command: {line}")
            self._print_help()
            return True

        print("Thinking...", end="", flush=True)
        self.bus.user_input(line)
        return True

    async def _handle_response(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        thinking = payload.get("thinking")
        print(f"\r\x1b[KAssistant: {text}")
        if self._show_thinking and thinking:
            print(f"\033[90m  [{thinking[:200]}]\033[0m")
        print(f"\n{self.prompt}", end="", flush=True)

    async def _handle_listening(self, topic: str, payload: dict) -> None:
        print(f"\r\x1b[K\033[33m● Listening...\033[0m", end="", flush=True)

    async def _handle_processing(self, topic: str, payload: dict) -> None:
        print(f"\r\x1b[K\033[36m● Processing...\033[0m", end="", flush=True)

    async def _handle_transcribed(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        print(f"\r\x1b[K\033[32mYou: {text}\033[0m")
        print(f"{self.prompt}", end="", flush=True)

    async def _handle_ready(self, topic: str, payload: dict) -> None:
        print("Ready. Type /help for commands.\n")

    async def _handle_error(self, topic: str, payload: dict) -> None:
        print(f"\n[!] Error ({topic}): {payload.get('error', 'unknown')}\n{self.prompt}", end="", flush=True)

    def _set_log_level(self, line: str):
        arg = line[4:].strip()
        levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "off": logging.CRITICAL,
        }
        if not arg:
            current = logging.getLevelName(logging.root.level)
            print(f"Log level: {current.lower()}")
            print(f"Usage: /log [debug|info|warning|error|off]")
            return
        level = levels.get(arg.lower())
        if level is None:
            print(f"Unknown level: {arg}")
            print(f"Usage: /log [debug|info|warning|error|off]")
            return
        logging.root.setLevel(level)
        print(f"Log level: {arg.lower()}")

    _commands = ["/exit", "/help", "/status", "/log", "/thinking", "/clear"]
    _log_levels = ["debug", "info", "warning", "error", "off"]

    def _complete(self, text: str, state: int) -> str | None:
        buf = readline.get_line_buffer()
        if buf.startswith("/log ") and buf.index(" ") == 4:
            # Complete /log sub-arguments
            prefix = buf[5:]
            matches = [l for l in self._log_levels if l.startswith(text)]
        elif buf.startswith("/"):
            matches = [c for c in self._commands if c.startswith(text)]
        else:
            return None
        return matches[state] if state < len(matches) else None

    def _print_help(self):
        print()
        print("Commands:")
        print("  /exit      Quit the assistant")
        print("  /help      Show this help")
        print("  /status    Show module status")
        print("  /log [debug|info|warning|error|off]  Show or set log level")
        print("  /clear     Clear the terminal")
        print()
        print("Hotwords: say a hotword to activate audio input, then speak your message.")
        print()

    def _print_status(self):
        modules = self.bus.registry.list_all()
        if not modules:
            print("\nNo modules registered.")
            return
        print()
        print(f"{'Module':<12} {'Status':<12} {'Remote':<8}")
        print("-" * 32)
        for name, info in sorted(modules.items()):
            status = info.get("status", "unknown")
            remote = "yes" if info.get("remote") else "no"
            print(f"{name:<12} {status:<12} {remote:<8}")
        print()
