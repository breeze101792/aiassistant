# Security — Threat Model

Trust boundaries, the pi confinement story, and what is explicitly not
contained. Complements [ADR-0012](../architecture/decisions/ADR-0012-pi-confinement.md).

## Trust boundaries

| # | Boundary | Trusted side | Untrusted side |
| --- | --- | --- | --- |
| 1 | Bus WebSocket | The assistant process | Any client that can reach the port |
| 2 | pi child process | Us (we spawn it) | Its own tool calls, its model output, files in its workspace |
| 3 | Messaging platforms | — | Every inbound message |
| 4 | Filesystem paths in tool calls | Configured safe roots | Everything else |
| 5 | Model output | — | Any model, which may emit tool calls or instructions |
| 6 | The pi workspace's own contents | — | Files inside it, which can carry prompt injection |

## Threats and mitigations

### RISK-0001 — Unauthenticated bus reachable over the network

**Evidence:** `bus/remote.py:32` binds `0.0.0.0`; `config.yaml:6` sets
`remote_auth_token: ""`; `remote.py:50` enforces auth only when the token is
non-empty. So on a shared network, anyone could publish `user.input.text`.

**Impact:** With `harness: pi` active, an injected `user.input.text` reaches an
agent that can run shell commands as the user. That is remote code execution, not
a nuisance.

**Mitigation (required, REQ-SEC-001/002):**

1. Bind `127.0.0.1` by default.
2. Refuse to start on a non-loopback bind without a non-empty token.
3. Keep the token out of the checked-in config (env or keychain).

**Status:** open until chunk 1 lands. This is the highest-priority item in the
refactor and is the reason the bus fix comes before everything that depends on it.

### RISK-0002 — pi runs with the user's full permissions

**Evidence:** pi's own README: it has no built-in permission system and "runs
with the permissions of the user and process that launched it". Its default tools
are `read`, `bash`, `edit`, `write`.

**Impact:** On a pi turn the model can read, write, and execute as the user.

**Mitigation (REQ-SEC-003..006, ADR-0012):**

| Layer | Mechanism |
| --- | --- |
| Opt-in | `pi.enabled: true` required; startup warns |
| No shell | `--tools read,write,edit,grep,find,ls` |
| Path policy | `workspace_guard.ts` (packaged, loaded from an absolute path; a missing guard prevents pi from starting) `tool_call` hook returns `{block: true}` for paths outside the workspace |
| cwd pin | `cwd` = the workspace (sets defaults, not a boundary) |
| Env scrub | Explicit minimal environment; never logged |
| RPC discipline | The host never sends pi's `bash` command |
| Channel gating | `allow_channels` excludes messaging by default |

**Residual risk, stated plainly:** network access is not contained, and prompt
injection from files inside the workspace is not contained. pi's own
documentation recommends a container or OS sandbox as the only true boundary,
and ships an example using `sandbox-exec` (macOS) and `bubblewrap` (Linux). That
is the documented next step, not an MVP claim.

### RISK-0003 — Messaging input reaching a shell-capable harness

**Evidence:** `ChatModule._on_chat_message` (`chat.py:49`) publishes any inbound
message as `user.input.text`.

**Impact:** If pi is enabled globally, a Telegram message becomes a shell-capable
prompt from an untrusted sender.

**Mitigation:** `pi.allow_channels` defaults to local channels only. The existing
`telegram_allowed_users` list is a second gate. **Status:** open; enforced in the
harness dispatch path.

### RISK-0004 — Sandbox path prefix escape

**Evidence:** `sandbox.py:58` uses `abs_path.startswith(safe_abs)`, so
`/tmp/aiassistant-evil` passes as inside `/tmp/aiassistant`.

**Impact:** A crafted path escapes the intended root.

**Mitigation:** Resolve with `os.path.realpath` and compare against resolved safe
roots with a separator boundary. Tested (REQ-TOOL-004, T-0704). **Status:** open
until chunk 2, where `tools/` is created — this fix has no home in any other
chunk and moves with the module.

### RISK-0005 — Secrets in memory or logs

**Evidence:** `config.yaml:16` has an `api_key` field; env scrubbing for pi is
new. The transcript is plaintext markdown.

**Impact:** A key could land in a transcript, a fact, or a log line.

**Mitigation:** Keys come from env or keychain, never the checked-in file
(REQ-CFG-005); the pi child env is never logged (REQ-SEC-006); a test asserts no
key-shaped value appears in the transcript (REQ-MEM-005, T-0402). **Status:**
partially open.

### RISK-0006 — Prompt injection through tool results

**Impact:** Web search results or file contents can contain instructions the
model may follow.

**Mitigation:** Bounded by tool capabilities rather than by text filtering.
Filtering is unreliable and gives false confidence. The honest mitigation is the
confinement above: pi turns have no shell, and native turns are bounded by the
sandbox. Documented as an accepted residual risk.

## What is explicitly not a boundary

Saying these out loud prevents false confidence:

- **The workspace cwd.** pi's docs state it sets defaults, not a boundary.
- **The tool allowlist.** It removes the shell; it does not constrain the tools
  that remain.
- **The policy extension.** It constrains file-tool paths, not network access,
  and an extension runs in-process with pi's permissions.
- **Model behavior.** Instructions are not enforcement.

## Verification

Some clauses here are inspection-only claims, not test assertions. They are
marked honestly rather than pointed at a test that does not exist.

| Clause | Method | Test |
| --- | --- | --- |
| Loopback bind by default | host | T-0509 |
| Non-loopback bind requires a token | host | T-0509 |
| Auth rejects a wrong token | host | T-0508 |
| Malformed client frame is ignored | host | T-0510 |
| Disconnect cleans up subscriptions | host | T-0511 |
| pi refuses to start without `enabled: true` | host | **unverified** — REQ-SEC-003 has no proving T yet; add `tests/test_security.py` |
| pi start command omits shell tools | host (inspection of argv) | **unverified** — REQ-SEC-004 partial; the argv assertion is the missing test |
| Workspace guard blocks outside paths | host (fixture) | T-0309 |
| Sandbox refuses prefix escapes | host | T-0704 |
| No secret appears in the transcript | host | **unverified** — REQ-MEM-005 has no proving T yet; add `tests/test_security.py` |
| The child env is minimal and never logged | host | **unverified** — REQ-SEC-006 has no proving T yet |
| The host never sends the RPC `bash` command | inspection | **unverified** — REQ-SEC-005 is an inspection claim; no T asserts it |
