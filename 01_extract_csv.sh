#!/usr/bin/env bash
set -u

# Change directory to the script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Locate Python 3.12 virtual environment (checking .venv312 and .venv)
if [ -x "$SCRIPT_DIR/.venv312/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv312/bin/python"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    echo "[ERROR] Python 3.12 virtual environment not found: .venv312" >&2
    echo "Run: python3.12 -m venv .venv312" >&2
    echo "Then: .venv312/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# Execute extraction
if [ $# -eq 0 ]; then
    echo "Extracting the latest 30 days with weekly windows (--weekly)..."
    "$PYTHON" "$SCRIPT_DIR/gencsv/date_range_runner.py" --days 30 --weekly
else
    echo "Extracting CSV data with arguments: $*"
    "$PYTHON" "$SCRIPT_DIR/gencsv/date_range_runner.py" "$@"
fi

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] CSV extraction failed with exit code $EXIT_CODE." >&2
fi
exit $EXIT_CODE
