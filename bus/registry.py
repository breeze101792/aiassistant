from datetime import datetime, timezone
from typing import Any


class ModuleRegistry:
    """Tracks connected modules and their state."""

    def __init__(self):
        self._modules: dict[str, dict[str, Any]] = {}

    def add(self, module_name: str, remote: bool = False, capabilities: dict | None = None) -> None:
        self._modules[module_name] = {
            "status": "starting",
            "remote": remote,
            "capabilities": capabilities or {},
            "subscription_ids": [],
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }

    def remove(self, module_name: str) -> None:
        self._modules.pop(module_name, None)

    def update_status(self, module_name: str, status: str) -> None:
        if module_name in self._modules:
            self._modules[module_name]["status"] = status

    def add_subscription(self, module_name: str, subscription_id: str) -> None:
        if module_name in self._modules:
            self._modules[module_name]["subscription_ids"].append(subscription_id)

    def get(self, module_name: str) -> dict | None:
        return self._modules.get(module_name)

    def list_all(self) -> dict[str, dict]:
        return dict(self._modules)

    def is_registered(self, module_name: str) -> bool:
        return module_name in self._modules

    @property
    def module_names(self) -> list[str]:
        return list(self._modules.keys())
