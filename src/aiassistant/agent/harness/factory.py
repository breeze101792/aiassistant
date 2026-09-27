"""Harness factory.

Resolves the configured harness for an agent. Selection is by
``agents.<id>.harness`` (REQ-HARNESS-001). There is no silent fallback between
harnesses: they differ in tool ownership, so a fallback would silently change
what the assistant can do (REQ-HARNESS-006).
"""

import logging

from aiassistant.agent.harness.base import AgentHarness, HarnessCaps
from aiassistant.reasoning import factory as provider_factory

logger = logging.getLogger(__name__)

NATIVE = "native"
PI = "pi"
SUPPORTED = (NATIVE, PI)


class HarnessConfigError(ValueError):
    """The configured harness cannot be built."""


def create_harness(agent_cfg: dict, *, tool_schemas: list[dict] | None = None) -> AgentHarness:
    """Build the harness named by ``agent_cfg['harness']`` (default ``native``).

    ``agent_cfg`` is one entry from the ``agents:`` map: it carries ``harness``,
    ``persona``, ``llm``, and ``pi``.
    """
    name = (agent_cfg.get("harness") or NATIVE).strip().lower()
    if name not in SUPPORTED:
        raise HarnessConfigError(
            f"Unknown harness {name!r}. Supported: {', '.join(SUPPORTED)}."
        )
    if name == PI:
        return _create_pi(agent_cfg)
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


def _create_pi(agent_cfg: dict) -> AgentHarness:
    pi_cfg = agent_cfg.get("pi", {}) or {}
    if not pi_cfg.get("enabled", False):
        # Opt-in is mandatory: pi runs with the user's permissions and has no
        # permission system of its own (REQ-SEC-003, RISK-0002).
        raise HarnessConfigError(
            "The pi harness is disabled. Set agents.<id>.pi.enabled: true to use "
            "it, and read docs/security/threat-model.md first."
        )

    from aiassistant.agent.harness.pi.adapter import PiHarness

    return PiHarness(pi_cfg)


def harness_is_available(name: str) -> bool:
    """Whether a harness can be built at all, for first-run detection (REQ-SETUP-001)."""
    if name == NATIVE:
        return True
    if name == PI:
        return _pi_installed()
    return False


def _pi_installed() -> bool:
    import shutil

    return shutil.which("pi") is not None


__all__ = [
    "AgentHarness", "HarnessCaps", "HarnessConfigError",
    "create_harness", "harness_is_available", "NATIVE", "PI",
]
