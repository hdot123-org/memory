"""Tests for ci-hygiene feature (VAL-CI-001 through VAL-CI-008)."""
import subprocess
from pathlib import Path

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
    workflows = list((REPO_ROOT / ".github/workflows").glob("*.yml"))
    assert len(workflows) > 0
    result = subprocess.run(
        ["actionlint"] + [str(w) for w in workflows],
        capture_output=True,
        text=True,
    )
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
