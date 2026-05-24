from modules.hands.skills.base import SkillBase


class DailyBriefingSkill(SkillBase):
    """Daily briefing: date + weather → formatted summary."""

    name = "daily_briefing"
    description = "Get a daily briefing with current date, time, and weather for a location."
    parameters = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "Location for weather (e.g., 'Taipei')"},
        },
        "required": ["location"],
    }

    def execute(self, location: str) -> str:
        # Get current date/time
        dt = self.call_tool("datetime")

        # Get weather
        weather = self.call_tool("weather", location=location)

        # Format briefing
        date_str = dt.get("date", "unknown")
        time_str = dt.get("time", "unknown")
        day = dt.get("day_of_week", "unknown")

        return (
            f"Daily Briefing — {day}, {date_str} at {time_str}\n"
            f"Location: {location}\n"
            f"Weather: {weather}"
        )
