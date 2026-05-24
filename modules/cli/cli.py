import asyncio
import logging
import signal

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class CLIModule(BaseModule):
    """Terminal interface — reads stdin, prints response.text to stdout."""

    module_name = "cli"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        cli_cfg = config.get("cli", {})
        self.prompt = cli_cfg.get("prompt", "> ")
        self.verbose = cli_cfg.get("verbose", False)
        self._running = False

    async def setup(self) -> bool:
        logger.info("CLI setup complete")
        return True

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("response.text", self._handle_response)
        if self.verbose:
            self.bus.subscribe("response.thinking", self._handle_thinking)
        self.bus.subscribe("status.ears.error", self._handle_error)
        self.bus.subscribe("status.mouth.error", self._handle_error)

        logger.info("CLI started — reading stdin")
        asyncio.ensure_future(self._read_loop())

    async def stop(self) -> None:
        self._running = False
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
                elif line.startswith("/verbose"):
                    arg = line[8:].strip()
                    if arg == "on":
                        self.verbose = True
                    elif arg == "off":
                        self.verbose = False
                    elif arg == "":
                        self.verbose = not self.verbose
                    else:
                        print(f"Usage: /verbose [on|off]")
                        continue
                    print(f"Verbose mode: {'on' if self.verbose else 'off'}")
                    continue
                elif line == "/clear":
                    print("\033[2J\033[H", end="")
                    continue

                self.bus.user_input(line)
            except EOFError:
                break
            except Exception as e:
                logger.error(f"CLI read error: {e}")

    async def _handle_response(self, topic: str, payload: dict) -> None:
        text = payload.get("text", "")
        thinking = payload.get("thinking")
        print(f"\nAssistant: {text}")
        if self.verbose and thinking:
            print(f"  [thinking: {thinking}]")
        print(f"\n{self.prompt}", end="", flush=True)

    async def _handle_thinking(self, topic: str, payload: dict) -> None:
        if self.verbose:
            print(f"  [thinking: {payload.get('text', '')}]")

    async def _handle_error(self, topic: str, payload: dict) -> None:
        print(f"\n[!] Error ({topic}): {payload.get('error', 'unknown')}\n{self.prompt}", end="", flush=True)

    def _print_help(self):
        print()
        print("Commands:")
        print("  /exit      Quit the assistant")
        print("  /help      Show this help")
        print("  /status    Show module status")
        print("  /verbose [on|off]  Toggle or set verbose mode (show thinking)")
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
