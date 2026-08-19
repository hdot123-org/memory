"""Tests for scripts/branch_cleanup_issue.sh (INFRA-385 tracking-issue dedup).

Contract under test:
- at most ONE open branch-cleanup tracking issue exists at any time
- same protected set  -> reuse silently (no new issue, no comment)
- protected set grown -> update body + comment
- protected set shrunk-> update body + comment; auto-close when empty
- nothing actionable  -> close the tracking issue as resolved
- pre-INFRA-385 duplicate open issues are closed pointing to the active one
- VAL-NTF-001: issue creation requires deleted_count > 0; protected-only runs
  must NOT create a new issue (may comment on existing tracker if one exists)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.shellcheck_helpers import assert_shellcheck_clean


def get_script_path() -> Path:
    """Get path to branch_cleanup_issue.sh script."""
    return Path(__file__).parent.parent / "scripts" / "branch_cleanup_issue.sh"


class GhCall:
    """A recorded gh CLI invocation."""

    def __init__(self, args: list[str], stdin: str | None = None) -> None:
        self.args = args
        self.stdin = stdin


class GhMockHarness:
    """Mocks the gh CLI for branch_cleanup_issue.sh tests.

    Simulates the repository state (open issues, issue bodies) and records
    all gh invocations for assertions.
    """

    def __init__(self, tmp_path: Path, issues: dict[int, str] | None = None) -> None:
        """Args:
        issues: mapping of issue number -> body for OPEN issues.
        """
        self.tmp_path = tmp_path
        self.issues: dict[int, str] = dict(issues or {})
        self.calls: list[GhCall] = []
        self.next_number = max(self.issues, default=100) + 1

        mock_dir = tmp_path / "mock_bin"
        mock_dir.mkdir(exist_ok=True)
        # State shared with the mock script via files (simplest robust IPC)
        self.state_file = tmp_path / "gh_state.json"
        self.calls_file = tmp_path / "gh_calls.jsonl"
        self._write_state()
        self.calls_file.write_text("")

        mock_gh = mock_dir / "gh"
        mock_gh.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            f"state_file = {str(self.state_file)!r}\n"
            f"calls_file = {str(self.calls_file)!r}\n"
            "with open(calls_file, 'a') as f:\n"
            "    f.write(json.dumps({'args': args}) + '\\n')\n"
            "state = json.load(open(state_file))\n"
            "if args[:2] == ['search', 'issues']:\n"
            "    query = ' '.join(a for a in args if not a.startswith('-'))\n"
            "    if 'branch-cleanup-tracker' in query:\n"
            "        marker_hits = [{'repository': 'example-org/memory', 'url': f'https://github.com/example-org/memory/issues/{n}'} for n, b in state['issues'].items() if 'branch-cleanup-tracker' in b]\n"
            "        print(json.dumps(marker_hits))\n"
            "    else:\n"
            "        print(json.dumps([{'url': f'https://github.com/hdot123-org/memory/issues/{n}'} for n in sorted(state['issues'], reverse=True)]))\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['issue', 'view']:\n"
            "    n = args[2]\n"
            "    if n not in [str(k) for k in state['issues']]:\n"
            "        sys.stderr.write('not found\\n'); sys.exit(1)\n"
            "    payload = {'body': state['issues'][str(n)]}\n"
            "    if '--jq' in args:\n"
            "        jq_expr = args[args.index('--jq') + 1]\n"
            "        if jq_expr == '.body':\n"
            "            print(payload['body']); sys.exit(0)\n"
            "        sys.stderr.write(f'unmocked jq: {jq_expr}\\n'); sys.exit(1)\n"
            "    print(json.dumps(payload)); sys.exit(0)\n"
            "if args[:2] == ['issue', 'close']:\n"
            "    n = args[2]\n"
            "    state['issues'].pop(str(n), None)\n"
            "    json.dump(state, open(state_file, 'w'))\n"
            "    print(f'Closed issue #{n}')\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['issue', 'create']:\n"
            "    n = state['next']\n"
            "    state['next'] += 1\n"
            "    body_idx = args.index('--body') + 1\n"
            "    state['issues'][str(n)] = args[body_idx]\n"
            "    json.dump(state, open(state_file, 'w'))\n"
            "    print(f'https://github.com/hdot123-org/memory/issues/{n}')\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['issue', 'edit']:\n"
            "    n = args[2]\n"
            "    body_idx = args.index('--body') + 1\n"
            "    state['issues'][str(n)] = args[body_idx]\n"
            "    json.dump(state, open(state_file, 'w'))\n"
            "    print(f'Updated issue #{n}')\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['issue', 'comment']:\n"
            "    n = args[2]\n"
            "    body_idx = args.index('--body') + 1\n"
            "    print(f'Commented on issue #{n}')\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['label', 'create']:\n"
            "    sys.exit(0)\n"
            "sys.stderr.write(f'unmocked: {args}\\n'); sys.exit(1)\n"
        )
        mock_gh.chmod(0o755)
        self.mock_bin = mock_dir

    def _write_state(self) -> None:
        self.state_file.write_text(json.dumps({"issues": self.issues, "next": self.next_number}))

    def read_calls(self) -> list[GhCall]:
        calls = []
        for line in self.calls_file.read_text().splitlines():
            if line.strip():
                data = json.loads(line)
                calls.append(GhCall(data["args"]))
        return calls

    def run_script(
        self,
        deleted: list[str] | None = None,
        protected: list[str] | None = None,
        run_url: str = "https://github.com/hdot123-org/memory/actions/runs/1",
        run_date: str = "2026-08-18 00:00 UTC",
    ) -> tuple[int, str, str]:
        deleted_file = self.tmp_path / "deleted_branches.txt"
        protected_file = self.tmp_path / "protected_branches.txt"
        deleted_file.write_text("".join(f"{b}\n" for b in (deleted or [])))
        protected_file.write_text("".join(f"{b}\n" for b in (protected or [])))

        import os

        env = os.environ.copy()
        env["PATH"] = f"{self.mock_bin}:{env['PATH']}"
        env["GH_REPO_KEY"] = "example-org/memory"

        result = subprocess.run(
            [
                "bash",
                str(get_script_path()),
                "--deleted", str(deleted_file),
                "--protected", str(protected_file),
                "--run-url", run_url,
                "--run-date", run_date,
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode, result.stdout, result.stderr

    def open_issue_numbers(self) -> list[str]:
        state = json.loads(self.state_file.read_text())
        return sorted(state["issues"].keys())


def tracker_body(branches: list[str]) -> str:
    """Build a tracker-format issue body listing protected branches.

    `branches` items are full entry strings as emitted by branch_cleanup.sh's
    PROTECTED_BRANCHES array, e.g. "feat/x (2 unique commits)".
    """
    lines = [
        "## Automated Branch Cleanup (tracking)",
        "",
        "**Protected branches:** " + str(len(branches)),
        "### 🛡️ Protected branches (unmerged unique commits)",
        "",
    ]
    for b in branches:
        lines.append(f"- `{b}`")
    lines.append("---")
    lines.append("<!-- branch-cleanup-tracker -->")
    return "\n".join(lines)


def legacy_body(branches: list[str]) -> str:
    """Pre-INFRA-385 issue body (no tracker marker)."""
    lines = [
        "## Automated Branch Cleanup",
        "",
        "### 🛡️ Protected branches (unmerged unique commits)",
        "",
    ]
    for b in branches:
        lines.append(f"- `{b} ({len(b)} unique commits)`")
    return "\n".join(lines)


def calls_matching(calls: list[GhCall], prefix: list[str]) -> list[GhCall]:
    return [c for c in calls if c.args[: len(prefix)] == prefix]


# ============================================================================
# VAL-BCI-001: unchanged protected set -> silent reuse, no new issue/comment
# ============================================================================
def test_duplicate_run_same_protected_set_silent(tmp_path: Path):
    """INFRA-385 core scenario: same protected branches on the next run must
    NOT create a new issue and NOT post a duplicate comment."""
    harness = GhMockHarness(
        tmp_path,
        issues={781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"])},
    )

    exit_code, stdout, _ = harness.run_script(
        protected=["fix/pr-ref-consistency-gate (4 unique commits)"]
    )

    assert exit_code == 0, stdout
    assert "issue_action=reused-silent" in stdout
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == [], "must NOT create a new issue"
    assert calls_matching(calls, ["issue", "comment"]) == [], "must NOT comment on duplicate run"
    assert calls_matching(calls, ["issue", "edit"]) == [], "must NOT edit body on duplicate run"
    assert harness.open_issue_numbers() == ["781"], "original issue stays open"


# ============================================================================
# VAL-BCI-002: new protected branch -> single tracking issue updated in place
# ============================================================================
def test_new_protected_branch_updates_tracker(tmp_path: Path):
    """A newly protected branch updates the existing tracking issue body and
    posts a comment; no second issue is created."""
    harness = GhMockHarness(
        tmp_path,
        issues={781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"])},
    )

    exit_code, stdout, _ = harness.run_script(
        protected=[
            "fix/pr-ref-consistency-gate (4 unique commits)",
            "feat/other-branch (2 unique commits)",
        ]
    )

    assert exit_code == 0, stdout
    assert "issue_action=updated" in stdout
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == [], "must NOT create a new issue"
    edits = calls_matching(calls, ["issue", "edit"])
    assert len(edits) == 1, "tracker body must be updated exactly once"
    assert edits[0].args[2] == "781"
    comments = calls_matching(calls, ["issue", "comment"])
    assert len(comments) == 1, "state change must be commented exactly once"
    assert harness.open_issue_numbers() == ["781"]


# ============================================================================
# VAL-BCI-003: protected set emptied -> tracking issue auto-closed
# ============================================================================
def test_all_resolved_closes_tracker(tmp_path: Path):
    """When the run reports nothing actionable, the tracking issue is closed
    as resolved with an explanatory comment."""
    harness = GhMockHarness(
        tmp_path,
        issues={781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"])},
    )

    exit_code, stdout, _ = harness.run_script()

    assert exit_code == 0, stdout
    assert "issue_action=closed" in stdout
    calls = harness.read_calls()
    closes = calls_matching(calls, ["issue", "close"])
    assert len(closes) == 1 and closes[0].args[2] == "781"
    assert harness.open_issue_numbers() == [], "tracker must be closed"


# ============================================================================
# VAL-BCI-004: no tracker + nothing actionable -> no issue created
# ============================================================================
def test_no_actionable_no_tracker_creates_nothing(tmp_path: Path):
    """A clean run with no existing tracking issue must not create one."""
    harness = GhMockHarness(tmp_path)

    exit_code, stdout, _ = harness.run_script()

    assert exit_code == 0, stdout
    assert "issue_action=none" in stdout
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == []
    assert calls_matching(calls, ["issue", "close"]) == []
    assert harness.open_issue_numbers() == []


# ============================================================================
# VAL-BCI-005: no tracker + deletion -> creates the single tracker
# ============================================================================
def test_first_deletion_creates_single_tracker(tmp_path: Path):
    """First-ever deletion event creates exactly one tracking issue with
    the marker and labels."""
    harness = GhMockHarness(tmp_path)

    exit_code, stdout, _ = harness.run_script(
        deleted=["fix/pr-ref-consistency-gate"]
    )

    assert exit_code == 0, stdout
    assert "issue_action=created" in stdout
    calls = harness.read_calls()
    creates = calls_matching(calls, ["issue", "create"])
    assert len(creates) == 1, "exactly one tracking issue must be created"
    labels_idx = creates[0].args.index("--label") + 1
    assert creates[0].args[labels_idx] == "automation,branch-cleanup"
    assert harness.open_issue_numbers() == ["101"]


# ============================================================================
# VAL-BCI-006: shrunk protected set -> update + comment, stays open
# ============================================================================
def test_shrunk_protected_set_updates_and_keeps_open(tmp_path: Path):
    """One of two tracked branches disappears: body updated, comment posted,
    issue stays open because one branch is still protected."""
    harness = GhMockHarness(
        tmp_path,
        issues={
            781: tracker_body([
                "fix/pr-ref-consistency-gate (4 unique commits)",
                "feat/other (2 unique commits)",
            ])
        },
    )

    exit_code, stdout, _ = harness.run_script(
        protected=["fix/pr-ref-consistency-gate (4 unique commits)"]
    )

    assert exit_code == 0, stdout
    assert "issue_action=updated" in stdout
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == []
    assert len(calls_matching(calls, ["issue", "comment"])) == 1
    assert harness.open_issue_numbers() == ["781"], "still-protection -> stays open"


# ============================================================================
# VAL-BCI-007: legacy duplicate issues are closed pointing to the tracker
# ============================================================================
def test_legacy_duplicates_closed_pointing_to_tracker(tmp_path: Path):
    """INFRA-385 leftovers: an open legacy issue (same protected set, no
    marker) is closed with a pointer comment to the active tracker."""
    harness = GhMockHarness(
        tmp_path,
        issues={
            781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"]),
            774: legacy_body(["fix/pr-ref-consistency-gate (4 unique commits)"]),
        },
    )

    exit_code, stdout, _ = harness.run_script(
        protected=["fix/pr-ref-consistency-gate (4 unique commits)"]
    )

    assert exit_code == 0, stdout
    calls = harness.read_calls()
    closes = calls_matching(calls, ["issue", "close"])
    assert len(closes) == 1 and closes[0].args[2] == "774", "legacy duplicate must be closed"
    assert harness.open_issue_numbers() == ["781"], "active tracker stays open"


# ============================================================================
# VAL-BCI-008: deletions-only run updates tracker and comments
# ============================================================================
def test_deletions_only_run_reports_on_tracker(tmp_path: Path):
    """Branches were deleted and nothing protected: the tracker body is
    updated and a comment reports the deletions (issue stays open only if
    it existed; here none exists, so one is created)."""
    harness = GhMockHarness(tmp_path)

    exit_code, stdout, _ = harness.run_script(deleted=["feat/gone-branch"])

    assert exit_code == 0, stdout
    assert "issue_action=created" in stdout
    calls = harness.read_calls()
    creates = calls_matching(calls, ["issue", "create"])
    assert len(creates) == 1
    body_idx = creates[0].args.index("--body") + 1
    assert "feat/gone-branch" in creates[0].args[body_idx]


# ============================================================================
# VAL-BCI-009: deletions with unchanged protected set still comments
# ============================================================================
def test_deletions_with_same_protected_set_comments(tmp_path: Path):
    """Unchanged protected set PLUS deletions is a reportable state change:
    body updated and comment posted (not silent)."""
    harness = GhMockHarness(
        tmp_path,
        issues={781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"])},
    )

    exit_code, stdout, _ = harness.run_script(
        deleted=["feat/gone-branch"],
        protected=["fix/pr-ref-consistency-gate (4 unique commits)"],
    )

    assert exit_code == 0, stdout
    assert "issue_action=updated" in stdout
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == []
    assert len(calls_matching(calls, ["issue", "comment"])) == 1


# ============================================================================
# VAL-BCI-010: shellcheck clean
# ============================================================================
def test_shellcheck_clean():
    """shellcheck scripts/branch_cleanup_issue.sh exits 0."""
    assert_shellcheck_clean(get_script_path())


# ============================================================================
# VAL-NTF-001a: protected-only run with no existing tracker creates NO issue
# ============================================================================
def test_protected_only_no_tracker_creates_nothing(tmp_path: Path):
    """When deleted_count == 0 and no tracker exists, protected-only run must
    NOT create a new tracking issue. It may log the event but must not touch
    GitHub issues."""
    harness = GhMockHarness(tmp_path)

    exit_code, stdout, _ = harness.run_script(
        protected=["fix/pr-ref-consistency-gate (4 unique commits)"]
    )

    assert exit_code == 0, stdout
    assert "issue_action=none" in stdout or "protected_only" in stdout.lower()
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == [], \
        "protected-only run must NOT create an issue"
    assert harness.open_issue_numbers() == [], "no issue should be created"


# ============================================================================
# VAL-NTF-001b: protected-only run with existing tracker updates but doesn't create
# ============================================================================
def test_protected_only_with_tracker_updates_no_create(tmp_path: Path):
    """When deleted_count == 0 and a tracker exists, protected-only run may
    update the tracker (if protected set changed) but must NOT create a new issue."""
    harness = GhMockHarness(
        tmp_path,
        issues={781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"])},
    )

    exit_code, stdout, _ = harness.run_script(
        protected=[
            "fix/pr-ref-consistency-gate (4 unique commits)",
            "feat/new-protected (2 unique commits)",  # new protected branch
        ]
    )

    assert exit_code == 0, stdout
    calls = harness.read_calls()
    assert calls_matching(calls, ["issue", "create"]) == [], \
        "protected-only run must NOT create an issue even if tracker updated"
    # May update or comment on existing tracker, but not create new one
    assert harness.open_issue_numbers() == ["781"], "existing tracker remains"


# ============================================================================
# VAL-NTF-001c: deleted_count > 0 creates tracker (existing behavior)
# ============================================================================
def test_deletions_create_tracker(tmp_path: Path):
    """When deleted_count > 0 and no tracker exists, a new tracker is created.
    This is the existing behavior from VAL-BCI-008, verified here for completeness."""
    harness = GhMockHarness(tmp_path)

    exit_code, stdout, _ = harness.run_script(
        deleted=["feat/gone-branch"]
    )

    assert exit_code == 0, stdout
    assert "issue_action=created" in stdout
    calls = harness.read_calls()
    creates = calls_matching(calls, ["issue", "create"])
    assert len(creates) == 1, "deletions must create a tracker"
    assert harness.open_issue_numbers() == ["101"]


# ============================================================================
# VAL-BCI-011: bash syntax check
# ============================================================================
def test_bash_syntax_valid():
    """bash -n parses the script without errors."""
    result = subprocess.run(
        ["bash", "-n", str(get_script_path())],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


# ============================================================================
# VAL-BCI-012: script is idempotent — running twice produces no duplicates
# ============================================================================
def test_double_run_idempotent(tmp_path: Path):
    """Running the script twice with the same state doesn't create duplicate issues."""
    # First run: create tracker with deletion
    harness = GhMockHarness(tmp_path)
    rc1, out1, _ = harness.run_script(deleted=["old-branch"])
    assert rc1 == 0 and "issue_action=created" in out1
    created = harness.open_issue_numbers()
    assert created == ["101"]

    # Second run with same deletion - should update (not create new issue)
    rc2, out2, _ = harness.run_script(deleted=["old-branch"])
    assert rc2 == 0 and "issue_action=updated" in out2

    # Check that only ONE issue was created total (from the first run)
    calls = harness.read_calls()
    create_calls = calls_matching(calls, ["issue", "create"])
    assert len(create_calls) == 1, f"Expected 1 create call, got {len(create_calls)}"
    assert harness.open_issue_numbers() == ["101"], "tracker must remain exactly one open issue"


