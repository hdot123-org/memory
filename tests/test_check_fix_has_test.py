"""Tests for scripts/check_fix_has_test.py — Fix-has-test CI guard.

Covers: detection logic (VAL-GUARD-001 to VAL-GUARD-010), exemptions
(VAL-GUARD-011 to VAL-GUARD-014), CLI interface (VAL-GUARD-015 to VAL-GUARD-018),
and cross-cutting (VAL-CROSS-001).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.script_module_helpers import load_script_module

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_fix_has_test.py"


def _run_script(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the guard script with given args."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)] + args,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _create_fixture_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with controlled commits for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    return repo


def _add_commit(repo: Path, msg: str, files: dict[str, str]) -> None:
    """Add files and create a commit with given message."""
    for path, content in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        subprocess.run(["git", "add", path], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True, capture_output=True)


# ============================================================================
# VAL-GUARD-001: Fix commit with test files → exit 0
# ============================================================================
def test_fix_with_tests_passes(tmp_path):
    """Fix commit + test file changed → exit 0."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct null pointer dereference",
        {
            "memory_core/tools/foo.py": "def foo(): pass",
            "tests/test_foo.py": "def test_foo(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ============================================================================
# VAL-GUARD-019~021: gh pr view 瞬时故障重试（TD-503-02，2026-08-18）
# ============================================================================
def _make_called_process_error(stderr: str) -> subprocess.CalledProcessError:
    exc = subprocess.CalledProcessError(1, ["gh"])
    exc.stderr = stderr
    exc.stdout = ""
    return exc


def test_get_pr_data_retries_on_503(monkeypatch):
    """VAL-GUARD-019: gh pr view 遇 503 瞬时错误重试后成功 → 正常返回数据。"""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    calls = []

    def fake_run_503_then_ok(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            raise _make_called_process_error("gh pr view failed: HTTP 503: No server is currently available")

        class R:
            stdout = json.dumps({"commits": [], "files": [], "author": "x"})
            stderr = ""

        return R()

    monkeypatch.setattr(mod, "_run", fake_run_503_then_ok)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    data = mod.get_pr_data(42)
    assert data == {"commits": [], "files": [], "author": "x"}
    assert len(calls) == 2


def test_get_pr_data_gives_up_after_3_transient_failures(monkeypatch):
    """VAL-GUARD-020: 持续 503 重试 3 次后仍失败 → exit 2（fail-closed）。

    最后一轮的非重试分支直接 SystemExit(2)（2026-08-18 清理了循环后不可达的
    兜底错误处理，行为不变：仍 fail-closed）。
    """
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    calls = []

    def fake_run_always_503(cmd, **kwargs):
        calls.append(cmd)
        raise _make_called_process_error("HTTP 503: server unavailable")

    monkeypatch.setattr(mod, "_run", fake_run_always_503)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit) as exc_info:
        mod.get_pr_data(42)
    assert exc_info.value.code == 2
    assert len(calls) == 3


def test_get_pr_data_no_retry_on_404(monkeypatch):
    """VAL-GUARD-021: 非瞬时错误（404）不重试 → 立即 exit 2。"""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    calls = []

    def fake_run_404(cmd, **kwargs):
        calls.append(cmd)
        raise _make_called_process_error("HTTP 404: Not Found")

    monkeypatch.setattr(mod, "_run", fake_run_404)
    with pytest.raises(SystemExit) as exc_info:
        mod.get_pr_data(999)
    assert exc_info.value.code == 2
    assert len(calls) == 1


def test_get_pr_data_uses_repo_flag_from_github_repository_env(monkeypatch):
    """CI 环境（GITHUB_REPOSITORY 已设置）→ gh pr view 显式 --repo。

    self-hosted runner 配置 git url.<mirror>.insteadOf 全局重写后，gh 基于
    workspace remote 的仓库推断误判 "no known GitHub host"，guard 以 exit 2
    阻塞一切 PR（2026-08-28 INFRA-597 CI 事故，两台 pve runner 复现）。
    GITHUB_REPOSITORY（Actions 运行器默认注入）显式指定 OWNER/REPO，
    仓库解析不再依赖 workspace remote。
    """
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)

        class R:
            stdout = json.dumps({"commits": [], "files": [], "author": "x"})
            stderr = ""

        return R()

    monkeypatch.setenv("GITHUB_REPOSITORY", "hdot123-org/memory")
    monkeypatch.setattr(mod, "_run", fake_run)
    data = mod.get_pr_data(42)
    assert data == {"commits": [], "files": [], "author": "x"}
    assert captured["cmd"] == [
        "gh",
        "pr",
        "view",
        "42",
        "--repo",
        "hdot123-org/memory",
        "--json",
        "commits,files,author",
    ]


