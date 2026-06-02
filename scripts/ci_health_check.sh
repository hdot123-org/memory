#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "=== validate_memory_system ==="
python3 -c "
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
if python3 memory_core/tools/validate_memory_system.py --help 2>&1 | grep -q -i pollution; then
    python3 memory_core/tools/validate_memory_system.py --check pollution
else
    echo "(pollution check sub-command not yet available; skipping non-fatally)"
fi

echo "=== CI config integrity check ==="

check_ci_config() {
    local CI_FILE=".gitlab-ci.yml"
    local errors=0

    # 1. Check .gitlab-ci.yml is non-empty
    if [ ! -s "$CI_FILE" ]; then
        echo "✗ $CI_FILE is empty or missing"
        errors=$((errors + 1))
    else
        echo "✓ $CI_FILE is non-empty"
    fi

    # 2. Validate YAML syntax
    if [ "$errors" -eq 0 ]; then
        if ! python3 -c "
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
if 'stages' not in data:
    print('Missing required top-level key: stages')
    sys.exit(1)
" 2>/dev/null; then
            echo "✗ YAML syntax validation failed"
            errors=$((errors + 1))
        else
            echo "✓ YAML syntax is valid"
        fi
    fi

    # 3. Verify required stages exist
    if [ "$errors" -eq 0 ]; then
        REQUIRED_STAGES=("test" "health_check" "sync")
        MISSING_STAGES=""
        for stage in "${REQUIRED_STAGES[@]}"; do
            if ! python3 -c "
import yaml
with open('$CI_FILE', 'r') as f:
    data = yaml.safe_load(f)
stages = data.get('stages', [])
import sys
sys.exit(0 if '$stage' in stages else 1)
" 2>/dev/null; then
                if [ -z "$MISSING_STAGES" ]; then
                    MISSING_STAGES="$stage"
                else
                    MISSING_STAGES="$MISSING_STAGES, $stage"
                fi
            fi
        done

        if [ -n "$MISSING_STAGES" ]; then
            echo "✗ Missing required stages: $MISSING_STAGES"
            errors=$((errors + 1))
        else
            echo "✓ Required stages (test, health_check, sync) present"
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
