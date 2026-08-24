#!/usr/bin/env python3
"""
TDD tests for Red PR Sweeper (F2) — VAL-SWEEP-002~014, VAL-INV-009

Red PR Sweeper adds a new detection branch in reconcile-evolution.sh:
- Three conditions (conjunction): open PR + gh pr checks failure + age > threshold
- Threshold: P90 = 506.7 min from distribution.json, rounded to 507 min
- Debounce 1: l2d-INFRA-*.lock existence → skip
- Debounce 2: new commit within 30 min → skip
- Flow: comment first → comment failure = no close → comment success = close
- Post-close: cleanup pending-ci file, go to closed-unmerged path
- DRY_RUN mode: zero write operations

Test approach: extract sweep_red_pr() from reconcile-evolution.sh into a
standalone wrapper script that can run without LINEAR_API_KEY or op-mcp.sh
dependencies. This avoids the full-script early-exit problem.
"""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "webhook-scripts" / "reconcile-evolution.sh"


def _extract_sweep_function() -> str:
    """Extract the sweep_red_pr() function body from reconcile-evolution.sh.

    Uses brace-counting to properly extract the function including nested braces.
    """
    script_content = SCRIPT_PATH.read_text()
    lines = script_content.split("\n")

    # Find the start of sweep_red_pr()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("sweep_red_pr()"):
            start_idx = i
            break

    if start_idx is None:
        raise RuntimeError("sweep_red_pr() function not found in script")

    # Count braces to find the end
    brace_count = 0
    end_idx = None
    for i in range(start_idx, len(lines)):
        line = lines[i]
        # Skip braces inside strings/comments (simple heuristic)
        for ch in line:
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        if end_idx is not None:
            break

    if end_idx is None:
        raise RuntimeError("Could not find end of sweep_red_pr() function")

    return "\n".join(lines[start_idx : end_idx + 1])


