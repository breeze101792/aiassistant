import asyncio

from modules.hands.builtin_tools.base import ToolBase


class SkillBase(ToolBase):
    """A skill is a tool that orchestrates other tools + LLM calls.

    Same contract as ToolBase (name, description, parameters, execute)
    so the LLM sees them identically. Internally, skills chain multiple
    tool calls and optionally call the LLM for reasoning subtasks.

    call_tool() — publishes action.execute, waits for status.hand.done
    call_llm()   — calls brain.ask RPC for reasoning/subtasks
    """

    def __init__(self):
        self._bus = None

    def set_bus(self, bus):
        self._bus = bus

    def call_tool(self, name: str, **params):
        """Execute another tool and return its result."""
        if not self._bus:
            raise RuntimeError("Skill has no bus reference — set_bus() not called")

        import uuid
        request_id = str(uuid.uuid4())[:8]
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_done(topic, payload):
            if payload.get("request_id") == request_id and not future.done():
                future.set_result(payload.get("result"))

        def on_error(topic, payload):
            if payload.get("request_id") == request_id and not future.done():
                future.set_exception(RuntimeError(payload.get("error", "Tool failed")))

        sub_done = self._bus.subscribe("status.hand.done", on_done)
        sub_error = self._bus.subscribe("status.hand.error", on_error)

        try:
            self._bus.publish("action.execute", {
                "tool": name,
                "params": params,
                "request_id": request_id,
            })
            result = asyncio.get_event_loop().run_until_complete(
                asyncio.wait_for(future, timeout=30.0)
            )
            return result
        finally:
            self._bus.unsubscribe(sub_done)
            self._bus.unsubscribe(sub_error)

    def call_llm(self, prompt: str, context: list | None = None):
        """Call the brain for reasoning/subtasks via RPC."""
        if not self._bus:
            raise RuntimeError("Skill has no bus reference")

        future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(topic, payload):
            if not future.done():
                future.set_result(payload)

        sub = self._bus.subscribe("brain.ask.response", on_response)
        try:
            self._bus.publish("brain.ask", {"question": prompt, "context": context})
            result = asyncio.get_event_loop().run_until_complete(
                asyncio.wait_for(future, timeout=60.0)
            )
            return result.get("answer", "")
        except asyncio.TimeoutError:
            return "LLM call timed out"
        finally:
            self._bus.unsubscribe(sub)
