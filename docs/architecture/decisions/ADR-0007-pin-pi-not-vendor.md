# ADR-0007 — Pin pi; do not fork or submodule it

**Status:** accepted · **Date:** 2026-09-26

## Decision

Integrate pi as a **pinned external dependency**, provisioned by
`scripts/setup_pi.sh`. Do not fork it. Do not add it as a git submodule. Keep
the integration in-tree:

```
agent/harness/pi/          our adapter (Python)
agent/harness/pi/workspace_guard.ts   our confinement extension (TypeScript)
scripts/setup_pi.sh        pinned install
```

## Why

| Factor | Value |
| --- | --- |
| Language | TypeScript / Node ≥ 22.19 or a standalone binary |
| Version pace | v0.87.1, actively developed |
| Our codebase | Python |

Vendoring would put a Node toolchain inside a Python repo and require us to
track upstream changes by hand for the privilege. A submodule pins a commit but
still requires the Node toolchain at build time and invites local patches that
diverge.

Pinning gives us the harness on day one, which is what the user asked for,
without owning upstream.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Git submodule | Pulls a Node build into the Python repo; local patches drift |
| Fork | We would own maintenance of a fast-moving TS project |
| Reimplement pi's loop ourselves | Enormous scope; the point is to reuse it |
| Require npm | The standalone binary avoids a Node runtime dependency entirely |

## Consequences

- `scripts/setup_pi.sh` installs a pinned version, preferring the standalone
  darwin/linux binary so Node is not required.
- Upgrades are one version bump plus a re-run of the adapter's fixture tests
  against newly recorded JSONL.
- If we ever must patch pi, the decision flips to a submodule and this ADR is
  superseded.
- `operations/repos.md` records the pinned version and the upgrade procedure.
