"""Frontend spawn-plan tests.

``frontend_plan`` is the pure decision behind the spawn: what to run, and why.
Keeping it pure means the degradation rules are testable without a display,
a terminal, or spawning a process.
"""

from aiassistant.config import FRONTEND_GUI, FRONTEND_NONE, FRONTEND_TUI
from aiassistant.main import frontend_plan


class TestFrontendPlan:
    def test_gui_with_a_display_spawns_the_orb(self, monkeypatch):
        monkeypatch.setattr("aiassistant.main.gui_available", lambda: True)
        kind, note = frontend_plan(FRONTEND_GUI, tui_ok=False)
        assert kind == FRONTEND_GUI
        assert note == ""

    def test_gui_without_a_display_falls_to_tui(self, monkeypatch):
        monkeypatch.setattr("aiassistant.main.gui_available", lambda: False)
        kind, note = frontend_plan(FRONTEND_GUI, tui_ok=True)
        assert kind == FRONTEND_TUI
        assert "no display server" in note

    def test_gui_without_a_display_or_terminal_is_none(self, monkeypatch):
        monkeypatch.setattr("aiassistant.main.gui_available", lambda: False)
        kind, note = frontend_plan(FRONTEND_GUI, tui_ok=False)
        assert kind == FRONTEND_NONE
        assert note

    def test_tui_with_a_terminal_spawns_the_tui(self):
        kind, note = frontend_plan(FRONTEND_TUI, tui_ok=True)
        assert kind == FRONTEND_TUI
        assert note == ""

    def test_tui_without_a_terminal_is_none(self):
        kind, note = frontend_plan(FRONTEND_TUI, tui_ok=False)
        assert kind == FRONTEND_NONE
        assert "terminal" in note

    def test_none_spawns_nothing(self):
        kind, note = frontend_plan(FRONTEND_NONE, tui_ok=True)
        assert kind == FRONTEND_NONE
        assert note == ""

    def test_none_ignores_terminal_availability(self):
        assert frontend_plan(FRONTEND_NONE, tui_ok=False)[0] == FRONTEND_NONE

    def test_every_branch_returns_a_spawnable_kind(self):
        for frontend in (FRONTEND_GUI, FRONTEND_TUI, FRONTEND_NONE):
            for tui_ok in (True, False):
                kind, _ = frontend_plan(frontend, tui_ok)
                assert kind in (FRONTEND_GUI, FRONTEND_TUI, FRONTEND_NONE)


class TestFrontendStdio:
    """The TUI needs the real terminal; the GUI orb must not touch it."""

    def test_tui_inherits_the_terminal(self):
        from aiassistant.main import frontend_inherits_terminal
        assert frontend_inherits_terminal(FRONTEND_TUI) is True

    def test_gui_does_not_inherit_the_terminal(self):
        from aiassistant.main import frontend_inherits_terminal
        assert frontend_inherits_terminal(FRONTEND_GUI) is False

    def test_none_does_not_inherit(self):
        from aiassistant.main import frontend_inherits_terminal
        assert frontend_inherits_terminal(FRONTEND_NONE) is False


class _FakeProc:
    """A fake subprocess whose exit is controlled by the test."""

    def __init__(self, pid: int, returncode: int | None = None):
        self.pid = pid
        self.returncode = returncode
        self._waiters: list = []

    async def wait(self):
        if self.returncode is None:
            import asyncio
            fut = asyncio.get_running_loop().create_future()
            self._waiters.append(fut)
            return await fut
        return self.returncode

    def exit_with(self, code: int) -> None:
        self.returncode = code
        for fut in self._waiters:
            if not fut.done():
                fut.set_result(code)
        self._waiters.clear()

    def terminate(self):
        self.exit_with(-15)

    def kill(self):
        self.exit_with(-9)


