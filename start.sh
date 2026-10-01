#!/usr/bin/env bash
# AI Assistant launcher.
#
# Sets up the environment if needed, then starts the assistant.
#
# Usage:
#   ./start.sh                  # run with the code defaults
#   ./start.sh --frontend none  # text only
#   ./start.sh --frontend tui   # terminal orb
#   ./start.sh --audio          # voice via a self-hosted Whisper server
#   ./start.sh --offline        # fully offline voice in and out
#   ./start.sh test             # run the test suite
#   ./start.sh -h               # show assistant help
#
# Environment:
#   PYTHON  override the interpreter used to create the venv (default python3)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
MIN_PY_MINOR=11
CONFIG_FILE="$SCRIPT_DIR/config.yaml"

# A venv holds absolute symlinks to the interpreter that built it, so it is not
# portable between machines. The repo is often on a shared or synced folder, so
# name it per host: a venv built here is never mistaken for one built elsewhere.
# VENV overrides the whole path.
host_slug() {
    local name
    name="$(uname -n 2>/dev/null || hostname -s 2>/dev/null || true)"
    # Keep it filesystem-safe; never empty.
    name="$(printf '%s' "$name" | tr -c 'A-Za-z0-9._-' '-' | tr -s '-')"
    name="${name%-}"
    printf '%s' "${name:-unknown}"
}

HOST_SLUG="$(host_slug)"
VENV_DIR="${VENV:-$SCRIPT_DIR/.venv_$HOST_SLUG}"

cd "$SCRIPT_DIR"

log()  { printf '\033[32m[start]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[start]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[start]\033[0m %s\n' "$*" >&2; exit 1; }

# ── Interpreter check ────────────────────────────────────────
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    die "$PYTHON not found. Install Python ${MIN_PY_MINOR}+ or set PYTHON=/path/to/python3"
fi

PY_VERSION="$($PYTHON -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_OK="$($PYTHON -c "import sys; print(1 if sys.version_info[:2] >= (3, $MIN_PY_MINOR) else 0)")"
if [ "$PY_OK" != "1" ]; then
    die "Python ${MIN_PY_MINOR}+ required, found $PY_VERSION."
fi

# One-time cleanup of the old shared `.venv`. It cannot be adopted: a venv
# hardcodes its own path in bin/activate and in every console-script shebang, so
# moving or renaming it leaves it pointing at the old location. Rename it aside
# so a per-host venv can take over.
LEGACY_VENV="$SCRIPT_DIR/.venv"
if [ -e "$LEGACY_VENV" ]; then
    warn "Found the old shared .venv; it is not used any more (see below)."
    warn "Renaming it to $(basename "$LEGACY_VENV").old so the per-host venv can exist."
    mv "$LEGACY_VENV" "$LEGACY_VENV.old.$(date +%Y%m%d%H%M%S)"
fi

# ── Virtual environment ──────────────────────────────────────
# Checking for the directory (or the activate script) is not enough. A venv
# copied from another machine carries absolute symlinks into that machine's
# Python, so it looks present while `python` silently falls through to the
# system interpreter -- which may have no pip. Verify by running it.
venv_is_usable() {
    local py="$VENV_DIR/bin/python"
    [ -x "$py" ] || return 1
    # The interpreter must report the venv as its prefix, not some other one.
    local prefix
    prefix="$("$py" -c 'import sys; print(sys.prefix)' 2>/dev/null)" || return 1
    [ "$prefix" = "$VENV_DIR" ] || return 1
    # And it must have pip, or the install step below cannot run.
    "$py" -m pip --version >/dev/null 2>&1 || return 1
    return 0
}

if ! venv_is_usable; then
    if [ -d "$VENV_DIR" ]; then
        # Move it aside rather than delete: a broken venv may still hold
        # something the user wants, and this is recoverable. A timestamp keeps
        # an older one from being clobbered.
        local_broken="$VENV_DIR.broken.$(date +%Y%m%d%H%M%S)"
        warn "Existing $VENV_DIR is unusable here (wrong Python, or no pip)."
        warn "Moving it to $(basename "$local_broken") and recreating."
        mv "$VENV_DIR" "$local_broken"
    fi
    log "Creating virtual environment with $PYTHON ($PY_VERSION) at $(basename "$VENV_DIR")..."
    "$PYTHON" -m venv "$VENV_DIR"
    venv_is_usable || die "The new venv has no pip. On Debian/Ubuntu install python3-venv."
fi

# Call the venv's interpreter by absolute path; never `source .../activate`.
# A venv hardcodes VIRTUAL_ENV to its creation path, so sourcing a venv that was
# moved makes `python` resolve to the system interpreter instead. Using the
# absolute path is correct wherever the venv lives.
VENV_PY="$VENV_DIR/bin/python"

# The suite needs the dev extra (pytest). Running the assistant needs the
# offline ASR extra, because `voice.asr.backend: faster_whisper` is the default
# voice backend; without it the voice module disables itself at setup. Install
# both for `test` so the offline-ASR tests run instead of skipping.
INSTALL_TARGET=".[asr-offline]"
if [ $# -gt 0 ] && [ "$1" = "test" ]; then
    INSTALL_TARGET=".[dev,asr-offline]"
fi

# Let pip reconcile every run. It is a no-op (~2 s) when satisfied, and it is
# the only check that cannot drift: a hand-written "import yaml, websockets"
# list silently misses a dependency added later, which is how numpy went
# undeclared and broke a fresh install. pip reads the real requirement set.
log "Checking dependencies ($INSTALL_TARGET)..."
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -e "$INSTALL_TARGET"

# ── Dispatch ─────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    exec "$VENV_PY" -m aiassistant.main -c "$CONFIG_FILE"
fi

case "$1" in
    test)
        shift
        exec "$VENV_PY" -m pytest tests/ -q "$@"
        ;;
    -h|--help)
        exec "$VENV_PY" -m aiassistant.main -h
        ;;
    *)
        exec "$VENV_PY" -m aiassistant.main -c "$CONFIG_FILE" "$@"
        ;;
esac