def test_get_pr_data_no_repo_flag_without_github_repository_env(monkeypatch):
    """GITHUB_REPOSITORY 未设置（本地调试）→ 保持原命令形态（无 --repo）。"""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)

        class R:
            stdout = json.dumps({"commits": [], "files": [], "author": "x"})
            stderr = ""

        return R()

    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(mod, "_run", fake_run)
    mod.get_pr_data(42)
    assert captured["cmd"] == ["gh", "pr", "view", "42", "--json", "commits,files,author"]


# ============================================================================
# VAL-GUARD-002: Fix commit without test files → exit 1
# ============================================================================
def test_fix_without_tests_fails(tmp_path):
    """Fix commit + no test files → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct null pointer dereference",
        {
            "memory_core/tools/foo.py": "def foo(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, (
        f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "fix" in result.stdout.lower() or "fix" in result.stderr.lower()


# ============================================================================
# VAL-GUARD-003: hotfix: prefix detected as fix
# ============================================================================
def test_hotfix_prefix_detected(tmp_path):
    """hotfix: prefix treated as fix → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "hotfix: patch security hole",
        {
            "memory_core/tools/security.py": "def secure(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1 for hotfix:, got {result.returncode}"


# ============================================================================
# VAL-GUARD-004: bugfix: prefix detected as fix
# ============================================================================
def test_bugfix_prefix_detected(tmp_path):
    """bugfix: prefix treated as fix → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "bugfix: resolve race condition",
        {
            "memory_core/tools/concurrent.py": "def sync(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1 for bugfix:, got {result.returncode}"


# ============================================================================
# VAL-GUARD-005: fix(scope): conventional commit format detected
# ============================================================================
def test_fix_with_scope_detected(tmp_path):
    """fix(scope): conventional format → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix(api): handle empty response",
        {
            "memory_core/tools/api.py": "def api(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1 for fix(scope):, got {result.returncode}"


# ============================================================================
# VAL-GUARD-006: feat: commit without tests → exit 0
# ============================================================================
def test_feat_commit_passes(tmp_path):
    """feat: commit without tests → exit 0."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "feat: add new endpoint",
        {
            "memory_core/tools/endpoint.py": "def endpoint(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, f"Expected exit 0 for feat:, got {result.returncode}"


# ============================================================================
# VAL-GUARD-007: chore: commit without tests → exit 0
# ============================================================================
def test_chore_commit_passes(tmp_path):
    """chore: commit without tests → exit 0."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "chore: update dependencies",
        {
            "requirements.txt": "pytest>=7.0",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, f"Expected exit 0 for chore:, got {result.returncode}"


# ============================================================================
# VAL-GUARD-008: Non-PR context (push to main) → exit 0
# ============================================================================
def test_non_pr_context_passes(tmp_path):
    """Local mode without --pr or --base → exit 0."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "fix: something broken", {"src/foo.py": "code"})
    result = _run_script([], cwd=repo)
    assert result.returncode == 0, f"Expected exit 0 for non-PR context, got {result.returncode}"


# ============================================================================
# VAL-GUARD-009: Script error handling → exit 2
# ============================================================================
def test_error_handling_exit_2(tmp_path):
    """Script error (invalid git ref) → exit 2."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    # Try to use a non-existent base ref to trigger git error
    result = _run_script(["--base", "nonexistent-ref"], cwd=repo)
    assert result.returncode == 2, f"Expected exit 2 for invalid git ref, got {result.returncode}"
    assert "error" in result.stderr.lower() or "fatal" in result.stderr.lower()


# ============================================================================
# VAL-GUARD-010: fix! with breaking-change marker detected
# ============================================================================
def test_fix_breaking_change_detected(tmp_path):
    """fix! or fix(scope)! detected as fix → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix!: redesign error handling",
        {
            "memory_core/tools/errors.py": "def error(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1 for fix!:, got {result.returncode}"


# ============================================================================
# VAL-GUARD-011: Dependabot PR exempted
# ============================================================================
def test_dependabot_exempted(monkeypatch):
    """Dependabot author → exit 0."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    assert mod.is_dependabot("dependabot[bot]")
    assert mod.is_dependabot("dependabot")
    assert mod.is_dependabot("Dependabot[bot]")
    assert not mod.is_dependabot("octocat")


# ============================================================================
# VAL-GUARD-012: Release-please PR exempted
# ============================================================================
def test_release_please_exempted():
    """Release-please commit → exit 0."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    commits = ["chore(main): release 1.2.3"]
    assert mod.is_release_please(commits)
    commits = ["fix: something", "chore(main): release 2.0.0"]
    assert mod.is_release_please(commits)
    commits = ["fix: something"]
    assert not mod.is_release_please(commits)


# ============================================================================
# VAL-GUARD-013: Docs-only PR exempted
# ============================================================================
def test_docs_only_exempted():
    """All .md files → exit 0."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = ["docs/guide.md", "README.md"]
    assert mod.is_docs_only(files)
    files = ["docs/guide.md", "src/foo.py"]
    assert not mod.is_docs_only(files)
    files = []
    assert not mod.is_docs_only(files)


# ============================================================================
# VAL-GUARD-014: Mixed docs and code with fix commit → NOT exempted
# ============================================================================
def test_mixed_doc_code_not_exempted(tmp_path):
    """Mixed .md + .py with fix → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct bug",
        {
            "docs/guide.md": "Updated guide",
            "memory_core/tools/foo.py": "def foo(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1 for mixed docs+code, got {result.returncode}"


# ============================================================================
# VAL-GUARD-015: --json output format valid on violation
# ============================================================================
def test_json_output_violation(tmp_path):
    """--json on violation: valid JSON with violations+count."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(repo, "fix: something broken", {"memory_core/tools/foo.py": "code"})
    result = _run_script(["--base", "base", "--json"], cwd=repo)
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert "violations" in data
    assert "count" in data
    assert data["count"] == 1
    assert len(data["violations"]) == 1
    assert "commit" in data["violations"][0]


# ============================================================================
# VAL-GUARD-016: --json output format valid on clean
# ============================================================================
def test_json_output_clean(tmp_path):
    """--json on clean: violations=[], count=0."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(repo, "feat: add feature", {"memory_core/tools/foo.py": "code"})
    result = _run_script(["--base", "base", "--json"], cwd=repo)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["violations"] == []
    assert data["count"] == 0


# ============================================================================
# VAL-GUARD-017: Error message on violation is clear and actionable
# ============================================================================
def test_error_message_clarity(tmp_path):
    """Violation message includes commit message and actionable instruction."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(repo, "fix: null pointer dereference", {"memory_core/tools/foo.py": "code"})
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "fix" in output.lower() or "bug fix" in output.lower()
    assert "null pointer dereference" in output or "tests/" in output
    assert "add" in output.lower() or "include" in output.lower()


# ============================================================================
# VAL-GUARD-018: --base flag works for custom base ref
# ============================================================================
def test_base_flag_works(tmp_path):
    """--base flag uses custom base ref."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "custom-base"], cwd=repo, check=True, capture_output=True)
    _add_commit(repo, "fix: something broken", {"memory_core/tools/foo.py": "code"})
    result = _run_script(["--base", "custom-base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1 with custom base, got {result.returncode}"


# ============================================================================
# VAL-CROSS-001: Guard script has test coverage (meta)
# ============================================================================
def test_script_exists_and_testable():
    """Script exists and is importable."""
    assert SCRIPT_PATH.is_file(), "scripts/check_fix_has_test.py must exist"
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    assert hasattr(mod, "main")
    assert hasattr(mod, "FIX_PATTERN")
    assert hasattr(mod, "has_fix_commit")
    assert hasattr(mod, "has_test_files")
    assert hasattr(mod, "is_dependabot")
    assert hasattr(mod, "is_release_please")
    assert hasattr(mod, "is_docs_only")
    assert hasattr(mod, "is_non_code_only")


def test_fix_pattern_matches_conventional_formats():
    """FIX_PATTERN matches all conventional fix commit formats."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    assert mod.FIX_PATTERN.match("fix: something")
    assert mod.FIX_PATTERN.match("fix!: breaking change")
    assert mod.FIX_PATTERN.match("fix(scope): something")
    assert mod.FIX_PATTERN.match("fix(scope)!: breaking change")
    assert mod.FIX_PATTERN.match("hotfix: something")
    assert mod.FIX_PATTERN.match("bugfix: something")
    assert mod.FIX_PATTERN.match("FIX: uppercase")
    assert not mod.FIX_PATTERN.match("feat: something")
    assert not mod.FIX_PATTERN.match("chore: something")
    assert not mod.FIX_PATTERN.match("fix something")


# ============================================================================
# VAL-GUARD-022: is_non_code_only function unit tests
# ============================================================================
def test_is_non_code_only_webhook_scripts_exempted():
    """webhook-scripts-only PR → exempted (is_non_code_only returns True)."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = [
        "webhook-scripts/trigger-ci-droid.sh",
        "webhook-scripts/MANIFEST.sh",
    ]
    assert mod.is_non_code_only(files)


def test_is_non_code_only_mixed_infra_exempted():
    """Mixed webhook-scripts + .github/workflows + docs → exempted."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = [
        "webhook-scripts/trigger-ci-droid.sh",
        ".github/workflows/ci.yml",
        "docs/architecture/ci-notify-n8n-workflow.md",
    ]
    assert mod.is_non_code_only(files)


def test_is_non_code_only_memory_core_not_exempted():
    """memory_core/ files → NOT exempted (is_non_code_only returns False)."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = [
        "memory_core/tools/pretooluse_guard.py",
        "docs/guide.md",
    ]
    assert not mod.is_non_code_only(files)


def test_is_non_code_only_scripts_not_exempted():
    """scripts/ files → NOT exempted."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = [
        "scripts/check_fix_has_test.py",
        "docs/guide.md",
    ]
    assert not mod.is_non_code_only(files)


def test_is_non_code_only_tests_not_exempted():
    """tests/ files → NOT exempted."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = [
        "tests/test_check_fix_has_test.py",
    ]
    assert not mod.is_non_code_only(files)


def test_is_non_code_only_empty_list():
    """Empty file list → False."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    assert not mod.is_non_code_only([])


def test_is_non_code_only_empty_strings_ignored():
    """Empty strings in file list are ignored."""
    mod = load_script_module(SCRIPT_PATH, "check_fix_has_test")
    files = ["", "webhook-scripts/foo.sh", ""]
    assert mod.is_non_code_only(files)


# ============================================================================
# VAL-GUARD-023: Integration test — webhook-scripts-only fix PR exempted
# ============================================================================
def test_webhook_scripts_only_fix_exempted(tmp_path):
    """fix: commit with only webhook-scripts/ changes → exit 0 (exempted)."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct webhook script path",
        {
            "webhook-scripts/trigger-ci-droid.sh": "#!/bin/bash\necho fixed",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, (
        f"Expected exit 0 for webhook-scripts-only fix, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_mixed_infra_fix_exempted(tmp_path):
    """fix: commit with webhook-scripts + .github + docs → exit 0 (exempted)."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct ci notification logic",
        {
            ".github/workflows/ci.yml": "name: CI\non: push",
            "webhook-scripts/trigger-ci-droid.sh": "#!/bin/bash\necho fixed",
            "docs/architecture/ci-notify.md": "# CI Notification",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, (
        f"Expected exit 0 for mixed infra fix, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_memory_core_fix_without_test_still_violates(tmp_path):
    """fix: commit with memory_core/ but no tests/ → exit 1 (NOT exempted)."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct gateway logic",
        {
            "memory_core/tools/pretooluse_guard.py": "def guard(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, (
        f"Expected exit 1 for memory_core fix without test, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_memory_core_fix_with_test_passes(tmp_path):
    """fix: commit with memory_core/ + tests/ → exit 0 (test present)."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(
        repo,
        "fix: correct gateway logic",
        {
            "memory_core/tools/pretooluse_guard.py": "def guard(): pass",
            "tests/test_pretooluse_guard.py": "def test_guard(): pass",
        },
    )
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, (
        f"Expected exit 0 for memory_core fix with test, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_live_repo_does_not_violate():
    """Current repository state does not violate the guard."""
    result = _run_script([])
    assert result.returncode == 0, (
        f"Live repo should be clean (no fix commits without tests).\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
