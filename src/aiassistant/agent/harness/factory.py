"""Harness factory.

Resolves the configured harness for an agent. Selection is by
``agents.<id>.harness`` (REQ-HARNESS-001). One harness is implemented — our own
loop, ``native`` — but the interface and this seam are kept, so a second loop
could be added without touching the agent module or the tests.
"""

import logging

from aiassistant.agent.harness.base import AgentHarness, HarnessCaps
from aiassistant.reasoning import factory as provider_factory

logger = logging.getLogger(__name__)

NATIVE = "native"
SUPPORTED = (NATIVE,)


class HarnessConfigError(ValueError):
    """The configured harness cannot be built."""


def create_harness(agent_cfg: dict, *, tool_schemas: list[dict] | None = None) -> AgentHarness:
    """Build the harness named by ``agent_cfg['harness']`` (default ``native``).

    ``agent_cfg`` is one entry from the ``agents:`` map: it carries ``harness``,
    ``persona``, ``llm``, and ``memory``.
    """
    name = (agent_cfg.get("harness") or NATIVE).strip().lower()
    if name not in SUPPORTED:
        raise HarnessConfigError(
            f"Unknown harness {name!r}. Supported: {', '.join(SUPPORTED)}."
        )
    return _create_native(agent_cfg, tool_schemas)


def _create_native(agent_cfg: dict, tool_schemas: list[dict] | None) -> AgentHarness:
    from aiassistant.agent.harness.native import NativeHarness

    llm_cfg = agent_cfg.get("llm", {})
    try:
        provider = provider_factory.create_provider(llm_cfg, role="chat")
    except provider_factory.ProviderError as exc:
        raise HarnessConfigError(str(exc)) from exc

    return NativeHarness(
        provider=provider,
        persona=agent_cfg.get("persona", ""),
        tool_schemas=tool_schemas,
        temperature=llm_cfg.get("temperature", 0.7),
        max_tokens=llm_cfg.get("max_tokens", 4096),
    )


def harness_is_available(name: str) -> bool:
    """Whether a harness can be built at all, for first-run detection (REQ-SETUP-001)."""
    return name == NATIVE


__all__ = [
    "AgentHarness", "HarnessCaps", "HarnessConfigError",
    "create_harness", "harness_is_available", "NATIVE",
]
