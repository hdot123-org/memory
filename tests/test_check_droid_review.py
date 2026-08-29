"""Tests for scripts/check_droid_review.sh jq decision logic.

Validates the fix for the stale-check race condition:
When a stale concluded check (e.g., 'skipped' from draft era) coexists
with a new in-progress review on the same SHA, the poller must NOT
immediately read the stale conclusion. It must return 'pending' until
all check runs are completed.

Bug: run 32435306919/32435603998 — ci-ok read stale 'skipped' while
review was in_progress, causing cancel-on-ci-fail to kill the running
review and creating a merge deadlock.

Fix: The jq expression first checks for any active (non-completed) check
runs. If found, returns 'pending'. Only when all runs are completed does
it read the latest non-cancelled conclusion.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

# The jq expression extracted from check_droid_review.sh
# This must be kept in sync with the script's actual jq logic.
SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_droid_review.sh"


def _extract_jq_expression():
    """Extract the jq expression from the script source.

    Returns the raw jq filter string used for check-run decision logic.
    """
    script_text = SCRIPT_PATH.read_text()
    # The jq expression is between the single-quoted delimiters in the
    # STATUS=$(echo "$CHECKS" | jq -r '...') block
    # We search for the block that starts after 'STATUS=$(echo "$CHECKS" | jq -r'
    start_marker = 'STATUS=$(echo "$CHECKS" | jq -r \''
    start_idx = script_text.find(start_marker)
    assert start_idx != -1, "Could not find STATUS jq block in script"
    start_idx += len(start_marker)
    # Find matching closing single-quote — the jq expression ends at
    # the line that contains only "  ')"
    end_marker = "\n  ')"
    end_idx = script_text.find(end_marker, start_idx)
    assert end_idx != -1, "Could not find end of jq expression"
    return script_text[start_idx:end_idx]


def _run_jq(jq_expr: str, check_runs_json: dict) -> str:
    """Run a jq expression against a check-runs API response fixture.

    Returns the stripped stdout string (the decision result).
    """
    payload = json.dumps(check_runs_json)
    result = subprocess.run(
        ["jq", "-r", jq_expr],
        input=payload,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"jq failed: {result.stderr}"
    return result.stdout.strip()


def _make_check_run(status: str, conclusion, started_at: str = "2026-08-21T00:00:00Z"):
    """Helper to build a single check_run entry."""
    return {
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
    }


@pytest.fixture
def jq_expr():
    """Extract the jq expression from the script (cached per session)."""
    return _extract_jq_expression()


class TestStaleCheckRaceCondition:
    """Four fixture scenarios for the stale-check race condition."""

    def test_stale_skip_only_returns_skipped(self, jq_expr):
        """Fixture 1: Only a stale concluded 'skipped' check exists.

        Expected: 'skipped' — no active runs, so read the conclusion.
        This is the Dependabot path: when droid-review is skipped,
        the Dependabot exception can allow merge.
        """
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "skipped", "2026-08-21T00:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "skipped"

    def test_stale_skip_plus_inprogress_returns_pending(self, jq_expr):
        """Fixture 2: Stale 'skipped' + new in-progress review.

        Expected: 'pending' — must NOT read stale 'skipped'.
        This is the exact race condition from run 32435306919.
        """
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "skipped", "2026-08-21T00:00:00Z"),
                _make_check_run("in_progress", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_inprogress_only_no_concluded_returns_pending(self, jq_expr):
        """Fixture 3: Only in-progress check, no concluded checks.

        Expected: 'pending' — review is running, keep polling.
        """
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("in_progress", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_latest_success_returns_success(self, jq_expr):
        """Fixture 4: All completed, latest is 'success'.

        Expected: 'success' — normal happy path.
        """
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "success", "2026-08-21T02:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "success"


class TestDualTriggerCancelled:
    """Dual-trigger scenario: one cancelled, one completed."""

    def test_cancelled_plus_success_returns_success(self, jq_expr):
        """When dual triggers create two runs and one is cancelled,
        the non-cancelled conclusion should be returned."""
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "cancelled", "2026-08-21T00:00:00Z"),
                _make_check_run("completed", "success", "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "success"

    def test_cancelled_plus_queued_returns_pending(self, jq_expr):
        """One cancelled (old) + one queued (new) — must wait."""
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "cancelled", "2026-08-21T00:00:00Z"),
                _make_check_run("queued", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"


class TestEdgeCases:
    """Edge cases for the jq decision logic."""

    def test_empty_check_runs_returns_pending(self, jq_expr):
        """No check runs at all → pending (keep polling)."""
        fixture = {"total_count": 0, "check_runs": []}
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_completed_failure_returns_failure(self, jq_expr):
        """All completed, latest is 'failure'."""
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "failure", "2026-08-21T02:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "failure"

    def test_completed_neutral_returns_neutral(self, jq_expr):
        """All completed, latest is 'neutral'."""
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "neutral", "2026-08-21T02:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "neutral"

    def test_stale_failure_plus_inprogress_returns_pending(self, jq_expr):
        """Stale 'failure' + new in-progress review — must wait,
        not immediately report failure."""
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "failure", "2026-08-21T00:00:00Z"),
                _make_check_run("in_progress", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_multiple_completed_latest_wins(self, jq_expr):
        """Multiple completed runs (dual trigger), latest non-cancelled wins."""
        fixture = {
            "total_count": 3,
            "check_runs": [
                _make_check_run("completed", "cancelled", "2026-08-21T00:00:00Z"),
                _make_check_run("completed", "failure", "2026-08-21T00:30:00Z"),
                _make_check_run("completed", "success", "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "success"


class TestActiveCheckGuardStructure:
    """Structural lock: the script must contain an active-check guard.

    This ensures the fix is not accidentally reverted — the script must
    check for non-completed check runs BEFORE reading conclusions.
    """

    def test_script_checks_active_runs_before_conclusion(self):
        """The jq expression must reference .status to detect active runs."""
        jq_expr = _extract_jq_expression()
        # Must contain a check for non-completed status
        assert ".status" in jq_expr, (
            "Script must check .status of check runs to detect active runs "
            "before reading conclusions (stale-check race guard)"
        )
        assert "completed" in jq_expr, (
            "Script must compare .status against 'completed' to identify active (in-progress/queued) check runs"
        )

    def test_script_preserves_cancelled_exclusion(self):
        """The cancelled exclusion must remain for dual-trigger handling."""
        jq_expr = _extract_jq_expression()
        assert "cancelled" in jq_expr, (
            "Script must still exclude 'cancelled' conclusions for dual-trigger race handling"
        )


# ---------------------------------------------------------------------------
# Network resilience (droid-review P1/P2 findings on infra-core PR #44,
# 2026-08-29; both repos' copies share the bug).
#
# P1: under `set -e`, a curl-level failure (timeout/DNS/refused) inside the
#     polling loop exits the whole script, breaking the 120-retry mechanism —
#     a single transient network blip turns ci-ok red.
# P2: is_dependabot_pr() has no guard on curl/jq failure — a transient API
#     error silently misjudges the PR author.
#
# Contract after the fix: transient curl/jq failures are retried inside the
# loop; the Dependabot probe fails CLOSED (never fail-open); loop exhaustion
# exits 1 (never falls through with curl's exit code or exit 0).
# ---------------------------------------------------------------------------

SUCCESS_BODY = json.dumps(
    {
        "total_count": 1,
        "check_runs": [
            {
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-08-29T00:00:00Z",
            },
        ],
    }
)
SKIPPED_BODY = json.dumps(
    {
        "total_count": 1,
        "check_runs": [
            {
                "status": "completed",
                "conclusion": "skipped",
                "started_at": "2026-08-29T00:00:00Z",
            },
        ],
    }
)
RATE_LIMIT_BODY = json.dumps(
    {
        "message": "API rate limit exceeded for installation.",
        "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api",
    }
)

# Fake curl driven by $FAKE_CURL_BEHAVIORS (JSON: kind -> [(exit_code, body)]).
# The Nth call of a kind uses behaviors[N-1]; the last entry repeats. Call
# counts persist in $FAKE_CURL_STATE_DIR so recovery sequences are possible.
FAKE_CURL_TEMPLATE = """#!/usr/bin/env python3
import json
import os
import sys

