import importlib
import logging
import os
import pkgutil
import time
import traceback
import uuid
from typing import Any

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class HandsModule(BaseModule):
    """Executes tools and skills. The hands of the assistant."""

    module_name = "hands"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        hands_cfg = config.get("hands", {})
        self.tool_paths: list[str] = hands_cfg.get("tool_paths", [
            "./modules/hands/builtin_tools",
            "./modules/hands/skills",
        ])
        self.sandbox_default: bool = hands_cfg.get("sandbox_default", False)
        self.command_timeout: float = hands_cfg.get("command_timeout", 30.0)
        self.safe_paths: list[str] = hands_cfg.get("safe_paths", ["./workspace", "/tmp/aiassistant"])
        self._tools: dict[str, Any] = {}

    async def setup(self) -> bool:
        self._load_all_tools()
        logger.info(f"Hands setup complete — {len(self._tools)} tools loaded: {list(self._tools.keys())}")
        return True

    async def start(self) -> None:
        self.bus.subscribe("action.execute", self._handle_execute)
        self.bus.subscribe("hands.list_tools", self._handle_list_tools)

        # Announce tools to brain
        self.bus.publish("status.hands.ready", {
            "tools": self._tool_schemas(),
            "remote_targets": [],
        })
        logger.info("Hands started — published tool list")

    async def stop(self) -> None:
        logger.info("Hands stopped")

    async def health(self) -> dict:
        return {
            "status": "ok",
            "details": {
                "tools_loaded": len(self._tools),
                "tool_names": list(self._tools.keys()),
            }
        }

    # ── Tool Loading ─────────────────────────────────────────

    def _load_all_tools(self):
        for path in self.tool_paths:
            if not os.path.isdir(path):
                logger.debug(f"Tool path not found: {path}")
                continue
            self._load_tools_from_path(path)

    def _load_tools_from_path(self, path: str):
        abs_path = os.path.abspath(path)
        sys_path_added = False
        if abs_path not in __import__("sys").path:
            __import__("sys").path.insert(0, os.path.dirname(abs_path))
            sys_path_added = True

        pkg_name = os.path.basename(abs_path)
        try:
            pkg = importlib.import_module(pkg_name)
            for _, mod_name, _ in pkgutil.iter_modules([abs_path]):
                if mod_name in ("base", "__init__"):
                    continue
                try:
                    module = importlib.import_module(f"{pkg_name}.{mod_name}")
                    self._register_tools_from_module(module)
                except Exception as e:
                    logger.warning(f"Failed to load tool module {mod_name}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load tool package {pkg_name}: {e}")
        finally:
            if sys_path_added:
                __import__("sys").path.remove(os.path.dirname(abs_path))

    def _register_tools_from_module(self, module):
        from modules.hands.builtin_tools.base import ToolBase
        from modules.hands.skills.base import SkillBase
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                issubclass(attr, ToolBase) and
                    attr not in (ToolBase, SkillBase)):
                try:
                    instance = attr()
                    if hasattr(instance, 'set_bus'):
                        instance.set_bus(self.bus)
                    if instance.name:
                        self._tools[instance.name] = instance
                        logger.debug(f"Registered tool: {instance.name}")
                except TypeError:
                    # Skip abstract classes that can't be instantiated
                    pass

    def _tool_schemas(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    # ── Message Handlers ──────────────────────────────────────

    async def _handle_execute(self, topic: str, payload: dict) -> None:
        tool_name = payload.get("tool", "")
        params = payload.get("params", {})
        request_id = payload.get("request_id", str(uuid.uuid4())[:8])
        sandbox = payload.get("sandbox", self.sandbox_default)

        tool = self._tools.get(tool_name)
        if not tool:
            self.bus.publish("status.hand.error", {
                "request_id": request_id,
                "tool": tool_name,
                "error": f"Tool not found: {tool_name}",
            })
            return

        start = time.monotonic()
        try:
            if sandbox:
                result = self._execute_sandboxed(tool, params)
            else:
                result = tool.execute(**params)
            duration_ms = (time.monotonic() - start) * 1000
            self.bus.publish("status.hand.done", {
                "request_id": request_id,
                "result": result,
                "duration_ms": round(duration_ms, 1),
                "tool": tool_name,
            })
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            self.bus.publish("status.hand.error", {
                "request_id": request_id,
                "tool": tool_name,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "duration_ms": round(duration_ms, 1),
            })

    async def _handle_list_tools(self, topic: str, payload: dict) -> None:
        request_id = payload.get("_request_id")
        if request_id:
            self.bus.respond_rpc(request_id, {"tools": self._tool_schemas()})

    def _execute_sandboxed(self, tool, params: dict) -> Any:
        """Execute a tool in restricted mode."""
        from modules.hands.sandbox import Sandbox
        sb = Sandbox(safe_paths=self.safe_paths, timeout=self.command_timeout)
        return sb.run_tool(tool, params)