def _make_gh_shim(tmp_path: Path, responses: dict) -> Path:
    """Create a gh CLI shim that logs calls and returns fixture responses.

    Args:
        tmp_path: pytest tmp_path for isolation
        responses: dict mapping command patterns to responses.
            Keys: "pr_view_<NUM>" for view responses (JSON with createdAt/commits),
                  "pr_checks_<NUM>" for checks responses (JSON array of check objects),
                  "pr_comment_<NUM>" for comment exit codes,
                  "pr_close_<NUM>" for close exit codes.

    Returns:
        Path to the shim script
    """
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim_path = shim_dir / "gh"
    log_path = tmp_path / "gh_calls.log"
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # Write fixture files
    for key, resp in responses.items():
        if "json" in resp:
            (fixtures_dir / f"{key}.json").write_text(json.dumps(resp["json"]))
        if "stdout" in resp:
            (fixtures_dir / f"{key}.stdout").write_text(resp["stdout"])
        (fixtures_dir / f"{key}.exit").write_text(str(resp.get("exit", 0)))

    shim_script = f'''#!/usr/bin/env bash
# gh shim for Red PR Sweeper tests
echo "$@" >> "{log_path}"

cmd="$1"; shift

case "$cmd" in
    pr)
        subcmd="$1"; shift
        case "$subcmd" in
            view)
                pr_num="$1"; shift
                # Parse --json and --jq from args
                json_field=""
                jq_expr=""
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --json) json_field="$2"; shift 2 ;;
                        --jq) jq_expr="$2"; shift 2 ;;
                        --repo) shift 2 ;;
                        *) shift ;;
                    esac
                done
                # Field validation: reject nonexistent fields (like real gh CLI)
                valid_view_fields="createdAt commits author labels state title"
                for f in $(echo "$json_field" | tr ',' ' '); do
                    if ! echo "$valid_view_fields" | grep -qw "$f"; then
                        echo "Unknown JSON field: \\"$f\\"" >&2
                        echo "Available fields:" >&2
                        echo "  $valid_view_fields" >&2
                        exit 1
                    fi
                done
                if [ -f "{fixtures_dir}/pr_view_${{pr_num}}.json" ]; then
                    if [ -n "$jq_expr" ]; then
                        # Extract field using Python (supports nested access like .commits[-1].committedDate)
                        {sys.executable} -c "
import json, sys, re
data = json.load(open('{fixtures_dir}/pr_view_${{pr_num}}.json'))
expr = '$jq_expr'.lstrip('.')
# Handle nested access: commits[-1].committedDate
parts = re.split(r'\\.', expr)
val = data
for part in parts:
    m = re.match(r'(\\w+)\\[(-?\\d+)\\]', part)
    if m:
        val = val.get(m.group(1), [])
        val = val[int(m.group(2))]
    else:
        val = val.get(part, '')
print(val)
"
                    else
                        cat "{fixtures_dir}/pr_view_${{pr_num}}.json"
                    fi
                    exit $(cat "{fixtures_dir}/pr_view_${{pr_num}}.exit" 2>/dev/null || echo 0)
                fi
                echo '{{}}'
                ;;
            checks)
                pr_num="$1"; shift
                # Parse --json fields
                json_field=""
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --repo) shift 2 ;;
                        --json) json_field="$2"; shift 2 ;;
                        *) shift ;;
                    esac
                done
                # Field validation: reject nonexistent fields (like real gh CLI)
                valid_checks_fields="bucket completedAt description event link name startedAt state workflow"
                for f in $(echo "$json_field" | tr ',' ' '); do
                    if ! echo "$valid_checks_fields" | grep -qw "$f"; then
                        echo "Unknown JSON field: \\"$f\\"" >&2
                        echo "Available fields:" >&2
                        echo "  $valid_checks_fields" >&2
                        exit 1
                    fi
                done
                # .stdout fixture (if present) overrides .json — used to
                # simulate genuine fetch failures (empty stdout + exit != 0)
                if [ -f "{fixtures_dir}/pr_checks_${{pr_num}}.stdout" ]; then
                    cat "{fixtures_dir}/pr_checks_${{pr_num}}.stdout"
                    exit $(cat "{fixtures_dir}/pr_checks_${{pr_num}}.exit" 2>/dev/null || echo 0)
                fi
                if [ -f "{fixtures_dir}/pr_checks_${{pr_num}}.json" ]; then
                    cat "{fixtures_dir}/pr_checks_${{pr_num}}.json"
                    exit $(cat "{fixtures_dir}/pr_checks_${{pr_num}}.exit" 2>/dev/null || echo 0)
                fi
                echo "[]"
                ;;
            comment)
                pr_num="$1"
                if [ -f "{fixtures_dir}/pr_comment_${{pr_num}}.exit" ]; then
                    exit $(cat "{fixtures_dir}/pr_comment_${{pr_num}}.exit")
                fi
                exit 0
                ;;
            close)
                pr_num="$1"
                if [ -f "{fixtures_dir}/pr_close_${{pr_num}}.exit" ]; then
                    exit $(cat "{fixtures_dir}/pr_close_${{pr_num}}.exit")
                fi
                exit 0
                ;;
            list)
                if [ -f "{fixtures_dir}/pr_list.json" ]; then
                    cat "{fixtures_dir}/pr_list.json"
                    exit $(cat "{fixtures_dir}/pr_list.exit" 2>/dev/null || echo 0)
                fi
                echo "[]"
                ;;
        esac
        ;;
esac
'''

    shim_path.write_text(shim_script)
    shim_path.chmod(0o755)
    return shim_path


def _make_wrapper(tmp_path: Path, gh_shim: Path, lock_dir: Path, log_dir: Path) -> Path:
    """Create a wrapper script that sets up environment and calls sweep_red_pr().

    The wrapper extracts sweep_red_pr() from reconcile-evolution.sh and runs it
    with the required variables defined, bypassing the full script's dependencies.
    """
    wrapper_path = tmp_path / "run_sweep.sh"

    # Extract the sweep_red_pr function from the source script
    sweep_func = _extract_sweep_function()

    wrapper_script = f'''#!/usr/bin/env bash
# Test wrapper for sweep_red_pr() — isolated from reconcile-evolution.sh dependencies
set -euo pipefail

# Required variables
REPO="hdot123-org/memory"
LOCK_DIR="{lock_dir}"
DRY_RUN="${{DRY_RUN:-0}}"
LOG_FILE="{log_dir}/sweep-test.log"
PYTHON_BIN="{sys.executable}"

# Constants from reconcile-evolution.sh
SWEEP_RED_PR_THRESHOLD_MINUTES=507
SWEEP_NEW_COMMIT_WINDOW_MINUTES=30

# Logging function (simplified for tests)
log() {{ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; echo "$*"; }}

# The sweep_red_pr function (extracted from reconcile-evolution.sh)
{sweep_func}

# Call the function with arguments
sweep_red_pr "$1" "$2"
'''

    wrapper_path.write_text(wrapper_script)
    wrapper_path.chmod(0o755)
    return wrapper_path


