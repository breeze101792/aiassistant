from datetime import datetime, timezone

from modules.hands.builtin_tools.base import ToolBase


class DateTimeTool(ToolBase):
    name = "datetime"
    description = "Get the current date, time, and timezone information."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self) -> dict:
        now = datetime.now()
        utc = datetime.now(timezone.utc)
        return {
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timezone": now.astimezone().tzinfo.tzname(now) if now.astimezone().tzinfo else "unknown",
            "utc": utc.isoformat(),
            "day_of_week": now.strftime("%A"),
        }
