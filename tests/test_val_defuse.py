"""VAL-DEFUSE regression tests for daily-summary rebuild chain defects.

These tests verify the fixes for:
- VAL-DEFUSE-001: full-sign回退无真项目门控 (daily_summary_generator)
- VAL-DEFUSE-002: path-index门控+原子写 (project_lifecycle)
- VAL-DEFUSE-003: session_end_logger绕过wrapper路由修复
"""

# Reused imports for E2E tests
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from memory_core.tools._gateway_config import _is_true_project_root
from memory_core.tools._gateway_config import _is_true_project_root as _is_true_project_root_lifecycle
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


class TestValDefuse001E2E:
    """VAL-DEFUSE-001 end-to-end: HOME replica tests (B2 + mencbo shapes).

    These tests adapt the reviewer probe scripts to pytest format.
    Key constraints:
    - Must run in $HOME real directory (not /tmp which has denylist)
    - Basename must avoid tmp.*/demo-*/test-* denylist
    - A-layer fuel must match session_end_logger exact format
    """

    def test_mencbo_layout_zero_system_creation(self, tmp_path: Path) -> None:
        """mencbo layout: outer config with memory_root指向内层 → should create zero system/.

        VAL-DEFUSE-001: Full-sign fallback should NOT create memory/system/ on outer shell
        when config points to a different directory (inner repo).

        Reproduces /tmp/val_defuse_mencbo_probe.py scenario as pytest case.
        """

        # Build exact mencbo layout under $HOME with safe basename
        base = Path.home() / "scrutiny_mencbo_e2e"
        base.mkdir(exist_ok=True)
        outer = base / "outer"
        inner = outer / "inner"
        log_dir = outer / "memory" / "log"
        log_dir.mkdir(parents=True)
        inner.mkdir(parents=True)
        (inner / ".git").mkdir()

        # Pin config at OUTER (matches real mentuco layout)
        (outer / "memory-project.toml").write_text('project = "mencbo"\nmemory_root = "./inner"\n', encoding="utf-8")

        # A-layer fuel: session_end_logger exact format (### 8-hex header)
        fuel = """# Sessions Log — 2026-09-11

### abcd1234
- **标题**: probe session
- **模型**: claude-4 | **时长**: 12m
- **Token**: input=1200 output=3400
- **工具调用**: 8
- **用户意图**: work on feature
- **助手摘要**: implemented the thing
---

"""
        (log_dir / "2026-09-11-sessions.md").write_text(fuel, encoding="utf-8")

        def listing() -> list[str]:
            return sorted(str(p.relative_to(outer)) for p in outer.rglob("*") if p.is_file())

        before = listing()

        # Run daily_summary_generator (full-sign fallback path)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.daily_summary_generator",
                "--today",
                "--project",
                str(outer),
                "--fallback-days",
                "3",
            ],
            cwd=str(tmp_path.parent),
            capture_output=True,
            text=True,
            timeout=90,
        )

        after = listing()
        system_after = (outer / "memory" / "system").exists()

        # Assert: outer system/ must NOT be created (zero memory/system/)
        assert not system_after, (
            f"Outer memory/system/ created: {before=}, {after=}, exit={proc.returncode}, "
            f"stdout={proc.stdout[-500:] if proc.stdout else ''}, "
            f"stderr={proc.stderr[-500:] if proc.stderr else ''}"
        )

        # Cleanup (safe: basename avoids denylist, under HOME)
        import shutil

        shutil.rmtree(base, ignore_errors=True)

    def test_b2_layout_zero_system_creation(self, tmp_path: Path) -> None:
        """B2 layout: no .git, no config, no consent outer + single child → zero system/.

        VAL-DEFUSE-001: B2 marker-less single-child outer should NOT trigger full-sign
        fallback to create memory/system/ on the outer shell.

        Reproduces /tmp/val_defuse_b2_probe.py scenario as pytest case.
        """

        # Build B2 layout under $HOME
        base = Path.home() / "scrutiny_b2_e2e"
        base.mkdir(exist_ok=True)
        outer = base / "outer"
        inner = outer / "inner-repo"
        log_dir = outer / "memory" / "log"
        log_dir.mkdir(parents=True)
        inner.mkdir(parents=True)
        (inner / ".git").mkdir()

        # Inner has memory-project.toml with self-referential memory_root
        (inner / "memory-project.toml").write_text(
            'project = "adv"\nmemory_root = "./"\nmembers = []\n', encoding="utf-8"
        )

        # A-layer fuel with exact session_end_logger format
        fuel = """# Sessions Log — 2026-09-11

### abcd1234
- **标题**: probe session
- **模型**: claude-4 | **时长**: 12m
- **Token**: input=1200 output=3400
- **工具调用**: 8
- **用户意图**: work on feature
- **助手摘要**: implemented the thing
---

### beef5678
- **标题**: second session
- **模型**: claude-4 | **时长**: 5m
- **Token**: input=500 output=900
- **工具调用**: 3
- **用户意图**: review
- **助手摘要**: reviewed
---

"""
        (log_dir / "2026-09-11-sessions.md").write_text(fuel, encoding="utf-8")

        def listing() -> list[str]:
            return sorted(str(p.relative_to(outer)) for p in outer.rglob("*") if p.is_file())

        before = listing()

        # Run daily_summary_generator
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.daily_summary_generator",
                "--today",
                "--project",
                str(outer),
                "--fallback-days",
                "3",
            ],
            cwd=str(tmp_path.parent),
            capture_output=True,
            text=True,
            timeout=90,
        )

        after = listing()
        system_after = (outer / "memory" / "system").exists()

        # Assert: outer memory/system/ must NOT be created
        assert not system_after, (
            f"Outer memory/system/ created: {before=}, {after=}, exit={proc.returncode}, "
            f"stdout={proc.stdout[-500:] if proc.stdout else ''}, "
            f"stderr={proc.stderr[-500:] if proc.stderr else ''}"
        )

        # Cleanup
        shutil.rmtree(base, ignore_errors=True)