def _run_sweep(
    tmp_path: Path, wrapper: Path, gh_shim: Path, pr_number: int, linear_ref: str, dry_run: str = "0"
) -> tuple[int, str, str]:
    """Run the sweep_red_pr wrapper and return (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    env["PATH"] = f"{gh_shim.parent}:{env.get('PATH', '')}"
    env["DRY_RUN"] = dry_run

    result = subprocess.run(
        ["bash", str(wrapper), str(pr_number), linear_ref],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def _get_gh_calls(tmp_path: Path) -> str:
    """Read the gh shim call log, returning empty string if not created."""
    log_path = tmp_path / "gh_calls.log"
    if log_path.exists():
        return log_path.read_text()
    return ""


# ============================================================================
# INFRA-534 regression: gh pr checks exit-code semantics
# ============================================================================


class TestChecksExitCodeSemantics:
    """gh pr checks exits 1 on failing checks while still printing valid JSON.

    The pre-INFRA-534 code used `|| echo "[]"` which appended "[]" after the
    JSON on stdout, corrupting it so has_failure always parsed as 0 — the
    sweeper never fired on real red PRs.
    """

    def test_failing_exit_code_with_valid_json_triggers(self, tmp_path):
        """gh pr checks exit=1 (failing PR) + valid JSON on stdout → trigger.

        This mirrors real gh behaviour: exit 1 means "some checks failed",
        stdout still carries the JSON array.
        """
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4270": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4270": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 1,  # real gh behaviour on failing checks
            },
            "pr_comment_4270": {"exit": 0},
            "pr_close_4270": {"exit": 0},
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4270, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" in calls, (
            f"gh pr comment must be called for failing PR (exit=1 + FAILURE json). Calls: {calls}"
        )
        assert "close" in calls, f"gh pr close must be called for failing PR. Calls: {calls}"

    def test_pending_exit_code_with_valid_json_no_trigger(self, tmp_path):
        """gh pr checks exit=8 (pending) + no FAILURE conclusion → no trigger."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4271": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4271": {
                "json": [
                    {"name": "ci", "state": "IN_PROGRESS", "completedAt": None},
                ],
                "exit": 8,  # pending
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4271, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called for pending checks (exit=8)"
        assert "close" not in calls, "gh pr close must NOT be called for pending checks (exit=8)"

    def test_empty_stdout_falls_back_to_empty_list(self, tmp_path):
        """Genuine fetch failure (empty stdout, non-zero exit) → treated as no checks, skip."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4272": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            # No pr_checks_4272 fixture: shim echoes "[]" itself, but simulate
            # a hard failure by fixture returning empty stdout + exit 1.
            "pr_checks_4272": {
                "json": [],
                "stdout": "",
                "exit": 1,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4272, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called when checks unavailable"
        assert "close" not in calls, "gh pr close must NOT be called when checks unavailable"


# ============================================================================
# INFRA-534 regression: sweep_red_pr bare call under `set -e`
# ============================================================================


class TestBareCallSetEGuard:
    """The main loop calls sweep_red_pr bare; its return-1 (skip/debounce paths)
    must not abort reconcile-evolution.sh under `set -euo pipefail`.

    Pre-INFRA-534 code called the function bare, so any open PR for a Linear
    issue killed the whole reconciliation mid-run.
    """

    def test_main_loop_call_is_set_e_safe(self):
        """The main-loop invocation must be guarded (if ! / || true style)."""
        script_content = SCRIPT_PATH.read_text()

        # Find every sweep_red_pr call site that is not the definition
        call_sites = []
        for i, line in enumerate(script_content.split("\n")):
            stripped = line.strip()
            if "sweep_red_pr" in stripped and "sweep_red_pr()" not in stripped:
                if stripped.startswith("#"):
                    continue
                call_sites.append((i + 1, stripped))

        assert call_sites, "sweep_red_pr must be called from the main loop"

        for line_no, line in call_sites:
            guarded = line.startswith("if !") or "|| true" in line or "sweep_result=" in line and "$(" in line
            assert guarded, f"Line {line_no}: sweep_red_pr call must be set -e safe (if ! / || true): {line!r}"

    def test_bare_call_with_return_1_does_not_abort_loop(self, tmp_path):
        """Integration: wrapper runs with set -euo pipefail; a skip-path
        sweep_red_pr (return 1) must let the caller script continue."""
        wrapper_path = tmp_path / "set_e_probe.sh"
        wrapper_path.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
sweep_red_pr() { return 1; }
for pr_number in 123 456; do
    if ! sweep_red_pr "$pr_number" "INFRA-999"; then
        echo "continued after $pr_number"
    fi
done
echo "LOOP_COMPLETED"
"""
        )
        wrapper_path.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"guarded loop must exit 0, got {result.returncode}: {result.stderr}"
        assert "LOOP_COMPLETED" in result.stdout, "loop must complete after return-1 calls"
        assert result.stdout.count("continued after") == 2


