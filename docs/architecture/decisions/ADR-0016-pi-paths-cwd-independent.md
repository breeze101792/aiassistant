# ADR-0016 — Resolve pi's guard and workspace independent of the process CWD

**Status:** accepted · **Date:** 2026-09-27

## Context

Two pi paths were resolved against the process CWD:

- `PiProcess.build_argv` passed `os.path.abspath(self.cfg.policy_extension)` for
  the `-e` guard flag.
- `PiProcess.start` passed `os.path.abspath(self.cfg.workspace)` as the child's
  `cwd`.

Both defaults were relative literals (`./pi_extensions/workspace_guard.ts`,
`./pi_workspace`). `os.path.abspath` resolves against the directory the assistant
was launched from, so launching outside the repo root silently pointed `-e` at a
file that did not exist. pi ran with `--no-extensions` and no `-e`, which loads
no extension at all: the workspace guard never loaded and confinement layer 2 of
[ADR-0012](ADR-0012-pi-confinement.md) was off with no error. The same launch
also created and pinned the workspace under an unpredictable directory.

A second defect compounded it: the adapter read `pi_cfg.get("policy_extension")`
with **no default**, so an omitted key passed `None` and overrode the dataclass
default — the guard was disabled by an absent key, not only by a wrong path.

## Decision

Anchor each path to the thing that owns it, and fail closed.

| Path | Kind | Anchor | Default |
| --- | --- | --- | --- |
| `workspace_guard.ts` | source (policy) | the `aiassistant` package, via `importlib.resources` | packaged with `aiassistant.agent.harness.pi` |
| pi workspace | runtime data | `$HOME` | `~/.config/aiassistant/pi_workspace` |

`policy_extension` becomes a three-valued specifier:

| Value | Meaning |
| --- | --- |
| key absent, or `"builtin"` | load the shipped guard from the package |
| any other string | a user path; `~` is expanded and it is made absolute |
| `null` | guard disabled (logged loudly at startup) |

Resolution lives in `agent/harness/pi/process.py` as pure functions
(`packaged_guard_path`, `resolve_policy_extension`, `resolve_workspace`). Only
`start()` creates directories.

**Fail closed.** `start()` verifies the resolved guard is a real file *before*
it checks the `pi` binary. A missing guard raises `FileNotFoundError` naming the
path; a disabled guard logs a WARNING. It never silently omits `-e`.

## Why

- The guard is source that enforces a security property. Its absence must be an
  error, not a downgrade. Checking it first means the security condition is
  always diagnosed first.
- A guard kept as a top-level directory outside any package is invisible to
  pip; it would not ship in a wheel or a frozen build. Inside the package, one
  `[tool.setuptools.package-data]` stanza ships it and `importlib.resources`
  resolves it in the source tree, an editable install, a wheel, and (by API
  contract) a frozen build.
- The workspace is runtime data and must not live in site-packages, where an
  upgrade could strand or clobber it. Anchoring it to `$HOME` fixes the
  scattering that `makedirs` caused when the CWD was arbitrary.
- A relative user override still works, but a wrong one now fails loudly instead
  of disabling the guard.

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Keep `pi_extensions/`, resolve against the repo root | No reliable repo root exists once installed; keeps the root clutter; the anchor would fail the same silent way |
| Guard as runtime data under `.config/` | Policy is source, not data: unversioned, user-editable, unshipped; inverts the security model |
| `__file__`-relative instead of `importlib.resources` | Works today, but `resources` is the API with a frozen/bundled-data story, and the project names frozen builds as a goal |
| Workspace relative under `.config/` | Reintroduces the CWD scatter and an unpredictable child `cwd` |
| Raise when `policy_extension` is `null` | Removes a documented escape hatch; a loud warning is honest without being a nanny |

## Consequences

- `config.yaml` defaults become `workspace: "~/.config/aiassistant/pi_workspace"`
  and `policy_extension: "builtin"`.
- An old config with `policy_extension: "./pi_extensions/workspace_guard.ts"`
  now disables the pi harness loudly, naming the path and suggesting `"builtin"`; the assistant still starts in console (REQ-SETUP-003).
- `pi_extensions/` is gone; the guard lives at
  `src/aiassistant/agent/harness/pi/workspace_guard.ts`.
- The other runtime paths (memory, scheduler, console, tools) remain
  CWD-relative. Their failure mode is data scatter, not a silent security
  downgrade, so they are out of scope here; this ADR introduces the
  `~/.config/aiassistant/` anchor they should converge on later.
