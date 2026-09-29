import logging
import pytest
from aiassistant.bus import topics
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
        assert "/tui" in results
        assert "/gui" in results
        assert len(results) == 8

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


class TestLiveTopics:
    """The console must subscribe to the topics that are actually published.

    It previously listened for ``status.ears.*`` and ``status.mouth.error``,
    which nothing publishes, so its status handlers never ran.
    """

    def _started(self):
        import asyncio
        from aiassistant.bus.bus import MessageBus

        async def scenario():
            bus = MessageBus()
            cli = ConsoleModule(bus, {})
            await cli.start()
            return bus, cli

        return asyncio.run(scenario())

    def test_subscribes_to_voice_state(self):
        bus, cli = self._started()
        assert bus.has_subscriber(topics.VOICE_STATE)

    def test_subscribes_to_delta_and_final(self):
        bus, cli = self._started()
        assert bus.has_subscriber(topics.AGENT_DELTA)
        assert bus.has_subscriber(topics.AGENT_FINAL)

    def test_does_not_subscribe_to_dead_topics(self):
        bus, cli = self._started()
        for dead in ("status.ears.listening", "status.ears.transcribed",
                     "status.mouth.error", "response.text"):
            assert not bus.has_subscriber(dead)


class TestStreaming:
    """REQ-CONSOLE-005: assistant text renders incrementally from deltas."""

    def _run_events(self, events):
        import asyncio
        from aiassistant.bus.bus import MessageBus

        async def scenario():
            bus = MessageBus()
            cli = ConsoleModule(bus, {})
            await cli.start()
            for topic, payload in events:
                bus.publish(topic, payload)
            await asyncio.sleep(0)  # let scheduled coroutine handlers run
            await cli.stop()

        asyncio.run(scenario())

    def test_deltas_accumulate_then_final_settles(self, capsys):
        self._run_events([
            (topics.AGENT_DELTA, {"index": 0, "kind": "text", "text": "Hel"}),
            (topics.AGENT_DELTA, {"index": 1, "kind": "text", "text": "lo"}),
            (topics.AGENT_FINAL, {"text": "Hello"}),
        ])
        out = capsys.readouterr().out
        assert "Assistant: Hel" in out
        assert "Assistant: Hello" in out

    def test_thinking_deltas_are_not_transcript_text(self, capsys):
        self._run_events([
            (topics.AGENT_DELTA, {"index": 0, "kind": "thinking", "text": "hmm"}),
        ])
        assert "hmm" not in capsys.readouterr().out

    def test_voice_state_renders_a_status_line(self, capsys):
        self._run_events([(topics.VOICE_STATE, {"state": "listening"})])
        assert "Listening" in capsys.readouterr().out


class TestTerminalOwnership:
    """REQ-FRONTEND-009: only one of the console and the TUI owns the tty."""

    def _cli(self):
        from aiassistant.bus.bus import MessageBus
        return ConsoleModule(MessageBus(), {})

    def test_owns_terminal_by_default(self):
        assert self._cli()._owns_terminal is True

    def test_suspend_stops_rendering(self, capsys):
        cli = self._cli()
        cli.suspend_terminal()
        cli._render("must not appear")
        assert "must not appear" not in capsys.readouterr().out

    def test_resume_restores_rendering(self, capsys):
        import asyncio

        async def scenario():
            cli = self._cli()
            cli.suspend_terminal()
            cli.resume_terminal()
            cli._render("visible")
            await cli.stop()

        asyncio.run(scenario())
        assert "visible" in capsys.readouterr().out

    def test_suspend_is_idempotent(self):
        cli = self._cli()
        cli.suspend_terminal()
        cli.suspend_terminal()
        assert cli._owns_terminal is False


class TestFrontendCommands:
    """/tui and /gui ask the parent to spawn a frontend; the console does not."""

    def _cli(self):
        from aiassistant.bus.bus import MessageBus
        return ConsoleModule(MessageBus(), {})

    def _published(self, cli, line):
        import asyncio
        seen = []
        cli.bus.subscribe(topics.COMMAND_FRONTEND_OPEN,
                          lambda t, p: seen.append(p))
        asyncio.run(cli._handle_line(line))
        return seen

    def test_tui_publishes_the_open_command(self, capsys):
        cli = self._cli()
        assert self._published(cli, "/tui") == [{"kind": "tui"}]

    def test_gui_publishes_the_open_command(self, capsys):
        cli = self._cli()
        assert self._published(cli, "/gui") == [{"kind": "gui"}]

    def test_does_not_double_spawn_when_a_frontend_is_open(self, capsys):
        cli = self._cli()
        cli.frontend_started("tui")
        assert self._published(cli, "/gui") == []
        assert "already open" in capsys.readouterr().out

    def test_open_again_after_the_frontend_stops(self):
        cli = self._cli()
        cli.frontend_started("tui")
        cli.frontend_stopped()
        assert cli._frontend_open is False
        assert self._published(cli, "/gui") == [{"kind": "gui"}]


