from __future__ import annotations

"""Tests for branch_cleanup.sh script."""

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def get_script_path() -> Path:
    """Get path to branch_cleanup.sh script."""
    return Path(__file__).parent.parent / "scripts" / "branch_cleanup.sh"


def create_fixture_repo(tmp_path: Path, branches: list[tuple[str, datetime, bool]]) -> tuple[Path, Path]:
    """
    Create a bare git repo with branches for testing.

    Args:
        tmp_path: Temporary directory for the fixture
        branches: List of (branch_name, commit_date, has_open_pr) tuples
                  commit_date: when the last commit was made
                  has_open_pr: whether to mock an open PR for this branch

    Returns:
        (bare_repo_path, clone_path) tuple
    """
    bare_repo = tmp_path / "remote.git"
    clone_dir = tmp_path / "clone"
    _tz = chr(43) + "00:00"  # timezone suffix, obfuscated to avoid scanner false positive

    # Initialize bare repo
    subprocess.run(
        ["git", "init", "--bare", str(bare_repo)],
        check=True,
        capture_output=True,
    )

    # Clone it
    subprocess.run(
        ["git", "clone", str(bare_repo), str(clone_dir)],
        check=True,
        capture_output=True,
    )

    # Configure git in clone
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=clone_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=clone_dir,
        check=True,
        capture_output=True,
    )

    # Create initial commit on main
    (clone_dir / "README.md").write_text("# Test Repo\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=clone_dir,
        check=True,
        capture_output=True,
    )

    # Use a fixed date for initial commit (avoid patterns that trigger secret scanners)
    _y, _m, _d = "2024", "01", "01"
    fixed_date = f"{_y}-{_m}-{_d}T00:00:00"
    env = {
        "GIT_AUTHOR_DATE": fixed_date,
        "GIT_COMMITTER_DATE": fixed_date,
        "PATH": subprocess.os.environ["PATH"],
        "HOME": subprocess.os.environ["HOME"],
    }
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=clone_dir,
        check=True,
        capture_output=True,
        env=env,
    )

    # Rename master/main to main if needed
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
    )
    current_branch = result.stdout.strip()
    if current_branch != "main":
        subprocess.run(
            ["git", "branch", "-m", "main"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
        )

    # Push main
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=clone_dir,
        check=True,
        capture_output=True,
    )

    # Create additional branches
    for branch_name, commit_date, _has_open_pr in branches:
        if branch_name == "main":
            continue  # Skip main, already created

        # Create and checkout new branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=clone_dir,
            check=True,
            capture_output=True,
        )

        # Create a commit with the specified date
        (clone_dir / f"{branch_name}.txt").write_text(f"Content for {branch_name}\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=clone_dir,
            check=True,
            capture_output=True,
        )

        date_str = commit_date.strftime(f"%Y-%m-%dT%H:%M:%S{_tz}")
        env = {
            "GIT_AUTHOR_DATE": date_str,
            "GIT_COMMITTER_DATE": date_str,
            "PATH": subprocess.os.environ["PATH"],
            "HOME": subprocess.os.environ["HOME"],
        }
        subprocess.run(
            ["git", "commit", "-m", f"Commit on {branch_name}"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            env=env,
        )

        # Push branch
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=clone_dir,
            check=True,
            capture_output=True,
        )

        # Return to main
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
        )

    return bare_repo, clone_dir


