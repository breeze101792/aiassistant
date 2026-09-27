"""pi child-process lifecycle.

Owns the spawn, the stdout reader, the stderr drain, and the restart policy.
The reader must never stop: pi's documentation warns that an unread stdout pipe
can stall the process, and the stderr pipe must be drained for the same reason.

Cancellation is a protocol message, never a signal. **Closing stdin is pi's
orderly-shutdown signal**, so it is used only on teardown.
"""

import asyncio
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aiassistant.agent.harness.pi.protocol import (
    GET_STATE,
    RpcMessage,
    decode,
    encode,
    command_request,
)

logger = logging.getLogger(__name__)

# Only these variables reach the child. pi runs with the user's permissions and
# has no permission system, so its environment is explicit rather than inherited
# (REQ-SEC-006).
ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "LANG", "LC_ALL", "TMPDIR",
    "PI_CODING_AGENT_DIR", "PI_OFFLINE",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
)

_STDERR_TAIL_CHARS = 2000


@dataclass
class PiProcessConfig:
    """Everything the child needs, resolved from config."""

    command: str = "pi"
    workspace: str = "./pi_workspace"
    tools: list[str] = field(default_factory=lambda: [
        "read", "write", "edit", "grep", "find", "ls",
    ])
    policy_extension: str | None = "./pi_extensions/workspace_guard.ts"
    no_session: bool = True
    restart_backoff_s: list[int] = field(default_factory=lambda: [1, 2, 4, 8, 30])
    model: str = ""


class PiProcess:
    """A long-lived ``pi --mode rpc`` child, with supervised respawn."""

    def __init__(
        self,
        cfg: PiProcessConfig,
        on_message: Callable[[RpcMessage], None],
        on_exit: Callable[[int | None], None] | None = None,
    ):
        self.cfg = cfg
        self.on_message = on_message
        self.on_exit = on_exit
        self._proc: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_tail: list[str] = []
        self._restarts = 0
        self._closed = False

    # ── Lifecycle ────────────────────────────────────────────

    def build_argv(self) -> list[str]:
        """The documented start command. See IF-0003 and ADR-0012.

        ``--no-extensions`` disables *discovered* extensions while an explicit
        ``-e`` path still loads, so our guard loads and the workspace's own do
        not. Shell tools are excluded by the allowlist.
        """
        argv = [self.cfg.command, "--mode", "rpc"]
        if self.cfg.no_session:
            argv.append("--no-session")
        if self.cfg.tools:
            argv += ["--tools", ",".join(self.cfg.tools)]
        argv.append("--no-extensions")
        if self.cfg.policy_extension:
            argv += ["-e", os.path.abspath(self.cfg.policy_extension)]
        argv += ["--no-approve", "-nc"]
        if self.cfg.model:
            argv += ["--model", self.cfg.model]
        return argv

    def build_env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in ENV_ALLOWLIST if k in os.environ}
        # Marks the process as agent-driven, per pi's environment docs.
        env["AI_AGENT"] = "pi"
        env["PI_CODING_AGENT"] = "true"
        return env

    async def start(self) -> None:
        if shutil.which(self.cfg.command) is None and not os.path.isabs(self.cfg.command):
            raise FileNotFoundError(
                f"pi command {self.cfg.command!r} not found on PATH. "
                f"Run scripts/setup_pi.sh, or set agents.<id>.pi.command."
            )
        workspace = os.path.abspath(self.cfg.workspace)
        os.makedirs(workspace, exist_ok=True)

        self._closed = False
        self._proc = await asyncio.create_subprocess_exec(
            *self.build_argv(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
            env=self.build_env(),
        )
        self._stdout_task = asyncio.ensure_future(self._read_stdout())
        self._stderr_task = asyncio.ensure_future(self._drain_stderr())
        logger.info("pi started (pid=%s) in %s", self._proc.pid, workspace)

    async def restart(self) -> bool:
        """Respawn after an unexpected exit, within the backoff budget."""
        await self._stop_tasks()
        if self._restarts >= len(self.cfg.restart_backoff_s):
            logger.error("pi restart budget exhausted (%d attempts)", self._restarts)
            return False
        delay = self.cfg.restart_backoff_s[self._restarts]
        self._restarts += 1
        logger.warning("Restarting pi in %ss (attempt %d)", delay, self._restarts)
        await asyncio.sleep(delay)
        await self.start()
        return True

    async def close(self) -> None:
        """Orderly shutdown: close stdin, wait, then terminate, then kill."""
        self._closed = True
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
        except Exception:
            logger.debug("Closing pi stdin raised", exc_info=True)

        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("pi did not exit on stdin close; terminating")
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("pi ignored terminate; killing")
                proc.kill()
                await proc.wait()
        await self._stop_tasks()
        self._proc = None

    async def _stop_tasks(self) -> None:
        for task in (self._stdout_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._stdout_task = None
        self._stderr_task = None

    # ── I/O ──────────────────────────────────────────────────

    def send(self, request) -> None:
        """Write one command. Never raises for a closed pipe; the caller sees
        the turn error via the process exit instead."""
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdin.is_closing():
            raise BrokenPipeError("pi is not running")
        proc.stdin.write(encode(request))
        # write() buffers; drain in the background so a full pipe cannot stall us.
        asyncio.ensure_future(self._drain_stdin())

    async def _drain_stdin(self) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("pi stdin closed while draining")

    async def _read_stdout(self) -> None:
        """Read LF-delimited JSON forever.

        Splits on LF only: U+2028/U+2029 are legal inside JSON strings and must
        not be treated as line boundaries.
        """
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        buffer = b""
        try:
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._handle_line(line)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pi stdout reader failed")
        finally:
            if buffer.strip():
                self._handle_line(buffer)
            await self._handle_exit()

    def _handle_line(self, line: bytes) -> None:
        if not line.strip():
            return
        try:
            message = decode(line)
        except Exception as exc:
            # A malformed line must not kill the reader (REQ-HARNESS-003).
            logger.warning("pi sent an undecodable line: %s", exc)
            return
        try:
            self.on_message(message)
        except Exception:
            logger.exception("pi message handler raised")

    async def _drain_stderr(self) -> None:
        """Drain stderr. Leaving it unread can block the child."""
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                self._remember_stderr(text)
                logger.debug("pi stderr: %s", text)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("pi stderr drain ended", exc_info=True)

    def _remember_stderr(self, text: str) -> None:
        self._stderr_tail.append(text)
        joined = "\n".join(self._stderr_tail)
        if len(joined) > _STDERR_TAIL_CHARS:
            self._stderr_tail = [joined[-_STDERR_TAIL_CHARS:]]

    def stderr_tail(self) -> str:
        """Recent stderr, for an actionable error message."""
        return "\n".join(self._stderr_tail)

    async def _handle_exit(self) -> None:
        proc = self._proc
        code = proc.returncode if proc else None
        if not self._closed:
            logger.warning("pi exited unexpectedly (code=%s)", code)
            if self.on_exit:
                self.on_exit(code)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None
