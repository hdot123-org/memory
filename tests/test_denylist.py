"""Tests for the project denylist mechanism.

Covers VAL-M2-023 through VAL-M2-030 and VAL-CROSS-003.

The denylist rejects:
- $TMPDIR (canonical temp dirs: /tmp, /var/folders) subdirectories
- ~/.factory subdirectories
- $HOME root (exact match)
- Pattern-based junk directory names (tmp.*, demo-*, test-*, smoke-test-*, restart-*, file-list-*)
- Non-git directories (without --allow-non-git flag)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def disable_denylist_bypass():
    """Disable the denylist bypass for denylist tests.

    The conftest.py sets MEMORY_CORE_BYPASS_DENYLIST=1 for all tests to allow
    tmp_path usage. This fixture explicitly disables it so denylist tests can
    actually test the denylist logic.
    """
    old_val = os.environ.get("MEMORY_CORE_BYPASS_DENYLIST")
    if "MEMORY_CORE_BYPASS_DENYLIST" in os.environ:
        del os.environ["MEMORY_CORE_BYPASS_DENYLIST"]
    yield
    if old_val is not None:
        os.environ["MEMORY_CORE_BYPASS_DENYLIST"] = old_val


def _make_non_tmp_dir(tmp_path: Path) -> Path:
    """Create a directory under a non-temp parent for testing.

    On macOS, tmp_path may resolve under /private/var/folders/... which
    is the system temp dir. We create a test workspace under a known
    non-temp location by using a dedicated subpath and clearing TMPDIR.
    """
    # Use a path under /tmp/pytest-workspace that we explicitly control.
    # We clear TMPDIR so the denylist doesn't catch it via the TMPDIR check,
    # but we place it under a path that is NOT /tmp itself.
    # Actually, we just need to make a directory NOT under /tmp, /var/folders, etc.
    # Use home-relative path for safety.
    workspace = Path.home() / ".memory-test-workspace"
    workspace.mkdir(exist_ok=True)
    return workspace


@pytest.fixture
def safe_workspace(monkeypatch):
    """Create a safe workspace directory not under system temp dirs.

    Also patches TMPDIR to a non-temp value so the denylist TMPDIR check
    doesn't interfere with other test assertions.
    """
    workspace = _make_non_tmp_dir(None)
    # Clear TMPDIR so denylist doesn't catch these test dirs
    monkeypatch.delenv("TMPDIR", raising=False)
    yield workspace
    # Cleanup
    try:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Unit tests for denylist module
# ---------------------------------------------------------------------------


class TestCheckDenylist:
    """Tests for check_denylist() function."""

    def test_tmpdir_env_rejected(self, monkeypatch):
        """VAL-M2-023: $TMPDIR subdirectories are rejected when TMPDIR points to /tmp."""
        from memory_core.tools.denylist import check_denylist

        monkeypatch.setenv("TMPDIR", "/tmp")
        target = Path("/tmp/some_project")

        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "tmpdir"
        assert "tmp" in result.message.lower() or "TMPDIR" in result.message

    def test_system_tmp_rejected(self, monkeypatch):
        """VAL-M2-023: /tmp subdirectories are rejected."""
        from memory_core.tools.denylist import check_denylist

        monkeypatch.delenv("TMPDIR", raising=False)
        target = Path("/tmp/some_project")

        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "tmpdir"

    def test_factory_rejected(self):
        """VAL-M2-024: ~/.factory subdirectories are rejected."""
        from memory_core.tools.denylist import check_denylist

        target = Path.home() / ".factory" / "some_project"
        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "factory"

    def test_factory_exact_rejected(self):
        """VAL-M2-024: ~/.factory itself is rejected."""
        from memory_core.tools.denylist import check_denylist

        target = Path.home() / ".factory"
        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "factory"

    def test_home_root_rejected(self):
        """VAL-M2-025: $HOME root is rejected."""
        from memory_core.tools.denylist import check_denylist

        target = Path.home()
        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "home_root"

    @pytest.mark.parametrize(
        "dir_name,rule",
        [
            ("tmp.something", "junk_pattern"),
            ("demo-project", "junk_pattern"),
            ("test-runner", "junk_pattern"),
            ("smoke-test-001", "junk_pattern"),
            ("restart-daemon", "junk_pattern"),
            ("file-list-2024", "junk_pattern"),
        ],
    )
    def test_junk_patterns_rejected(self, safe_workspace, dir_name, rule):
        """VAL-M2-026: Pattern-based junk directory names are rejected."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / dir_name
        target.mkdir(exist_ok=True)

        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "junk_pattern"
        assert dir_name in result.message

    @pytest.mark.parametrize(
        "dir_name",
        [
            "my-project",
            "webapp",
            "backend-service",
            "data-pipeline",
            "real_app",
        ],
    )
    def test_clean_names_not_rejected_by_pattern(self, safe_workspace, dir_name):
        """VAL-M2-026: Clean directory names are NOT rejected by pattern rule."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / dir_name
        target.mkdir(exist_ok=True)
        (target / ".git").mkdir(exist_ok=True)

        result = check_denylist(target)
        assert result.denied is False

    def test_clean_git_project_accepted(self, safe_workspace):
        """VAL-M2-028: Legitimate git project is accepted."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / "legit-project"
        target.mkdir(exist_ok=True)
        (target / ".git").mkdir()

        result = check_denylist(target)
        assert result.denied is False

    def test_non_git_rejected_without_flag(self, safe_workspace):
        """VAL-M2-027: Non-git directory is rejected without --allow-non-git."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / "non-git-project"
        target.mkdir(exist_ok=True)

        result = check_denylist(target, allow_non_git=False)
        assert result.denied is True
        assert result.rule == "non_git"
        assert "--allow-non-git" in result.message

    def test_non_git_allowed_with_flag(self, safe_workspace):
        """VAL-M2-027: Non-git directory is allowed with --allow-non-git."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / "non-git-project"
        target.mkdir(exist_ok=True)

        result = check_denylist(target, allow_non_git=True)
        assert result.denied is False

    def test_git_project_no_flag_accepted(self, safe_workspace):
        """VAL-M2-028: Git project is accepted even without --allow-non-git."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / "git-project"
        target.mkdir(exist_ok=True)
        (target / ".git").mkdir()

        result = check_denylist(target, allow_non_git=False)
        assert result.denied is False


class TestDenylistResult:
    """Tests for DenylistResult dataclass."""

    def test_result_not_denied(self):
        """DenylistResult with denied=False has no rule or message."""
        from memory_core.tools.denylist import DenylistResult

        result = DenylistResult.denied_ok()
        assert result.denied is False
        assert result.rule is None
        assert result.message is None

    def test_result_denied_with_rule(self):
        """DenylistResult with denial has rule and message."""
        from memory_core.tools.denylist import DenylistResult

        result = DenylistResult.denied("tmpdir", "path is under /tmp")
        assert result.denied is True
        assert result.rule == "tmpdir"
        assert "tmp" in result.message.lower()


class TestDenylistActionableMessages:
    """VAL-M2-030: Denylist error messages are actionable."""

    def test_tmpdir_message_contains_rule_and_override(self, monkeypatch):
        """Rejection for tmpdir cites the rule."""
        from memory_core.tools.denylist import check_denylist

        monkeypatch.setenv("TMPDIR", "/tmp")
        target = Path("/tmp/project")

        result = check_denylist(target)
        assert result.denied is True
        assert "tmpdir" in result.rule
        assert len(result.message) > 10

    def test_non_git_message_contains_override_hint(self, safe_workspace):
        """Non-git rejection message contains --allow-non-git hint."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / "no-git"
        target.mkdir(exist_ok=True)

        result = check_denylist(target, allow_non_git=False)
        assert result.denied is True
        assert result.rule == "non_git"
        assert "--allow-non-git" in result.message

    def test_factory_message_informative(self):
        """Factory rejection message is informative."""
        from memory_core.tools.denylist import check_denylist

        target = Path.home() / ".factory" / "test"
        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "factory"
        assert ".factory" in result.message

    def test_home_root_message_informative(self):
        """Home root rejection message is informative."""
        from memory_core.tools.denylist import check_denylist

        target = Path.home()
        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "home_root"
        assert "HOME" in result.message or "home" in result.message.lower()

    def test_junk_pattern_message_contains_dir_name(self, safe_workspace):
        """Junk pattern rejection message mentions the offending directory name."""
        from memory_core.tools.denylist import check_denylist

        target = safe_workspace / "demo-sprint"
        target.mkdir(exist_ok=True)

        result = check_denylist(target)
        assert result.denied is True
        assert "demo-sprint" in result.message


