"""The pi harness: drive the external pi coding agent as an AgentHarness.

pi owns its own loop, its own tools, and its own session context, so this
adapter's job is narrow and deliberate:

* spawn and supervise one child process (``process.py``),
* frame commands and responses over JSONL (``protocol.py``),
* map pi's events onto our vocabulary (``events.py``),
* gate on the documented turn boundary (``agent_settled``).

It does **not** inject our memory context into prompts except for one prime
after a crash, because pi already holds session context and double-contexting
would duplicate it (ADR-0008, REQ-MEM-004).
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from aiassistant.agent.harness.base import (
    AgentHarness,
    EventKind,
    HarnessCaps,
    HarnessHealth,
    TurnEvent,
    TurnRequest,
)
from aiassistant.agent.harness.pi import events as pi_events
from aiassistant.agent.harness.pi.process import (
    BUILTIN_GUARD,
    DEFAULT_WORKSPACE,
    PiProcess,
    PiProcessConfig,
)
from aiassistant.agent.harness.pi.protocol import (
    ABORT,
    CLEAR_QUEUE,
    GET_STATE,
    ProtocolError,
    RpcMessage,
    command_request,
    decode,
    prompt_request,
)

logger = logging.getLogger(__name__)

# The message prime is bounded; pi gets continuity, not our whole transcript.
_PRIME_TURNS = 6
_PROMPT_ACK_TIMEOUT_S = 30.0
_ABORT_TIMEOUT_S = 10.0


class PiHarness(AgentHarness):
    """pi as a managed child process."""

    name = "pi"

    def __init__(self, pi_cfg: dict):
        self.cfg = PiProcessConfig(
            command=pi_cfg.get("command", "pi"),
            workspace=pi_cfg.get("workspace", DEFAULT_WORKSPACE),
            tools=pi_cfg.get("tools") or PiProcessConfig().tools,
            policy_extension=pi_cfg.get("policy_extension", BUILTIN_GUARD),
            no_session=pi_cfg.get("no_session", True),
            restart_backoff_s=pi_cfg.get("restart_backoff_s") or [1, 2, 4, 8, 30],
            model=pi_cfg.get("model", ""),
        )
        self.turn_timeout_s = pi_cfg.get("turn_timeout_s", 300)
        self.memory_prime_on_start = pi_cfg.get("memory_prime_on_start", True)

        self._proc: PiProcess | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._turn_queue: asyncio.Queue | None = None
        self._turn_active = False
        self._abort_pending: asyncio.Future | None = None
        self._needs_prime = False

    # ── Contract ─────────────────────────────────────────────

    @property
    def caps(self) -> HarnessCaps:
        # pi runs its own tools and holds its own context; we only observe.
        return HarnessCaps(
            owns_tools=True,
            owns_memory=True,
            streaming=True,
            cancellable=True,
            usage_reporting=True,
        )

    async def health(self) -> HarnessHealth:
        if self._proc is None or not self._proc.running:
            return HarnessHealth(ok=False, detail="pi process is not running")
        try:
            response = await self._command(GET_STATE, timeout=5.0)
        except Exception as exc:
            return HarnessHealth(ok=False, detail=f"{type(exc).__name__}: {exc}")
        if response.success:
            return HarnessHealth(ok=True, detail="pi rpc ready")
        return HarnessHealth(ok=False, detail=response.error or "get_state failed")

    async def ensure_started(self) -> None:
        """Spawn the child if it is not running. Called by setup and on demand."""
        if self._proc is not None and self._proc.running:
            return
        self._proc = PiProcess(
            self.cfg,
            on_message=self._on_message,
            on_exit=self._on_exit,
        )
        await self._proc.start()
        self._needs_prime = self.memory_prime_on_start

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[TurnEvent]:
        if self._turn_active:
            yield TurnEvent(
                kind=EventKind.TURN_ERROR,
                text="pi already has a turn in flight",
                error_class="harness",
            )
            return
        if self._proc is None or not self._proc.running:
            yield TurnEvent(
                kind=EventKind.TURN_ERROR,
                text="pi is not running",
                error_class="harness",
            )
            return

        self._turn_active = True
        self._turn_queue = asyncio.Queue()
        prompt = self._build_prompt(req)

        try:
            request_id = f"turn-{uuid.uuid4().hex[:8]}"
            self._proc.send(prompt_request(request_id, prompt))
            try:
                ack = await self._await_response(request_id, _PROMPT_ACK_TIMEOUT_S)
            except asyncio.TimeoutError:
                yield TurnEvent(
                    kind=EventKind.TURN_ERROR,
                    text="pi did not acknowledge the prompt",
                    error_class="harness",
                )
                return

            if not ack.success:
                yield TurnEvent(
                    kind=EventKind.TURN_ERROR,
                    text=ack.error or "pi rejected the prompt",
                    error_class=_classify(ack.error),
                )
                return

            # `disposition: handled` means no run started, so no agent_settled
            # will arrive; the prompt was consumed by an extension.
            if ack.data.get("disposition") == "handled":
                yield TurnEvent(kind=EventKind.TURN_DONE)
                return

            async for event in self._stream_turn_events():
                yield event

        finally:
            self._turn_active = False
            self._turn_queue = None
            self._needs_prime = False

    async def cancel(self) -> None:
        """clear_queue then abort. Never closes stdin — that is shutdown."""
        if self._proc is None or not self._proc.running or not self._turn_active:
            return
        try:
            await self._command(CLEAR_QUEUE, timeout=_ABORT_TIMEOUT_S)
        except Exception:
            logger.debug("clear_queue failed", exc_info=True)
        try:
            await self._command(ABORT, timeout=_ABORT_TIMEOUT_S)
        except Exception:
            logger.warning("abort did not complete; the turn may keep running")

    async def close(self) -> None:
        if self._proc is not None:
            await self._proc.close()
            self._proc = None

    # ── Turn streaming ───────────────────────────────────────

    async def _stream_turn_events(self) -> AsyncIterator[TurnEvent]:
        """Drain events until the turn boundary, with a watchdog."""
        queue = self._turn_queue
        assert queue is not None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.turn_timeout_s

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                yield TurnEvent(
                    kind=EventKind.TURN_ERROR,
                    text=f"pi turn exceeded {self.turn_timeout_s}s",
                    error_class="harness",
                )
                return
            try:
                item = await asyncio.wait_for(queue.get(), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                continue

            if item is _TURN_LOST:
                yield TurnEvent(
                    kind=EventKind.TURN_ERROR,
                    text="pi exited during the turn",
                    error_class="harness",
                )
                return

            for event in item:
                yield event
                if event.kind is EventKind.TURN_DONE:
                    return
                if event.kind is EventKind.TURN_ERROR:
                    return

    # ── Message routing ──────────────────────────────────────

    def _on_message(self, message: RpcMessage) -> None:
        if not message.is_event:
            future = self._pending.get(message.id or "")
            if future and not future.done():
                future.set_result(message)
            return

        if message.type == "response" and self._abort_pending:
            if not self._abort_pending.done():
                self._abort_pending.set_result(message)
            return

        mapped = pi_events.map_event(message)
        if mapped and self._turn_queue is not None:
            self._turn_queue.put_nowait(mapped)

    def _on_exit(self, code: int | None) -> None:
        """Fail the active turn, then attempt a supervised restart."""
        if self._turn_queue is not None:
            self._turn_queue.put_nowait(_TURN_LOST)
        self._restart_task = asyncio.ensure_future(self._restart())

    async def _restart(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            await proc.restart()
            self._needs_prime = self.memory_prime_on_start
        except Exception:
            logger.exception("pi restart failed")

    # ── Commands ─────────────────────────────────────────────

    async def _command(self, command: str, timeout: float) -> RpcMessage:
        if self._proc is None:
            raise BrokenPipeError("pi is not running")
        request_id = f"cmd-{uuid.uuid4().hex[:8]}"
        self._pending[request_id] = asyncio.get_running_loop().create_future()
        try:
            self._proc.send(command_request(request_id, command))
            return await self._await_response(request_id, timeout)
        finally:
            self._pending.pop(request_id, None)

    async def _await_response(self, request_id: str, timeout: float) -> RpcMessage:
        future = self._pending.get(request_id)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
        return await asyncio.wait_for(future, timeout=timeout)

    # ── Prompt construction ──────────────────────────────────

    def _build_prompt(self, req: TurnRequest) -> str:
        """The bare user text, plus a one-time prime after a (re)start.

        pi holds its own session, so injecting our memory context every turn
        would double-context it. The exception is the first turn after a
        restart, where a compact summary restores continuity.
        """
        if self._needs_prime and req.memory_context:
            return (
                "Context from before this session (previous conversation):\n"
                f"{req.memory_context}\n\n"
                f"User: {req.text}"
            )
        return req.text


def _classify(error: str) -> str:
    lowered = (error or "").lower()
    if "model" in lowered or "auth" in lowered or "api key" in lowered:
        return "config"
    return "harness"


# Marker pushed onto the turn queue when the child dies mid-turn.
_TURN_LOST = object()