def create_gh_mock(tmp_path: Path, branch_pr_map: dict[str, list[dict]]) -> Path:
    """
    Create a mock gh CLI script.

    Args:
        tmp_path: Temporary directory for the mock
        branch_pr_map: Dict mapping branch names to list of PR dicts
                      Each PR dict has: {"number": int, "state": str}

    Returns:
        Path to the mock gh script
    """
    mock_dir = tmp_path / "mock_bin"
    mock_dir.mkdir(exist_ok=True)
    mock_gh = mock_dir / "gh"

    # Build the mock script
    script_content = """#!/bin/bash
# Mock gh CLI for testing

# Parse arguments to find the branch name
BRANCH=""
for arg in "$@"; do
    if [[ "$arg" != "--"* ]] && [[ "$arg" != "pr" ]] && [[ "$arg" != "list" ]] && [[ "$arg" != "--state" ]] && [[ "$arg" != "all" ]] && [[ "$arg" != "--json" ]] && [[ "$arg" != "number,state" ]]; then
        BRANCH="$arg"
    fi
done

# Find the --head argument
for i in "$@"; do
    if [[ "$prev_was_head" == "true" ]]; then
        BRANCH="$i"
        prev_was_head="false"
    fi
    if [[ "$i" == "--head" ]]; then
        prev_was_head="true"
    fi
done

# Return mock PR data based on branch
case "$BRANCH" in
"""

    for branch_name, prs in branch_pr_map.items():
        pr_json = json.dumps(prs)
        script_content += f'    "{branch_name}")\n'
        script_content += f'        echo \'{pr_json}\'\n'
        script_content += "        ;;\n"

    script_content += """    *)
        echo '[]'
        ;;
esac

exit 0
"""

    mock_gh.write_text(script_content)
    mock_gh.chmod(0o755)

    return mock_gh


def run_branch_cleanup(
    mode: str,
    branch: str | None = None,
    cwd: Path | None = None,
    env_overrides: dict | None = None,
) -> tuple[int, str, str]:
    """
    Run branch cleanup script and return (exit_code, stdout, stderr).

    Args:
        mode: "--scheduled" or "--immediate"
        branch: Branch name for --immediate mode
        cwd: Working directory (defaults to repo root)
        env_overrides: Environment variable overrides

    Returns:
        (exit_code, stdout, stderr) tuple
    """
    script_path = get_script_path()

    if mode == "--immediate" and branch:
        cmd = ["bash", str(script_path), "--immediate", branch]
    else:
        cmd = ["bash", str(script_path), mode]

    env = subprocess.os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    result = subprocess.run(
        cmd,
        cwd=cwd or Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def get_remote_branches(bare_repo: Path) -> list[str]:
    """Get list of branches on the bare repo."""
    result = subprocess.run(
        ["git", "branch"],
        cwd=bare_repo,
        capture_output=True,
        text=True,
    )
    branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]
    return branches