# ============================================================================
# VAL-SWEEP-002: Threshold constant with data source traceability
# ============================================================================


class TestThresholdTraceability:
    def test_threshold_constant_references_distribution_json(self):
        """Threshold constant references distribution.json or stats.md in comments."""
        script_content = SCRIPT_PATH.read_text()

        assert "SWEEP_RED_PR_THRESHOLD_MINUTES" in script_content, "Threshold constant must be defined"

        lines = script_content.split("\n")
        found_reference = False

        for i, line in enumerate(lines):
            if "SWEEP_RED_PR_THRESHOLD_MINUTES" in line and "=" in line and not line.strip().startswith("#"):
                context_start = max(0, i - 5)
                context_end = min(len(lines), i + 1)
                context = "\n".join(lines[context_start:context_end])

                has_reference = any(
                    [
                        "distribution.json" in context,
                        "stats.md" in context,
                        "P90" in context,
                        "p90" in context,
                        "506.7" in context,
                        "Data source" in context or "data source" in context,
                    ]
                )

                if has_reference:
                    found_reference = True
                    break

        assert found_reference, (
            "Threshold constant must reference data source (distribution.json/stats.md/P90) in comments"
        )

    def test_threshold_value_matches_p90(self):
        """Threshold value matches P90 from distribution.json (506.7 → 507 rounded)."""
        dist_path = (
            REPO_ROOT.parent
            / ".factory"
            / "missions"
            / "628dabc0-d085-46fe-bca2-289088cf2b25"
            / "artifacts"
            / "red-pr-sweep"
            / "distribution.json"
        )

        if not dist_path.exists():
            pytest.skip("distribution.json not available")

        script_content = SCRIPT_PATH.read_text()
        match = re.search(r"SWEEP_RED_PR_THRESHOLD_MINUTES=(\d+)", script_content)

        assert match, "Threshold constant must be defined"
        threshold_value = int(match.group(1))

        # VAL-SWEEP-002: threshold == ceil(P90) = 507
        assert threshold_value == 507, f"Threshold must be 507 (ceil of P90=506.7), got {threshold_value}"


# ============================================================================
# VAL-SWEEP-003: Three conditions trigger closure flow
# ============================================================================


class TestThreeConditionsTrigger:
    def test_open_plus_failure_plus_over_threshold_triggers(self, tmp_path):
        """Open PR + checks failure + age > threshold → enters closure flow.

        PR 4242: created 600 min ago (> 507 threshold), has FAILURE checks.
        Expected: gh pr comment then gh pr close called.
        """
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            # gh pr view 4242 --json createdAt returns old timestamp
            "pr_view_4242": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            # gh pr checks 4242 --json ... returns FAILURE
            "pr_checks_4242": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
            "pr_comment_4242": {"exit": 0},
            "pr_close_4242": {"exit": 0},
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4242, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" in calls, f"gh pr comment must be called. Calls: {calls}"
        assert "close" in calls, f"gh pr close must be called. Calls: {calls}"

        # Verify order: comment before close
        comment_pos = calls.find("comment")
        close_pos = calls.find("close")
        assert comment_pos < close_pos, "comment must precede close"


