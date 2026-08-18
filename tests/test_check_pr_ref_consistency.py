"""Tests for scripts/check_pr_ref_consistency.py (VAL-GATE-201/202/204).

TDD: all three test classes written BEFORE the script implementation.
Each test case maps to a validation contract assertion.

⚠️ FIXTURE DISCLOSURE (scrutiny 2026-08-18):
All fixture data below is **synthetic** — constructed to replicate the
structure of historical PR/issue data, NOT literal API response dumps.
Reason: PR #729's actual `closingIssuesReferences` is structurally `[]`
on the API level (GitHub's closing reference detection depends on branch
head commit message at merge time, not PR body text). The PR-side
interception logic can therefore only be replayed via fixture-form
mocking. This is **disclosure, not fabrication** — the fixtures exercise
the same regex/subset logic that would run against real API data; they
just cannot be populated from a live `gh pr view` snapshot of #729.
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


# ===========================================================================
# NEW: Closes/Resolves variant support (scrutiny 2026-08-18)
# GitHub supports "Fixes", "Closes", "Resolves" as equivalent keywords
# ===========================================================================

class TestClosesResolvesVariants:
    """PR body may use Closes/Resolves instead of Fixes (all are valid GitHub keywords)."""

    def test_closes_keyword_passes(self):
        """PR using 'Closes INFRA-xxx' should be accepted (greenAtBirth after fix)."""
        body = "## 修复\n\nCloses INFRA-337\nCloses INFRA-342"

        side_effect = _make_side_effect(
            800,
            body,
            [711, 718],
            {
                711: ISSUE_711_COMMENTS,  # INFRA-337
                718: ISSUE_718_COMMENTS,  # INFRA-342
            },
        )

        exit_code, _ = _run_check(800, side_effect)
        assert exit_code == 0, "Closes keyword should be accepted"

    def test_resolves_keyword_passes(self):
        """PR using 'Resolves INFRA-xxx' should be accepted (greenAtBirth after fix)."""
        body = "## 修复\n\nResolves INFRA-337"

        side_effect = _make_side_effect(
            801,
            body,
            [711],
            {
                711: ISSUE_711_COMMENTS,  # INFRA-337
            },
        )

        exit_code, _ = _run_check(801, side_effect)
        assert exit_code == 0, "Resolves keyword should be accepted"

    def test_mixed_keywords_passes(self):
        """PR using mixed Fixes/Closes/Resolves should all be extracted (greenAtBirth)."""
        body = "## 修复\n\nFixes INFRA-337\nCloses INFRA-342\nResolves INFRA-345"

        side_effect = _make_side_effect(
            802,
            body,
            [711, 718, 722],
            {
                711: ISSUE_711_COMMENTS,  # INFRA-337
                718: ISSUE_718_COMMENTS,  # INFRA-342
                722: ISSUE_722_COMMENTS,  # INFRA-345
            },
        )

        exit_code, _ = _run_check(802, side_effect)
        assert exit_code == 0, "Mixed Fixes/Closes/Resolves should all be extracted"


# ===========================================================================
# NEW: None body defense (scrutiny 2026-08-18)
# PR body can be None (not just empty string) — must not crash with TypeError
# ===========================================================================

class TestNoneBodyDefense:
    """PR body may be None (not empty string) — must handle gracefully."""

    def test_none_body_no_typeerror(self):
        """PR with body=None should not crash (greenAtBirth after fix)."""
        def side_effect(args, **kwargs):
            cmd = " ".join(args)
            if "pr view" in cmd:
                result = MagicMock()
                result.returncode = 0
                # GitHub API can return null for body
                data = {
                    "body": None,  # ← This is the key: body is None, not ""
                    "closingIssuesReferences": [],
                }
                result.stdout = json.dumps(data)
                result.stderr = ""
                return result
            return _mock_ok()

        exit_code, _ = _run_check(900, side_effect)
        # Should not crash with TypeError, should exit 0 (no closing refs)
        assert exit_code == 0, "None body should not crash"

    def test_none_body_with_closing_refs_still_works(self):
        """PR with body=None but closing refs should still extract (empty set, not crash)."""
        def side_effect(args, **kwargs):
            cmd = " ".join(args)
            if "pr view" in cmd:
                result = MagicMock()
                result.returncode = 0
                data = {
                    "body": None,
                    "closingIssuesReferences": [{"number": 711}],
                }
                result.stdout = json.dumps(data)
                result.stderr = ""
                return result
            if "issue view 711" in cmd:
                return _mock_gh_issue_comments(ISSUE_711_COMMENTS)
            return _mock_ok()

        exit_code, _ = _run_check(901, side_effect)
        # Should not crash; will fail because linkback {337} ⊄ empty Fixes set
        assert exit_code != 0, "None body with refs should fail (not crash)"


# ===========================================================================
# NEW: Comma-separated multi-number list support
# Some PRs write "Fixes #1, #2, #3" or "Closes INFRA-100, INFRA-200"
# ===========================================================================

class TestCommaSeparatedList:
    """PR body may use comma-separated lists for multiple references."""

    def test_comma_separated_fixes(self):
        """'Fixes INFRA-337, INFRA-342' should extract both (greenAtBirth)."""
        body = "## 修复\n\nFixes INFRA-337, INFRA-342"

        side_effect = _make_side_effect(
            910,
            body,
            [711, 718],
            {
                711: ISSUE_711_COMMENTS,  # INFRA-337
                718: ISSUE_718_COMMENTS,  # INFRA-342
            },
        )

        exit_code, _ = _run_check(910, side_effect)
        assert exit_code == 0, "Comma-separated Fixes should work"

    def test_comma_separated_closes(self):
        """'Closes INFRA-337, INFRA-342, INFRA-345' should extract all three (greenAtBirth)."""
        body = "## 修复\n\nCloses INFRA-337, INFRA-342, INFRA-345"

        side_effect = _make_side_effect(
            911,
            body,
            [711, 718, 722],
            {
                711: ISSUE_711_COMMENTS,
                718: ISSUE_718_COMMENTS,
                722: ISSUE_722_COMMENTS,
            },
        )

        exit_code, _ = _run_check(911, side_effect)
        assert exit_code == 0, "Comma-separated Closes should work"
