import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

from modules.base import BaseModule
from modules.scheduler.storage import ScheduleStorage

logger = logging.getLogger(__name__)


class SchedulerModule(BaseModule):
    """Time-based task scheduler — reminders, recurring tasks, delayed execution."""

    module_name = "scheduler"
    RECURRING_MAP = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "hourly": timedelta(hours=1)}

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        sched_cfg = config.get("scheduler", {})
        self.storage = ScheduleStorage(sched_cfg.get("storage_path", "./data/schedules.json"))
        self.max_pending = sched_cfg.get("max_pending", 100)
        self._running = False
        self._task: asyncio.Task | None = None

    async def setup(self) -> bool:
        pending = self.storage.list_all()
        logger.info(f"Scheduler setup — {len(pending)} pending tasks")
        return True

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("action.schedule.add", self._handle_add)
        self.bus.subscribe("action.schedule.list", self._handle_list)
        self.bus.subscribe("action.schedule.delete", self._handle_delete)
        self._task = asyncio.ensure_future(self._clock_loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Scheduler stopped")

    async def health(self) -> dict:
        tasks = self.storage.list_all()
        return {"status": "ok", "details": {"pending_count": len(tasks)}}

    # ── Handlers ──────────────────────────────────────────────

    async def _handle_add(self, topic: str, payload: dict) -> None:
        tasks = self.storage.list_all()
        if len(tasks) >= self.max_pending:
            self.bus.publish("status.scheduler.error", {"error": "Max pending tasks reached"})
            return

        task = {
            "id": str(uuid.uuid4())[:8],
            "task": payload.get("task", ""),
            "time": payload.get("time", ""),
            "repeat": payload.get("repeat"),
            "description": payload.get("description", ""),
        }
        self.storage.add(task)
        self.bus.publish("status.schedule.added", task)

    async def _handle_list(self, topic: str, payload: dict) -> None:
        tasks = self.storage.list_all()
        self.bus.publish("status.schedule.list", {"tasks": tasks})

    async def _handle_delete(self, topic: str, payload: dict) -> None:
        task_id = payload.get("id", "")
        self.storage.delete(task_id)
        self.bus.publish("status.schedule.deleted", {"id": task_id})

    # ── Clock Loop ────────────────────────────────────────────

    async def _clock_loop(self):
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                tasks = self.storage.list_all()
                triggered = []

                for task in tasks:
                    try:
                        task_time = datetime.fromisoformat(task["time"])
                    except (ValueError, KeyError):
                        continue

                    if task_time <= now:
                        self.bus.publish("schedule.triggered", {
                            "id": task["id"],
                            "task": task["task"],
                            "time": task["time"],
                            "description": task.get("description", ""),
                        })
                        triggered.append(task)

                        if task.get("repeat") and task["repeat"] in self.RECURRING_MAP:
                            next_time = task_time + self.RECURRING_MAP[task["repeat"]]
                            task["time"] = next_time.isoformat()
                        else:
                            continue

                if triggered:
                    remaining = [t for t in tasks if t["id"] not in {tr["id"] for tr in triggered}]
                    for tr in triggered:
                        if tr.get("repeat") and tr["repeat"] in self.RECURRING_MAP:
                            remaining.append(tr)
                    self.storage.save(remaining)

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler clock error: {e}")
                await asyncio.sleep(5)
