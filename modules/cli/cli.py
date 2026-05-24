import asyncio
import logging
import os
import readline
import signal

from modules.base import BaseModule

logger = logging.getLogger(__name__)

HISTORY_FILE = ".config/aiassistant/history"
HISTORY_MAX = 1000


class CLIModule(BaseModule):
    """Terminal interface — reads stdin, prints response.text to stdout."""

    module_name = "cli"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        cli_cfg = config.get("cli", {})
        self.prompt = cli_cfg.get("prompt", "> ")
        self._running = False

    async def setup(self) -> bool:
        logger.info("CLI setup complete")
        return True

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("response.text", self._handle_response)
        self.bus.subscribe("status.ears.error", self._handle_error)
        self.bus.subscribe("status.mouth.error", self._handle_error)
        self.bus.subscribe("status.assistant.ready", self._handle_ready)

        readline.set_completer(self._complete)
        if "libedit" in readline.__doc__:
            readline.parse_and_bind("bind -s ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass

        logger.info("CLI started — reading stdin")
        asyncio.ensure_future(self._read_loop())

    async def stop(self) -> None:
        self._running = False
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            readline.set_history_length(HISTORY_MAX)
            readline.write_history_file(HISTORY_FILE)
        except Exception:
            pass
        logger.info("CLI stopped")

    async def health(self) -> dict:
        return {"status": "ok" if self._running else "stopped"}

    async def _read_loop(self):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                line = await loop.run_in_executor(None, input, self.prompt)
                line = line.strip()
                if not line:
                    continue
                readline.add_history(line)

                if line == "/exit":
                    logger.info("Exit command received")
                    self._running = False
                    signal.raise_signal(signal.SIGINT)
                    break
                elif line == "/help":
                    self._print_help()
                    continue
                elif line == "/status":
                    self._print_status()
                    continue
                elif line.startswith("/log"):
                    self._set_log_level(line)
                    continue
                elif line == "/clear":
                    print("\033[2J\033[H", end="")
                    continue
                elif line.startswith("/"):
                    print(f"Unknown command: {line}")
                    self._print_help()
                    continue

                print("Thinking...", end="", flush=True)
                self.bus.user_input(line)
            except EOFError:
                break
            except Exception as e:
                logger.error(f"CLI read error: {e}")

    async def _handle_response(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        thinking = payload.get("thinking")
        print(f"\r\x1b[KAssistant: {text}")
        if logging.root.level <= logging.DEBUG and thinking:
            print(f"  [thinking: {thinking}]")
        print(f"\n{self.prompt}", end="", flush=True)

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

    _commands = ["/exit", "/help", "/status", "/log", "/clear"]
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