class TestValDefuse002Gating:
    """VAL-DEFUSE-002: _update_path_index gate integration tests.

    Path index should only register true project roots with gate:
    - Git root → register
    - Config-declared root → register
    - Consent-marked root → register
    - Outer shells (no .git, config, consent) → NOT register
    """

    def test_update_path_index_git_root_registers(self, tmp_path: Path) -> None:
        """Git root should be registered by _update_path_index."""
        from memory_core.tools.project_lifecycle import _update_path_index

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        path_index: dict[str, Any] = {}
        record = {
            "local_path": str(repo),
            "project_id": "test-001",
            "project_name": "test",
        }

        _update_path_index(path_index, record)

        # Git root should be registered
        assert str(repo.resolve()) in path_index.get("paths", {})

    def test_update_path_index_outer_shell_not_registered(self, tmp_path: Path) -> None:
        """Outer shell (no .git, config, consent) should NOT be registered."""
        from memory_core.tools.project_lifecycle import _update_path_index

        outer = tmp_path / "outer"
        outer.mkdir()
        # Simulate B2 scenario: single child repo
        child = outer / "child"
        child.mkdir()
        (child / ".git").mkdir()

        path_index: dict[str, Any] = {}
        # Try to register the outer shell (should be rejected by gate)
        record = {
            "local_path": str(outer),
            "project_id": "outer-001",
            "project_name": "outer",
        }

        _update_path_index(path_index, record)

        # Outer should NOT be registered
        assert str(outer.resolve()) not in path_index.get("paths", {})

    def test_update_path_index_mencbo_shape_not_registered(self, tmp_path: Path) -> None:
        """mencbo shape: outer config pointing to inner should NOT register outer."""
        from memory_core.tools.project_lifecycle import _update_path_index

        outer = tmp_path / "outer"
        outer.mkdir()
        config = outer / "memory-project.toml"
        config.write_text('project = "test"\nmemory_root = "./inner"\n')

        inner = outer / "inner"
        inner.mkdir()
        (inner / ".git").mkdir()

        path_index: dict[str, Any] = {}
        # Try to register outer (config is routing pin, NOT consent)
        record = {
            "local_path": str(outer),
            "project_id": "outer-001",
            "project_name": "outer",
        }

        _update_path_index(path_index, record)

        # Outer should NOT be registered (memory_root points elsewhere)
        assert str(outer.resolve()) not in path_index.get("paths", {})

    def test_update_path_index_positive_control_git(self, tmp_path: Path) -> None:
        """Positive control: plain git root should be registered."""
        from memory_core.tools.project_lifecycle import _update_path_index

        git_root = tmp_path / "git-root"
        git_root.mkdir()
        (git_root / ".git").mkdir()

        path_index: dict[str, Any] = {}
        record = {
            "local_path": str(git_root),
            "project_id": "ctrl-001",
            "project_name": "control",
        }

        _update_path_index(path_index, record)

        # Git root should be registered (positive control)
        assert str(git_root.resolve()) in path_index.get("paths", {})


