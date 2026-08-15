"""Tests for scripts/check_fix_has_test.py — Fix-has-test CI guard.

Covers: detection logic (VAL-GUARD-001 to VAL-GUARD-010), exemptions
(VAL-GUARD-011 to VAL-GUARD-014), CLI interface (VAL-GUARD-015 to VAL-GUARD-018),
and cross-cutting (VAL-CROSS-001).
"""

import json
import subprocess
import sys
from pathlib import Path

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
    _add_commit(repo, "fix: correct null pointer dereference", {
        "src/foo.py": "def foo(): pass",
        "tests/test_foo.py": "def test_foo(): pass",
    })
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"


# ============================================================================
# VAL-GUARD-002: Fix commit without test files → exit 1
# ============================================================================
def test_fix_without_tests_fails(tmp_path):
    """Fix commit + no test files → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(repo, "fix: correct null pointer dereference", {
        "src/foo.py": "def foo(): pass",
    })
    result = _run_script(["--base", "base"], cwd=repo)
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "fix" in result.stdout.lower() or "fix" in result.stderr.lower()


# ============================================================================
# VAL-GUARD-003: hotfix: prefix detected as fix
# ============================================================================
def test_hotfix_prefix_detected(tmp_path):
    """hotfix: prefix treated as fix → exit 1."""
    repo = _create_fixture_repo(tmp_path)
    _add_commit(repo, "chore: initial commit", {"README.md": "# Test"})
    subprocess.run(["git", "tag", "base"], cwd=repo, check=True, capture_output=True)
    _add_commit(repo, "hotfix: patch security hole", {
        "src/security.py": "def secure(): pass",
    })
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
    _add_commit(repo, "bugfix: resolve race condition", {
        "src/concurrent.py": "def sync(): pass",
    })
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
    _add_commit(repo, "fix(api): handle empty response", {
        "src/api.py": "def api(): pass",
    })
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
    _add_commit(repo, "feat: add new endpoint", {
        "src/endpoint.py": "def endpoint(): pass",
    })
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
    _add_commit(repo, "chore: update dependencies", {
        "requirements.txt": "pytest>=7.0",
    })
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
    _add_commit(repo, "fix!: redesign error handling", {
        "src/errors.py": "def error(): pass",
    })
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
    _add_commit(repo, "fix: correct bug", {
        "docs/guide.md": "Updated guide",
        "src/foo.py": "def foo(): pass",
    })
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
    _add_commit(repo, "fix: something broken", {"src/foo.py": "code"})
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
    _add_commit(repo, "feat: add feature", {"src/foo.py": "code"})
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
    _add_commit(repo, "fix: null pointer dereference", {"src/foo.py": "code"})
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
    _add_commit(repo, "fix: something broken", {"src/foo.py": "code"})
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


def test_live_repo_does_not_violate():
    """Current repository state does not violate the guard."""
    result = _run_script([])
    assert result.returncode == 0, (
        f"Live repo should be clean (no fix commits without tests).\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
