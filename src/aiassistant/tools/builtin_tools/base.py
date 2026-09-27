from abc import ABC, abstractmethod
from typing import Any


class ToolBase(ABC):
    """Every tool and skill inherits from this.

    The LLM sees: name + description + parameters (JSON Schema).
    The system executes: execute(**params) — deterministic Python.
    """

    name: str = ""
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Run the tool. Receives validated parameters, returns result."""
        ...