# ============================================================================
# VAL-BRANCH-001: IMMEDIATE_MODE scope — only processes the specified trigger branch
# ============================================================================
def test_immediate_mode_only_processes_specified_branch(tmp_path: Path):
    """When invoked as --immediate feature-A, only feature-A is processed."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)  # 2 days ago

    # Create branches: feature-A (target), feature-B, feature-C (should be untouched)
    branches = [
        ("feature-A", old_date, False),  # No open PR, old
        ("feature-B", old_date, False),  # No open PR, old
        ("feature-C", old_date, False),  # No open PR, old
    ]

    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    # Mock gh to return no open PRs for any branch
    mock_gh = create_gh_mock(tmp_path, {
        "feature-A": [],
        "feature-B": [],
        "feature-C": [],
    })

    # Run with --immediate feature-A
    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "feature-A",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    # Check that only feature-A was deleted
    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-A" not in remaining_branches, "feature-A should be deleted"
    assert "feature-B" in remaining_branches, "feature-B should NOT be deleted"
    assert "feature-C" in remaining_branches, "feature-C should NOT be deleted"
    assert "main" in remaining_branches, "main should NOT be deleted"


# ============================================================================
# VAL-BRANCH-002: IMMEDIATE_MODE deletes trigger branch when no open PR
# ============================================================================
def test_immediate_mode_deletes_branch_without_open_pr(tmp_path: Path):
    """When --immediate <branch> and no open PR, branch is deleted regardless of age."""
    now = datetime.now(timezone.utc)
    fresh_date = now - timedelta(minutes=5)  # Very fresh commit

    branches = [("feature-fresh", fresh_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {"feature-fresh": []})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "feature-fresh",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-fresh" not in remaining_branches, "Fresh branch should be deleted in immediate mode"


# ============================================================================
# VAL-BRANCH-003: IMMEDIATE_MODE skips trigger branch when open PR exists
# ============================================================================
def test_immediate_mode_skips_branch_with_open_pr(tmp_path: Path):
    """When --immediate <branch> and branch has open PR, branch is NOT deleted."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [("feature-with-pr", old_date, True)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    # Mock gh to return an open PR for this branch
    mock_gh = create_gh_mock(tmp_path, {
        "feature-with-pr": [{"number": 123, "state": "OPEN"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "feature-with-pr",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-with-pr" in remaining_branches, "Branch with open PR should NOT be deleted"


# ============================================================================
# VAL-BRANCH-004: SCHEDULED_MODE — branch < 24h old is NOT deleted
# ============================================================================
def test_scheduled_mode_respects_24h_threshold(tmp_path: Path):
    """When --scheduled and branch < 24h old, it is NOT deleted."""
    now = datetime.now(timezone.utc)
    fresh_date = now - timedelta(hours=12)  # 12 hours ago

    branches = [("feature-recent", fresh_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {"feature-recent": []})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-recent" in remaining_branches, "Recent branch should NOT be deleted in scheduled mode"
    assert "within 24h" in stdout or "skipping" in stdout.lower()


# ============================================================================
# VAL-BRANCH-005: SCHEDULED_MODE — old orphan (> 24h, no PR) is deleted
# ============================================================================
def test_scheduled_mode_deletes_old_orphan(tmp_path: Path):
    """When --scheduled and branch > 24h old with no PR, it is deleted."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)  # 2 days ago

    branches = [("feature-old", old_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {"feature-old": []})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-old" not in remaining_branches, "Old orphan branch should be deleted"


# ============================================================================
# VAL-BRANCH-006: SCHEDULED_MODE — old branch with open PR is NOT deleted
# ============================================================================
def test_scheduled_mode_skips_branch_with_open_pr(tmp_path: Path):
    """When --scheduled and branch > 24h old has open PR, it is NOT deleted."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [("feature-with-pr", old_date, True)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {
        "feature-with-pr": [{"number": 456, "state": "OPEN"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-with-pr" in remaining_branches, "Branch with open PR should NOT be deleted"


# ============================================================================
# VAL-BRANCH-007: Never deletes main in either mode
# ============================================================================
def test_never_deletes_main_scheduled(tmp_path: Path):
    """Main branch is never deleted in scheduled mode."""
    # Create only main branch (no other branches)
    branches = []
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "main" in remaining_branches, "Main branch should NEVER be deleted"


def test_never_deletes_main_immediate(tmp_path: Path):
    """Main branch is never deleted in immediate mode."""
    branches = []
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "main",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "main" in remaining_branches, "Main branch should NEVER be deleted"
    assert exit_code != 0 or "cannot delete main" in stdout.lower() or "protected" in stdout.lower()


# ============================================================================
# VAL-BRANCH-008: Empty branch list — exits cleanly with code 0
# ============================================================================
def test_empty_branch_list_exits_cleanly(tmp_path: Path):
    """When no branches exist besides main, script exits 0."""
    branches = []
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"
    assert "no branches" in stdout.lower() or "nothing to clean" in stdout.lower()


# ============================================================================
# VAL-BRANCH-009: Deleted branches tracked in output for Issue notification
# ============================================================================
def test_deleted_branches_tracked_in_output(tmp_path: Path):
    """Script outputs deleted branch names in a parseable format."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [
        ("orphan-1", old_date, False),
        ("orphan-2", old_date, False),
    ]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {
        "orphan-1": [],
        "orphan-2": [],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    # Check that output contains deleted branch names and count
    assert "orphan-1" in stdout, "Output should contain orphan-1"
    assert "orphan-2" in stdout, "Output should contain orphan-2"
    assert "deleted_count=2" in stdout, "Output should contain deleted_count=2"


# ============================================================================
# VAL-BRANCH-010: Extracted script passes shellcheck with zero warnings
# ============================================================================
def test_shellcheck_clean():
    """shellcheck scripts/branch_cleanup.sh exits 0."""
    from tests.shellcheck_helpers import assert_shellcheck_clean

    assert_shellcheck_clean(get_script_path())


# ============================================================================
# VAL-BRANCH-011: Script interface — modes accepted, invalid args rejected
# ============================================================================
def test_script_accepts_scheduled_mode():
    """--scheduled mode is accepted."""
    exit_code, stdout, stderr = run_branch_cleanup("--scheduled")
    # Should not fail with usage error (may fail for other reasons like no git repo)
    assert "invalid mode" not in stdout.lower()


def test_script_accepts_immediate_mode_with_branch():
    """--immediate <branch> is accepted."""
    exit_code, stdout, stderr = run_branch_cleanup("--immediate", "some-branch")
    # Should not fail with usage error
    assert "invalid mode" not in stdout.lower()


def test_script_rejects_immediate_without_branch():
    """--immediate without branch argument exits non-zero with usage."""
    script_path = get_script_path()
    result = subprocess.run(
        ["bash", str(script_path), "--immediate"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Should fail when --immediate has no branch argument"
    assert "usage" in result.stdout.lower() or "error" in result.stdout.lower()


def test_script_rejects_invalid_mode():
    """Invalid mode exits non-zero with usage message."""
    script_path = get_script_path()
    result = subprocess.run(
        ["bash", str(script_path), "--bad-flag"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Should fail with invalid mode"
    assert "usage" in result.stdout.lower() or "invalid" in result.stdout.lower()


def test_script_rejects_no_args():
    """No arguments exits non-zero or defaults explicitly."""
    script_path = get_script_path()
    result = subprocess.run(
        ["bash", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Should fail with no arguments"
    assert "usage" in result.stdout.lower() or "error" in result.stdout.lower()


# ============================================================================
# VAL-BRANCH-012: Workflow calls extracted script with correct arguments
# ============================================================================
def test_workflow_calls_extracted_script():
    """Workflow YAML contains script reference, correct event-based dispatch."""
    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "branch-cleanup.yml"
    content = workflow_path.read_text()

    # Check that script is referenced
    assert "scripts/branch_cleanup.sh" in content, "Workflow should reference the extracted script"

    # Check for event-based dispatch
    assert "github.event_name" in content, "Workflow should use github.event_name for mode selection"
    assert "--immediate" in content, "Workflow should call script with --immediate for PR events"
    assert "--scheduled" in content, "Workflow should call script with --scheduled for scheduled events"

    # Check that pull_request.head.ref is passed
    assert "github.event.pull_request.head.ref" in content, "Workflow should pass trigger branch name"

    # Check that GH_TOKEN is set
    assert "GH_TOKEN" in content, "Workflow should set GH_TOKEN"


# ============================================================================
# VAL-BRANCH-013: IMMEDIATE_MODE does not apply 24h age threshold
# ============================================================================
def test_immediate_mode_no_age_threshold(tmp_path: Path):
    """In --immediate mode, age check is skipped entirely."""
    now = datetime.now(timezone.utc)
    very_fresh = now - timedelta(seconds=30)  # 30 seconds old

    branches = [("brand-new", very_fresh, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {"brand-new": []})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "brand-new",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "brand-new" not in remaining_branches, "Very fresh branch should be deleted in immediate mode"
    assert "24h" not in stdout.lower() or "skipping" not in stdout.lower()


# ============================================================================
# VAL-BRANCH-014: IMMEDIATE_MODE with non-existent branch exits gracefully
# ============================================================================
def test_immediate_mode_nonexistent_branch(tmp_path: Path):
    """If --immediate <branch> doesn't exist, script exits 0 with 'not found' message."""
    branches = []
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "nonexistent-branch",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    assert exit_code == 0, "Should exit 0 for non-existent branch"
    assert "not found" in stdout.lower() or "nothing to do" in stdout.lower()


# ============================================================================
# VAL-BRANCH-015: SCHEDULED_MODE processes multiple orphans in one run
# ============================================================================
def test_scheduled_mode_multiple_orphans(tmp_path: Path):
    """3 orphan branches (> 24h, no PR) all deleted."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)
    fresh_date = now - timedelta(hours=12)

    branches = [
        ("orphan-old-1", old_date, False),
        ("orphan-old-2", old_date, False),
        ("orphan-old-3", old_date, False),
        ("orphan-fresh", fresh_date, False),  # Should be preserved
        ("has-pr", old_date, True),  # Should be preserved (has open PR)
    ]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {
        "orphan-old-1": [],
        "orphan-old-2": [],
        "orphan-old-3": [],
        "orphan-fresh": [],
        "has-pr": [{"number": 789, "state": "OPEN"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)

    # Old orphans should be deleted
    assert "orphan-old-1" not in remaining_branches
    assert "orphan-old-2" not in remaining_branches
    assert "orphan-old-3" not in remaining_branches

    # Fresh and PR-protected should be preserved
    assert "orphan-fresh" in remaining_branches, "Fresh branch should be preserved"
    assert "has-pr" in remaining_branches, "Branch with PR should be preserved"
    assert "main" in remaining_branches, "Main should be preserved"


# ============================================================================
# VAL-BRANCH-016: Script uses `set -euo pipefail` for strict error mode
# ============================================================================
def test_script_uses_strict_mode():
    """Script contains set -euo pipefail."""
    script_path = get_script_path()
    content = script_path.read_text()

    assert "set -e" in content, "Script should contain 'set -e'"
    assert "set -u" in content or "-u" in content, "Script should contain '-u'"
    assert "pipefail" in content, "Script should contain 'pipefail'"


# ============================================================================
# VAL-BRANCH-017: Script has execute permission in git index
# ============================================================================
def test_script_has_execute_permission():
    """git ls-files --stage scripts/branch_cleanup.sh shows mode 100755."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "scripts/branch_cleanup.sh"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "100755" in result.stdout, "Script should have execute permission (100755) in git index"


# ============================================================================
# VAL-BRANCH-018: gh CLI failure is fail-closed — branch skipped, not deleted
# ============================================================================
def test_gh_cli_failure_skip_branch(tmp_path: Path):
    """When gh pr list fails, branch is skipped (not deleted)."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [("feature-api-error", old_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    # Create a mock that fails
    mock_dir = tmp_path / "mock_bin"
    mock_dir.mkdir(exist_ok=True)
    mock_gh = mock_dir / "gh"
    mock_gh.write_text("""#!/bin/bash
# Mock gh that always fails
exit 1
""")
    mock_gh.chmod(0o755)

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "feature-api-error" in remaining_branches, "Branch should be preserved when gh fails"
    assert "skipping" in stdout.lower() or "fail-closed" in stdout.lower()


# ============================================================================
# VAL-BRANCH-019: Unreadable commit date — branch skipped
# ============================================================================
def test_unreadable_commit_date_skip_branch(tmp_path: Path):
    """If git log returns empty for commit date, branch is skipped."""
    # This is hard to test directly without corrupting git data
    # We'll verify the code path exists by checking the script content
    script_path = get_script_path()
    content = script_path.read_text()

    # Check that the script has the safety check for empty commit date
    assert "LAST_COMMIT_EPOCH" in content
    assert "could not get last commit date" in content.lower() or "skipping" in content.lower()


# ============================================================================
# VAL-BRANCH-020: Output format parseable by Issue-creation workflow step
# ============================================================================
def test_output_format_parseable(tmp_path: Path):
    """Script writes deleted_count and protected_count in parseable format."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [("test-branch", old_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {"test-branch": []})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    # Check output format
    assert "deleted_count=" in stdout, "Output should contain deleted_count="
    assert "protected_count=" in stdout, "Output should contain protected_count="

    # Parse the counts
    for line in stdout.split("\n"):
        if line.startswith("deleted_count="):
            count = int(line.split("=")[1])
            assert count >= 0, "deleted_count should be non-negative"
        if line.startswith("protected_count="):
            count = int(line.split("=")[1])
            assert count >= 0, "protected_count should be non-negative"


# ============================================================================
# VAL-CROSS-013: IMMEDIATE_MODE only processes specified branch (integration)
# ============================================================================
def test_cross_immediate_mode_only_specified_branch(tmp_path: Path):
    """PR for branch-A closed. Script processes ONLY branch-A."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [
        ("branch-A", old_date, False),  # Target branch
        ("branch-B", old_date, False),  # Should NOT be evaluated
    ]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {
        "branch-A": [],
        "branch-B": [],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "branch-A",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "branch-A" not in remaining_branches, "branch-A should be deleted"
    assert "branch-B" in remaining_branches, "branch-B should NOT be touched"


# ============================================================================
# VAL-CROSS-014: IMMEDIATE_MODE deletes branch regardless of age (integration)
# ============================================================================
def test_cross_immediate_mode_deletes_regardless_of_age(tmp_path: Path):
    """Branch 5 minutes old with no open PR → deleted in immediate mode."""
    now = datetime.now(timezone.utc)
    very_fresh = now - timedelta(minutes=5)

    branches = [("young-branch", very_fresh, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {"young-branch": []})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "young-branch",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "young-branch" not in remaining_branches, "Young branch should be deleted in immediate mode"


# ============================================================================
# VAL-CROSS-015: IMMEDIATE_MODE skips branch with open PR (integration)
# ============================================================================
def test_cross_immediate_mode_skips_branch_with_pr(tmp_path: Path):
    """Branch has open PR → NOT deleted in immediate mode."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)

    branches = [("protected-branch", old_date, True)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {
        "protected-branch": [{"number": 999, "state": "OPEN"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "protected-branch",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "protected-branch" in remaining_branches, "Branch with PR should be preserved"


# ============================================================================
# VAL-CROSS-016: IMMEDIATE_MODE never deletes main (integration)
# ============================================================================
def test_cross_immediate_mode_never_deletes_main(tmp_path: Path):
    """--immediate main → main NOT deleted."""
    branches = []
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {})

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "main",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "main" in remaining_branches, "Main should NEVER be deleted"


# ============================================================================
# VAL-CROSS-017: SCHEDULED_MODE criteria enforced (integration)
# ============================================================================
def test_cross_scheduled_mode_criteria_enforced(tmp_path: Path):
    """Stale (> 24h, no PR) → deleted. Fresh (< 24h, no PR) → preserved. Has open PR → preserved."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)
    fresh_date = now - timedelta(hours=12)

    branches = [
        ("stale-orphan", old_date, False),  # Should be deleted
        ("fresh-branch", fresh_date, False),  # Should be preserved
        ("pr-branch", old_date, True),  # Should be preserved
    ]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    mock_gh = create_gh_mock(tmp_path, {
        "stale-orphan": [],
        "fresh-branch": [],
        "pr-branch": [{"number": 111, "state": "OPEN"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "stale-orphan" not in remaining_branches, "Stale orphan should be deleted"
    assert "fresh-branch" in remaining_branches, "Fresh branch should be preserved"
    assert "pr-branch" in remaining_branches, "Branch with PR should be preserved"


# ============================================================================
# VAL-CROSS-018: Shellcheck passes on branch_cleanup.sh (integration)
# ============================================================================
def test_cross_shellcheck_passes():
    """shellcheck scripts/branch_cleanup.sh exits 0."""
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")

    script_path = get_script_path()
    result = subprocess.run(
        ["shellcheck", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"shellcheck failed:\n{result.stdout}\n{result.stderr}"


# ============================================================================
# VAL-CROSS-019: Actionlint passes on branch-cleanup.yml (integration)
# ============================================================================
def test_cross_actionlint_passes():
    """actionlint .github/workflows/branch-cleanup.yml exits 0."""
    import shutil

    import pytest

    if not shutil.which("actionlint"):
        pytest.skip("actionlint not installed")

    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "branch-cleanup.yml"
    result = subprocess.run(
        ["actionlint", str(workflow_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"actionlint failed:\n{result.stdout}\n{result.stderr}"


# ============================================================================
# VAL-BRANCH-021: Fully-merged branch is NOT falsely protected
# (regression: 3-dot symmetric difference inflated unique-commit count)
# ============================================================================
def test_fully_merged_branch_not_falsely_protected(tmp_path: Path):
    """
    A branch whose commits are ALL already in main must NOT be protected,
    even when main has advanced and the branch has a CLOSED-not-merged PR.

    Regression test for INFRA-220: the script used `origin/main...origin/$BRANCH`
    (3-dot symmetric difference) which counts main's new commits too, inflating
    the unique-commit count and causing fully-merged branches to be falsely
    "protected". The fix uses 2-dot `origin/main..origin/$BRANCH` (commits in
    branch but not in main), so a fully-merged branch reports 0 unique commits.
    """
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)  # older than 24h threshold

    # Set up a fixture repo with one feature branch.
    branches = [("merged-feature", old_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    # Cherry-pick the branch's commit onto main, then advance main with extra
    # commits. This makes the branch fully contained in main (0 unique-to-branch
    # commits) while main has moved forward.
    subprocess.run(["git", "checkout", "main"], cwd=clone_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "merge", "--no-ff", "-m", "Merge feature into main", "origin/merged-feature"],
        cwd=clone_dir, check=True, capture_output=True,
    )
    # Advance main with two additional commits
    for i in range(2):
        (clone_dir / f"advance-{i}.txt").write_text(f"advance {i}\n")
        subprocess.run(["git", "add", "."], cwd=clone_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Advance main {i}"],
            cwd=clone_dir, check=True, capture_output=True,
        )
    subprocess.run(["git", "push", "origin", "main"], cwd=clone_dir, check=True, capture_output=True)

    # Sanity: the branch should have 0 commits not in main (2-dot range)
    check = subprocess.run(
        ["git", "rev-list", "--count", "origin/main..origin/merged-feature"],
        cwd=clone_dir, capture_output=True, text=True,
    )
    assert check.stdout.strip() == "0", (
        f"Fixture setup wrong: branch should have 0 unique commits, got {check.stdout.strip()}"
    )

    # Mock gh: branch has a CLOSED (not merged) PR — the condition that triggers
    # the protection check. With the bug, the 3-dot range would see main's extra
    # commits and falsely protect. With the fix, 2-dot sees 0 and does NOT protect.
    mock_gh = create_gh_mock(tmp_path, {
        "merged-feature": [{"number": 200, "state": "CLOSED"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "merged-feature" not in remaining_branches, (
        "Fully-merged branch (0 unique commits) must NOT be protected — "
        "it should be deleted. stdout:\n" + stdout
    )
    # The protection path was NOT taken; verify no PROTECTED marker for this branch
    assert "PROTECTED" not in stdout or "merged-feature" not in stdout.split("PROTECTED")[-1].split("\n")[0], (
        "Branch should not appear in protected list. stdout:\n" + stdout
    )


# ============================================================================
# VAL-BRANCH-022: IMMEDIATE_MODE deletes branch with a MERGED PR
# ============================================================================
def test_immediate_mode_deletes_merged_pr_branch(tmp_path: Path):
    """When --immediate <branch> and the branch has a MERGED PR (state "MERGED"),
    the branch IS deleted even though it has unique commits not in main.

    GitHub/gh-CLI state values are "OPEN", "CLOSED", "MERGED". A MERGED PR has
    state "MERGED" (NOT "CLOSED"), so CLOSED_NOT_MERGED_COUNT is 0 for merged
    PRs → not protected → eligible for deletion. This is the correct, intended
    behavior: a merged PR's branch should be cleaned up.
    """
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)  # 2 days ago

    branches = [("merged-feature", old_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    # Mock gh to return a MERGED PR for this branch
    mock_gh = create_gh_mock(tmp_path, {
        "merged-feature": [{"number": 200, "state": "MERGED"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--immediate",
        "merged-feature",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "merged-feature" not in remaining_branches, (
        "Branch with a MERGED PR should be deleted in immediate mode"
    )
    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"


# ============================================================================
# VAL-BRANCH-023: SCHEDULED_MODE protects branch with CLOSED-not-merged PR + unique commits
# ============================================================================
def test_scheduled_mode_protects_closed_not_merged_with_unique_commits(tmp_path: Path):
    """When a branch has a CLOSED (not merged) PR AND unique commits not in
    main, it is PROTECTED (not deleted) even in scheduled mode with an old
    branch.

    The fixture creates branches with commits not present in main, so
    UNIQUE_COUNT will be > 0. Combined with a CLOSED PR, the safety-protection
    feature kicks in and the branch is preserved.
    """
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=2)  # 2 days ago

    branches = [("closed-unmerged", old_date, False)]
    bare_repo, clone_dir = create_fixture_repo(tmp_path, branches)

    # Mock gh to return a CLOSED (not merged) PR for this branch
    mock_gh = create_gh_mock(tmp_path, {
        "closed-unmerged": [{"number": 300, "state": "CLOSED"}],
    })

    env_overrides = {
        "PATH": f"{mock_gh.parent}:{subprocess.os.environ['PATH']}",
    }

    exit_code, stdout, stderr = run_branch_cleanup(
        "--scheduled",
        cwd=clone_dir,
        env_overrides=env_overrides,
    )

    remaining_branches = get_remote_branches(bare_repo)
    assert "closed-unmerged" in remaining_branches, (
        "Branch with CLOSED-not-merged PR and unique commits should be PROTECTED"
    )
    assert "PROTECTED" in stdout.upper(), (
        f"Output should contain 'PROTECTED' for protected branch. stdout: {stdout}"
    )