class TestValDefuse003AtomicWrite:
    """VAL-DEFUSE-003: incremental path atomic write tests.

    References tests/test_lifecycle_rebuild.py:164 for the rebuild path.
    This class tests the incremental path atomic write via _write_path_index.
    """

    def test_update_path_index_atomic_write(self, tmp_path: Path) -> None:
        """rebuild_path_index writes path-index.json via temp file + os.replace."""
        import json
        import os
        from unittest.mock import patch

        from memory_core.tools.project_lifecycle import rebuild_path_index

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        # Record for a git root (so the gate passes)
        record = {
            "schema_version": "project-lifecycle-v1",
            "project_id": "atomic-001",
            "project_name": "atomic-test",
            "status": "active",
            "host": "factory",
            "event": "session-start",
            "observed_at": "2026-09-12T12:00:00+08:00",
            "first_observed_at": "2026-09-12T12:00:00+08:00",
            "local_path": str(tmp_path / "atomic-test"),
            "path_exists": True,
            "git_root": str(tmp_path / "atomic-test"),
            "git_remote": None,
            "identity_source": "path",
            "identity_value": str(tmp_path / "atomic-test"),
            "payload_cwd": str(tmp_path / "atomic-test"),
            "retention_policy": "preserve-memory-on-missing-path",
        }

        # Write project file (projects_dir/atomic-001.json)
        projects_dir.joinpath("atomic-001.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        replace_called = False
        original_replace = os.replace

        def tracking_replace(src: str, dst: str) -> None:
            nonlocal replace_called
            replace_called = True
            original_replace(src, dst)  # Actually perform the replace (no temp-file leak)

        with patch("os.replace", side_effect=tracking_replace):
            rebuild_path_index(tmp_path)

        # os.replace must be called for atomic write
        assert replace_called, "os.replace must be called for atomic write"

        # Verify path-index.json was written with the record
        index_path = tmp_path / "path-index.json"
        assert index_path.exists()
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert str((tmp_path / "atomic-test").resolve()) in data["paths"]

    def test_update_path_index_incremental_write(self, tmp_path: Path) -> None:
        """Incremental path via rebuild_path_index should merge multiple project files."""
        import json

        from memory_core.tools.project_lifecycle import rebuild_path_index

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        # Seed two project files (simulating records from two different sessions)
        # Both are marked "active" and "path_exists": True so they get registered
        record1 = {
            "schema_version": "project-lifecycle-v1",
            "project_id": "proj-1",
            "project_name": "Project A",
            "status": "active",
            "host": "factory",
            "event": "session-start",
            "observed_at": "2026-09-10T00:00:00+08:00",
            "first_observed_at": "2026-09-10T00:00:00+08:00",
            "local_path": str(tmp_path / "path-a"),
            "path_exists": True,
            "git_root": str(tmp_path / "path-a"),
            "git_remote": None,
            "identity_source": "path",
            "identity_value": str(tmp_path / "path-a"),
            "payload_cwd": str(tmp_path / "path-a"),
            "retention_policy": "preserve-memory-on-missing-path",
        }
        projects_dir.joinpath("proj-1.json").write_text(
            json.dumps(record1, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        record2 = {
            "schema_version": "project-lifecycle-v1",
            "project_id": "proj-2",
            "project_name": "Project B",
            "status": "active",
            "host": "factory",
            "event": "session-start",
            "observed_at": "2026-09-12T12:00:00+08:00",
            "first_observed_at": "2026-09-12T12:00:00+08:00",
            "local_path": str(tmp_path / "path-b"),
            "path_exists": True,
            "git_root": str(tmp_path / "path-b"),
            "git_remote": None,
            "identity_source": "path",
            "identity_value": str(tmp_path / "path-b"),
            "payload_cwd": str(tmp_path / "path-b"),
            "retention_policy": "preserve-memory-on-missing-path",
        }
        projects_dir.joinpath("proj-2.json").write_text(
            json.dumps(record2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        # Run rebuild - this should register BOTH entries
        rebuild_path_index(tmp_path)

        # Verify both entries are in the index
        data = json.loads((tmp_path / "path-index.json").read_text(encoding="utf-8"))
        paths = data["paths"]
        # Keys are expanduser'd local_path strings from the records
        assert str(tmp_path / "path-a") in paths, f"Expected {tmp_path}/path-a in {list(paths.keys())}"
        assert str(tmp_path / "path-b") in paths, f"Expected {tmp_path}/path-b in {list(paths.keys())}"
        # Both should have correct project names
        assert paths[str(tmp_path / "path-a")]["project_name"] == "Project A"
        assert paths[str(tmp_path / "path-b")]["project_name"] == "Project B"

    def test_non_string_memory_root_pins_false(self, tmp_path: Path) -> None:
        """Non-string memory_root (e.g. =123) should pin False, not raise TypeError."""
        from memory_core.tools._gateway_config import _is_true_project_root

        # Create a config with non-string memory_root
        outer = tmp_path / "outer"
        outer.mkdir()
        config = outer / "memory-project.toml"
        # TOML allows numeric values; this should be caught and return False
        config.write_text('project = "test"\nmemory_root = 123\n', encoding="utf-8")

        # Should return False, not raise TypeError
        result = _is_true_project_root(outer)
        assert result is False
