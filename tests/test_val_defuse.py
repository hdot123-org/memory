"""VAL-DEFUSE regression tests for daily-summary rebuild chain defects.

These tests verify the fixes for:
- VAL-DEFUSE-001: full-sign回退无真项目门控 (daily_summary_generator)
- VAL-DEFUSE-002: path-index门控+原子写 (project_lifecycle)
- VAL-DEFUSE-003: session_end_logger绕过wrapper路由修复
"""

from pathlib import Path
from typing import Any

from memory_core.tools.daily_summary_generator import _is_true_project_root
from memory_core.tools.project_lifecycle import _is_true_project_root as _is_true_project_root_lifecycle
from memory_core.tools.session_end_logger import _resolve_project_root


class TestValDefuse001:
    """VAL-DEFUSE-001: full-sign回退无真项目门控.

    Daily summary generator should skip signing for non-project roots
    (directories without .git, memory-project.toml, or consent marker).
    """

    def test_is_true_project_root_git_repo(self, tmp_path: Path) -> None:
        """Git repo root should be recognized as true project root."""
        repo_root = tmp_path / "git-repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        assert _is_true_project_root(repo_root) is True

    def test_is_true_project_root_no_git_no_config(self, tmp_path: Path) -> None:
        """Directory without .git, config, or consent should NOT be true project root."""
        outer_shell = tmp_path / "outer"
        outer_shell.mkdir()
        # Create some log files (simulating the adversarial probe B2 scenario)
        (outer_shell / "session.log").write_text("test")

        # Should be False since no .git, config, or consent
        assert _is_true_project_root(outer_shell) is False

    def test_is_true_project_root_with_config(self, tmp_path: Path) -> None:
        """Directory with memory-project.toml should be true project root."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        config = project_root / "memory-project.toml"
        config.write_text('project = "test"\nmemory_root = "."')

        assert _is_true_project_root(project_root) is True

    def test_is_true_project_root_with_consent(self, tmp_path: Path) -> None:
        """Directory with consent marker (allow_non_git=true) should be true project root."""
        outer = tmp_path / "outer"
        outer.mkdir()
        system_dir = outer / "memory" / "system"
        system_dir.mkdir(parents=True)
        ownership = system_dir / "ownership.toml"
        ownership.write_text("[policy]\nallow_non_git = true")

        assert _is_true_project_root(outer) is True

    def test_outer_config_routing_pin_not_true_root(self, tmp_path: Path) -> None:
        """Outer layer with memory_root pointing to inner should NOT be true root.

        VAL-DEFUSE-001: Outer shell config with memory_root指向内层 = routing pin ≠ sign-consent.
        The predicate must reject outer because resolved root ≠ outer.
        """
        # Outer layer (no .git, has config pointing to inner)
        outer = tmp_path / "outer"
        outer.mkdir()
        config = outer / "memory-project.toml"
        # memory_root指向内层，这是路由指针，不是同意
        config.write_text('project = "test"\nmemory_root = "./inner"')

        # Inner layer (has .git)
        inner = outer / "inner"
        inner.mkdir()
        (inner / ".git").mkdir()

        # Outer should be False - config points elsewhere, not self-referential
        assert _is_true_project_root(outer) is False

        # Inner should be True - has .git
        assert _is_true_project_root(inner) is True


class TestValDefuse002:
    """VAL-DEFUSE-002: path-index门控+原子写.

    Path index should only register true project roots and use atomic writes.
    """

    def test_is_true_project_root_lifecycle_git_repo(self, tmp_path: Path) -> None:
        """Lifecycle helper should recognize git repo roots."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        assert _is_true_project_root_lifecycle(repo_root) is True

    def test_is_true_project_root_lifecycle_no_git(self, tmp_path: Path) -> None:
        """Non-git outer shells should not be registered in path index."""
        outer = tmp_path / "outer"
        outer.mkdir()
        # Create a log file (simulating the adversarial probe B2 scenario)
        # but NOT memory/system (no consent marker)
        (outer / "session.log").write_text("test data")

        # Without .git, config, or consent, should be False
        assert _is_true_project_root_lifecycle(outer) is False

    def test_outer_no_marker_single_child_refinement_not_true_root(self, tmp_path: Path) -> None:
        """No .git, config, consent outer + single child → still NOT true root.

        VAL-DEFUSE-002: B-layer单子仓精炼宽松分支放过无标记外层 = 计划外失效。
        The predicate must NOT use B-layer refinement result for gating.
        Even if gateway would refine outer→inner, outer itself is not true root.
        """
        # Outer layer (no .git, no config, no consent)
        outer = tmp_path / "outer"
        outer.mkdir()
        # Simulate B2 scenario: single child repo inside outer
        inner = outer / "repo"
        inner.mkdir()
        (inner / ".git").mkdir()

        # Outer should be False - no .git, no config, no consent of its own
        assert _is_true_project_root_lifecycle(outer) is False

        # Inner should be True - has .git
        assert _is_true_project_root_lifecycle(inner) is True


class TestValDefuse003:
    """VAL-DEFUSE-003: session_end_logger绕过wrapper路由修复.

    Session end logger should use gateway's root resolution, not payload cwd directly.
    """

    def test_resolve_project_root_uses_gateway_resolution(self, tmp_path: Path) -> None:
        """When gateway resolution available, outer cwd should resolve to inner repo root."""
        # Create nested layout: outer (no git) + inner (git repo)
        outer = tmp_path / "outer"
        inner = outer / "repo"
        inner.mkdir(parents=True)
        (inner / ".git").mkdir()

        # Payload cwd points to outer (non-git shell)
        payload_cwd = outer
        stdin_payload: dict[str, Any] = {}

        resolved = _resolve_project_root(payload_cwd, stdin_payload)

        # Gateway resolution should find the inner git repo
        assert resolved == inner

    def test_resolve_project_root_fallback(self, tmp_path: Path) -> None:
        """When gateway resolution unavailable, fallback to cwd."""
        # Temporarily disable gateway
        import memory_core.tools.session_end_logger as sel

        original = sel._gateway_resolve_root
        sel._gateway_resolve_root = None

        try:
            test_dir = tmp_path / "test"
            test_dir.mkdir()

            resolved = _resolve_project_root(test_dir, {})

            assert resolved == test_dir.resolve()
        finally:
            sel._gateway_resolve_root = original
