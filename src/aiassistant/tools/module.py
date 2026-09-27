import asyncio
import importlib
import logging
import pkgutil
import time
import traceback
import uuid
from typing import Any

from aiassistant.bus import topics
from aiassistant.base import BaseModule

logger = logging.getLogger(__name__)


class ToolsModule(BaseModule):
    """Executes tools and skills. The hands of the assistant."""

    module_name = "tools"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        tools_cfg = config.get("tools", {})
        self.package_paths: list[str] = tools_cfg.get("packages", [
            "aiassistant.tools.builtin_tools",
            "aiassistant.tools.skills",
        ])
        self.sandbox_default: bool = tools_cfg.get("sandbox_default", False)
        self.command_timeout: float = tools_cfg.get("command_timeout", 30.0)
        self.safe_paths: list[str] = tools_cfg.get("safe_paths", ["./workspace", "/tmp/aiassistant"])
        self._tools: dict[str, Any] = {}

    async def setup(self) -> bool:
        self._load_all_tools()
        logger.info("Tools setup complete — %d tools loaded: %s",
                    len(self._tools), list(self._tools.keys()))
        return True

    async def start(self) -> None:
        self.bus.subscribe(topics.TOOL_EXECUTE, self._handle_execute)
        self.bus.subscribe("tools.list_tools", self._handle_list_tools)

        # Announce available tools to the agent.
        self.bus.publish(topics.STATUS_TOOLS_READY, {
            "tools": self._tool_schemas(),
            "remote_targets": [],
        })
        logger.info("Tools started — published tool list")

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
        """Discover tools by importing each configured package and scanning it.

        Packages are imported by dotted name, so discovery works the same from
        source, an installed package, or a frozen build. Tools must live inside
        an importable package; a loose directory of files is not supported.
        """
        for package in self.package_paths:
            try:
                pkg = importlib.import_module(package)
            except Exception as e:
                logger.warning("Tool package %s not importable: %s", package, e)
                continue
            for _, mod_name, _ in pkgutil.iter_modules(pkg.__path__):
                if mod_name in ("base", "__init__"):
                    continue
                try:
                    module = importlib.import_module(f"{package}.{mod_name}")
                    self._register_tools_from_module(module)
                except Exception as e:
                    logger.warning("Failed to load tool module %s: %s", mod_name, e)

    def _register_tools_from_module(self, module):
        from aiassistant.tools.builtin_tools.base import ToolBase
        from aiassistant.tools.skills.base import SkillBase
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
            self.bus.publish(topics.STATUS_TOOL_ERROR, {
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
            if asyncio.iscoroutine(result):
                result = await result
            duration_ms = (time.monotonic() - start) * 1000
            self.bus.publish(topics.STATUS_TOOL_DONE, {
                "request_id": request_id,
                "result": result,
                "duration_ms": round(duration_ms, 1),
                "tool": tool_name,
            })
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            self.bus.publish(topics.STATUS_TOOL_ERROR, {
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
        from aiassistant.tools.sandbox import Sandbox
        sb = Sandbox(safe_paths=self.safe_paths, timeout=self.command_timeout)
        return sb.run_tool(tool, params)
