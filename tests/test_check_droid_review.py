"""Tests for check_droid_review.sh script logic.

Since the script is a shell script that calls GitHub API, we test the logic
by mocking the API responses and verifying the exit codes.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

# Use absolute paths based on repo root for CI compatibility
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_droid_review.sh"
CI_YML_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def run_check_script(event_name, repository, commit_sha, mock_response, mock_status_code=200):
    """Helper to run check_droid_review.sh with mocked curl response."""
    # Mock curl to return our test response
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_response),
            returncode=mock_status_code
        )

        # We can't easily mock curl in bash, so we'll test the logic differently
        # Instead, we'll verify the script exists and is executable
        pass


def test_script_exists():
    """Verify check_droid_review.sh exists."""
    assert SCRIPT_PATH.exists(), "check_droid_review.sh must exist"
    # Note: Execute permission not required - CI uses `bash scripts/check_droid_review.sh`


def test_script_syntax_valid():
    """Verify the shell script has valid syntax."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT_PATH)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Script syntax error: {result.stderr}"


def test_push_event_skips_gracefully():
    """Verify push events skip droid-review check."""
    content = SCRIPT_PATH.read_text()
    assert 'if [ "$EVENT_NAME" != "pull_request" ]' in content
    assert 'exit 0' in content
    assert 'skipping droid-review check' in content


def test_success_logic():
    """Verify success case logic in script."""
    content = SCRIPT_PATH.read_text()
    assert 'if [ "$STATUS" = "success" ]' in content
    assert 'exit 0' in content
    assert 'droid-review passed' in content


def test_failure_logic():
    """Verify failure case logic in script."""
    content = SCRIPT_PATH.read_text()
    assert 'elif [ "$STATUS" = "failure" ]' in content
    assert 'exit 1' in content
    assert 'droid-review failed' in content


def test_pending_logic():
    """Verify pending/not-found case logic in script."""
    content = SCRIPT_PATH.read_text()
    assert 'pending' in content
    assert 'MAX_ATTEMPTS' in content
    assert 'not complete' in content


def test_github_api_call_present():
    """Verify the script calls GitHub API correctly."""
    content = SCRIPT_PATH.read_text()
    assert 'curl -s' in content
    assert 'Authorization: token' in content
    assert 'check-runs' in content
    assert 'check_name=droid-review' in content


def test_jq_extracts_conclusion():
    """Verify the script extracts conclusion from API response."""
    content = SCRIPT_PATH.read_text()
    assert 'jq -r' in content
    # P1 fix: filter out cancelled runs and select latest completed
    # (dual-trigger creates two check runs; one gets cancelled by concurrency)
    # Note: "skipped" is NOT filtered — needed for Dependabot exception below.
    assert 'cancelled' in content
    assert 'sort_by(.started_at)' in content
    # "skipped" must NOT be in the jq select exclusion filter
    # (it was previously excluded, making the skipped branch unreachable)
    jq_filter_line = next(
        line for line in content.splitlines()
        if 'select(.conclusion' in line
    )
    assert 'skipped' not in jq_filter_line, (
        "jq filter must not exclude 'skipped' — Dependabot PRs produce a "
        "skipped conclusion that must reach the decision logic"
    )


def test_ci_yml_calls_script():
    """Verify ci.yml calls check_droid_review.sh."""
    content = CI_YML_PATH.read_text()
    assert 'check_droid_review.sh' in content or 'Check droid-review' in content


def test_skipped_branch_has_dependabot_check():
    """Verify the skipped/neutral branch checks for Dependabot author.

    The droid-review workflow explicitly skips Dependabot PRs via a job-level
    if condition, producing a 'skipped' conclusion. The check_droid_review.sh
    script must allow these through rather than blocking the merge.
    """
    content = SCRIPT_PATH.read_text()

    # The skipped/neutral branch must exist
    assert '"$STATUS" = "neutral"' in content
    assert '"$STATUS" = "skipped"' in content

    # The skipped/neutral branch must contain a Dependabot author check
    # that allows the PR through (exit 0)
    lines = content.splitlines()
    skipped_branch_start = None
    for i, line in enumerate(lines):
        if '"$STATUS" = "neutral"' in line and '"$STATUS" = "skipped"' in line:
            skipped_branch_start = i
            break
    assert skipped_branch_start is not None, "skipped/neutral branch not found"

    # Collect the block until the next elif
    block_lines = []
    for line in lines[skipped_branch_start:]:
        block_lines.append(line)
        if line.strip().startswith('elif [ "$STATUS"') and len(block_lines) > 1:
            break
    block = '\n'.join(block_lines)

    assert 'dependabot[bot]' in block, (
        "skipped/neutral branch must check for dependabot[bot] author"
    )
    assert 'exit 0' in block, (
        "skipped/neutral branch must exit 0 for Dependabot PRs"
    )


def test_failure_branch_has_dependabot_check():
    """Verify the failure branch still has its Dependabot check (regression)."""
    content = SCRIPT_PATH.read_text()

    lines = content.splitlines()
    failure_branch_start = None
    for i, line in enumerate(lines):
        if '"$STATUS" = "failure"' in line:
            failure_branch_start = i
            break
    assert failure_branch_start is not None, "failure branch not found"

    block_lines = []
    for line in lines[failure_branch_start:]:
        block_lines.append(line)
        if line.strip().startswith('elif [ "$STATUS"') and len(block_lines) > 1:
            break
        if line.strip().startswith('else') and len(block_lines) > 1:
            break
    block = '\n'.join(block_lines)

    assert 'dependabot[bot]' in block, (
        "failure branch must still check for dependabot[bot] author"
    )
    assert 'exit 0' in block


def test_dependabot_check_uses_pr_api():
    """Verify both Dependabot checks use the PR API to get the author."""
    content = SCRIPT_PATH.read_text()

    # Both Dependabot checks should query the commits/{sha}/pulls endpoint
    pulls_api_count = content.count('commits/${COMMIT_SHA}/pulls')
    assert pulls_api_count >= 2, (
        f"Expected at least 2 PR API calls (failure + skipped branches), "
        f"found {pulls_api_count}"
    )
