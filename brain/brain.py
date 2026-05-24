import asyncio
import logging
import uuid
from datetime import datetime, timezone

from modules.base import BaseModule
from brain.perceive import Perceiver, PerceivedInput
from brain.understand import Understander
from brain.reason import Reasoner
from brain.plan import Planner
from brain.reflect import Reflector, ReflectVerdict
from brain.respond import Responder
from brain.memory import MemoryManager
from brain.embeddings import EmbeddingsEngine
from brain.persona import Persona
from brain.tools import ToolCache

logger = logging.getLogger(__name__)


class BrainModule(BaseModule):
    """Central intelligence — 7-stage thinking loop."""

    module_name = "brain"

    def __init__(self, bus, config: dict):
        super().__init__(bus, config)
        brain_cfg = config.get("brain", {})
        llm_cfg = brain_cfg.get("llm", {})
        mem_cfg = brain_cfg.get("memory", {})
        emb_cfg = brain_cfg.get("embeddings", {})
        thinking_cfg = brain_cfg.get("thinking", {})

        self.max_reflect_loops = thinking_cfg.get("max_reflect_loops", 3)

        # LLM backend (set in setup)
        self.llm = None
        self.llm_config = llm_cfg

        # Persona
        self.persona = Persona(brain_cfg.get("persona", ""))

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
        self.understander = Understander()
        self.planner = Planner()
        self.reflector = Reflector(max_loops=self.max_reflect_loops)
        self.responder = Responder(
            conversations_path=mem_cfg.get("conversations_path", ".config/aiassistant/memory/conversations"),
            context_recent_messages=self.context_recent_messages,
        )

        # State
        self._pending_tool_requests: dict[str, asyncio.Future] = {}
        self._running = False

    async def setup(self) -> bool:
        # Resolve LLM backend
        provider = self.llm_config.get("provider", "ollama")
        model = self.llm_config.get("model", "qwen3:1.7b")
        url = self.llm_config.get("url", "")

        if provider == "ollama":
            from llm.ollama import OllamaBackend
            self.llm = OllamaBackend(model=model, url=url or "http://127.0.0.1:11434")
        elif provider == "openai":
            from llm.openai import OpenAIBackend
            api_key = self.llm_config.get("api_key", "")
            self.llm = OpenAIBackend(model=model, url=url or "https://api.openai.com/v1", api_key=api_key)
        else:
            logger.error(f"Unknown LLM provider: {provider}")
            return False

        # Resolve embeddings backend (may be different from chat LLM)
        emb_cfg = self.config.get("brain", {}).get("embeddings", {})
        emb_provider = emb_cfg.get("provider", "same")
        emb_model = emb_cfg.get("model", "")
        emb_url = emb_cfg.get("url", "")
        if emb_provider == "same":
            self.embeddings.set_llm(self.llm)
        elif emb_provider == "ollama":
            from llm.ollama import OllamaBackend
            emb_llm = OllamaBackend(model=emb_model or model, url=emb_url or url or "http://127.0.0.1:11434")
            self.embeddings.set_llm(emb_llm)
            logger.info(f"Embeddings backend: ollama/{emb_model or model}")
        elif emb_provider == "openai":
            from llm.openai import OpenAIBackend
            emb_llm = OpenAIBackend(model=emb_model or "text-embedding-3-small", url=emb_url or "https://api.openai.com/v1", api_key=self.llm_config.get("api_key", ""))
            self.embeddings.set_llm(emb_llm)
            logger.info(f"Embeddings backend: openai/{emb_model or 'text-embedding-3-small'}")
        else:
            logger.warning(f"Unknown embeddings provider: {emb_provider}, embeddings disabled")

        self.persona = Persona(self.config.get("brain", {}).get("persona", ""))
        self._reasoner = Reasoner(
            self.llm, self.persona.get_system_prompt(),
            compress_target=600,
            context_max_tokens=self.context_max_tokens,
        )

        logger.info(f"Brain setup complete — provider={provider}, model={model}")
        return True

    async def start(self) -> None:
        self._running = True

        # Subscribe to all input topics
        self.bus.subscribe("user.input.text", self._handle_input)
        self.bus.subscribe("sensory.speech.heard", self._handle_input)
        self.bus.subscribe("sensory.speech.hotword", self._handle_hotword)
        self.bus.subscribe("sensory.vision.frame", self._handle_input)
        self.bus.subscribe("sensory.canvas.click", self._handle_input)
        self.bus.subscribe("sensory.canvas.input", self._handle_input)
        self.bus.subscribe("sensory.canvas.draw", self._handle_input)
        self.bus.subscribe("schedule.triggered", self._handle_input)
        self.bus.subscribe("status.hand.done", self._handle_tool_result)
        self.bus.subscribe("status.hand.error", self._handle_tool_result)
        self.bus.subscribe("bus.module.disconnected", self._handle_module_disconnect)

        # Register RPC endpoint
        self.bus.subscribe("brain.ask", self._handle_rpc_ask)

        # Load tool schemas when Hands module is ready
        self.bus.subscribe("status.hands.ready", self._handle_hands_ready)

        logger.info("Brain started — listening for input")

    async def stop(self) -> None:
        self._running = False
        logger.info("Brain stopped")

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

        asyncio.ensure_future(self._thinking_loop(perceived, topic))

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
        """Load tool schemas when Hands publishes ready."""
        tools = payload.get("tools", [])
        if tools:
            self.tool_cache.load(tools)
            self._reasoner.set_tools(self.tool_cache.get_formatted_schemas())
            logger.info(f"Loaded {len(tools)} tools from Hands: {sorted(self.tool_cache.tool_names)}")

    # ── Thinking Loop ────────────────────────────────────────

    async def _thinking_loop(self, perceived: PerceivedInput, topic: str) -> None:
        try:
            self.reflector.reset()

            # Determine if this input should trigger speech output
            should_speak = perceived.raw_payload.get("source") == "ears"

            # 1. PERCEIVE — already done

            # 2. UNDERSTAND
            text = self._extract_text(perceived)
            if not text:
                return

            intent = self.understander.classify(text)
            if intent.needs_clarification:
                response = self.responder.respond(
                    text=intent.clarification_question or "Could you repeat that?"
                )
                self._deliver_response(response, should_speak)
                return

            logger.debug(f"Intent: {intent.type}, urgency: {intent.urgency}")

            # 3. REASON
            memory_context = self._assemble_memory_context(text)

            llm_response = self._reasoner.reason(
                user_message=text,
                memory_context=memory_context,
            )

            # Record user turn
            now = datetime.now(timezone.utc)
            self.responder.save_turn("user", text)
            try:
                self.embeddings.index_conversation_turn(
                    now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "user", text
                )
            except Exception:
                pass

            # 4. PLAN
            has_tools = bool(self.tool_cache.tool_names)
            plan = self.planner.decide(
                intent_type=intent.type,
                llm_response=llm_response,
                has_tools=has_tools,
            )

            # 5. ACT (if needed)
            tools_used = []
            tool_results_for_feedback = []
            if plan.action == "call_tool" and plan.tool_calls:
                raw_tool_calls = llm_response.get("tool_calls") or []
                for i, tc in enumerate(plan.tool_calls):
                    tool_result = await self._execute_tool(tc.name, tc.arguments or {})
                    tools_used.append({
                        "name": tc.name,
                        "request_id": tool_result.get("request_id", "?"),
                        "duration_ms": tool_result.get("duration_ms", 0),
                    })

                    # 6. REFLECT per tool
                    error = tool_result.get("error")
                    result_data = tool_result.get("result")
                    reflection = self.reflector.evaluate(
                        tool_result=result_data,
                        error=error,
                        goal=text,
                    )

                    if reflection.verdict == ReflectVerdict.ABORT:
                        response = self.responder.respond(
                            text=f"Sorry, I wasn't able to complete that: {error}",
                            thinking=plan.reasoning,
                            tools_used=tools_used,
                        )
                        self._deliver_response(response, should_speak)
                        self._save_response(response, tools_used)
                        return

                    # Collect for feedback loop
                    raw_tc = raw_tool_calls[i] if i < len(raw_tool_calls) else {}
                    tool_results_for_feedback.append({
                        "call": raw_tc,
                        "result": result_data,
                    })

                # Let LLM synthesize a response from tool results
                if tool_results_for_feedback:
                    calls = [t["call"] for t in tool_results_for_feedback]
                    results = [{"result": t["result"]} for t in tool_results_for_feedback]
                    synthesis = self._reasoner.reason_with_tool_results(calls, results)
                    llm_response = synthesis

            # 7. RESPOND
            final_text = llm_response.get("content") or "I'm not sure how to respond to that."
            response = self.responder.respond(
                text=final_text,
                thinking=plan.reasoning,
                tools_used=tools_used,
            )
            self._deliver_response(response, should_speak)
            self._save_response(response, tools_used)

        except Exception as e:
            logger.exception(f"Error in thinking loop: {e}")
            error_response = self.responder.respond(
                text="Something went wrong while processing that. Can you try again?"
            )
            self._deliver_response(error_response, should_speak)

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
        if perceived.input_type == "canvas":
            return p.get("text", "") or f"Canvas interaction at ({p.get('x', 0)}, {p.get('y', 0)})"
        return p.get("text", str(p))

    def _assemble_memory_context(self, query: str) -> str:
        parts = []
        recent = self.memory.get_recent_turns(self.context_recent_messages)
        if recent:
            lines = [f"{t['speaker']}: {t['content'][:200]}" for t in recent[-10:]]
            parts.append("Recent conversation:\n" + "\n".join(lines))

        try:
            facts = self.embeddings.search_facts(query, top_k=3)
            if facts:
                lines = [f"[{f['category']}] {f['fact']}" for f in facts]
                parts.append("Remembered facts:\n" + "\n".join(lines))
        except Exception:
            pass  # embeddings unavailable, skip

        return "\n\n".join(parts)

    async def _execute_tool(self, name: str, params: dict) -> dict:
        request_id = str(uuid.uuid4())[:8]
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_tool_requests[request_id] = future

        self.bus.publish("action.execute", {
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
        self.bus.publish("response.text", {
            "text": response["text"],
            "conversation_id": response["conversation_id"],
            "thinking": response.get("thinking"),
            "tools_used": response.get("tools_used", []),
        })
        # Only speak when input came from voice (ears)
        if should_speak:
            self.bus.publish("action.speak", {
                "text": response["text"],
                "voice": None,
                "speed": 1.0,
                "interrupt": False,
            })

    def _save_response(self, response: dict, tools_used: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        self.responder.save_turn("assistant", response["text"],
                                 thinking=response.get("thinking"),
                                 tools_used=tools_used)
        try:
            self.embeddings.index_conversation_turn(
                now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "assistant", response["text"]
            )
        except Exception:
            pass

    async def _quick_answer(self, question: str) -> dict:
        messages = [{"role": "user", "content": question}]
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.llm.chat, messages)
        return {"answer": response.get("content", ""), "thinking": None}
