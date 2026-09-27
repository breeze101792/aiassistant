# ADR-0008 — pi owns tools on its own turns

**Status:** accepted · **Date:** 2026-09-26

## Decision

When `harness: pi`, pi executes its own tools. Set `caps.owns_tools = True` and
do not invoke `tools/` for that turn. Our tools serve the `native` harness only.

## Why

The alternative — exposing our tools to pi — requires a mechanism pi does not
offer over RPC. The RPC command set has no tool-registration or
tool-execution-callback command. Tool bridging is possible only by writing a
**TypeScript pi extension** (`--extension`, `pi.registerTool()`), which loads in
RPC mode and is therefore a real path, but it means a second language, a second
deployable, and a mechanism designed for IDE integration rather than a voice
assistant.

Three further facts make "pi owns tools" the honest choice for the MVP:

1. `tool_execution_*` events are notifications. pi computes the result; there is
   no interception point without an extension.
2. Our tools would be unreachable anyway: during a pi turn the host never talks
   to a model directly, so `tools/` has no caller.
3. Capability overlap is bounded and, with this decision, **per-backend
   exclusive**. No single turn sees both tool sets, so there is no ambiguity
   inside a conversation.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Bridge our tools via a pi extension | Real but out of MVP scope: a TS deployable and a second tool registry |
| Both tool sets active | Ambiguous and dangerous; pi's tools run as the user with no permission system |
| Disable pi's tools, use only ours | pi is a coding agent; removing its tools removes its reason to exist |

## Consequences

**What we lose on pi turns:**

- Web search and research skills — accepted MVP gap. Sanctioned future path: a
  pi extension.
- Our sandbox and `safe_paths` do not apply. pi's confinement is its own
  (ADR-0012).
- The tool audit trail comes from pi's `tool_result` events, not our
  `status.tool.done`.

**Consequence for the config:** tool ownership is a capability, not a hidden
detail. `caps` reports it and the orb can show it, so the user is never surprised
that a tool was unavailable.

**Future:** exposing a curated subset of our tools through a pi extension is the
sanctioned follow-up. It is a new ADR, not a silent change.
