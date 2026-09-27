import asyncio
import logging
import uuid
from datetime import datetime, timezone

from aiassistant.base import BaseModule
from aiassistant.bus import topics
from aiassistant.agent.perceive import Perceiver, PerceivedInput
from aiassistant.agent.harness.base import (
    AgentHarness, EventKind, HarnessError, TurnEvent, TurnRequest,
)
from aiassistant.agent.harness.factory import HarnessConfigError, create_harness
from aiassistant.reasoning.factory import ProviderError, resolve_embedding_provider
from aiassistant.agent.transcript import Responder
from aiassistant.agent.memory import MemoryManager
from aiassistant.agent.embeddings import EmbeddingsEngine
from aiassistant.agent.persona import Persona
from aiassistant.agent.toolcache import ToolCache

logger = logging.getLogger(__name__)


class AgentModule(BaseModule):
    """Central intelligence — the agent turn loop."""

    module_name = "agent"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        agent_cfg = config.get("agent", {})
        llm_cfg = agent_cfg.get("llm", {})
        mem_cfg = agent_cfg.get("memory", {})
        emb_cfg = agent_cfg.get("embeddings", {})
        thinking_cfg = agent_cfg.get("thinking", {})

        self.max_reflect_loops = thinking_cfg.get("max_reflect_loops", 3)
        # What to do when input arrives during a turn: "interrupt" (default) or
        # "queue". See docs/contracts/schemas.md (conversation.busy).
        self.busy_policy = config.get("conversation", {}).get("busy", "interrupt")

        # LLM backend (set in setup)
        self.llm_config = llm_cfg

        # Persona
        self.persona = Persona(agent_cfg.get("persona", ""))

        # Memory
        self.memory = MemoryManager(
            conversations_path=mem_cfg.get("conversations_path", ".config/aiassistant/memory/conversations"),
            facts_path=mem_cfg.get("facts_path", ".config/aiassistant/memory/facts"),
            knowledge_path=mem_cfg.get("knowledge_path", ".config/aiassistant/memory/knowledge"),
            embeddings_db_path=mem_cfg.get("embeddings_db", ".config/aiassistant/embeddings.db"),
        )
        self.context_max_tokens = mem_cfg.get("context_max_tokens", 4096)
        self.context_recent_messages = mem_cfg.get("context_recent_messages", 20)

        # Embeddings
        self.embeddings = EmbeddingsEngine(
            db_path=mem_cfg.get("embeddings_db", ".config/aiassistant/embeddings.db"),
        )

        # Tools
        self.tool_cache = ToolCache()

        # Pipeline stages
        self.perceiver = Perceiver()
        self.responder = Responder(
            conversations_path=mem_cfg.get("conversations_path", ".config/aiassistant/memory/conversations"),
            context_recent_messages=self.context_recent_messages,
        )

        # State
        self._pending_tool_requests: dict[str, asyncio.Future] = {}
        self._running = False
        # The active turn. Retaining this handle is what makes interrupt and
        # shutdown able to cancel work in flight; it used to be dropped.
        self._turn_task: asyncio.Task | None = None
        self._turn_cancelled = False
        self._turn_had_response = False
        # Channels permitted to reach a tool-owning harness; empty means all.
        self.allowed_channels: set[str] = set()
        # Persistence jobs outlive the turn; kept so they are not garbage
        # collected mid-flight and can be awaited on shutdown.
        self._background_tasks: set[asyncio.Task] = set()
        # Built in setup(); the loop owner for this agent (native or pi).
        self.harness: AgentHarness | None = None

    async def setup(self) -> bool:
        agent_cfg = dict(self.config.get("agent", {}))
        agent_cfg.setdefault("persona", self.config.get("agent", {}).get("persona", ""))

        try:
            self.harness = create_harness(
                agent_cfg,
                tool_schemas=self.tool_cache.get_formatted_schemas() or None,
            )
        except HarnessConfigError as exc:
            logger.error("Harness not available: %s", exc)
            return False

        # A process-backed harness (pi) must be spawned before probing.
        ensure = getattr(self.harness, "ensure_started", None)
        if ensure is not None:
            try:
                await ensure()
            except FileNotFoundError as exc:
                logger.error("Harness %s cannot start: %s", self.harness.name, exc)
                return False
            except Exception as exc:
                logger.error("Harness %s failed to start: %s", self.harness.name, exc)
                return False

        # Channels allowed to reach this harness. pi is excluded from
        # untrusted channels by default: it runs with the user's permissions
        # (REQ-SEC-003, RISK-0003).
        self.allowed_channels = set(agent_cfg.get("pi", {}).get("allow_channels", [])) \
            if self.harness.caps.owns_tools else set()

        health = await self.harness.health()
        if not health.ok:
            # Do not fail setup: the app must still start and show the problem
            # (REQ-SETUP-003). The turn itself fails visibly instead.
            logger.warning(
                "Harness %s is unhealthy: %s — turns will fail until this is fixed",
                self.harness.name, health.detail,
            )

        # Embeddings use the harness's provider when the harness is our own, so
        # a single configured endpoint serves both.
        emb_cfg = agent_cfg.get("embeddings", {})
        provider = getattr(self.harness, "provider", None)
        if provider is not None:
            try:
                self.embeddings.set_llm(
                    resolve_embedding_provider(emb_cfg, provider)
                )
            except ProviderError as exc:
                logger.warning("Embeddings disabled: %s", exc)

        self.persona = Persona(agent_cfg.get("persona", ""))
        logger.info(
            "Agent setup complete — harness=%s model=%s",
            self.harness.name, getattr(provider, "model", "n/a"),
        )
        return True

    async def start(self) -> None:
        self._running = True

        # Subscribe to all input topics
        self.bus.subscribe(topics.USER_INPUT_TEXT, self._handle_input)
        self.bus.subscribe("sensory.speech.heard", self._handle_input)
        self.bus.subscribe("sensory.speech.hotword", self._handle_hotword)
        self.bus.subscribe(topics.SENSORY_VISION_FRAME, self._handle_input)
        self.bus.subscribe(topics.SCHEDULE_TRIGGERED, self._handle_input)
        self.bus.subscribe(topics.STATUS_TOOL_DONE, self._handle_tool_result)
        self.bus.subscribe(topics.STATUS_TOOL_ERROR, self._handle_tool_result)
        self.bus.subscribe(topics.BUS_MODULE_DISCONNECTED, self._handle_module_disconnect)

        # Register RPC endpoint
        self.bus.subscribe(topics.AGENT_ASK, self._handle_rpc_ask)

        # Load tool schemas when the tools module is ready
        self.bus.subscribe(topics.STATUS_TOOLS_READY, self._handle_hands_ready)

        # Interrupt: cancel the in-flight turn and stop playback.
        self.bus.subscribe(topics.COMMAND_AGENT_INTERRUPT, self._handle_interrupt)

        # The orb requests a transcript snapshot after a delta gap.
        self.bus.subscribe(
            topics.AGENT_TRANSCRIPT_SNAPSHOT + ".request", self._handle_snapshot_request,
        )

        logger.info("Agent started — listening for input")

    async def stop(self) -> None:
        self._running = False
        await self.interrupt()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        if self.harness is not None:
            try:
                await self.harness.close()
            except Exception:
                logger.debug("Harness close raised", exc_info=True)
        logger.info("Agent stopped")

    # ── Interrupt ────────────────────────────────────────────

    async def _handle_interrupt(self, topic: str, payload: dict) -> None:
        await self.interrupt()

    async def _handle_snapshot_request(self, topic: str, payload: dict) -> None:
        """Serve a transcript snapshot so the orb can resync after a gap.

        Rebuilt from the transcript store rather than an in-memory buffer, so it
        works after a reconnect in a fresh orb process.
        """
        try:
            turns = await self._run_blocking(self.memory.get_recent_turns, 50)
        except Exception:
            logger.debug("snapshot read failed", exc_info=True)
            turns = []
        self.bus.publish(topics.AGENT_TRANSCRIPT_SNAPSHOT, {
            "transcript": [
                {"role": t.get("speaker", "assistant"),
                 "text": t.get("content", ""),
                 "streaming": False}
                for t in turns
            ],
        })

    async def interrupt(self) -> None:
        """Cancel the active turn, if any. Safe to call at any time.

        The ordered cancel sequence from docs/requirements/flows.md (c):
        cancel the task, ask the harness to stop, silence playback, end the turn
        as cancelled. A cancelled turn is terminal — no response, no error.
        """
        self._turn_cancelled = True
        task = self._turn_task

        # Ask the harness first: for pi this sends clear_queue + abort, and it
        # must reach the backend before we tear the task down.
        if self.harness is not None and task and not task.done():
            try:
                await self.harness.cancel()
            except Exception:
                logger.debug("Harness cancel raised", exc_info=True)

        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Turn raised during cancel", exc_info=True)
        self._turn_task = None
        self.bus.publish(topics.VOICE_SPEAK, {
            "text": "", "interrupt": True, "source": "cancel",
        })

    async def health(self) -> dict:
        return {
            "status": "ok" if self._running else "stopped",
            "details": {
                "llm_provider": self.llm_config.get("provider"),
                "tools_cached": len(self.tool_cache.tool_names),
                "pending_requests": len(self._pending_tool_requests),
            }
        }

    # ── Input Handlers ───────────────────────────────────────

    async def _handle_input(self, topic: str, payload: dict) -> None:
        perceived = self.perceiver.classify(topic, payload)

        if perceived.is_noise:
            return
        if not perceived.is_addressed_to_assistant:
            return
        if perceived.is_tool_result:
            return  # handled by _handle_tool_result

        self._start_turn(perceived, topic)

    def _start_turn(self, perceived: PerceivedInput, topic: str) -> None:
        """Start a turn, applying the configured busy policy.

        The handle is retained so interrupt and shutdown can cancel it. Under
        the default ``interrupt`` policy a new input supersedes the in-flight
        turn (REQ-CONV-002).
        """
        busy = self._turn_task is not None and not self._turn_task.done()
        if busy:
            logger.info("Turn in flight — superseding it (conversation.busy=%s)",
                        self.busy_policy)
            self._turn_task.cancel()

        self._turn_cancelled = False
        self._turn_task = asyncio.ensure_future(self._thinking_loop(perceived, topic))
        self._turn_task.add_done_callback(self._on_turn_done)

    def _on_turn_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Turn failed", exc_info=exc)

    async def _handle_hotword(self, topic: str, payload: dict) -> None:
        logger.debug(f"Wake word detected: {payload.get('hotword')}")

    async def _handle_tool_result(self, topic: str, payload: dict) -> None:
        request_id = payload.get("request_id")
        if request_id and request_id in self._pending_tool_requests:
            future = self._pending_tool_requests.pop(request_id)
            if not future.done():
                future.set_result(payload)

    async def _handle_module_disconnect(self, topic: str, payload: dict) -> None:
        module_name = payload.get("module_name", "unknown")
        logger.warning(f"Module disconnected: {module_name}")
        # Brain adapts automatically — if mouth is gone, don't publish action.speak

    async def _handle_rpc_ask(self, topic: str, payload: dict) -> None:
        request_id = payload.get("_request_id")
        question = payload.get("question", "")
        if request_id:
            result = await self._quick_answer(question)
            self.bus.respond_rpc(request_id, result)

    async def _handle_hands_ready(self, topic: str, payload: dict) -> None:
        """Load tool schemas when the tools module publishes ready."""
        tools = payload.get("tools", [])
        if not tools:
            return
        self.tool_cache.load(tools)
        schemas = self.tool_cache.get_formatted_schemas()
        # NativeHarness reads schemas per turn; keep it current without a restart.
        harness = self.harness
        if harness is not None and hasattr(harness, "tool_schemas"):
            harness.tool_schemas = schemas
        logger.info("Loaded %d tools from tools module: %s",
                    len(tools), sorted(self.tool_cache.tool_names))

    # ── Turn loop ────────────────────────────────────────────

    async def _thinking_loop(self, perceived: PerceivedInput, topic: str) -> None:
        """Run one turn through the harness and publish its stream.

        The harness owns *how* a turn is reasoned; this method owns the bus
        contract around it: it builds the request, maps every harness event to a
        topic, and persists the turn exactly once. Nothing here branches on which
        harness is running.
        """
        payload = perceived.raw_payload
        channel = payload.get("channel") or payload.get("source") or ""
        should_speak = topics.should_speak(channel)

        # A tool-owning harness (pi) must not accept untrusted input channels
        # unless explicitly allowed (REQ-SEC-003, RISK-0003).
        if self.allowed_channels and channel and channel not in self.allowed_channels:
            logger.warning(
                "Channel %r is not allowed to reach the %s harness; ignoring",
                channel, self.harness.name,
            )
            self.bus.publish(topics.AGENT_TURN_ERROR, {
                "message": "That input channel is not enabled for this assistant.",
                "class": "config",
                "hint": "Add the channel to agents.<id>.pi.allow_channels to enable it.",
            })
            return

        try:
            text = self._extract_text(perceived)
            if not text:
                return

            self._turn_had_response = False
            req = TurnRequest(
                text=text,
                turn_id=str(uuid.uuid4())[:8],
                channel=channel,
                execute_tool=self._execute_tool,
                memory_context=await self._assemble_memory_context(text),
                tool_schemas=self.tool_cache.get_formatted_schemas() or None,
            )

            await self._record_user_turn(text)

            final_text = ""
            thinking_parts: list[str] = []
            tools_used: list[dict] = []
            usage: dict = {}
            delta_index = 0

            async for event in self.harness.run_turn(req):
                if event.kind is EventKind.TEXT_DELTA:
                    self.bus.publish(topics.AGENT_DELTA, {
                        "kind": "text", "text": event.text, "index": delta_index,
                    })
                    delta_index += 1

                elif event.kind is EventKind.THINKING_DELTA:
                    thinking_parts.append(event.text)
                    self.bus.publish(topics.AGENT_DELTA, {
                        "kind": "thinking", "text": event.text, "index": delta_index,
                    })
                    delta_index += 1

                elif event.kind is EventKind.TOOL_CALL:
                    self.bus.publish(topics.AGENT_TOOL_EVENT, {
                        "call_id": event.call_id, "name": event.tool_name,
                        "status": "running", "args": event.args,
                        "source": self.harness.name,
                    })

                elif event.kind is EventKind.TOOL_RESULT:
                    tools_used.append({
                        "name": event.tool_name, "call_id": event.call_id,
                        "is_error": event.is_error,
                    })
                    self.bus.publish(topics.AGENT_TOOL_EVENT, {
                        "call_id": event.call_id, "name": event.tool_name,
                        "status": "error" if event.is_error else "done",
                        "result": event.result,
                        "source": self.harness.name,
                    })

                elif event.kind is EventKind.USAGE:
                    usage = event.usage

                elif event.kind is EventKind.TEXT_FINAL:
                    final_text = event.text

                elif event.kind is EventKind.TURN_DONE:
                    # Cancelled turns are terminal and produce no response.
                    if event.cancelled:
                        logger.info("Turn %s cancelled", req.turn_id)
                        return
                    self._finish_turn(
                        final_text, thinking_parts, tools_used, usage, should_speak,
                    )
                    return

                elif event.kind is EventKind.TURN_ERROR:
                    self._fail_turn(event, should_speak)
                    return

            # The harness ended without a terminal event: a contract violation,
            # but the turn must still terminate visibly (REQ-CONV-006).
            self._fail_turn(
                TurnEvent(kind=EventKind.TURN_ERROR, text="Harness ended without a terminal event"),
                should_speak,
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Turn failed: %s", exc)
            self._fail_turn(
                TurnEvent(kind=EventKind.TURN_ERROR, text=str(exc)),
                should_speak,
            )

    def _finish_turn(
        self,
        final_text: str,
        thinking_parts: list[str],
        tools_used: list[dict],
        usage: dict,
        should_speak: bool,
    ) -> None:
        final_text = final_text or "I'm not sure how to respond to that."
        thinking = "\n".join(thinking_parts).strip() or None

        response = self.responder.respond(
            text=final_text, thinking=thinking, tools_used=tools_used,
        )
        self._turn_had_response = True
        payload = {
            "text": response["text"],
            "conversation_id": response.get("conversation_id"),
            "thinking": thinking,
            "tools_used": tools_used,
        }
        self.bus.publish(topics.AGENT_FINAL, {**payload, "usage": usage, "harness": self.harness.name})
        # The frozen messaging module and the console still consume response.text.
        self.bus.publish(topics.MESSAGING_RESPONSE, payload)
        if should_speak:
            self.bus.publish(topics.VOICE_SPEAK, {
                "text": response["text"], "voice": None,
                "speed": 1.0, "interrupt": False,
            })
        # Persist in the background. This must NOT reassign _turn_task: the turn
        # task is still running (we are inside it), and clobbering the handle
        # would make interrupt cancel the save instead of the turn.
        save = asyncio.ensure_future(self._save_response(response, tools_used))
        self._background_tasks.add(save)
        save.add_done_callback(self._background_tasks.discard)

    def _fail_turn(self, event, should_speak: bool) -> None:
        self._turn_had_response = True
        message = "Something went wrong while processing that. Can you try again?"
        logger.error("Turn error (%s): %s", event.error_class, event.text)
        self.bus.publish(topics.AGENT_TURN_ERROR, {
            "message": message,
            "detail": event.text,
            "class": event.error_class or "harness",
            "hint": _error_hint(event.error_class),
        })
        self.bus.publish(topics.MESSAGING_RESPONSE, {
            "text": message, "conversation_id": None, "thinking": None,
            "tools_used": [],
        })

    async def _record_user_turn(self, text: str) -> None:
        now = datetime.now(timezone.utc)
        self.responder.save_turn("user", text)
        try:
            await self._run_blocking(
                self.embeddings.index_conversation_turn,
                now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "user", text,
            )
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────

    def _extract_text(self, perceived: PerceivedInput) -> str:
        p = perceived.raw_payload
        if perceived.input_type == "text":
            return p.get("text", "")
        if perceived.input_type == "speech":
            return p.get("text", "")
        if perceived.input_type == "vision":
            return p.get("description", "")
        if perceived.input_type == "schedule":
            return f"Reminder: {p.get('task', '')} — {p.get('description', '')}"
        return p.get("text", str(p))

    async def _assemble_memory_context(self, query: str) -> str:
        parts = []
        recent = self.memory.get_recent_turns(self.context_recent_messages)
        if recent:
            lines = [f"{t['speaker']}: {t['content'][:200]}" for t in recent[-10:]]
            parts.append("Recent conversation:\n" + "\n".join(lines))

        try:
            facts = await self._run_blocking(self.embeddings.search_facts, query, 3)
            if facts:
                lines = [f"[{f['category']}] {f['fact']}" for f in facts]
                parts.append("Remembered facts:\n" + "\n".join(lines))
        except Exception:
            pass  # embeddings unavailable, skip

        return "\n\n".join(parts)

    @staticmethod
    async def _run_blocking(fn, *args, **kwargs):
        """Run a synchronous provider/embedding call off the event loop.

        The provider SDKs block. Calling them directly from a coroutine stalls
        every other module on the bus, which is why streaming and interrupt
        could not work.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def _execute_tool(self, name: str, params: dict) -> dict:
        request_id = str(uuid.uuid4())[:8]
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_tool_requests[request_id] = future

        self.bus.publish(topics.TOOL_EXECUTE, {
            "tool": name,
            "params": params,
            "request_id": request_id,
        })

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            self._pending_tool_requests.pop(request_id, None)
            return {"request_id": request_id, "error": "Tool execution timed out"}

    def _deliver_response(self, response: dict, should_speak: bool = False) -> None:
        """Legacy publish path, kept for callers that build a response dict.

        New code goes through ``_finish_turn``; this stays because tests and the
        RPC quick-answer path both use it.
        """
        self.bus.publish(topics.AGENT_FINAL, {
            "text": response["text"],
            "conversation_id": response["conversation_id"],
            "thinking": response.get("thinking"),
            "tools_used": response.get("tools_used", []),
        })
        self.bus.publish(topics.MESSAGING_RESPONSE, {
            "text": response["text"],
            "conversation_id": response["conversation_id"],
            "thinking": response.get("thinking"),
            "tools_used": response.get("tools_used", []),
        })
        # Only speak when the turn came from the voice channel (topics.should_speak).
        if should_speak:
            self.bus.publish(topics.VOICE_SPEAK, {
                "text": response["text"],
                "voice": None,
                "speed": 1.0,
                "interrupt": False,
            })

    async def _save_response(self, response: dict, tools_used: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        self.responder.save_turn("assistant", response["text"],
                                 thinking=response.get("thinking"),
                                 tools_used=tools_used)
        try:
            await self._run_blocking(
                self.embeddings.index_conversation_turn,
                now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
                "assistant", response["text"],
            )
        except Exception:
            pass

    async def _quick_answer(self, question: str) -> dict:
        """Answer a short subtask for a skill, without a full turn."""
        provider = getattr(self.harness, "provider", None)
        if provider is None:
            return {"answer": "", "thinking": None}
        messages = [{"role": "user", "content": question}]
        response = await self._run_blocking(provider.chat, messages, max_tokens=256)
        return {"answer": response.get("content", ""), "thinking": None}


def _error_hint(error_class: str) -> str:
    """A recovery hint for the UI (REQ-ERR-001). Never empty."""
    return {
        "config": "Check the agent's provider and model settings, then retry.",
        "harness": "The reasoning backend did not respond. Retry, or switch harness.",
        "tool": "The tool could not run. Retry, or rephrase the request.",
        "audio": "Check the microphone and speaker, then retry from the UI.",
        "memory": "The turn could not be saved. Check disk space and memory paths.",
    }.get(error_class, "Retry the request.")
