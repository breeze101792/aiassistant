"""pi RPC framing: JSONL over stdin/stdout.

pi speaks a strict line protocol: one complete JSON object per line, terminated
by LF. Two rules matter and are easy to get wrong:

* Split on ``\\n`` **only**. U+2028 and U+2029 are valid inside JSON strings and
  must not be treated as line boundaries.
* stdout carries protocol records exclusively; diagnostics go to stderr. A line
  that is not JSON is a protocol error, logged and skipped, never fatal.

Commands are correlated by an ``id`` we generate. Session events carry no id;
they are attributed to the active turn temporally.

Contract: docs/contracts/protocols.md IF-0003.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ProtocolError(Exception):
    """A line from pi was not a JSON object."""


@dataclass
class RpcRequest:
    """A command sent to pi."""

    id: str
    type: str
    fields: dict = field(default_factory=dict)

    def to_line(self) -> bytes:
        payload = {"id": self.id, "type": self.type, **self.fields}
        return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


@dataclass
class RpcMessage:
    """One decoded line from pi."""

    raw: dict

    @property
    def id(self) -> str | None:
        value = self.raw.get("id")
        return value if isinstance(value, str) else None

    @property
    def type(self) -> str:
        return self.raw.get("type", "") or ""

    @property
    def is_response(self) -> bool:
        return self.type == "response" or "command" in self.raw

    @property
    def is_event(self) -> bool:
        """Events carry no id; responses and commands do."""
        return self.id is None

    @property
    def command(self) -> str:
        return self.raw.get("command", "") or ""

    @property
    def success(self) -> bool:
        return bool(self.raw.get("success", False))

    @property
    def data(self) -> dict:
        value = self.raw.get("data")
        return value if isinstance(value, dict) else {}

    @property
    def error(self) -> str:
        return str(self.raw.get("error", "") or "")


def encode(request: RpcRequest) -> bytes:
    """Serialize a command to one LF-terminated line."""
    return request.to_line()


def decode(line: bytes | str) -> RpcMessage:
    """Decode one line. Raises :class:`ProtocolError` if it is not an object."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    text = line.strip()
    if not text:
        raise ProtocolError("empty line")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"not JSON: {text[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError(f"not a JSON object: {text[:120]!r}")
    return RpcMessage(parsed)


def prompt_request(request_id: str, message: str) -> RpcRequest:
    return RpcRequest(id=request_id, type="prompt", fields={"message": message})


def command_request(request_id: str, command: str, **fields: Any) -> RpcRequest:
    return RpcRequest(id=request_id, type=command, fields=fields)


# Commands we use. The RPC `bash` command is deliberately absent: the host must
# never send it, because it bypasses pi's tool allowlist (ADR-0012).
GET_STATE = "get_state"
ABORT = "abort"
CLEAR_QUEUE = "clear_queue"
GET_SESSION_STATS = "get_session_stats"
GET_LAST_ASSISTANT_TEXT = "get_last_assistant_text"
