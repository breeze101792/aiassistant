import os
from typing import Any

from modules.hands.builtin_tools.base import ToolBase


class FileReadTool(ToolBase):
    name = "file.read"
    description = "Read the contents of a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
        },
        "required": ["path"],
    }

    def execute(self, path: str) -> str:
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r") as f:
            return f.read()


class FileWriteTool(ToolBase):
    name = "file.write"
    description = "Write content to a file, creating it if it doesn't exist."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["path", "content"],
    }

    def execute(self, path: str, content: str) -> dict:
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return {"path": path, "bytes_written": len(content)}


class FileListTool(ToolBase):
    name = "file.list"
    description = "List files and directories in a given path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list"},
        },
        "required": ["path"],
    }

    def execute(self, path: str) -> list[str]:
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            raise NotADirectoryError(f"Not a directory: {path}")
        return sorted(os.listdir(path))
