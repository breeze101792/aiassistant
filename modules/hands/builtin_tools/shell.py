import subprocess
from typing import Any

from modules.hands.builtin_tools.base import ToolBase


class ShellTool(ToolBase):
    name = "shell"
    description = "Execute a shell command and return stdout, stderr, and return code."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory for the command"},
        },
        "required": ["command"],
    }

    def execute(self, command: str, cwd: str | None = None) -> dict:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Command timed out after 30s", "returncode": -1}
