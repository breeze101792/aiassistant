import asyncio
import logging
import os
import readline
import signal
import sys

from aiassistant.base import BaseModule
from aiassistant.bus import topics

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
        # When a TUI owns the terminal, the console must not read stdin or
        # print (REQ-FRONTEND-009). Defaults True so standalone use and tests
        # are unchanged.
        self._owns_terminal = True
        self._streaming = False

    async def setup(self) -> bool:
        logger.info("Console setup complete")
        return True

    async def start(self) -> None:
        self._running = True
        # Text is always available (ADR-0017), so subscribe to the live topics.
        # These were previously the as-built status.ears.* names, which nothing
        # publishes, so the status handlers never ran.
        self.bus.subscribe(topics.AGENT_FINAL, self._handle_final)
        self.bus.subscribe(topics.AGENT_DELTA, self._handle_delta)
        self.bus.subscribe(topics.VOICE_STATE, self._handle_voice_state)
        self.bus.subscribe(topics.VOICE_TRANSCRIBED, self._handle_transcribed)
        self.bus.subscribe(topics.AGENT_TURN_ERROR, self._handle_error)
        self.bus.subscribe(topics.STATUS_ASSISTANT_READY, self._handle_ready)

        readline.set_completer(self._complete)
        if "libedit" in (readline.__doc__ or ""):
            readline.parse_and_bind("bind -s ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass

        logger.info("Console started — reading stdin")
        self._start_reader()

    def _start_reader(self) -> None:
        if self._read_task is None or self._read_task.done():
            self._read_task = asyncio.ensure_future(self._read_loop())

    def suspend_terminal(self) -> None:
        """Yield the tty to another frontend (the TUI). Idempotent."""
        if not self._owns_terminal:
            return
        self._owns_terminal = False
        task = self._read_task
        self._read_task = None
        self._remove_reader()
        if task and not task.done():
            task.cancel()
        logger.info("Console terminal I/O suspended")

    def resume_terminal(self) -> None:
        """Reclaim the tty after the other frontend exits."""
        if self._owns_terminal:
            return
        self._owns_terminal = True
        self._start_reader()
        logger.info("Console terminal I/O resumed")
        self._render(f"\n{self.prompt}")

    def _render(self, text: str) -> None:
        """Write to the terminal unless another frontend owns it."""
        if self._owns_terminal:
            print(text, end="", flush=True)

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
        logger.info("Console stopped")

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
            # Only clean up if this task still owns the reader. A cancelled loop
            # may finish after resume_terminal() started a replacement; removing
            # the reader then would leave the console with no stdin reader.
            if self._read_task is asyncio.current_task():
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

        self._render("Thinking...")
        self.bus.user_input(line)
        return True

    async def _handle_delta(self, topic: str, payload: dict) -> None:
        """Render assistant text incrementally (REQ-CONSOLE-005).

        Thinking deltas are not transcript text. The first text delta settles
        the "Thinking..." marker and opens the assistant line; later deltas
        append in place.
        """
        if payload.get("kind", "text") == "thinking":
            return
        text = payload.get("text", "")
        if not text:
            return
        if not self._streaming:
            self._streaming = True
            self._render(f"\r\x1b[KAssistant: {text}")
        else:
            self._render(text)

    async def _handle_final(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        thinking = payload.get("thinking")
        # Settle the authoritative text on the line the deltas were streaming to.
        self._render(f"\r\x1b[KAssistant: {text}")
        self._streaming = False
        if self._show_thinking and thinking:
            self._render(f"\n\033[90m  [{thinking[:200]}]\033[0m")
        self._render(f"\n{self.prompt}")

    async def _handle_voice_state(self, topic: str, payload: dict) -> None:
        state = payload.get("state", "")
        if state == "listening":
            self._render("\r\x1b[K\033[33m● Listening...\033[0m")
        elif state in ("transcribing", "thinking"):
            self._render("\r\x1b[K\033[36m● Processing...\033[0m")

    async def _handle_transcribed(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        self._render(f"\r\x1b[K\033[32mYou: {text}\033[0m\n{self.prompt}")

    async def _handle_ready(self, topic: str, payload: dict) -> None:
        self._render("Ready. Type /help for commands.\n")

    async def _handle_error(self, topic: str, payload: dict) -> None:
        message = payload.get("message") or payload.get("error", "unknown")
        self._streaming = False
        self._render(f"\n[!] Error ({topic}): {message}\n{self.prompt}")

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
