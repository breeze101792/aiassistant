import tempfile
import os

from modules.scheduler.storage import ScheduleStorage
from modules.scheduler.scheduler import SchedulerModule
from bus.bus import MessageBus


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
