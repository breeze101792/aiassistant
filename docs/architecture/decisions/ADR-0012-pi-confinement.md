# ADR-0012 — Confine pi at the coding level; document the gap

**Status:** accepted · **Date:** 2026-09-26

## Decision

Confine the pi child process with the strongest **application-level** mechanisms
pi supports, and state honestly what those do not cover. OS-level confinement is
documented as the next step, not built now.

Layers, strongest first:

| # | Layer | Mechanism | Covers |
| --- | --- | --- | --- |
| 1 | Tool allowlist | `--tools read,write,edit,grep,find,ls` — no `bash`, no `powershell` | Removes arbitrary program execution |
| 2 | Policy extension | `workspace_guard.ts` (shipped as package data, loaded from an absolute path — [ADR-0016](ADR-0016-pi-paths-cwd-independent.md)), a `tool_call` hook returning `{block: true}` | Blocks any file tool path resolving outside the workspace; a missing guard prevents the pi harness from starting |
| 3 | Process hygiene | `cwd` pinned to the workspace; explicit minimal env; `--no-extensions --no-approve -nc` | Reduces blast radius; stops the folder injecting its own extension |
| 4 | Host discipline | Never send pi's RPC `bash` command | Closes the RPC shell bypass |
| 5 | Opt-in | `pi.enabled: true` required; startup logs a warning | No accidental activation |

## Why this, and not an OS sandbox

The user asked whether confinement could be done "on a coding level". The
verified answer is: **for file tools yes; for a shell no; for the network no.**

What pi's own documentation and source establish:

- A `tool_call` extension hook **fires before a tool executes and can return
  `{block: true, reason, terminate}`**. The veto is implemented and tested
  upstream. This is real enforcement for `read`/`write`/`edit`/`grep`/`find`/`ls`.
- There is **no** workspace flag and **no** permission config key. `cwd` sets
  defaults but the docs say plainly it "does not prevent commands from accessing
  other paths available to the Pi process". Built-in tools resolve absolute paths
  and `~` as-is.
- The RPC surface adds a `bash` command that **bypasses tool selection** and is
  intercepted only by a separate `user_bash` hook. We simply never send it, and
  the allowlist removes pi's own shell tool, so this is closed by denial.
- **Network access and prompt injection are not containable at the application
  level.** pi's own security documentation recommends a container, VM, or OS
  sandbox as the only real boundary, and ships an example extension doing exactly
  that with `sandbox-exec` (macOS) and `bubblewrap` (Linux).

Layers 1–4 are a genuine, verified reduction in blast radius. Calling them a
security boundary would be false.

## Rejected

| Alternative | Why rejected for the MVP |
| --- | --- |
| Container (Docker/podman) | Strongest, but requires a container runtime and its own management surface; heavy for a desktop assistant |
| OS sandbox now (seatbelt / bubblewrap) | The right next step; needs a per-platform spike and careful profile authoring. pi ships a working example to adopt. |
| Document the risk and do nothing | The default (no tools restriction, LAN-reachable bus) is a remote-shell path. Unacceptable. |
| cwd pin only | Not a boundary, as pi's own docs state |

## Consequences

- **Mandatory companions.** This decision only holds with the bus fixed too:
  loopback bind by default and a required token for any non-loopback bind
  (REQ-SEC-001, REQ-SEC-002). An unauthenticated bus plus pi is a remote shell.
- pi is disabled for untrusted channels by default: `allow_channels` is local
  only (`console`, `voice`, `orb`).
- The residual gaps are written into `security/threat-model.md` as open risks,
  not glossed.
- The tool allowlist is config, so a user can widen it — with the documented
  consequence.