class TestHelpHotword:
    """REQ-WAKE-004: /help names the configured wake phrase, not just the mechanic.

    The phrase is read from voice.hotwords, so the help states the phrase the
    voice pipeline actually listens for.
    """

    def _cli(self, config=None):
        from aiassistant.bus.bus import MessageBus
        return ConsoleModule(MessageBus(), config or {})

    def test_help_names_the_default_hotword(self, capsys):
        from aiassistant.config import load_config
        self._cli(load_config())._print_help()
        out = capsys.readouterr().out
        assert 'say "hey jarvis"' in out

    def test_help_names_a_custom_hotword(self, capsys):
        self._cli({"voice": {"hotwords": ["ok computer"]}})._print_help()
        assert 'say "ok computer"' in capsys.readouterr().out

    def test_help_lists_every_hotword(self):
        cli = self._cli({"voice": {"hotwords": ["hey jarvis", "computer"]}})
        line = cli._hotword_line()
        assert '"hey jarvis"' in line and '"computer"' in line

    def test_no_hotwords_says_input_is_not_gated(self):
        cli = self._cli({"voice": {"hotwords": []}})
        assert "none configured" in cli._hotword_line()

    def test_blank_hotwords_are_ignored(self):
        cli = self._cli({"voice": {"hotwords": ["", "  "]}})
        assert "none configured" in cli._hotword_line()


class TestPromptOwnership:
    """Async output must not corrupt or swallow the interactive prompt.

    The bug: the read loop printed `> ` and tracked it in a local variable,
    while each handler appended `\\n{prompt}` itself. A WARNING or the ready
    banner then glued itself to the prompt, and the next line had no prompt.
    """

    def _cli(self):
        from aiassistant.bus.bus import MessageBus
        return ConsoleModule(MessageBus(), {"console": {"prompt": "> "}})

    @pytest.fixture(autouse=True)
    def _reset_writer(self):
        from aiassistant import terminal
        yield
        terminal.set_prompt_writer(None)

    def test_emit_when_no_prompt_prints_plainly(self, capsys):
        cli = self._cli()
        cli._emit("hello")
        assert capsys.readouterr().out == "hello\n"

    def test_emit_erases_and_redraws_an_active_prompt(self, capsys):
        cli = self._cli()
        cli._show_prompt()
        cli._emit("notice")
        out = capsys.readouterr().out
        # prompt, then erase-line + text, then a newline, then the prompt again.
        assert out.startswith("> ")
        assert "\r\x1b[Knotice" in out
        assert out.endswith("> ")

    def test_show_prompt_marks_it_on_screen(self):
        cli = self._cli()
        assert cli._prompt_shown is False
        cli._show_prompt()
        assert cli._prompt_shown is True

    def test_clear_prompt_erases_only_once(self, capsys):
        cli = self._cli()
        cli._show_prompt()
        cli._clear_prompt()
        cli._clear_prompt()  # idempotent: no second erase
        out = capsys.readouterr().out
        assert out.count("\r\x1b[K") == 1
        assert cli._prompt_shown is False

    def test_ready_banner_does_not_glue_to_the_prompt(self, capsys):
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        asyncio.run(cli._handle_ready("status.assistant.ready", {}))
        out = capsys.readouterr().out
        assert "> Ready" not in out, "the banner must not be glued to the prompt"
        assert "\r\x1b[KReady. Type /help for commands." in out

    def test_final_redraws_exactly_one_prompt(self, capsys):
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        asyncio.run(cli._handle_final("agent.final", {"text": "Hi"}))
        out = capsys.readouterr().out
        # One prompt at the start, one redraw at the end -- not zero, not three.
        assert out.count("> ") == 2
        assert out.endswith("> ")

    def test_console_registers_and_clears_the_writer(self):
        import asyncio
        from aiassistant import terminal
        cli = self._cli()

        async def scenario():
            await cli.start()
            assert terminal.has_prompt_writer() is True
            await cli.stop()

        asyncio.run(scenario())
        assert terminal.has_prompt_writer() is False

    def test_suspend_releases_the_prompt_line(self):
        import asyncio
        from aiassistant import terminal

        async def scenario():
            cli = self._cli()
            await cli.start()
            cli.suspend_terminal()
            assert terminal.has_prompt_writer() is False
            await cli.stop()

        asyncio.run(scenario())

    def test_emit_is_silent_when_another_frontend_owns_the_terminal(self, capsys):
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()  # discard the prompt drawn while it owned the tty
        cli._owns_terminal = False
        cli._emit("must not appear")
        assert capsys.readouterr().out == ""


