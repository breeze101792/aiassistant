#!/bin/bash
# AI Assistant launcher.
#
# Sets up the environment if needed, then starts the assistant.
#
# Usage:
#   ./start.sh                  # run with the code defaults
#   ./start.sh --frontend none  # text only
#   ./start.sh --frontend tui   # terminal orb
#   ./start.sh --audio          # force voice
#   ./start.sh test             # run the test suite
#   ./start.sh -h               # show assistant help
#
# Environment:
#   PYTHON  override the interpreter used to create the venv (default python3)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="${PYTHON:-python3}"
MIN_PY_MINOR=11
CONFIG_FILE="$SCRIPT_DIR/config.yaml"

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

# ── Virtual environment ──────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment with $PYTHON ($PY_VERSION)..."
    "$PYTHON" -m venv "$VENV_DIR"
    NEED_INSTALL=1
else
    NEED_INSTALL=0
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Install when the venv is new, or when the package or core deps are missing.
if [ "$NEED_INSTALL" = "1" ] || ! python -c "import yaml, websockets, aiassistant" >/dev/null 2>&1; then
    log "Installing dependencies..."
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -e .
    NEED_INSTALL=0
fi

# ── Dispatch ─────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    exec python -m aiassistant.main -c "$CONFIG_FILE"
fi

case "$1" in
    test)
        shift
        exec python -m pytest tests/ -q "$@"
        ;;
    -h|--help)
        exec python -m aiassistant.main -h
        ;;
    *)
        exec python -m aiassistant.main -c "$CONFIG_FILE" "$@"
        ;;
esac
