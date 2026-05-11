#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "=== validate_memory_system ==="
python3 memory_core/tools/validate_memory_system.py

echo "=== pollution detection (if available) ==="
if python3 memory_core/tools/validate_memory_system.py --help 2>&1 | grep -q -i pollution; then
    python3 memory_core/tools/validate_memory_system.py --check pollution
else
    echo "(pollution check sub-command not yet available; skipping non-fatally)"
fi

echo "=== CI health check OK ==="
