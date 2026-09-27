# Security — Threat Model

Trust boundaries and what is explicitly not contained. The external `pi` harness
was removed on 2026-09-27; its confinement story and the threats that depended on
it (an out-of-process, shell-capable agent) no longer apply and have been
withdrawn here.

## Trust boundaries

| # | Boundary | Trusted side | Untrusted side |
| --- | --- | --- | --- |
| 1 | Bus WebSocket | The assistant process | Any client that can reach the port |
| 2 | Messaging platforms | — | Every inbound message |
| 3 | Filesystem paths in tool calls | Configured safe roots | Everything else |
| 4 | Model output | — | Any model, which may emit tool calls or instructions |

## Threats and mitigations

### RISK-0001 — Unauthenticated bus reachable over the network

**Evidence:** `bus/remote.py:32` binds `0.0.0.0`; `config.yaml:6` sets
`remote_auth_token: ""`; `remote.py:50` enforces auth only when the token is
non-empty. So on a shared network, anyone could publish `user.input.text`.

**Impact:** An injected `user.input.text` reaches the agent and drives a turn
with the user's config, memory, and tool access. It is not remote shell
execution — the in-process agent has no shell — but it can invoke the file and
web tools the sandbox allows, read the transcript, and mutate assistant state.
That is unauthorized control, not a nuisance.

**Mitigation (required, REQ-SEC-001/002):**

1. Bind `127.0.0.1` by default.
2. Refuse to start on a non-loopback bind without a non-empty token.
3. Keep the token out of the checked-in config (env or keychain).

**Status:** open until chunk 1 lands. This is the highest-priority item in the
refactor and is the reason the bus fix comes before everything that depends on it.

### RISK-0004 — Sandbox path prefix escape

**Evidence:** `sandbox.py:58` uses `abs_path.startswith(safe_abs)`, so
`/tmp/aiassistant-evil` passes as inside `/tmp/aiassistant`.

**Impact:** A crafted path escapes the intended root.

**Mitigation:** Resolve with `os.path.realpath` and compare against resolved safe
roots with a separator boundary. Tested (REQ-TOOL-004, T-0704). **Status:** open
until chunk 2, where `tools/` is created — this fix has no home in any other
chunk and moves with the module.

### RISK-0005 — Secrets in memory or logs

**Evidence:** `config.yaml:16` has an `api_key` field. The transcript is plaintext
markdown.

**Impact:** A key could land in a transcript, a fact, or a log line.

**Mitigation:** Keys come from env or keychain, never the checked-in file
(REQ-CFG-005); a test asserts no key-shaped value appears in the transcript
(REQ-MEM-005, T-0402). **Status:** partially open.

### RISK-0006 — Prompt injection through tool results

**Impact:** Web search results or file contents can contain instructions the
model may follow.

**Mitigation:** Bounded by tool capabilities rather than by text filtering.
Filtering is unreliable and gives false confidence. The honest mitigation is the
sandbox: turns run in-process and every file tool path is confined to the
configured safe roots. Documented as an accepted residual risk.

## What is explicitly not a boundary

Saying these out loud prevents false confidence:

- **The tool allowlist.** Our tools are discovered and exposed to the model; the
  registry constrains which tools exist, not what a permitted tool can do.
- **The sandbox.** It constrains file-tool paths, not network access, and it
  runs in-process with the assistant's permissions.
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
| Sandbox refuses prefix escapes | host | T-0704 |
| No secret appears in the transcript | host | **unverified** — REQ-MEM-005 has no proving T yet; add `tests/test_security.py` |