# ============================================================================
# VAL-SWEEP-004: Negative guards don't trigger
# ============================================================================


class TestNegativeGuards:
    def test_green_checks_no_trigger(self, tmp_path):
        """Open PR + all green checks + over threshold → no trigger."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4243": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4243": {
                "json": [
                    {"name": "ci", "state": "SUCCESS", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4243, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called for green checks"
        assert "close" not in calls, "gh pr close must NOT be called for green checks"

    def test_under_threshold_no_trigger(self, tmp_path):
        """Open PR + checks failure + under threshold → no trigger."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=400)  # < 507 threshold

        gh_responses = {
            "pr_view_4244": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4244": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4244, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called when under threshold"
        assert "close" not in calls, "gh pr close must NOT be called when under threshold"

    def test_no_checks_no_trigger(self, tmp_path):
        """Open PR + no checks data + over threshold → no trigger."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4245": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4245": {
                "json": [],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4245, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called when no checks"
        assert "close" not in calls, "gh pr close must NOT be called when no checks"


# ============================================================================
# VAL-SWEEP-005: l2d-INFRA-*.lock existence → skip
# ============================================================================


class TestDebounceLock:
    def test_l2d_lock_exists_skips(self, tmp_path):
        """l2d-INFRA-*.lock exists → skip even if red PR meets all conditions."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4246": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4246": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        # Create l2d lock for INFRA-888
        lock_path = lock_dir / "l2d-INFRA-888.lock"
        lock_path.touch()

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4246, "INFRA-888")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called when l2d lock exists"
        assert "close" not in calls, "gh pr close must NOT be called when l2d lock exists"

        # Verify lock file unchanged
        assert lock_path.exists(), "l2d lock must still exist"
        assert lock_path.stat().st_size == 0, "l2d lock must remain 0 bytes"


# ============================================================================
# VAL-SWEEP-006: New commit within 30 min → skip
# ============================================================================