# ============================================================================
# VAL-BCI-013: workflow calls the tracking-issue script (wiring contract)
# ============================================================================
def test_workflow_calls_tracking_issue_script():
    """branch-cleanup.yml invokes scripts/branch_cleanup_issue.sh with the
    documented arguments and always() condition."""
    workflow_path = (
        Path(__file__).parent.parent / ".github" / "workflows" / "branch-cleanup.yml"
    )
    content = workflow_path.read_text()

    assert "scripts/branch_cleanup_issue.sh" in content, (
        "Workflow must call the INFRA-385 tracking-issue script"
    )
    assert "if: always()" in content, (
        "Step must run always so resolved tracking issues get closed"
    )
    for arg in ("--deleted", "--protected", "--run-url", "--run-date"):
        assert arg in content, f"Workflow must pass {arg}"
    assert "GH_REPO_KEY" in content, "Workflow must pass the repository key for gh search"


# ============================================================================
# VAL-BCI-014: script has execute permission in git index
# ============================================================================
def test_script_has_execute_permission():
    """git ls-files --stage shows mode 100755 for the new script."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "scripts/branch_cleanup_issue.sh"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() == "":
        pytest.skip("script not yet tracked in git index")
    assert "100755" in result.stdout, "Script must be executable (100755)"


# ============================================================================
# VAL-BCI-015: tracking-issue close comment contains resolution context
# ============================================================================
def test_close_comment_contains_context(tmp_path: Path):
    """The auto-close comment references the run date/url so the close is
    auditable."""
    harness = GhMockHarness(
        tmp_path,
        issues={781: tracker_body(["fix/pr-ref-consistency-gate (4 unique commits)"])},
    )

    exit_code, stdout, _ = harness.run_script(
        run_url="https://github.com/hdot123-org/memory/actions/runs/999",
        run_date="2026-08-18 08:00 UTC",
    )

    assert exit_code == 0, stdout
    calls = harness.read_calls()
    closes = calls_matching(calls, ["issue", "close"])
    assert closes, "tracker must be closed"
    comment_idx = closes[0].args.index("--comment") + 1
    comment = closes[0].args[comment_idx]
    assert "999" in comment and "2026-08-18 08:00 UTC" in comment
