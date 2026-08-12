"""Tests for ci-hygiene feature (VAL-CI-001 through VAL-CI-008)."""
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent


def test_pre_commit_includes_shellcheck():
    """VAL-CI-001: Pre-commit config includes shellcheck hook."""
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text())
    shellcheck_repos = [
        r for r in config["repos"] if "shellcheck" in r.get("repo", "").lower()
    ]
    assert len(shellcheck_repos) == 1
    repo = shellcheck_repos[0]
    assert "rev" in repo
    assert any(h["id"] == "shellcheck" for h in repo["hooks"])


def test_pre_commit_includes_actionlint():
    """VAL-CI-002: Pre-commit config includes actionlint hook."""
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text())
    actionlint_repos = [
        r for r in config["repos"] if "actionlint" in r.get("repo", "").lower()
    ]
    assert len(actionlint_repos) == 1
    repo = actionlint_repos[0]
    assert "rev" in repo
    assert any(h["id"] == "actionlint" for h in repo["hooks"])


def test_ci_runs_shellcheck():
    """VAL-CI-003: CI test job runs shellcheck on shell scripts."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    shell_lint_step = next(
        (s for s in steps if s.get("name") == "Shell lint"), None
    )
    assert shell_lint_step is not None
    assert "shellcheck scripts/*.sh" in shell_lint_step["run"]
    assert shell_lint_step.get("continue-on-error") is not True


def test_ci_runs_actionlint():
    """VAL-CI-004: CI test job runs actionlint on workflow files."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    shell_lint_step = next(
        (s for s in steps if s.get("name") == "Shell lint"), None
    )
    assert shell_lint_step is not None
    assert "actionlint .github/workflows/" in shell_lint_step["run"]
    assert shell_lint_step.get("continue-on-error") is not True


def test_shell_lint_contributes_to_ci_ok():
    """VAL-CI-005: Shell lint step contributes to ci-ok gate."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    # ci-ok job must depend on test job
    ci_ok_job = ci["jobs"]["ci-ok"]
    assert "test" in ci_ok_job["needs"]
    # shellcheck/actionlint are in test job, not continue-on-error
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    shell_lint_step = next(
        (s for s in steps if s.get("name") == "Shell lint"), None
    )
    assert shell_lint_step is not None
    assert shell_lint_step.get("continue-on-error") is not True


def test_all_scripts_pass_shellcheck():
    """VAL-CI-006: All existing shell scripts pass shellcheck."""
    import shutil
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    scripts = list((REPO_ROOT / "scripts").glob("*.sh"))
    assert len(scripts) > 0
    result = subprocess.run(
        ["shellcheck"] + [str(s) for s in scripts],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"shellcheck failed:\n{result.stdout}\n{result.stderr}"


def test_all_workflows_pass_actionlint():
    """VAL-CI-007: All workflow files pass actionlint."""
    import shutil
    if not shutil.which("actionlint"):
        pytest.skip("actionlint not installed")
    workflows = list((REPO_ROOT / ".github/workflows").glob("*.yml"))
    assert len(workflows) > 0
    try:
        result = subprocess.run(
            ["actionlint"] + [str(w) for w in workflows],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("actionlint not installed")
    assert result.returncode == 0, f"actionlint failed:\n{result.stdout}\n{result.stderr}"


def test_ci_installs_linters():
    """VAL-CI-008: shellcheck + actionlint installed in CI environment."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    install_step = next(
        (
            s
            for s in steps
            if "Install shellcheck and actionlint" in s.get("name", "")
        ),
        None,
    )
    assert install_step is not None
    run_content = install_step["run"]
    assert "shellcheck" in run_content.lower()
    assert "actionlint" in run_content.lower()


def test_ci_tarball_extraction_isolated():
    """VAL-CI-009: CI extracts tool tarballs to /tmp, not repo root.

    actionlint release tarball contains README.md at root level.
    Extracting to repo root overwrites the project's README.md,
    causing version-consistency health check to return NOT_FOUND.
    Regression test for PR #532 CI failure.
    """
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    install_step = next(
        s for s in steps if "Install shellcheck and actionlint" in s.get("name", "")
    )
    run_content = install_step["run"]

    # Every tar extraction must target /tmp to avoid overwriting repo files
    tar_lines = [line.strip() for line in run_content.splitlines() if "tar -" in line]
    assert len(tar_lines) > 0, "Expected tar extraction commands in install step"
    for line in tar_lines:
        assert "-C /tmp" in line, (
            f"tar extraction must target /tmp to avoid overwriting repo "
            f"files (README.md, LICENSE): {line}"
        )


# ============================================================================
# Fix-has-test guard structure assertions (VAL-CIGUARD-001 through VAL-CIGUARD-004)
# ============================================================================

def test_ci_has_fix_has_test_guard():
    """VAL-CIGUARD-001: ci.yml test job contains fix-has-test step."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    guard_step = next(
        (s for s in steps if "fix-has-test" in s.get("name", "").lower()
         or "check_fix_has_test" in s.get("run", "")),
        None
    )
    assert guard_step is not None, "Fix-has-test guard step not found in test job"
    assert "check_fix_has_test.py" in guard_step.get("run", "")


def test_fix_has_test_guard_not_advisory():
    """VAL-CIGUARD-002: Step is not continue-on-error (blocking, not advisory)."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    guard_step = next(
        (s for s in steps if "fix-has-test" in s.get("name", "").lower()
         or "check_fix_has_test" in s.get("run", "")),
        None
    )
    assert guard_step is not None
    assert guard_step.get("continue-on-error") is not True, \
        "Fix-has-test guard must not be continue-on-error"


def test_fix_has_test_guard_pr_only():
    """VAL-CIGUARD-003: Step gated on pull_request events only."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    guard_step = next(
        (s for s in steps if "fix-has-test" in s.get("name", "").lower()
         or "check_fix_has_test" in s.get("run", "")),
        None
    )
    assert guard_step is not None
    if_condition = guard_step.get("if", "")
    assert "pull_request" in str(if_condition), \
        f"Fix-has-test guard must be gated on pull_request, got: {if_condition}"


def test_fix_has_test_guard_uses_gh_token():
    """VAL-CROSS-002: CI step uses GH_TOKEN env var for gh API calls."""
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test"]
    steps = test_job["steps"]
    guard_step = next(
        (s for s in steps if "fix-has-test" in s.get("name", "").lower()
         or "check_fix_has_test" in s.get("run", "")),
        None
    )
    assert guard_step is not None
    env = guard_step.get("env", {})
    assert "GH_TOKEN" in env or "GITHUB_TOKEN" in env, \
        "Fix-has-test guard step must set GH_TOKEN or GITHUB_TOKEN"
    token_value = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    assert "secrets.GITHUB_TOKEN" in str(token_value), \
        f"Token must reference secrets.GITHUB_TOKEN, got: {token_value}"