class TestFrontendSupervision:
    """The restart policy is where the earlier bugs lived, so pin it."""

    def _runner(self, monkeypatch, exits, spawn_results=None):
        """Run _watch_frontend over a scripted sequence of exits."""
        import asyncio
        from aiassistant.main import AssistantRunner, FRONTEND_TUI

        runner = AssistantRunner.__new__(AssistantRunner)
        runner._shutting_down = False
        runner._frontend = FRONTEND_TUI
        runner._frontend_restarts = 0
        runner._frontend_generation = 0
        runner._frontend_process = None
        runner.modules = {}
        runner._config_path = "config.yaml"
        spawned = []
        results = list(spawn_results or [])

        async def fake_spawn(kind, argv, *, initial):
            spawned.append((kind, initial))
            proc = _FakeProc(pid=len(spawned) + 100)
            runner._frontend_process = proc
            if initial:
                runner._frontend_restarts = 0
            return True

        monkeypatch.setattr(runner, "_spawn_frontend", fake_spawn)
        monkeypatch.setattr("aiassistant.main.FRONTEND_RESTART_DELAY_S", 0)
        # The fake process exits within the same tick as the watcher starts, so
        # make the startup grace zero for the crash-path tests; the grace case is
        # covered by the clean-exit test, which returns before the check.
        monkeypatch.setattr("aiassistant.main.FRONTEND_STARTUP_GRACE_S", 0)

        async def scenario():
            runner._frontend_process = _FakeProc(pid=1)
            runner._frontend_generation = 1
            task = asyncio.ensure_future(runner._watch_frontend(FRONTEND_TUI, 1))
            await asyncio.sleep(0)
            for code in exits:
                runner._frontend_process.exit_with(code)
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                if task.done():
                    break
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return spawned

        return asyncio.run(scenario())

    def test_clean_exit_is_not_respawned(self, monkeypatch):
        """Ctrl+D (exit 0) means the user closed the UI; do not restart it."""
        spawned = self._runner(monkeypatch, [0])
        assert spawned == []

    def test_crash_after_grace_is_respawned(self, monkeypatch):
        spawned = self._runner(monkeypatch, [1])
        assert len(spawned) == 1
        assert spawned[0][1] is False  # respawn, not initial

    def test_restart_budget_is_finite(self, monkeypatch):
        """A crash loop must stop after FRONTEND_MAX_RESTARTS, not run forever."""
        from aiassistant.main import FRONTEND_MAX_RESTARTS
        spawned = self._runner(monkeypatch, [1] * 10)
        assert len(spawned) <= FRONTEND_MAX_RESTARTS + 1

    def test_only_one_watcher_spawns_per_exit(self, monkeypatch):
        """No watcher multiplication: one exit must produce one respawn."""
        spawned = self._runner(monkeypatch, [1, 1])
        assert len(spawned) == 2

    def test_clean_exit_after_grace_releases_the_terminal(self, monkeypatch):
        import asyncio
        from aiassistant.main import AssistantRunner, FRONTEND_TUI

        runner = AssistantRunner.__new__(AssistantRunner)
        runner._shutting_down = False
        runner._frontend = FRONTEND_TUI
        runner._frontend_restarts = 0
        runner._frontend_generation = 1
        runner.modules = {}
        released = []
        runner._release_terminal = lambda kind: released.append(kind)

        async def scenario():
            runner._frontend_process = _FakeProc(pid=1)
            runner._frontend_generation = 1
            task = asyncio.ensure_future(runner._watch_frontend(FRONTEND_TUI, 1))
            await asyncio.sleep(0)
            runner._frontend_process.exit_with(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
            return released

        released = asyncio.run(scenario())
        assert released == [FRONTEND_TUI]


class TestFrontendOpenCommand:
    """The parent handles `command.frontend.open` from the console/TUI."""

    def _runner(self, monkeypatch):
        from aiassistant.main import AssistantRunner, FRONTEND_GUI

        runner = AssistantRunner.__new__(AssistantRunner)
        runner._frontend = FRONTEND_GUI
        runner._frontend_process = None
        runner._frontend_spawning = False
        runner._frontend_restarts = 0
        runner._frontend_generation = 0
        runner._shutting_down = False
        runner.modules = {}
        runner._config_path = "config.yaml"
        return runner

    def test_open_command_schedules_a_spawn(self, monkeypatch):
        import asyncio
        runner = self._runner(monkeypatch)
        opened = []

        async def fake_open(kind):
            opened.append(kind)

        monkeypatch.setattr(runner, "_open_frontend", fake_open)

        async def scenario():
            runner._handle_frontend_open("command.frontend.open", {"kind": "tui"})
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        asyncio.run(scenario())
        assert opened == ["tui"]

    def test_unknown_kind_is_ignored(self, monkeypatch):
        import asyncio
        runner = self._runner(monkeypatch)
        opened = []

        async def fake_open(kind):
            opened.append(kind)

        monkeypatch.setattr(runner, "_open_frontend", fake_open)

        async def scenario():
            runner._handle_frontend_open("command.frontend.open", {"kind": "holo"})
            await asyncio.sleep(0)

        asyncio.run(scenario())
        assert opened == []

    def test_a_live_child_blocks_a_second_spawn(self, monkeypatch):
        import asyncio
        runner = self._runner(monkeypatch)
        runner._frontend_process = _FakeProc(pid=1, returncode=None)
        opened = []

        async def fake_open(kind):
            opened.append(kind)

        monkeypatch.setattr(runner, "_open_frontend", fake_open)

        async def scenario():
            runner._handle_frontend_open("command.frontend.open", {"kind": "gui"})
            await asyncio.sleep(0)

        asyncio.run(scenario())
        assert opened == []

    def test_two_requests_in_one_tick_spawn_once(self, monkeypatch):
        """The real `_open_frontend` runs twice; the in-flight flag stops the second.

        The first task sets the flag before its first await, so the second sees
        it and returns. `_do_open_frontend` is stubbed so no process is created.
        """
        import asyncio
        from aiassistant.main import FRONTEND_TUI
        runner = self._runner(monkeypatch)
        calls = []

        async def fake_do_open(kind, generation):
            calls.append((kind, generation))
            await asyncio.sleep(0)

        monkeypatch.setattr(runner, "_do_open_frontend", fake_do_open)

        async def scenario():
            t1 = asyncio.ensure_future(runner._open_frontend(FRONTEND_TUI))
            t2 = asyncio.ensure_future(runner._open_frontend(FRONTEND_TUI))
            await asyncio.gather(t1, t2)

        asyncio.run(scenario())
        assert len(calls) == 1, calls
        assert runner._frontend_spawning is False, "the flag must be cleared"
        assert runner._frontend_generation == 1

    def test_flag_is_cleared_even_when_the_spawn_degrades(self, monkeypatch):
        """The tui-unavailable early return must still clear the flag."""
        import asyncio
        from aiassistant.main import FRONTEND_TUI
        runner = self._runner(monkeypatch)
        monkeypatch.setattr("aiassistant.main.tui_available",
                            lambda: (False, "no terminal"))

        async def scenario():
            await runner._open_frontend(FRONTEND_TUI)

        asyncio.run(scenario())
        assert runner._frontend_spawning is False
        assert runner._frontend is not None

    def test_shutdown_command_sets_the_event(self):
        import asyncio
        from aiassistant.main import AssistantRunner
        runner = AssistantRunner.__new__(AssistantRunner)
        runner._shutdown_event = asyncio.Event()
        runner._handle_shutdown_command("command.assistant.shutdown", {})
        assert runner._shutdown_event.is_set() is True


class TestWatcherOwnership:
    """A replaced child's watcher must not release its successor's tty."""

    def _runner(self):
        from aiassistant.main import AssistantRunner, FRONTEND_TUI

        runner = AssistantRunner.__new__(AssistantRunner)
        runner._shutting_down = False
        runner._frontend = FRONTEND_TUI
        runner._frontend_restarts = 0
        runner._frontend_generation = 1
        runner.modules = {}
        runner._config_path = "config.yaml"
        return runner

    def test_stale_watcher_does_not_release_the_tty(self, monkeypatch):
        import asyncio
        runner = self._runner()
        released = []
        runner._release_terminal = lambda kind: released.append(kind)
        old = _FakeProc(pid=1)
        runner._frontend_process = old

        async def scenario():
            task = asyncio.ensure_future(runner._watch_frontend("tui", 1))
            await asyncio.sleep(0)
            # A replacement frontend claims the next generation before the old
            # child's exit is observed.
            runner._frontend_generation = 2
            runner._frontend_process = _FakeProc(pid=2)
            old.exit_with(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(scenario())
        assert released == [], "the old watcher must not release the new tty"

    def test_current_watcher_still_releases_on_clean_exit(self, monkeypatch):
        import asyncio
        runner = self._runner()
        released = []
        runner._release_terminal = lambda kind: released.append(kind)
        proc = _FakeProc(pid=1)
        runner._frontend_process = proc

        async def scenario():
            task = asyncio.ensure_future(runner._watch_frontend("tui", 1))
            await asyncio.sleep(0)
            proc.exit_with(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(scenario())
        assert released == ["tui"]


class TestStartupGrace:
    """A child that cannot run on this host must not be retried."""

    def test_quick_crash_within_grace_is_not_respawned(self, monkeypatch):
        import asyncio
        from aiassistant.main import AssistantRunner, FRONTEND_TUI

        runner = AssistantRunner.__new__(AssistantRunner)
        runner._shutting_down = False
        runner._frontend = FRONTEND_TUI
        runner._frontend_restarts = 0
        runner._frontend_generation = 1
        runner.modules = {}
        spawned = []

        async def fake_spawn(kind, argv, *, initial):
            spawned.append(initial)
            runner._frontend_process = _FakeProc(pid=1)
            return True

        monkeypatch.setattr(runner, "_spawn_frontend", fake_spawn)
        monkeypatch.setattr("aiassistant.main.FRONTEND_RESTART_DELAY_S", 0)
        # A generous grace, so the quick exit below counts as a startup failure.
        monkeypatch.setattr("aiassistant.main.FRONTEND_STARTUP_GRACE_S", 60)

        async def scenario():
            runner._frontend_process = _FakeProc(pid=1)
            runner._frontend_generation = 1
            task = asyncio.ensure_future(runner._watch_frontend(FRONTEND_TUI, 1))
            await asyncio.sleep(0)
            runner._frontend_process.exit_with(1)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
            return spawned

        spawned = asyncio.run(scenario())
        assert spawned == [], "a quick crash must not trigger a respawn"


class TestHarnessSeam:
    """The harness abstraction is kept deliberately (REQ-HARNESS-008).

    One harness ships, but the factory seam stays open: a new harness is added
    by implementing the contract and registering it, with no caller changes.
    """

    def test_native_is_the_only_shipped_harness(self):
        from aiassistant.agent.harness.factory import NATIVE, SUPPORTED
        assert NATIVE == "native"
        assert SUPPORTED == (NATIVE,)

    def test_native_is_available(self):
        from aiassistant.agent.harness.factory import harness_is_available
        assert harness_is_available("native") is True

    def test_removed_harness_is_not_available(self):
        from aiassistant.agent.harness.factory import harness_is_available
        assert harness_is_available("pi") is False

    def test_unknown_harness_is_rejected_loudly(self):
        from aiassistant.agent.harness.factory import (
            HarnessConfigError, create_harness,
        )
        import pytest as _pytest
        with _pytest.raises(HarnessConfigError, match="future-loop"):
            create_harness({"harness": "future-loop"})

    def test_harness_config_has_no_pi_key(self):
        from aiassistant.config import DEFAULTS
        assert "pi" not in DEFAULTS["agent"]

    def test_the_contract_is_still_abstract(self):
        """A future harness must be able to implement this without edits."""
        from aiassistant.agent.harness.base import AgentHarness
        assert hasattr(AgentHarness, "run_turn")
        assert hasattr(AgentHarness, "cancel")
        assert hasattr(AgentHarness, "health")


class TestHarnessContractSurface:
    """Every member a caller touches is on the contract, not duck-typed.

    The three leaks fixed here were `hasattr(harness, "tool_schemas")`,
    `getattr(harness, "provider", None)`, and a `getattr(harness,
    "ensure_started", None)` probe. A new harness now only implements the
    documented members.
    """

    def test_optional_members_have_defaults_on_the_abc(self):
        from aiassistant.agent.harness.base import AgentHarness
        # provider is a class-level default; ensure_started/close are methods.
        assert AgentHarness.provider is None
        assert callable(AgentHarness.ensure_started)
        assert callable(AgentHarness.close)

    def test_a_minimal_harness_needs_no_extra_members(self):
        """FakeHarness implements only the abstract four, and still works."""
        import asyncio
        from aiassistant.agent.harness.fake import FakeHarness

        h = FakeHarness()
        assert h.provider is None
        asyncio.run(h.ensure_started())   # default no-op
        asyncio.run(h.close())            # default: cancels

    def test_native_declares_its_provider(self):
        from aiassistant.agent.harness.native import NativeHarness
        from tests.test_integration import MockToolLLM

        h = NativeHarness(MockToolLLM(), persona="t")
        assert h.provider is not None
        assert h.provider.model == "mock"

    def test_no_caller_probes_the_harness_with_getattr(self):
        """A guard against reintroducing the duck-typing."""
        import pathlib
        source = pathlib.Path(
            "src/aiassistant/agent/module.py").read_text()
        assert "getattr(self.harness" not in source
        assert "hasattr(harness" not in source
        assert "hasattr(self.harness" not in source
