"""Tests for scripts/check_pr_ref_consistency.py (VAL-GATE-201/202/204).

TDD: all three test classes written BEFORE the script implementation.
Each test case maps to a validation contract assertion.

Fixtures use real historical data fetched via `gh` read-only queries,
stored as JSON fixtures in the test module.
"""
import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "check_pr_ref_consistency.py"


# ---------------------------------------------------------------------------
# Fixture data (real historical PRs/issues fetched via gh read-only)
# ---------------------------------------------------------------------------

# PR #729 body: "Fixes INFRA-335" (the root cause mismatch)
PR_729_BODY = """\
## 变更内容

引入参数化 mixin `_WarnsAndStderrMixin`...

Fixes INFRA-335"""

# PR #729 references issues #711, #718, #722 (via GitHub closing references)
PR_729_CLOSING_REFS = [711, 718, 722]

# Issue #711 linkback comment → INFRA-337
ISSUE_711_COMMENTS = """\
<!-- linear-linkback -->
<p><a href="https://linear.app/jtoom/issue/INFRA-337">INFRA-337</a></p>"""

# Issue #718 linkback comment → INFRA-342
ISSUE_718_COMMENTS = """\
<!-- linear-linkback -->
<p><a href="https://linear.app/jtoom/issue/INFRA-342">INFRA-342</a></p>"""

# Issue #722 linkback comment → INFRA-345
ISSUE_722_COMMENTS = """\
<!-- linear-linkback -->
<p><a href="https://linear.app/jtoom/issue/INFRA-345">INFRA-345</a></p>"""

# Linkback set from #729's issues: {INFRA-337, INFRA-342, INFRA-345}
# Fixes set from PR body: {INFRA-335}
# Mismatch: linkback ⊄ Fixes → should FAIL

# Compliant sample: PR whose Fixes covers all linkbacks
# Construct a synthetic but realistic compliant PR
PR_COMPLIANT_BODY = """\
## 修复

修复了三个 scanner finding 的重复代码问题。

Fixes INFRA-337
Fixes INFRA-342
Fixes INFRA-345"""

PR_COMPLIANT_CLOSING_REFS = [711, 718, 722]
# Same linkbacks {337, 342, 345}, but Fixes now covers all → should PASS

# No-linkback sample: PR references issues without any Linear linkback
PR_NO_LINKBACK_BODY = """\
## 修复

Fixes INFRA-400"""

PR_NO_LINKBACK_CLOSING_REFS = [800, 801]
ISSUE_800_COMMENTS = "Just a regular comment with no linkback"
ISSUE_801_COMMENTS = "Another comment without any INFRA reference"


def _mock_gh_pr_view(pr_number: int, body: str, closing_refs: list[int]) -> MagicMock:
    """Create a mock subprocess.CompletedProcess for gh pr view."""
    result = MagicMock()
    result.returncode = 0
    data = {
        "body": body,
        "closingIssuesReferences": [{"number": n} for n in closing_refs],
    }
    result.stdout = json.dumps(data)
    result.stderr = ""
    return result


def _mock_gh_issue_comments(comments_text: str) -> MagicMock:
    """Create a mock subprocess.CompletedProcess for gh issue view comments."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = comments_text
    result.stderr = ""
    return result


def _mock_ok(stdout: str = "") -> MagicMock:
    """Create a mock subprocess.CompletedProcess for any unmatched gh call."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


def _make_side_effect(
    pr_number: int,
    pr_body: str,
    closing_refs: list[int],
    issue_comments: Optional[dict] = None,
):
    """Build a subprocess.run side_effect mocking gh pr view + gh issue view.

    Args:
        pr_number: PR number the script is checking
        pr_body: PR body text to return for gh pr view
        closing_refs: closing issue numbers for gh pr view
        issue_comments: mapping of issue number → comments text;
            unmatched issue view calls return an empty success
    """
    issue_comments = issue_comments or {}

    def side_effect(args, **kwargs):
        cmd = " ".join(args)
        if "pr view" in cmd:
            return _mock_gh_pr_view(pr_number, pr_body, closing_refs)
        for issue_num, comments_text in issue_comments.items():
            if f"issue view {issue_num}" in cmd:
                return _mock_gh_issue_comments(comments_text)
        return _mock_ok()

    return side_effect


def _run_check(pr_number: int, side_effect_fn=None):
    """Run the check script with mocked gh calls.

    side_effect_fn: called with the args list of each subprocess.run call,
    returns the mock CompletedProcess to use.
    """
    with patch("subprocess.run", side_effect=side_effect_fn) as mock_run:
        # Import and run
        sys.path.insert(0, str(SCRIPT_PATH.parent))
        try:
            import importlib
            mod = importlib.import_module("check_pr_ref_consistency")
            importlib.reload(mod)
            exit_code = mod.main([str(pr_number)])
        finally:
            sys.path.pop(0)
    return exit_code, mock_run


# ===========================================================================
# VAL-GATE-201: #729 mismatch form must be caught
# ===========================================================================

