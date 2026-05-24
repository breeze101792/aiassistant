#!/bin/bash
# AI Assistant runner — handles venv activation transparently
# Usage: ./run.sh                        # Run the assistant
#        ./run.sh test                   # Run all tests
#        ./run.sh test tests/test_cli.py # Run specific test file
#        ./run.sh python main.py --help  # Show help
#        ./run.sh python -c "from bus.bus import MessageBus; print('ok')"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [ $# -eq 0 ]; then
    # Default: run the assistant
    python main.py
elif [ "$1" = "test" ]; then
    shift
    python -m pytest tests/ -v "$@"
else
    "$@"
fi
