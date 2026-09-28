import asyncio
import logging
import os
import readline
import re
import shutil
import signal
import sys
import unicodedata

from aiassistant.base import BaseModule
from aiassistant.bus import topics
from aiassistant import terminal

logger = logging.getLogger(__name__)

HISTORY_FILE = ".config/aiassistant/history"
HISTORY_MAX = 1000

# Poll interval for stdin readability when no tty reader is available.
_POLL_INTERVAL_S = 0.2

# Clear the current line before overwriting it (the prompt or a status line).
_CLEAR_LINE = "\r\x1b[K"

# The label that opens an assistant transcript line.
ASSISTANT_LABEL = "Assistant:"

# Terminal width when it cannot be measured (the conventional default).
_DEFAULT_COLUMNS = 80

# ANSI escape sequences, stripped to measure wrapped text by visible width.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

# Returned by the poll helper when no complete line is ready yet.
_NO_LINE = object()


def _display_width(text: str) -> int:
    """Terminal columns ``text`` occupies.

    A wide character (CJK, many emoji) takes two columns and a combining mark
    takes none, so the character count is not the display width. The persona
    matches the user's language, so a CJK answer is normal and a character
    count would understate the rows it wraps to.
    """
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


class ConsoleModule(BaseModule):
    """Terminal interface — reads stdin, prints response.text to stdout."""

    module_name = "console"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        console_cfg = config.get("console", {})
        self.prompt = console_cfg.get("prompt", "> ")
        # The wake phrases, so /help can name the one the user must actually
        # say instead of describing the mechanic in the abstract.
        self.hotwords = config.get("voice", {}).get("hotwords", [])
        self._running = False
        self._show_thinking = False
        self._read_task: asyncio.Task | None = None
        self._reader_added = False
        # When a TUI owns the terminal, the console must not read stdin or
        # print (REQ-FRONTEND-009). Defaults True so standalone use and tests
        # are unchanged.
        self._owns_terminal = True
        self._streaming = False
        # The text streamed so far and the label that opened the line, so the
        # final can tell whether the line is already correct and, if the model
        # revised, erase exactly the rows the stream occupied. Erasing only the
        # last row duplicates a wrapped answer (REQ-CONSOLE-009).
        self._streamed_text = ""
        self._stream_prefix = ""
        # Whether the prompt is currently on screen. The read loop draws it and
        # every async writer redraws it through `_emit`, so the console is the
        # single owner of the prompt line.
        self._prompt_shown = False

    async def setup(self) -> bool:
        logger.info("Console setup complete")
        return True

    async def start(self) -> None:
        self._running = True
        # The console owns the prompt line, so async output can be inserted
        # above it instead of colliding with it.
        terminal.set_prompt_writer(self._emit)
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
        self._clear_prompt()
        self._owns_terminal = False
        terminal.set_prompt_writer(None)
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
        self._show_prompt()

    def _render(self, text: str) -> None:
        """Write to the terminal unless another frontend owns it."""
        if self._owns_terminal:
            print(text, end="", flush=True)

    # ── Prompt ownership ─────────────────────────────────────

    def _emit(self, text: str) -> None:
        """Write output from an async writer (a handler, or the log handler).

        The prompt is erased first and redrawn afterwards, so the text lands on
        its own line and the prompt is never left glued to a banner or missing.
        This is the callback registered with `terminal.set_prompt_writer`.
        """
        if not self._owns_terminal:
            return
        if self._prompt_shown:
            # Erase the prompt, write the text on that line, then redraw below.
            print(_CLEAR_LINE + text, end="", flush=True)
            if not text.endswith("\n"):
                print()
            self._show_prompt()
            return
        print(text, end="", flush=True)
        if not text.endswith("\n"):
            print()

    def _show_prompt(self) -> None:
        """Draw the prompt at an empty line and mark it on screen."""
        if not self._owns_terminal:
            return
        print(self.prompt, end="", flush=True)
        self._prompt_shown = True

    def _clear_prompt(self) -> None:
        """Erase the on-screen prompt before writing a line of its own."""
        if self._prompt_shown:
            print(_CLEAR_LINE, end="", flush=True)
            self._prompt_shown = False

    async def stop(self) -> None:
        self._running = False
        # Release the prompt line so a later writer does not call into a stopped
        # console.
        terminal.set_prompt_writer(None)
        self._prompt_shown = False
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

        try:
            while self._running:
                if not self._prompt_shown:
                    self._show_prompt()

                if self._reader_added:
                    line = await queue.get()
                else:
                    line = await self._poll_stdin()
                    if line is _NO_LINE:
                        continue

                if line == "":  # EOF
                    logger.info("stdin closed")
                    break

                self._clear_prompt()
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

        # Echo the input only when the terminal is not already doing it. On a
        # tty the line is echoed at the prompt, so printing it again makes the
        # user read their own input twice (REQ-CONSOLE-011). A piped or
        # redirected run has no echo, so the transcript keeps the turn there.
        if not self._stdin_echoes():
            self._emit(f"\033[32mYou: {line}\033[0m")
        self.bus.user_input(line)
        return True

    @staticmethod
    def _stdin_echoes() -> bool:
        """Whether the terminal echoes typed input back to the screen."""
        try:
            return sys.stdin.isatty()
        except (ValueError, AttributeError):
            return False

    async def _handle_delta(self, topic: str, payload: dict) -> None:
        """Render assistant text incrementally (REQ-CONSOLE-005).

        The line is opened once and appended to in place; the prompt stays
        erased for the whole stream so later deltas cannot land after it. The
        text is accumulated so ``_handle_final`` can settle the line without
        reprinting it.

        Thinking is not transcript text. It goes to the debug log, never to the
        transcript, so a reasoning model cannot echo its scratchpad into the
        conversation.
        """
        text = payload.get("text", "")
        if payload.get("kind", "text") == "thinking":
            if text:
                logger.debug("thinking: %s", text)
            return
        if not text:
            return
        if not self._streaming:
            self._streaming = True
            self._clear_prompt()
            self._stream_prefix = f"{ASSISTANT_LABEL} "
            self._render(self._stream_prefix)
        self._streamed_text += text
        self._render(text)

    async def _handle_final(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        if self._streaming:
            if text == self._streamed_text:
                # The stream already rendered the authoritative text. Just end
                # the line: reprinting it would duplicate a wrapped answer.
                self._render("\n")
            else:
                # The model revised. Erase the rows the stream used and write
                # the final text once, so no partial text is left behind.
                self._erase_streamed_rows()
                self._render(f"{ASSISTANT_LABEL} {text}\n")
            self._streaming = False
            self._streamed_text = ""
            self._stream_prefix = ""
            self._show_thinking_note(payload)
            self._show_prompt()
            return
        # No deltas: `_emit` writes the line and redraws the prompt itself.
        self._emit(f"{ASSISTANT_LABEL} {text}")
        self._streaming = False
        self._show_thinking_note(payload)

    def _erase_streamed_rows(self) -> None:
        """Erase the physical rows the streamed line occupies.

        A streamed answer wraps, so the cursor sits on its last row. Moving up
        one row per line and clearing each removes the whole streamed block;
        clearing only the cursor row leaves the earlier rows and duplicates the
        answer when the final is written.
        """
        rows = self._wrapped_rows(self._stream_prefix + self._streamed_text)
        if rows > 1:
            self._render(f"\r\x1b[{rows - 1}A")
        # Clear each row from the bottom-most upward, ending back at column 0.
        self._render("\r\n".join("\x1b[2K" for _ in range(rows)))
        if rows > 1:
            self._render(f"\x1b[{rows - 1}A")
        self._render("\r")

    def _wrapped_rows(self, text: str) -> int:
        """How many terminal rows ``text`` occupies.

        Uses the display width, not the character count: a CJK or emoji
        character occupies two columns, so counting characters would understate
        the rows and leave the top of a wrapped block on screen.
        """
        columns = self._terminal_columns()
        width = _display_width(_ANSI_RE.sub("", text))
        if width <= 0:
            return 1
        return (width + columns - 1) // columns

    def _terminal_columns(self) -> int:
        """The terminal width, falling back to the conventional default."""
        try:
            columns = shutil.get_terminal_size(fallback=(_DEFAULT_COLUMNS, 24)).columns
        except (ValueError, OSError):
            return _DEFAULT_COLUMNS
        return columns if columns > 0 else _DEFAULT_COLUMNS

    def _show_thinking_note(self, payload: dict) -> None:
        """Optionally show a reasoning summary, only when /thinking is on.

        Off by default: the summary is diagnostic, so it is logged and shown
        only on request, never mixed into the answer.
        """
        thinking = payload.get("thinking")
        if not thinking:
            return
        logger.debug("thinking summary: %s", thinking[:200])
        if self._show_thinking:
            self._emit(f"\033[90m  [{thinking[:200]}]\033[0m")

    async def _handle_voice_state(self, topic: str, payload: dict) -> None:
        state = payload.get("state", "")
        if state == "listening":
            self._emit("\033[33m● Listening...\033[0m")
        elif state in ("transcribing", "thinking"):
            self._emit("\033[36m● Processing...\033[0m")

    async def _handle_transcribed(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        self._emit(f"\033[32mYou: {text}\033[0m")

    async def _handle_ready(self, topic: str, payload: dict) -> None:
        self._emit("Ready. Type /help for commands.")

    async def _handle_error(self, topic: str, payload: dict) -> None:
        message = payload.get("message") or payload.get("error", "unknown")
        self._streaming = False
        self._emit(f"[!] Error ({topic}): {message}")

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
        print(self._hotword_line())
        print()

    def _hotword_line(self) -> str:
        """The wake-phrase line for /help, naming the configured phrases.

        Printed from config, never hard-coded, so the help says the phrase the
        voice pipeline actually listens for. An empty list means the recognizer
        does not gate on a phrase, so the line says how input works instead.
        """
        phrases = [str(h) for h in (self.hotwords or []) if str(h).strip()]
        if not phrases:
            return ("Hotwords: none configured; audio input is not gated on a "
                    "wake phrase.")
        quoted = ", ".join(f'"{p}"' for p in phrases)
        return (f"Hotwords: say {quoted} to activate audio input, "
                f"then speak your message.")

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