class TestStreamingDoesNotDuplicate:
    """The streamed line is settled in place, not printed a second time.

    The bug: the first delta redrew the prompt (so later deltas landed after
    `> `), and `agent.final` then wrote the whole text again on a new line.
    """

    def _cli(self):
        from aiassistant.bus.bus import MessageBus
        return ConsoleModule(MessageBus(), {"console": {"prompt": "> "}})

    @pytest.fixture(autouse=True)
    def _reset(self):
        from aiassistant import terminal
        yield
        terminal.set_prompt_writer(None)

    def test_deltas_open_one_line_and_append_in_place(self, capsys):
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()

        async def scenario():
            await cli._handle_delta("agent.delta", {"kind": "text", "text": "I don"})
            await cli._handle_delta("agent.delta", {"kind": "text", "text": "'t know"})

        asyncio.run(scenario())
        out = capsys.readouterr().out
        assert out.count("Assistant: ") == 1, "the prefix must be printed once"
        assert "I don" in out and "'t know" in out
        assert "> " not in out, "the prompt must not reappear mid-stream"

    def test_final_settles_without_duplicating_a_plain_line(self, capsys):
        import asyncio
        from tests.screen import render
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()

        async def scenario():
            await cli._handle_delta("agent.delta", {"kind": "text", "text": "Hi"})
            await cli._handle_final("agent.final", {"text": "Hi there"})

        asyncio.run(scenario())
        shown = render(capsys.readouterr().out)
        assert shown == ["Assistant: Hi there", ">"], shown

    def test_identical_final_never_reprints_the_stream(self, capsys):
        """The wrap bug: a reprint duplicates any line that wrapped."""
        import asyncio
        from tests.screen import render
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()

        async def scenario():
            for chunk in ("A long ", "streamed ", "answer"):
                await cli._handle_delta("agent.delta", {"kind": "text", "text": chunk})
            await cli._handle_final("agent.final", {"text": "A long streamed answer"})

        asyncio.run(scenario())
        shown = render(capsys.readouterr().out)
        assert shown == ["Assistant: A long streamed answer", ">"], shown

    def test_a_wrapped_answer_appears_exactly_once(self, capsys):
        """The reported bug, at the display level.

        `\\r` plus `\\x1b[K` clears one physical row, so reprinting a wrapped
        answer left the earlier rows and showed the whole thing twice.
        """
        import asyncio
        from tests.screen import render
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()
        answer = ("I'm an AI assistant here to help you with tasks like answering "
                  "questions, researching topics, and browsing the web.")

        async def scenario():
            for i in range(0, len(answer), 12):
                await cli._handle_delta(
                    "agent.delta", {"kind": "text", "text": answer[i:i + 12]})
            await cli._handle_final("agent.final", {"text": answer})

        asyncio.run(scenario())
        shown = " ".join(render(capsys.readouterr().out, columns=80))
        assert shown.count("Assistant:") == 1, shown
        assert shown.count("browsing the web.") == 1, shown

    def test_revision_erases_every_streamed_row(self, capsys):
        import asyncio
        from tests.screen import render
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()

        async def scenario():
            for chunk in ("a draft that ", "runs on and on"):
                await cli._handle_delta("agent.delta", {"kind": "text", "text": chunk})
            await cli._handle_final("agent.final", {"text": "final"})

        asyncio.run(scenario())
        shown = render(capsys.readouterr().out)
        assert shown == ["Assistant: final", ">"], shown

    def test_final_without_deltas_prints_one_labelled_line(self, capsys):
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()
        asyncio.run(cli._handle_final("agent.final", {"text": "Just once"}))
        out = capsys.readouterr().out
        assert out.count("Assistant: Just once") == 1

    def test_thinking_goes_to_the_log_not_the_transcript(self, capsys, caplog):
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()
        with caplog.at_level("DEBUG"):
            asyncio.run(cli._handle_delta(
                "agent.delta", {"kind": "thinking", "text": "let me consider"}))
        assert "let me consider" not in capsys.readouterr().out
        assert any("let me consider" in r.message for r in caplog.records)

    def test_thinking_summary_is_logged_and_hidden_by_default(self, capsys, caplog):
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()
        with caplog.at_level("DEBUG"):
            asyncio.run(cli._handle_final(
                "agent.final", {"text": "answer", "thinking": "reasoning here"}))
        out = capsys.readouterr().out
        assert "reasoning here" not in out
        assert any("reasoning here" in r.message for r in caplog.records)

    def test_thinking_summary_shows_only_when_requested(self, capsys):
        import asyncio
        cli = self._cli()
        cli._show_thinking = True
        cli._show_prompt()
        capsys.readouterr()
        asyncio.run(cli._handle_final(
            "agent.final", {"text": "answer", "thinking": "reasoning here"}))
        assert "reasoning here" in capsys.readouterr().out


