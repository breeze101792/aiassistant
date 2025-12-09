import traceback
from datetime import datetime
import uuid
from api.base import BaseAPI

# class ScheduleAPI(BaseAPI):
#     NAME = "ScheduleAPI"
#     DESCRIPTION = "Add a todo job/things on scheduler for AI. when the time come, it'll callback to ai to do the task."


import threading
import time
from datetime import datetime, timedelta
from typing import Callable, List
import copy

class ScheduleManager:
    schedules: List[dict] = []
    callback = None
    running = True
    schedule_thread = None
    def __init__(self, callback: Callable[[dict], None]):
        if callback is not None:
            self.callback = callback
        if self.schedule_thread is None:
            # TODO, seperate start schedule_thread from init
            self.schedule_thread = threading.Thread(target=self._watcher, daemon=True)
            self.schedule_thread.start()

    def add_schedule(self, schedule: dict):
        self.schedules.append(schedule)
        self.schedules.sort(key=lambda x: x['time'])

    def _watcher(self):
        while self.running:
            now = datetime.now().isoformat()
            to_run = [s for s in self.schedules if s["time"] <= now]
            self.schedules = [s for s in self.schedules if s["time"] > now]

            for task in to_run:
                if self.callback is not None:
                    self.callback(task)
                    self._reschedule_if_needed(task)
                else:
                    print('Schedule callback is none.')

            time.sleep(1)

    def _reschedule_if_needed(self, task: dict):
        repeat = task.get("repeat")
        if not repeat:
            return

        original_time = datetime.fromisoformat(task["time"])
        next_time = None

        if repeat == "daily":
            next_time = original_time + timedelta(days=1)
        elif repeat == "weekly":
            next_time = original_time + timedelta(weeks=1)
        elif repeat == "hourly":
            next_time = original_time + timedelta(hours=1)
        else:
            return  # Unknown repeat pattern

        # Create new task
        new_task = copy.deepcopy(task)
        new_task["time"] = next_time.isoformat()
        self.add_schedule(new_task)

# FIXME, add callback.
schedule_manager = ScheduleManager(None)

class AddScheduleAPI(BaseAPI):
    NAME = "AddScheduleAPI"
    DESCRIPTION = "Add a new scheduled task that will trigger an LLM message later."
    PARAMETERS = {
        "time": "string – ISO8601 format datetime string. Example: '2025-04-06T10:00:00'",
        "llm_input": "string – The message to send to LLM at the scheduled time.",
        "description": "string – Optional. A description of the scheduled task.",
        "repeat": "string – Optional. Can be 'daily', 'weekly', 'hourly' or 'none'."
    }

    def execute(self, time, llm_input, description = "", repeat=None):
        task = {
            "id": str(uuid.uuid4()),
            "time": time,
            "llm_input": llm_input,
            "description": description,
            "repeat": repeat
        }
        schedule_manager.add_schedule(task)
        return f"Task scheduled: {description} at {time} (repeat: {repeat})"

class ListSchedulesAPI(BaseAPI):
    NAME = "ListSchedulesAPI"
    DESCRIPTION = "List all currently scheduled tasks."
    PARAMETERS = {}

    def execute(self):
        return schedule_manager.schedules

class DeleteScheduleAPI(BaseAPI):
    NAME = "DeleteScheduleAPI"
    DESCRIPTION = "Delete a scheduled task by its ID."
    PARAMETERS = {
        "schedule_id": "string – The ID of the schedule to delete."
    }

    def execute(self, schedule_id):
        before = len(schedule_manager.schedules)
        schedule_manager.schedules = [
            s for s in schedule_manager.schedules if s.get("id") != schedule_id
        ]
        after = len(schedule_manager.schedules)
        if before == after:
            return f"Schedule ID {schedule_id} not found."
        return f"Deleted schedule with ID {schedule_id}."
