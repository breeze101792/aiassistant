#!/bin/bash
# Install pi at the pinned version.
#
# pi is an external dependency, not vendored — see ADR-0007. The standalone
# binary is preferred so Node is not required at runtime.
#
# Usage:
#   ./scripts/setup_pi.sh            # install/verify the pinned version
#   ./scripts/setup_pi.sh --check    # report status without installing

set -euo pipefail

# Update this and docs/operations/repos.md together (ADR-0007).
PI_VERSION="0.87.1"
PI_INSTALL_URL="https://pi.dev/install.sh"
PI_NPM_PACKAGE="@earendil-works/pi-coding-agent"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

log()  { printf '\033[32m[pi]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[pi]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[pi]\033[0m %s\n' "$*" >&2; exit 1; }

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

installed_version() {
    if ! command -v pi >/dev/null 2>&1; then
        return 1
    fi
    pi --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

check() {
    local current
    if ! current="$(installed_version)"; then
        echo "not installed"
        return 1
    fi
    if [ "$current" = "$PI_VERSION" ]; then
        echo "installed ($current)"
        return 0
    fi
    echo "installed ($current, pinned is $PI_VERSION)"
    return 1
}

# ── Report ───────────────────────────────────────────────────
log "pinned version: $PI_VERSION"
STATUS="$(check || true)"
log "status: $STATUS"

if [ "$CHECK_ONLY" = "1" ]; then
    [ "$STATUS" = "installed ($PI_VERSION)" ] && exit 0 || exit 1
fi

if [ "$STATUS" = "installed ($PI_VERSION)" ]; then
    log "already at the pinned version; nothing to do"
    exit 0
fi

# ── Install ──────────────────────────────────────────────────
log "installing pi $PI_VERSION..."

if [ "${PI_INSTALL_METHOD:-binary}" = "npm" ]; then
    command -v npm >/dev/null 2>&1 || die "npm is required for PI_INSTALL_METHOD=npm"
    npm install -g "${PI_NPM_PACKAGE}@${PI_VERSION}"
elif curl --version >/dev/null 2>&1; then
    # Prefer the standalone binary: no Node runtime dependency at run time.
    if ! curl -fsSL "$PI_INSTALL_URL" | sh; then
        warn "the installer failed; retrying with npm if available"
        command -v npm >/dev/null 2>&1 || die "pi install failed and npm is unavailable"
        npm install -g "${PI_NPM_PACKAGE}@${PI_VERSION}"
    fi
else
    die "curl is required to install pi"
fi

# ── Verify ───────────────────────────────────────────────────
if ! command -v pi >/dev/null 2>&1; then
    die "pi is still not on PATH after install"
fi

ACTUAL="$(installed_version || echo unknown)"
if [ "$ACTUAL" != "$PI_VERSION" ]; then
    warn "installed $ACTUAL but $PI_VERSION is pinned; set agents.<id>.pi.model/config accordingly"
else
    log "installed pi $ACTUAL"
fi

# ── Notes ────────────────────────────────────────────────────
cat <<'EOF'

Next steps:
  1. Configure a model provider for pi itself (pi owns its provider, not us):
       pi config            # or edit ~/.pi/agent/models.json, auth.json
  2. Enable the harness in config.yaml:
       agent:
         harness: pi
         pi:
           enabled: true
           workspace: "./pi_workspace"
  3. Read docs/security/threat-model.md — pi runs with your permissions and has
     no permission system of its own. Our tool allowlist and workspace guard
     reduce the blast radius; they are not an OS sandbox.
EOF
