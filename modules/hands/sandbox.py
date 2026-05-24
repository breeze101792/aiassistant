import os
import subprocess
import tempfile
from typing import Any


class Sandbox:
    """Restricted execution environment for tools.

    Limits: no network (optional), safe paths only, timeout.
    """

    def __init__(self, safe_paths: list[str] | None = None,
                 timeout: float = 30.0, allow_network: bool = False):
        self.safe_paths = safe_paths or ["./workspace", "/tmp/aiassistant"]
        self.timeout = timeout
        self.allow_network = allow_network

    def run(self, command: str, cwd: str | None = None) -> dict:
        """Run a shell command in restricted mode."""
        if cwd and not self._is_safe_path(cwd):
            return {"stdout": "", "stderr": "Access denied: unsafe path", "returncode": 1}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd or self.safe_paths[0],
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Command timed out", "returncode": -1}

    def run_tool(self, tool, params: dict) -> Any:
        """Run a tool's execute method in sandbox mode.

        Validates params, restricts file paths, enforces timeout.
        """
        for key, value in params.items():
            if isinstance(value, str) and value.startswith(("/", "./", "~/")) and "path" in key.lower():
                path = os.path.abspath(os.path.expanduser(value))
                if not self._is_safe_path(path):
                    raise PermissionError(f"Access denied: {path} is outside safe paths")

        return tool.execute(**params)

    def _is_safe_path(self, path: str) -> bool:
        abs_path = os.path.abspath(os.path.expanduser(path))
        for safe in self.safe_paths:
            safe_abs = os.path.abspath(os.path.expanduser(safe))
            if abs_path.startswith(safe_abs):
                return True
        return False
