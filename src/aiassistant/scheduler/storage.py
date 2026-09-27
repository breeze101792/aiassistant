import json
import os
import tempfile


class ScheduleStorage:
    """Persist scheduled tasks to disk with atomic writes."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            self._write([])

    def load(self) -> list[dict]:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def save(self, tasks: list[dict]) -> None:
        self._write(tasks)

    def add(self, task: dict) -> list[dict]:
        tasks = self.load()
        tasks.append(task)
        self._write(tasks)
        return tasks

    def delete(self, task_id: str) -> list[dict]:
        tasks = [t for t in self.load() if t.get("id") != task_id]
        self._write(tasks)
        return tasks

    def list_all(self) -> list[dict]:
        return self.load()

    def _write(self, tasks: list[dict]) -> None:
        dirname = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(dir=dirname, suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(tasks, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            os.unlink(tmp)
            raise