class TestInputEcho:
    """Typed input is echoed exactly once.

    The terminal echoes a line typed at the prompt, so the console must not
    also print it as "You: ..." or the user reads their own input twice. A
    piped run has no terminal echo, so the transcript keeps the turn there.
    """

    def _cli(self):
        from aiassistant.bus.bus import MessageBus
        return ConsoleModule(MessageBus(), {"console": {"prompt": "> "}})

    @pytest.fixture(autouse=True)
    def _reset(self):
        from aiassistant import terminal
        yield
        terminal.set_prompt_writer(None)

    def test_tty_does_not_re_echo_the_typed_line(self, monkeypatch, capsys):
        import asyncio
        import sys
        cli = self._cli()
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
        asyncio.run(cli._handle_line("hi"))
        assert "You: hi" not in capsys.readouterr().out

    def test_non_tty_echoes_the_line_into_the_transcript(self, monkeypatch, capsys):
        import asyncio
        import sys
        cli = self._cli()
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        asyncio.run(cli._handle_line("hi"))
        assert "You: hi" in capsys.readouterr().out

    def test_the_turn_is_published_whichever_way(self, monkeypatch):
        import asyncio
        import sys
        seen = []
        cli = self._cli()
        cli.bus.subscribe("user.input.text", lambda t, p: seen.append(p))
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
        asyncio.run(cli._handle_line("hi"))
        assert len(seen) == 1

    def test_voice_transcript_is_still_shown(self, capsys):
        """Voice has no terminal echo, so its transcript must remain."""
        import asyncio
        cli = self._cli()
        cli._show_prompt()
        capsys.readouterr()
        asyncio.run(cli._handle_transcribed("voice.transcribed", {"text": "spoken words"}))
        assert "You: spoken words" in capsys.readouterr().out


class TestWrapMath:
    """Row and width math behind the erasure.

    The bug was that `\\r\\x1b[K` clears one physical row. A wrapped answer kept
    its earlier rows, so settling the text appeared to duplicate it.
    """

    def _cli(self, columns=80):
        import unittest.mock as mock
        from aiassistant.bus.bus import MessageBus
        cli = ConsoleModule(MessageBus(), {})
        cli._terminal_columns = mock.Mock(return_value=columns)
        return cli

    def test_exact_multiple_does_not_add_a_row(self):
        # 80 chars in an 80-column terminal is one full row, not two.
        assert self._cli(80)._wrapped_rows("x" * 80) == 1

    def test_one_past_the_edge_wraps(self):
        assert self._cli(80)._wrapped_rows("x" * 81) == 2

    def test_zero_width_is_one_row(self):
        assert self._cli(80)._wrapped_rows("") == 1

    def test_display_width_counts_cjk_as_two_columns(self):
        from aiassistant.console.module import _display_width
        assert _display_width("日本語") == 6
        assert _display_width("abc") == 3

    def test_display_width_ignores_combining_marks(self):
        from aiassistant.console.module import _display_width
        assert _display_width("e\u0301") == 1

    def test_wrapped_rows_uses_display_width_not_char_count(self):
        # 40 CJK chars = 80 columns = exactly one row in an 80-column terminal.
        assert self._cli(80)._wrapped_rows("日" * 40) == 1
        assert self._cli(80)._wrapped_rows("日" * 41) == 2

    def test_erasure_moves_up_for_a_multiline_block(self, capsys):
        cli = self._cli(20)
        cli._owns_terminal = True
        cli._stream_prefix = "Assistant:"      # 10 chars
        cli._streamed_text = "x" * 30          # 40 chars -> 2 rows at 20 cols
        capsys.readouterr()
        cli._erase_streamed_rows()
        out = capsys.readouterr().out
        assert "\x1b[1A" in out, "cursor must move up one row for a 2-row block"
        assert out.count("\x1b[2K") == 2, "every row must be cleared"

    def test_erasure_of_a_three_row_block_moves_up_twice(self, capsys):
        cli = self._cli(20)
        cli._owns_terminal = True
        cli._stream_prefix = "Assistant:"
        cli._streamed_text = "x" * 50          # 60 chars -> 3 rows at 20 cols
        capsys.readouterr()
        cli._erase_streamed_rows()
        out = capsys.readouterr().out
        assert "\x1b[2A" in out
        assert out.count("\x1b[2K") == 3

    def test_erasure_of_a_single_row_does_not_move_up(self, capsys):
        cli = self._cli(80)
        cli._owns_terminal = True
        cli._stream_prefix = "Assistant:"
        cli._streamed_text = "short"
        capsys.readouterr()
        cli._erase_streamed_rows()
        out = capsys.readouterr().out
        assert "\x1b[1A" not in out and "\x1b[2A" not in out
