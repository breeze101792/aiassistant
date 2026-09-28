import asyncio
import json
import tempfile
import os
from datetime import datetime, timezone, timedelta

import pytest

from aiassistant.scheduler.storage import ScheduleStorage
from aiassistant.scheduler.module import SchedulerModule
from aiassistant.bus.bus import MessageBus


def _run_clock(mod, seconds: float) -> None:
    """Start the scheduler, let the clock loop run, then stop it."""
    async def scenario():
        await mod.start()
        await asyncio.sleep(seconds)
        mod._running = False
        if mod._task:
            mod._task.cancel()
            try:
                await mod._task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


class TestScheduleStorage:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'schedules.json')

    def test_add_and_list(self):
        st = ScheduleStorage(self.path)
        task = {
            'id': 'sched_1',
            'task': 'Test reminder',
            'time': '2026-06-01T12:00:00+00:00',
            'repeat': None,
            'description': 'Test',
        }
        st.add(task)
        tasks = st.list_all()
        assert len(tasks) == 1
        assert tasks[0]['id'] == 'sched_1'
        assert tasks[0]['task'] == 'Test reminder'

    def test_delete(self):
        st = ScheduleStorage(self.path)
        st.add({'id': 't1', 'task': 'A', 'time': '', 'repeat': None, 'description': ''})
        st.add({'id': 't2', 'task': 'B', 'time': '', 'repeat': None, 'description': ''})
        st.delete('t1')
        tasks = st.list_all()
        assert len(tasks) == 1
        assert tasks[0]['id'] == 't2'

    def test_persistence_survives_reload(self):
        st = ScheduleStorage(self.path)
        st.add({'id': 't1', 'task': 'Persist', 'time': '', 'repeat': None, 'description': ''})
        st2 = ScheduleStorage(self.path)
        tasks = st2.list_all()
        assert len(tasks) == 1
        assert tasks[0]['task'] == 'Persist'

    def test_empty_file_returns_empty_list(self):
        st = ScheduleStorage(self.path)
        assert st.list_all() == []


class TestClockLoop:
    """REQ-SCHED-002/003/004: one fire, a future re-arm, and a bounded set."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'schedules.json')

    def _module(self, max_pending: int = 100):
        bus = MessageBus()
        mod = SchedulerModule(bus, {
            "scheduler": {"storage_path": self.path, "max_pending": max_pending},
        })
        fired = []
        bus.subscribe("schedule.triggered", lambda t, p: fired.append(p))
        return mod, fired

    def test_due_task_fires_once_then_is_removed(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        json.dump([{"id": "o1", "task": "once", "time": past,
                    "repeat": None, "description": ""}], open(self.path, "w"))

        mod, fired = self._module()
        _run_clock(mod, 2.2)

        assert len(fired) == 1, "a one-shot must fire exactly once"
        assert mod.storage.list_all() == [], "a fired one-shot is removed"

    @pytest.mark.xfail(strict=True,
                       reason="BUG-3: recurring re-arm is fire_time + interval, "
                              "so an overdue task stays in the past and re-fires "
                              "every tick instead of advancing past now")
    def test_overdue_recurring_task_rearms_into_the_future(self):
        """REQ-SCHED-003: after firing, a recurring task's next time is future.

        An overdue daily task must not re-arm to ``fire_time + 1 day`` if that
        is still in the past, or the clock loop re-fires it every tick.
        """
        overdue = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        json.dump([{"id": "d1", "task": "meds", "time": overdue,
                    "repeat": "daily", "description": ""}], open(self.path, "w"))

        mod, fired = self._module()
        _run_clock(mod, 2.4)

        stored = mod.storage.list_all()
        assert stored, "a recurring task is retained"
        next_time = datetime.fromisoformat(stored[0]["time"])
        assert next_time > datetime.now(timezone.utc), (
            "recurring re-arm must be strictly in the future"
        )
        assert len(fired) == 1, (
            f"an overdue daily task must fire once, not once per tick; got {len(fired)}"
        )

    def test_max_pending_refuses_adds(self):
        past = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        mod, _ = self._module(max_pending=1)
        errors = []
        mod.bus.subscribe("status.scheduler.error", lambda t, p: errors.append(p))

        asyncio.run(mod._handle_add("action.schedule.add", {"task": "a", "time": past}))
        asyncio.run(mod._handle_add("action.schedule.add", {"task": "b", "time": past}))

        assert errors, "further adds past max_pending are refused visibly"
        assert len(mod.storage.list_all()) == 1, "the pending count is unchanged"
