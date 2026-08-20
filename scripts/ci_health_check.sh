#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Python version selection: project requires Python 3.12+ (tomllib, memory_core).
# Prefer python3.12 explicitly, fallback to python3 if it's 3.11+.
if command -v python3.12 &>/dev/null; then
  PYTHON="python3.12"
elif command -v python3 &>/dev/null; then
  PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
    PYTHON="python3"
  else
    echo "Error: Python 3.11+ required, found $PY_VERSION" >&2
    exit 1
  fi
else
  echo "Error: Python 3.11+ not found" >&2
  exit 1
fi

echo "=== validate_memory_system ==="
$PYTHON -c "
import sys
sys.path.insert(0, 'memory_core/tools')
from validate_memory_system import ValidateResult, check_gateway_import, check_core_builder_resolve, check_context_package, check_core_config_path
result = ValidateResult()
ok = check_gateway_import(result)
if not ok:
    print(result.summary())
    sys.exit(1)
builder_ok, builder = check_core_builder_resolve(result)
if not builder_ok or builder is None:
    print(result.summary())
    sys.exit(1)
check_context_package(result, builder)
check_core_config_path(result)
print(result.summary())
if not result.all_passed:
    sys.exit(1)
"

echo "=== pollution detection (if available) ==="
if $PYTHON memory_core/tools/validate_memory_system.py --help 2>&1 | grep -q -i pollution; then
    $PYTHON memory_core/tools/validate_memory_system.py --check pollution
else
    echo "(pollution check sub-command not yet available; skipping non-fatally)"
fi

echo "=== CI config integrity check ==="

check_ci_config() {
    local CI_FILE=".github/workflows/ci.yml"
    local errors=0

    # 1. Check ci.yml is non-empty
    if [ ! -s "$CI_FILE" ]; then
        echo "✗ $CI_FILE is empty or missing"
        errors=$((errors + 1))
    else
        echo "✓ $CI_FILE is non-empty"
    fi

    # 2. Validate YAML syntax
    if [ "$errors" -eq 0 ]; then
        if ! $PYTHON -c "
import sys
try:
    import yaml
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'pyyaml'])
    import yaml
with open('$CI_FILE', 'r') as f:
    data = yaml.safe_load(f)
if data is None:
    print('YAML parsed as empty/null')
    sys.exit(1)
if 'jobs' not in data:
    print('Missing required top-level key: jobs')
    sys.exit(1)
" 2>/dev/null; then
            echo "✗ YAML syntax validation failed"
            errors=$((errors + 1))
        else
            echo "✓ YAML syntax is valid"
        fi
    fi

    # 3. Verify core required jobs exist (ci-ok is the aggregate gate)
    if [ "$errors" -eq 0 ]; then
        REQUIRED_JOBS=("test" "ci-ok")
        MISSING_JOBS=""
        for job in "${REQUIRED_JOBS[@]}"; do
            if ! $PYTHON -c "
import yaml
with open('$CI_FILE', 'r') as f:
    data = yaml.safe_load(f)
jobs = data.get('jobs', {})
import sys
sys.exit(0 if '$job' in jobs else 1)
" 2>/dev/null; then
                if [ -z "$MISSING_JOBS" ]; then
                    MISSING_JOBS="$job"
                else
                    MISSING_JOBS="$MISSING_JOBS, $job"
                fi
            fi
        done

        if [ -n "$MISSING_JOBS" ]; then
            echo "✗ Missing required jobs: $MISSING_JOBS"
            errors=$((errors + 1))
        else
            echo "✓ Required jobs (test, ci-ok) present"
        fi
    fi

    if [ "$errors" -gt 0 ]; then
        echo "✗ CI config integrity check failed ($errors error(s))"
        exit 1
    else
        echo "✓ CI config integrity check passed"
    fi
}

check_ci_config

echo "=== CI health check OK ==="
