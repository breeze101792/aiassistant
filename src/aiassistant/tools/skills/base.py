import asyncio
import uuid

from aiassistant.tools.builtin_tools.base import ToolBase


class SkillBase(ToolBase):
    """A skill is a tool that orchestrates other tools and agent subtasks.

    Same contract as ToolBase (name, description, parameters, execute), so the
    model sees skills and tools identically. Internally a skill chains calls:

    call_tool() — runs another tool over the bus and awaits its result
    call_llm()  — asks the agent for a reasoning subtask over the bus RPC
    """

    TOOL_TIMEOUT_S = 30.0
    LLM_TIMEOUT_S = 60.0

    def __init__(self):
        self._bus = None

    def set_bus(self, bus):
        self._bus = bus

    async def call_tool(self, name: str, **params):
        """Execute another tool and return its result.

        Uses the bus RPC path, which correlates the request and response by id.
        The previous implementation subscribed to ``status.hand.done`` and then
        called ``run_until_complete`` from inside a running loop, which raises
        immediately.
        """
        if not self._bus:
            raise RuntimeError("Skill has no bus reference — set_bus() not called")

        from aiassistant.bus import topics

        request_id = str(uuid.uuid4())[:8]
        done = asyncio.get_running_loop().create_future()

        def on_done(topic, payload):
            if payload.get("request_id") == request_id and not done.done():
                done.set_result(payload.get("result"))

        def on_error(topic, payload):
            if payload.get("request_id") == request_id and not done.done():
                done.set_exception(RuntimeError(payload.get("error", "Tool failed")))

        sub_done = self._bus.subscribe(topics.STATUS_TOOL_DONE, on_done)
        sub_error = self._bus.subscribe(topics.STATUS_TOOL_ERROR, on_error)
        try:
            self._bus.publish(topics.TOOL_EXECUTE, {
                "tool": name,
                "params": params,
                "request_id": request_id,
            })
            return await asyncio.wait_for(done, timeout=self.TOOL_TIMEOUT_S)
        finally:
            self._bus.unsubscribe(sub_done)
            self._bus.unsubscribe(sub_error)

    async def call_llm(self, prompt: str, context: list | None = None):
        """Ask the agent for a reasoning subtask, via the bus RPC endpoint.

        The previous implementation subscribed to ``brain.ask.response``, which
        is never published — the agent answers through ``respond_rpc`` — so the
        call could only ever time out.
        """
        if not self._bus:
            raise RuntimeError("Skill has no bus reference")

        from aiassistant.bus import topics

        try:
            result = await self._bus.request(
                topics.AGENT_ASK,
                {"question": prompt, "context": context},
                timeout=self.LLM_TIMEOUT_S,
            )
            return result.get("answer", "")
        except Exception:
            return "LLM call timed out"
