#!/bin/bash
# AI Assistant runner — handles venv activation transparently
# Usage: ./run.sh pytest tests/ -v
#        ./run.sh python main.py
#        ./run.sh python -c "from bus.bus import MessageBus; print('ok')"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [ $# -eq 0 ]; then
    # Default: run tests
    python -m pytest tests/ -v
else
    "$@"
fi
