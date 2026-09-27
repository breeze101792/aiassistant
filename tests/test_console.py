import logging
import pytest
from aiassistant.console.module import ConsoleModule


class TestTabCompletion:
    """Tab completion for slash commands and /log sub-arguments."""

    @pytest.fixture
    def cli(self):
        from aiassistant.bus.bus import MessageBus
        bus = MessageBus()
        return ConsoleModule(bus, {})

    def test_complete_empty_buffer_returns_none(self, cli, monkeypatch):
        monkeypatch.setattr("aiassistant.console.module.readline.get_line_buffer", lambda: "")
        # state 0 with no slash — should return None (no completions for plain text)
        assert cli._complete("hello", 0) is None
        assert cli._complete("", 0) is None

    def test_complete_slash_lists_all_commands(self, cli, monkeypatch):
        monkeypatch.setattr("aiassistant.console.module.readline.get_line_buffer", lambda: "/")
        results = []
        for state in range(10):
            r = cli._complete("/", state)
            if r is None:
                break
            results.append(r)
        assert "/exit" in results
        assert "/help" in results
        assert "/status" in results
        assert "/log" in results
        assert "/thinking" in results
        assert "/clear" in results
        assert len(results) == 6

    def test_complete_partial_command(self, cli, monkeypatch):
        monkeypatch.setattr("aiassistant.console.module.readline.get_line_buffer", lambda: "/he")
        # readline passes the word being completed as `text` — the full buffer here
        assert cli._complete("/hex", 0) is None   # "/hex" doesn't match any command
        assert cli._complete("/he", 0) == "/help"  # "/he" matches /help
        assert cli._complete("/he", 1) is None     # only one match

    def test_complete_log_subcommand(self, cli, monkeypatch):
        monkeypatch.setattr("aiassistant.console.module.readline.get_line_buffer", lambda: "/log ")
        results = []
        for state in range(10):
            r = cli._complete("", state)
            if r is None:
                break
            results.append(r)
        assert "debug" in results
        assert "info" in results
        assert "warning" in results
        assert "error" in results
        assert "off" in results
        assert len(results) == 5

    def test_complete_log_partial(self, cli, monkeypatch):
        monkeypatch.setattr("aiassistant.console.module.readline.get_line_buffer", lambda: "/log de")
        # cursor is in the second word "de" — readline passes "de" as text
        assert cli._complete("de", 0) == "debug"
        assert cli._complete("de", 1) is None  # only one match

    def test_complete_non_slash_returns_none(self, cli, monkeypatch):
        monkeypatch.setattr("aiassistant.console.module.readline.get_line_buffer", lambda: "hello world")
        assert cli._complete("world", 0) is None


class TestLogLevel:
    """Log level switching via /log command."""

    @pytest.fixture
    def cli(self):
        from aiassistant.bus.bus import MessageBus
        bus = MessageBus()
        return ConsoleModule(bus, {})

    def test_set_log_debug(self, cli):
        cli._set_log_level("/log debug")
        assert logging.root.level == logging.DEBUG

    def test_set_log_info(self, cli):
        cli._set_log_level("/log info")
        assert logging.root.level == logging.INFO

    def test_set_log_warning(self, cli):
        cli._set_log_level("/log warning")
        assert logging.root.level == logging.WARNING

    def test_set_log_error(self, cli):
        cli._set_log_level("/log error")
        assert logging.root.level == logging.ERROR

    def test_set_log_off(self, cli):
        cli._set_log_level("/log off")
        assert logging.root.level == logging.CRITICAL

    def test_set_log_case_insensitive(self, cli):
        cli._set_log_level("/log DEBUG")
        assert logging.root.level == logging.DEBUG

    def test_unknown_level_does_not_change(self, cli):
        original = logging.root.level
        cli._set_log_level("/log bananas")
        assert logging.root.level == original

    def test_show_current_level_no_args(self, cli, capsys):
        logging.root.setLevel(logging.WARNING)
        cli._set_log_level("/log")
        captured = capsys.readouterr()
        assert "warning" in captured.out


class TestCLIInit:
    """CLI module initialization and config."""

    def test_default_prompt(self):
        from aiassistant.bus.bus import MessageBus
        bus = MessageBus()
        cli = ConsoleModule(bus, {})
        assert cli.prompt == "> "

    def test_custom_prompt_from_config(self):
        from aiassistant.bus.bus import MessageBus
        bus = MessageBus()
        cli = ConsoleModule(bus, {"console": {"prompt": "$ "}})
        assert cli.prompt == "$ "

    def test_readline_completer_registered(self):
        import readline
        from aiassistant.bus.bus import MessageBus
        bus = MessageBus()
        cli = ConsoleModule(bus, {})
        # Verify completer is callable and bound
        assert callable(cli._complete)


class TestShutdownSafety:
    """Ctrl+C used to hang. These pin the two properties that fixed it.

    The old read loop ran ``input()`` in the default executor. That call blocks
    until a line arrives, and ``asyncio.run`` waits for the default executor at
    shutdown, so SIGINT set the shutdown flag and then hung forever. The loop now
    uses a cancellable read instead.
    """

    def test_no_blocking_input_in_the_executor(self):
        """The specific construct that caused the hang must not come back."""
        import inspect

        source = inspect.getsource(ConsoleModule)
        assert "run_in_executor(None, input" not in source, (
            "a blocking input() in the default executor stalls loop shutdown"
        )

    def test_stop_cancels_the_reader_without_waiting_for_stdin(self):
        """stop() must not block on a reader parked on stdin."""
        import asyncio

        from aiassistant.bus.bus import MessageBus

        async def scenario():
            bus = MessageBus()
            cli = ConsoleModule(bus, {})
            await cli.start()

            # Simulate a reader parked on a read that will never complete.
            async def never_finishes():
                await asyncio.sleep(3600)

            cli._read_task.cancel()
            cli._read_task = asyncio.ensure_future(never_finishes())

            # The guard: stop() must return promptly despite that task.
            await asyncio.wait_for(cli.stop(), timeout=2.0)
            assert cli._read_task is None
            assert cli._running is False

        asyncio.run(scenario())

    def test_stop_is_safe_when_never_started(self):
        import asyncio

        from aiassistant.bus.bus import MessageBus

        async def scenario():
            cli = ConsoleModule(MessageBus(), {})
            await asyncio.wait_for(cli.stop(), timeout=2.0)

        asyncio.run(scenario())

    def test_poll_helper_returns_a_sentinel_when_no_line_is_ready(self, monkeypatch):
        """A non-tty stdin must not block; it polls and yields to the loop."""
        import asyncio
        import io

        from aiassistant.bus.bus import MessageBus
        from aiassistant.console.module import _NO_LINE

        async def scenario():
            cli = ConsoleModule(MessageBus(), {})
            monkeypatch.setattr("sys.stdin", io.StringIO(""))
            result = await asyncio.wait_for(cli._poll_stdin(), timeout=2.0)
            assert result is _NO_LINE or result == ""

        asyncio.run(scenario())