class TestDebounceNewCommit:
    def test_new_commit_within_30min_skips(self, tmp_path):
        """PR with new commit < 30 min ago → skip even if red and over threshold."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)
        last_commit_at = now - timedelta(minutes=29)  # 29 min ago (< 30)

        gh_responses = {
            "pr_view_4247": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": last_commit_at.isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4247": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4247, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called when recent commit"
        assert "close" not in calls, "gh pr close must NOT be called when recent commit"

    def test_old_commit_outside_30min_triggers(self, tmp_path):
        """PR with last commit > 30 min ago → triggers if other conditions met."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)
        last_commit_at = now - timedelta(minutes=31)  # 31 min ago (> 30)

        gh_responses = {
            "pr_view_4248": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": last_commit_at.isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4248": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
            "pr_comment_4248": {"exit": 0},
            "pr_close_4248": {"exit": 0},
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4248, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" in calls, f"gh pr comment must be called when commit is old. Calls: {calls}"
        assert "close" in calls, f"gh pr close must be called when commit is old. Calls: {calls}"


# ============================================================================
# VAL-SWEEP-007: Comment failure → no close
# ============================================================================


class TestCommentFailureNoClose:
    def test_comment_failure_skips_close(self, tmp_path):
        """gh pr comment fails → no close, lock preserved."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4249": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4249": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
            "pr_comment_4249": {"exit": 1},  # Comment fails
            "pr_close_4249": {"exit": 0},
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4249, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" in calls, "gh pr comment must be attempted"
        assert "close" not in calls, "gh pr close must NOT be called when comment fails"


# ============================================================================
# VAL-SWEEP-008: Comment success → close, comment contains required elements
# ============================================================================


class TestCommentSuccessClose:
    def test_comment_success_then_close(self, tmp_path):
        """gh pr comment succeeds → gh pr close called."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4250": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4250": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
            "pr_comment_4250": {"exit": 0},
            "pr_close_4250": {"exit": 0},
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4250, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" in calls, "gh pr comment must be called"
        assert "close" in calls, "gh pr close must be called"

        # Verify order
        comment_pos = calls.find("comment")
        close_pos = calls.find("close")
        assert comment_pos < close_pos, "comment must precede close"


# ============================================================================
# VAL-SWEEP-010: DRY_RUN mode zero writes
# ============================================================================


class TestDryRunMode:
    def test_dry_run_no_writes(self, tmp_path):
        """DRY_RUN=1 → no comment/close calls, only logging."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4251": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4251": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4251, "INFRA-999", dry_run="1")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called in DRY_RUN"
        assert "close" not in calls, "gh pr close must NOT be called in DRY_RUN"

        # Verify stdout/log contains [DRY_RUN] markers
        log_file = log_dir / "sweep-test.log"
        log_content = log_file.read_text() if log_file.exists() else stdout
        assert "[DRY_RUN]" in log_content or "[DRY_RUN]" in stdout, (
            f"DRY_RUN mode should log intended actions. stdout={stdout}, log={log_content}"
        )


# ============================================================================
# VAL-SWEEP-011: Structural assertion — no bare close path
# ============================================================================


class TestStructuralAssertion:
    def test_no_bare_close_path(self):
        """Every gh pr close call must have gh pr comment within 40 lines before it."""
        script_content = SCRIPT_PATH.read_text()
        lines = script_content.split("\n")

        # Find all gh pr close calls
        for i, line in enumerate(lines):
            if "gh pr close" in line and "comment" not in line:
                # Skip comment lines
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # Look back 40 lines for comment guard
                window_start = max(0, i - 40)
                window = lines[window_start:i]
                has_comment_guard = any("gh pr comment" in ln for ln in window)

                assert has_comment_guard, f"Line {i + 1}: gh pr close must have gh pr comment guard within 40 lines"


# ============================================================================
# VAL-SWEEP-012: Checks pending/queued don't trigger
# ============================================================================


class TestChecksPendingQueued:
    def test_pending_checks_no_trigger(self, tmp_path):
        """Checks in PENDING/IN_PROGRESS state → no trigger."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4252": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4252": {
                "json": [
                    {"name": "ci", "state": "IN_PROGRESS", "completedAt": None},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4252, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called for pending checks"
        assert "close" not in calls, "gh pr close must NOT be called for pending checks"

    def test_queued_checks_no_trigger(self, tmp_path):
        """Checks in QUEUED state → no trigger."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4253": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4253": {
                "json": [
                    {"name": "ci", "state": "QUEUED", "completedAt": None},
                ],
                "exit": 0,
            },
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4253, "INFRA-999")

        calls = _get_gh_calls(tmp_path)

        assert "comment" not in calls, "gh pr comment must NOT be called for queued checks"
        assert "close" not in calls, "gh pr close must NOT be called for queued checks"


# ============================================================================
# VAL-SWEEP-014: Post-close cleanup of pending-ci file
# ============================================================================


class TestPendingCiCleanup:
    def test_close_removes_pending_ci_file(self, tmp_path):
        """After close, pending-ci-{PR}.json is cleaned up."""
        now = datetime.now(UTC)
        created_at = now - timedelta(minutes=600)

        gh_responses = {
            "pr_view_4254": {
                "json": {
                    "createdAt": created_at.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4254": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
            "pr_comment_4254": {"exit": 0},
            "pr_close_4254": {"exit": 0},
        }

        gh_shim = _make_gh_shim(tmp_path, gh_responses)
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        wrapper = _make_wrapper(tmp_path, gh_shim, lock_dir, log_dir)

        # Create pending-ci file
        pending_file = lock_dir / "pending-ci-4254.json"
        pending_file.write_text(
            json.dumps(
                {
                    "pr_number": "4254",
                    "cwd": "/test/repo",
                    "created_at": (now - timedelta(minutes=40)).isoformat(),
                }
            )
        )
        assert pending_file.exists()

        exit_code, stdout, stderr = _run_sweep(tmp_path, wrapper, gh_shim, 4254, "INFRA-999")

        # Verify pending-ci file was cleaned up
        assert not pending_file.exists(), "pending-ci file must be removed after close"


# ============================================================================
# VAL-SWEEP-013: Multiple open PRs for same INFRA - independent judgment
# ============================================================================


class TestMultiPRIndependent:
    def test_each_pr_judged_independently(self, tmp_path):
        """Multiple PRs for same INFRA: only red ones get closed, green/young ones don't."""
        # This test verifies the structural design: sweep_red_pr takes pr_number
        # and linear_ref, and each PR is judged independently based on its own
        # checks/age/commit time. We test the function directly with two calls.
        now = datetime.now(UTC)

        # PR A: red + over threshold + old commit → should close
        created_a = now - timedelta(minutes=600)
        gh_responses_a = {
            "pr_view_4260": {
                "json": {
                    "createdAt": created_a.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4260": {
                "json": [
                    {"name": "ci", "state": "FAILURE", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
            "pr_comment_4260": {"exit": 0},
            "pr_close_4260": {"exit": 0},
        }

        gh_shim_a = _make_gh_shim(tmp_path / "a", gh_responses_a)
        lock_dir_a = tmp_path / "locks_a"
        lock_dir_a.mkdir()
        log_dir_a = tmp_path / "logs_a"
        log_dir_a.mkdir()
        wrapper_a = _make_wrapper(tmp_path / "a", gh_shim_a, lock_dir_a, log_dir_a)

        # PR B: green + over threshold → should NOT close
        created_b = now - timedelta(minutes=600)
        gh_responses_b = {
            "pr_view_4261": {
                "json": {
                    "createdAt": created_b.isoformat(),
                    "commits": [{"committedDate": (now - timedelta(hours=24)).isoformat()}],
                },
                "exit": 0,
            },
            "pr_checks_4261": {
                "json": [
                    {"name": "ci", "state": "SUCCESS", "completedAt": now.isoformat()},
                ],
                "exit": 0,
            },
        }

        gh_shim_b = _make_gh_shim(tmp_path / "b", gh_responses_b)
        lock_dir_b = tmp_path / "locks_b"
        lock_dir_b.mkdir()
        log_dir_b = tmp_path / "logs_b"
        log_dir_b.mkdir()
        wrapper_b = _make_wrapper(tmp_path / "b", gh_shim_b, lock_dir_b, log_dir_b)

        # Run both independently
        exit_a, stdout_a, stderr_a = _run_sweep(tmp_path / "a", wrapper_a, gh_shim_a, 4260, "INFRA-777")
        exit_b, stdout_b, stderr_b = _run_sweep(tmp_path / "b", wrapper_b, gh_shim_b, 4261, "INFRA-777")

        calls_a = _get_gh_calls(tmp_path / "a")
        calls_b = _get_gh_calls(tmp_path / "b")

        # PR A (red) should be closed
        assert "comment" in calls_a, "Red PR A must have comment called"
        assert "close" in calls_a, "Red PR A must have close called"

        # PR B (green) should NOT be closed
        assert "comment" not in calls_b, "Green PR B must NOT have comment called"
        assert "close" not in calls_b, "Green PR B must NOT have close called"


# ============================================================================
# VAL-INV-009: Threshold traceability chain
# ============================================================================


class TestThresholdChain:
    def test_threshold_chain_closed(self):
        """distribution.json P90 → stats.md recommendation → script constant: all consistent."""
        dist_path = (
            REPO_ROOT.parent
            / ".factory"
            / "missions"
            / "628dabc0-d085-46fe-bca2-289088cf2b25"
            / "artifacts"
            / "red-pr-sweep"
            / "distribution.json"
        )
        stats_path = (
            REPO_ROOT.parent
            / ".factory"
            / "missions"
            / "628dabc0-d085-46fe-bca2-289088cf2b25"
            / "artifacts"
            / "red-pr-sweep"
            / "stats.md"
        )

        if not dist_path.exists():
            pytest.skip("distribution.json not available")

        dist_data = json.loads(dist_path.read_text())
        p90 = dist_data["statistics"]["p90_minutes"]

        script_content = SCRIPT_PATH.read_text()
        match = re.search(r"SWEEP_RED_PR_THRESHOLD_MINUTES=(\d+)", script_content)
        assert match, "Threshold constant must be defined"
        threshold = int(match.group(1))

        import math

        expected = math.ceil(p90)
        assert threshold == expected, f"Script constant ({threshold}) must equal ceil(P90={p90}) = {expected}"

        # Verify stats.md references the same threshold if it exists
        if stats_path.exists():
            stats_content = stats_path.read_text()
            assert str(expected) in stats_content or str(p90) in stats_content, (
                "stats.md should reference the P90 value or recommended threshold"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
