"""Frontend selection tests.

The frontend is the visual shell: ``gui | tui | none | auto``. Text and audio
are always-available capabilities, not modes (ADR-0017). These tests pin the
resolution rules, the aliases, and the terminal/display probes.
"""

import pytest

from aiassistant import config as config_mod
from aiassistant.config import (
    FRONTEND_GUI,
    FRONTEND_NONE,
    FRONTEND_TUI,
    canonical_frontend,
    gui_available,
    resolve_frontend,
    tui_available,
)

DISPLAY_ENV_VARS = config_mod._DISPLAY_ENV_VARS
SSH_ENV_VARS = config_mod._SSH_ENV_VARS
DISPLAY_OFF_ENV_VAR = config_mod._DISPLAY_OFF_ENV_VAR


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No display, no SSH, no override, and no real terminfo probe."""
    for var in DISPLAY_ENV_VARS + SSH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(DISPLAY_OFF_ENV_VAR, raising=False)
    monkeypatch.delenv("TERM", raising=False)


def _set_platform(monkeypatch, platform):
    monkeypatch.setattr(config_mod.sys, "platform", platform)


class TestGuiAvailable:
    def test_display_var_means_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        assert gui_available() is True

    def test_wayland_var_means_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert gui_available() is True

    def test_ssh_without_display_is_headless(self, monkeypatch):
        """A remote session with nothing forwarded cannot show a window."""
        _set_platform(monkeypatch, "darwin")
        monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 1 10.0.0.2 22")
        assert gui_available() is False

    def test_ssh_with_forwarded_display_is_a_gui(self, monkeypatch):
        """ssh -X exports DISPLAY; the window draws on the forwarded server."""
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 1 10.0.0.2 22")
        monkeypatch.setenv("DISPLAY", "localhost:10.0")
        assert gui_available() is True

    def test_macos_local_is_a_gui_without_display_vars(self, monkeypatch):
        """Aqua exports neither DISPLAY nor WAYLAND_DISPLAY."""
        _set_platform(monkeypatch, "darwin")
        assert gui_available() is True

    def test_other_platforms_assume_a_gui(self, monkeypatch):
        _set_platform(monkeypatch, "win32")
        assert gui_available() is True

    def test_linux_no_display_is_headless(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        assert gui_available() is False

    def test_empty_display_var_is_not_a_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", "")
        assert gui_available() is False


class TestCanonicalFrontend:
    def test_aliases(self):
        assert canonical_frontend("orb") == FRONTEND_GUI
        assert canonical_frontend("ui") == FRONTEND_GUI
        assert canonical_frontend("console") == FRONTEND_NONE

    def test_canonical_values_pass_through(self):
        for value in (FRONTEND_GUI, FRONTEND_TUI, FRONTEND_NONE, "auto"):
            assert canonical_frontend(value) == value

    def test_none_stays_none(self):
        assert canonical_frontend(None) is None


class TestResolveFrontend:
    def test_auto_with_gui_is_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        assert resolve_frontend({"display": {"mode": "auto"}}) == FRONTEND_GUI

    def test_auto_headless_is_none(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        assert resolve_frontend({"display": {"mode": "auto"}}) == FRONTEND_NONE

    def test_auto_never_picks_tui(self, monkeypatch):
        """tui is explicit; auto stays text-only on a headless host."""
        _set_platform(monkeypatch, "linux")
        assert resolve_frontend({}) == FRONTEND_NONE

    def test_explicit_tui_is_honoured(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        assert resolve_frontend({"display": {"mode": "tui"}}) == FRONTEND_TUI

    def test_legacy_console_alias_is_none(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        assert resolve_frontend({"display": {"mode": "console"}}) == FRONTEND_NONE

    def test_legacy_orb_alias_is_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        assert resolve_frontend({"display": {"mode": "orb"}}) == FRONTEND_GUI

    def test_unknown_mode_falls_back_to_auto_headless(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        assert resolve_frontend({"display": {"mode": "hologram"}}) == FRONTEND_NONE

    def test_unknown_mode_falls_back_to_auto_with_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        assert resolve_frontend({"display": {"mode": "hologram"}}) == FRONTEND_GUI

    def test_override_env_forces_none_even_with_a_gui(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setenv(DISPLAY_OFF_ENV_VAR, "1")
        assert resolve_frontend({"display": {"mode": "gui"}}) == FRONTEND_NONE

    def test_cli_choice_beats_the_override_env(self, monkeypatch):
        """REQ-CFG-002: CLI > environment."""
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv(DISPLAY_OFF_ENV_VAR, "1")
        assert resolve_frontend({"display": {"mode": "none"}},
                                cli_choice="gui") == FRONTEND_GUI

    def test_cli_console_alias_resolves_to_none(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        assert resolve_frontend({"display": {"mode": "gui"}},
                                cli_choice="console") == FRONTEND_NONE

    def test_cli_auto_yields_to_lower_layers(self, monkeypatch):
        """An explicit --frontend auto is not a choice; config still applies."""
        _set_platform(monkeypatch, "linux")
        monkeypatch.setenv(DISPLAY_OFF_ENV_VAR, "1")
        assert resolve_frontend({"display": {"mode": "gui"}},
                                cli_choice="auto") == FRONTEND_NONE

    def test_bogus_cli_choice_is_ignored(self, monkeypatch):
        _set_platform(monkeypatch, "linux")
        assert resolve_frontend({"display": {"mode": "none"}},
                                cli_choice="banana") == FRONTEND_NONE


class TestTuiAvailable:
    def test_non_tty_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(config_mod.sys.stdin, "isatty", lambda: False, raising=False)
        ok, reason = tui_available()
        assert ok is False
        assert "terminal" in reason

    def test_missing_term_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(config_mod.sys.stdin, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(config_mod.sys.stdout, "isatty", lambda: True, raising=False)
        ok, reason = tui_available()
        assert ok is False
        assert "TERM" in reason

    def test_dumb_term_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(config_mod.sys.stdin, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(config_mod.sys.stdout, "isatty", lambda: True, raising=False)
        monkeypatch.setenv("TERM", "dumb")
        ok, reason = tui_available()
        assert ok is False
        assert "dumb" in reason

    def test_reports_a_reason_when_unavailable(self, monkeypatch):
        """The caller logs this; it must never be empty on failure."""
        monkeypatch.setattr(config_mod.sys.stdin, "isatty", lambda: False, raising=False)
        ok, reason = tui_available()
        assert ok is False and reason

    def test_never_enters_curses(self, monkeypatch):
        """tui_available must not call initscr; it may only probe terminfo.

        A failed initscr can exit the interpreter, so the check runs first and
        must stay side-effect free.
        """
        import curses
        calls = []
        monkeypatch.setattr(curses, "initscr", lambda: calls.append("initscr"))
        monkeypatch.setattr(config_mod.sys.stdin, "isatty", lambda: False, raising=False)
        tui_available()
        assert calls == []


class TestTerminalPromptSeam:
    """The prompt seam routes async writes above the active prompt."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from aiassistant import terminal
        terminal.set_prompt_writer(None)
        yield
        terminal.set_prompt_writer(None)

    def test_no_writer_is_a_plain_stdout_write(self, capsys):
        from aiassistant import terminal
        terminal.write_above("plain")
        assert capsys.readouterr().out == "plain"

    def test_writer_receives_the_text(self):
        from aiassistant import terminal
        seen = []
        terminal.set_prompt_writer(seen.append)
        terminal.write_above("routed")
        assert seen == ["routed"]
        assert terminal.has_prompt_writer() is True

    def test_clearing_the_writer_restores_plain_writes(self, capsys):
        from aiassistant import terminal
        terminal.set_prompt_writer(lambda t: None)
        terminal.set_prompt_writer(None)
        terminal.write_above("plain again")
        assert capsys.readouterr().out == "plain again"
        assert terminal.has_prompt_writer() is False


class TestPromptAwareHandler:
    """A log record routes through the seam so the prompt survives."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from aiassistant import terminal
        terminal.set_prompt_writer(None)
        yield
        terminal.set_prompt_writer(None)

    def _record(self, msg):
        import logging
        return logging.LogRecord("t", logging.WARNING, __file__, 1, msg, None, None)

    def test_format_is_written_above_the_prompt(self):
        from aiassistant import terminal
        from aiassistant.main import PromptAwareHandler
        seen = []
        terminal.set_prompt_writer(seen.append)
        handler = PromptAwareHandler()
        handler.emit(self._record("boom"))
        assert any("boom" in s for s in seen)

    def test_write_is_plain_without_a_prompt_owner(self, capsys):
        from aiassistant.main import PromptAwareHandler
        handler = PromptAwareHandler()
        handler.emit(self._record("plain record"))
        captured = capsys.readouterr()
        # Defers to the plain StreamHandler, i.e. this handler's own stream
        # (stderr by default) -- not stdout, where the prompt lives.
        assert "plain record" in captured.err
        assert "plain record" not in captured.out