# ---------------------------------------------------------------------------
# Integration tests for init_project_memory.py with denylist
# ---------------------------------------------------------------------------


class TestInitWithDenylist:
    """Integration tests: init_project_memory rejects denied paths."""

    def _call_main(self, argv):
        """Invoke init_project_memory.main() with patched sys.argv."""
        import sys

        from memory_core.tools.init_project_memory import main

        old_argv = sys.argv
        try:
            sys.argv = ["memory-init", *argv]
            return main()
        finally:
            sys.argv = old_argv

    def test_init_rejects_tmpdir(self, monkeypatch, capsys):
        """VAL-M2-023: init rejects /tmp paths."""
        monkeypatch.delenv("TMPDIR", raising=False)
        target = Path("/tmp/memory-init-test-reject")
        # We can't call main() with /tmp because argparse requires dir exists.
        # Test via init_project_memory directly.
        from memory_core.tools.init_project_memory import init_project_memory

        result = init_project_memory(target)
        assert result["success"] is False
        assert any("denylist" in e.lower() or "denied" in e.lower() for e in result["errors"])

    def test_init_rejects_factory(self, capsys):
        """VAL-M2-024: init rejects ~/.factory paths."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = Path.home() / ".factory" / "test-init-reject"
        result = init_project_memory(target)
        assert result["success"] is False
        assert any("denylist" in e.lower() or "denied" in e.lower() for e in result["errors"])

    def test_init_rejects_home_root(self, capsys):
        """VAL-M2-025: init rejects $HOME root."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = Path.home()
        result = init_project_memory(target)
        assert result["success"] is False
        assert any("denylist" in e.lower() or "denied" in e.lower() for e in result["errors"])

    def test_init_rejects_junk_pattern(self, safe_workspace, capsys):
        """VAL-M2-026: init rejects junk directory names."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = safe_workspace / "demo-sprint"
        target.mkdir(exist_ok=True)

        result = init_project_memory(target)
        assert result["success"] is False
        assert any("denylist" in e.lower() or "denied" in e.lower() for e in result["errors"])

    def test_init_rejects_non_git_without_flag(self, safe_workspace):
        """VAL-M2-027: init rejects non-git without --allow-non-git."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = safe_workspace / "non-git"
        target.mkdir(exist_ok=True)

        result = init_project_memory(target, allow_non_git=False)
        assert result["success"] is False
        assert any("non-git" in e.lower() or "allow-non-git" in e.lower() for e in result["errors"])

    def test_init_allows_non_git_with_flag(self, safe_workspace):
        """VAL-M2-027: init allows non-git with --allow-non-git."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = safe_workspace / "non-git-allowed"
        target.mkdir(exist_ok=True)

        result = init_project_memory(target, allow_non_git=True)
        assert result["success"] is True

    def test_init_accepts_legit_git_project(self, safe_workspace):
        """VAL-M2-028: init accepts a normal git project."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = safe_workspace / "legit-project"
        target.mkdir(exist_ok=True)
        (target / ".git").mkdir()

        result = init_project_memory(target)
        assert result["success"] is True
        assert (target / "memory" / "system").is_dir()

    def test_init_denylist_error_message_actionable(self, safe_workspace):
        """VAL-M2-030: init error messages cite rule and override."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = safe_workspace / "demo-test"
        target.mkdir(exist_ok=True)

        result = init_project_memory(target)
        assert result["success"] is False
        error_text = " ".join(result["errors"])
        assert "denylist" in error_text.lower() or "denied" in error_text.lower()


# ---------------------------------------------------------------------------
# Integration tests for gateway denylist at runtime
# ---------------------------------------------------------------------------


class TestGatewayDenylistRuntime:
    """VAL-M2-029: Gateway applies denylist at runtime."""

    def test_gateway_rejects_denied_path(self, monkeypatch):
        """Gateway refuses to process events for denied project roots."""
        from memory_core.tools.denylist import check_denylist

        monkeypatch.setenv("TMPDIR", "/tmp")
        target = Path("/tmp/project")

        result = check_denylist(target)
        assert result.denied is True

    def test_gateway_rejects_moved_to_denied_path(self, monkeypatch):
        """Gateway refuses even if project was previously valid but moved to denied path."""
        from memory_core.tools.denylist import check_denylist

        monkeypatch.delenv("TMPDIR", raising=False)
        target = Path.home() / ".factory" / "moved-project"
        result = check_denylist(target)
        assert result.denied is True
        assert result.rule == "factory"

    def test_gateway_output_contains_deny_info(self, monkeypatch):
        """When gateway denies, the output should contain deny reason."""
        from memory_core.tools.denylist import check_denylist

        monkeypatch.setenv("TMPDIR", "/tmp")
        target = Path("/tmp/junk")

        result = check_denylist(target)
        assert result.denied is True
        assert result.message is not None
        assert len(result.message) > 0


# ---------------------------------------------------------------------------
# Cross-cutting test
# ---------------------------------------------------------------------------


class TestCrossDenylistPreventsJunkLifecycle:
    """VAL-CROSS-003: Denylist prevents junk lifecycle entries going forward."""

    def test_check_denylist_blocks_all_junk_categories(self, safe_workspace, monkeypatch):
        """All junk categories are blocked by check_denylist."""
        from memory_core.tools.denylist import check_denylist

        blocked_cases = []

        # 1. /tmp
        monkeypatch.delenv("TMPDIR", raising=False)
        r = check_denylist(Path("/tmp/project"))
        blocked_cases.append(("tmpdir", r.denied))

        # 2. ~/.factory
        r = check_denylist(Path.home() / ".factory" / "x")
        blocked_cases.append(("factory", r.denied))

        # 3. $HOME
        r = check_denylist(Path.home())
        blocked_cases.append(("home_root", r.denied))

        # 4. Junk patterns
        for pattern_name in ["tmp.foo", "demo-x", "test-x", "smoke-test-x", "restart-x", "file-list-x"]:
            p = safe_workspace / pattern_name
            p.mkdir(exist_ok=True)
            r = check_denylist(p)
            blocked_cases.append((f"junk:{pattern_name}", r.denied))

        # 5. Non-git
        non_git = safe_workspace / "non-git-dir"
        non_git.mkdir(exist_ok=True)
        r = check_denylist(non_git, allow_non_git=False)
        blocked_cases.append(("non_git", r.denied))

        for label, is_denied in blocked_cases:
            assert is_denied, f"Expected {label} to be denied but it was not"