url = sys.argv[-1]
kind = "checkruns" if "check-runs" in url else "pulls"
behaviors = json.loads(os.environ["FAKE_CURL_BEHAVIORS"])[kind]
state_dir = os.environ["FAKE_CURL_STATE_DIR"]
count_file = os.path.join(state_dir, kind + ".count")
try:
    count = int(open(count_file).read().strip())
except Exception:
    count = 0
count += 1
with open(count_file, "w") as fh:
    fh.write(str(count))
exit_code, body = behaviors[min(count - 1, len(behaviors) - 1)]
sys.stdout.write(body)
sys.exit(exit_code)
"""


class TestNetworkResilience:
    """Poll-loop and Dependabot-probe network resilience (P1/P2)."""

    @pytest.fixture
    def fake_bin(self, tmp_path):
        """PATH shim: instant sleep (skip the 30s backoff) + scripted curl."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        sleep = bin_dir / "sleep"
        sleep.write_text("#!/bin/bash\nexit 0\n")
        sleep.chmod(0o755)
        curl = bin_dir / "curl"
        curl.write_text(FAKE_CURL_TEMPLATE)
        curl.chmod(0o755)
        return bin_dir

    def _run_poller(self, script_path, fake_bin, behaviors):
        state_dir = fake_bin.parent / "state"
        state_dir.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
        env["FAKE_CURL_BEHAVIORS"] = json.dumps(behaviors)
        env["FAKE_CURL_STATE_DIR"] = str(state_dir)
        return subprocess.run(
            [
                "bash",
                str(script_path),
                "pull_request",
                "hdot123-org/memory",
                "deadbeefcafe",
                "fake-token",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

    def test_transient_curl_failure_retries_and_succeeds(self, fake_bin):
        """Two network-level curl failures must be absorbed; third succeeds."""
        behaviors = {
            "checkruns": [(7, ""), (7, ""), (0, SUCCESS_BODY)],
            "pulls": [(0, "[]")],
        }
        result = self._run_poller(SCRIPT_PATH, fake_bin, behaviors)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count("transient network error") == 2
        assert "✓ droid-review passed" in result.stdout

    def test_persistent_curl_failure_exhausts_attempts_fail_closed(self, fake_bin):
        """120 consecutive curl failures: keep retrying, then exit 1.

        Pre-fix behavior: the script dies on attempt 1 with curl's exit
        code (7) — the P1 bug. Post-fix: all 120 attempts run, then the
        fail-closed exhaustion handler exits 1 (never curl's code, never 0).
        """
        behaviors = {"checkruns": [(7, "")], "pulls": [(0, "[]")]}
        result = self._run_poller(SCRIPT_PATH, fake_bin, behaviors)
        assert result.returncode == 1
        assert "Attempt 120/120" in result.stdout, "poller must keep retrying, not die on the first transient failure"
        assert "exhausted 120 attempts" in result.stdout

    def test_rate_limit_body_is_transient_not_fatal(self, fake_bin):
        """A rate-limit body (no .check_runs) makes jq exit 5 — retry, not die."""
        behaviors = {
            "checkruns": [(0, RATE_LIMIT_BODY), (0, SUCCESS_BODY)],
            "pulls": [(0, "[]")],
        }
        result = self._run_poller(SCRIPT_PATH, fake_bin, behaviors)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "transient API error" in result.stdout
        assert "✓ droid-review passed" in result.stdout

    def test_dependabot_probe_failure_is_fail_closed(self, fake_bin):
        """API failure probing the PR author: BLOCK (exit 1), never fail-open."""
        behaviors = {"checkruns": [(0, SKIPPED_BODY)], "pulls": [(7, "")]}
        result = self._run_poller(SCRIPT_PATH, fake_bin, behaviors)
        assert result.returncode == 1
        assert "treating as non-Dependabot" in result.stdout
        assert "BLOCK" in result.stdout

    def test_dependabot_skipped_review_still_allows_merge(self, fake_bin):
        """Control: the Dependabot exception survives the guard refactor."""
        behaviors = {
            "checkruns": [(0, SKIPPED_BODY)],
            "pulls": [(0, json.dumps([{"user": {"login": "dependabot[bot]"}}]))],
        }
        result = self._run_poller(SCRIPT_PATH, fake_bin, behaviors)
        assert result.returncode == 0
        assert "allowing merge" in result.stdout


class TestNetworkResilienceStructure:
    """Belt-and-suspenders: the guard patterns must stay in the script."""

    def test_poll_loop_curl_has_transient_guard(self):
        text = SCRIPT_PATH.read_text()
        assert re.search(r'check-runs\?check_name=droid-review"\)\s*\\\n\s*\|\| \{', text), (
            "poll-loop curl needs a || { ... continue; } transient guard"
        )

    def test_status_jq_has_transient_guard(self):
        text = SCRIPT_PATH.read_text()
        assert re.search(r"'\)\s*\|\| \{", text), "STATUS jq assignment needs a transient-retry guard"

    def test_loop_exhaustion_fails_closed(self):
        text = SCRIPT_PATH.read_text()
        tail = text[text.rindex("\ndone") :]
        assert "exit 1" in tail, (
            "loop exhaustion must fail closed (exit 1), never fall through "
            "with exit 0 — ci-ok would read that as droid-review passed"
        )

    def test_dependabot_probe_has_fail_closed_guards(self):
        text = SCRIPT_PATH.read_text()
        start = text.index("is_dependabot_pr() {")
        body = text[start : text.index("\n}", start)]
        assert body.count("|| {") == 2, "is_dependabot_pr must guard both its curl and its jq call"
        assert body.count("return 1") >= 3, "guards must return 1 (non-Dependabot) — fail-closed, never fail-open"
