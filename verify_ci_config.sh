#!/bin/bash
# Verification script for ci-config-cleanup feature (10 assertions)

set -e

echo "Running 10 verification assertions for ci-config-cleanup..."
echo ""

# VAL-CI-001: CHANGELOG.md top entry is ## [0.9.0]
echo "VAL-CI-001: CHANGELOG.md top entry is ## [0.9.0]"
if head -5 CHANGELOG.md | grep -q '## \[0.9.0\]'; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-002: No feature_flags.cpython-*.pyc exists anywhere in repo
echo "VAL-CI-002: No feature_flags.cpython-*.pyc exists"
if ! find . -name 'feature_flags.cpython-*.pyc' -not -path './.venv/*' -not -path './build/*' | grep -q .; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-003: .env.example documents real MEMORY_FEATURE_* vars
echo "VAL-CI-003: .env.example documents MEMORY_FEATURE_* vars"
if grep -q '功能开关' .env.example && grep 'MEMORY_FEATURE_' .env.example | wc -l | xargs test 2 -le; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-004: dependabot.yml has minimum-release-age: 7 days
echo "VAL-CI-004: dependabot.yml has minimum-release-age: 7 days"
if grep -A1 'minimum-release-age' .github/dependabot.yml | grep -q '7 days'; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-005: pytest config includes --durations=10
echo "VAL-CI-005: pytest config includes --durations=10"
if grep -q '\-\-durations=10' pyproject.toml || grep -q '\-\-durations=10' .github/workflows/ci.yml; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-006: pytest config includes --cov-fail-under=15
echo "VAL-CI-006: pytest config includes --cov-fail-under=15"
if grep -q '\-\-cov-fail-under=15' pyproject.toml || grep -q '\-\-cov-fail-under=15' .github/workflows/ci.yml; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-007: pytest-rerunfailures in dev deps and --reruns 2 configured
echo "VAL-CI-007: pytest-rerunfailures in dev deps and --reruns 2 configured"
if grep -q 'pytest-rerunfailures' pyproject.toml && (grep -q '\-\-reruns 2' pyproject.toml || grep -q '\-\-reruns 2' .github/workflows/ci.yml); then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-008: ci.yml has at least 3 date/timestamp markers
echo "VAL-CI-008: ci.yml has at least 3 date/timestamp markers"
DATE_COUNT=$(grep -c 'date' .github/workflows/ci.yml 2>/dev/null || echo 0)
if [ "$DATE_COUNT" -ge 3 ]; then
    echo "  ✓ PASS (found $DATE_COUNT markers)"
else
    echo "  ✗ FAIL (found $DATE_COUNT markers, need at least 3)"
    exit 1
fi

# VAL-CI-009: ci.yml has TODO/FIXME scanner step
echo "VAL-CI-009: ci.yml has TODO/FIXME scanner step"
if grep -qi 'TODO\|FIXME' .github/workflows/ci.yml && grep -A5 -i 'TODO\|FIXME' .github/workflows/ci.yml | grep -q 'grep\|rg\|todo'; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

# VAL-CI-010: CONTRIBUTING.md has test naming convention section
echo "VAL-CI-010: CONTRIBUTING.md has test naming convention section"
if grep -qi 'test.*naming\|test.*convention\|naming.*convention\|test_*' CONTRIBUTING.md; then
    echo "  ✓ PASS"
else
    echo "  ✗ FAIL"
    exit 1
fi

echo ""
echo "========================================="
echo "All 10 assertions PASSED ✓"
echo "========================================="