class TestMismatchCaught:
    """#729 form: linkback {337,342,345} vs Fixes {335} → exit non-zero + diff output."""

    def _side_effect(self):
        return _make_side_effect(
            729,
            PR_729_BODY,
            PR_729_CLOSING_REFS,
            {
                711: ISSUE_711_COMMENTS,
                718: ISSUE_718_COMMENTS,
                722: ISSUE_722_COMMENTS,
            },
        )

    def test_exit_nonzero_on_mismatch(self):
        """When linkback set is NOT subset of Fixes set, exit code must be non-zero."""
        exit_code, mock_run = _run_check(729, self._side_effect())
        assert exit_code != 0, "Expected non-zero exit for #729 mismatch form"

    def test_outputs_comparison_diff(self, capsys):
        """Output must contain a readable diff: linkback set vs Fixes set."""
        exit_code, _ = _run_check(729, self._side_effect())
        captured = capsys.readouterr()
        output = captured.out + captured.err
        # Must contain the mismatch details
        assert "INFRA-337" in output or "INFRA-342" in output or "INFRA-345" in output
        assert "INFRA-335" in output  # The Fixes set must also be shown


# ===========================================================================
# VAL-GATE-202: Compliant PR must pass
# ===========================================================================

class TestCompliantPasses:
    """Compliant PR: linkback ⊆ Fixes → exit 0."""

    def test_exit_zero_when_linkback_subset_of_fixes(self):
        """When all linkback IDs are in Fixes set, exit 0."""
        side_effect = _make_side_effect(
            999,
            PR_COMPLIANT_BODY,
            PR_COMPLIANT_CLOSING_REFS,
            {
                711: ISSUE_711_COMMENTS,
                718: ISSUE_718_COMMENTS,
                722: ISSUE_722_COMMENTS,
            },
        )

        exit_code, _ = _run_check(999, side_effect)
        assert exit_code == 0, "Expected exit 0 for compliant PR"


# ===========================================================================
# VAL-GATE-204: No-linkback PR must pass (backward compat)
# ===========================================================================

class TestNoLinkbackPasses:
    """Issues without linkback → check passes (backward compat)."""

    def test_exit_zero_when_no_linkback(self):
        """When referenced issues have no Linear linkback, exit 0."""
        side_effect = _make_side_effect(
            888,
            PR_NO_LINKBACK_BODY,
            PR_NO_LINKBACK_CLOSING_REFS,
            {
                800: ISSUE_800_COMMENTS,
                801: ISSUE_801_COMMENTS,
            },
        )

        exit_code, _ = _run_check(888, side_effect)
        assert exit_code == 0, "Expected exit 0 when no linkback exists"


# ===========================================================================
# Read-only proof (VAL-GATE-203)
# ===========================================================================

class TestReadOnly:
    """The check must be strictly read-only — no write operations."""

    def test_no_write_operations(self):
        """Verify that all gh commands issued are read-only (view/list, not create/close/comment)."""
        side_effect = _make_side_effect(
            729,
            PR_729_BODY,
            PR_729_CLOSING_REFS,
            {711: ISSUE_711_COMMENTS},
        )

        _, mock_run = _run_check(729, side_effect)
        # Verify no write operations were called
        for call in mock_run.call_args_list:
            args = call[0][0] if call[0] else call[1].get("args", [])
            cmd_str = " ".join(args) if isinstance(args, list) else str(args)
            # Must not contain write operations
            assert "issue close" not in cmd_str, f"Write operation detected: {cmd_str}"
            assert "issue create" not in cmd_str, f"Write operation detected: {cmd_str}"
            assert "issue comment" not in cmd_str, f"Write operation detected: {cmd_str}"
            assert "issue edit" not in cmd_str, f"Write operation detected: {cmd_str}"
            assert "pr create" not in cmd_str, f"Write operation detected: {cmd_str}"
            assert "pr edit" not in cmd_str, f"Write operation detected: {cmd_str}"


# ===========================================================================
# Subset direction (architecture §3.5: direction fixed as ⊆)
# ===========================================================================

class TestSubsetDirection:
    """Direction is fixed as ⊆ (linkback ⊆ Fixes).

    PR with Fixes containing MORE than linkback should still pass.
    Only the reverse (linkback has items not in Fixes) should fail.
    """

    def test_fixes_superset_of_linkback_passes(self):
        """Fixes = {335, 337, 342, 345}, linkback = {337, 342, 345} → passes."""
        body = "Some fix\n\nFixes INFRA-335\nFixes INFRA-337\nFixes INFRA-342\nFixes INFRA-345"

        side_effect = _make_side_effect(
            555,
            body,
            [711, 718, 722],
            {
                711: ISSUE_711_COMMENTS,
                718: ISSUE_718_COMMENTS,
                722: ISSUE_722_COMMENTS,
            },
        )

        exit_code, _ = _run_check(555, side_effect)
        assert exit_code == 0, "Fixes superset of linkback should pass"

    def test_no_closing_refs_passes(self):
        """PR with no referenced issues → exit 0 (nothing to check)."""
        side_effect = _make_side_effect(111, "Just a fix\n\nFixes INFRA-100", [])

        exit_code, _ = _run_check(111, side_effect)
        assert exit_code == 0, "No closing refs should pass"
