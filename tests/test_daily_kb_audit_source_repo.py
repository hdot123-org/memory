"""Tests for daily_kb_audit.py source repo version check skip.

VAL-HOOK-009: daily_kb_audit 对 memory-core 源仓库不再报 version_mismatch 违规。
"""

from pathlib import Path
from unittest.mock import patch

from memory_core.tools.daily_kb_audit import (
    audit_project,
)


class TestSourceRepoVersionCheckSkip:
    """Source repo should skip _c5 (check_version_consistency)."""

    def test_source_repo_skips_version_check(self, tmp_path: Path) -> None:
        """When is_source_repo is True, _c5 should NOT be in the checks list."""
        # Create a fake project with memory_core markers so is_source_repo = True
        memory_core_dir = tmp_path / "memory_core" / "tools"
        memory_core_dir.mkdir(parents=True)
        (memory_core_dir / "memory_hook_gateway.py").touch()
        (memory_core_dir / "factory_global_hooks.py").touch()
        ownership_py = tmp_path / "memory_core" / "ownership.py"
        ownership_py.touch()

        # Create a manifest.json to avoid check 1 noise
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text('{"entries": []}')

        # Patch check_version_consistency to track if it's called
        with patch(
            "memory_core.tools.daily_kb_audit.check_version_consistency"
        ) as mock_c5:
            mock_c5.return_value = []

            audit_project("test-project", tmp_path, {})

            # For source repo, _c5 should NOT be called
            mock_c5.assert_not_called()

    def test_non_source_repo_runs_version_check(self, tmp_path: Path) -> None:
        """When is_source_repo is False, _c5 SHOULD be called."""
        # No memory_core markers → is_source_repo = False
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text('{"entries": []}')

        with patch(
            "memory_core.tools.daily_kb_audit.check_version_consistency"
        ) as mock_c5:
            mock_c5.return_value = []

            audit_project("consumer-project", tmp_path, {})

            # For non-source repo, _c5 SHOULD be called
            mock_c5.assert_called_once_with(tmp_path)

    def test_source_repo_no_version_mismatch_violation(self, tmp_path: Path) -> None:
        """Source repo should have zero version_mismatch violations."""
        # Create markers for source repo detection
        memory_core_dir = tmp_path / "memory_core" / "tools"
        memory_core_dir.mkdir(parents=True)
        (memory_core_dir / "memory_hook_gateway.py").touch()
        (memory_core_dir / "factory_global_hooks.py").touch()
        (tmp_path / "memory_core" / "ownership.py").touch()

        # Create manifest
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text('{"entries": []}')

        result = audit_project("memory-core", tmp_path, {})

        # No version_mismatch violations should exist
        version_violations = [
            v for v in result["violations"]
            if v.get("type") == "version_mismatch"
        ]
        assert len(version_violations) == 0

    def test_source_repo_has_note(self, tmp_path: Path) -> None:
        """Source repo result should have a note about skipped checks."""
        # Create markers
        memory_core_dir = tmp_path / "memory_core" / "tools"
        memory_core_dir.mkdir(parents=True)
        (memory_core_dir / "memory_hook_gateway.py").touch()
        (memory_core_dir / "factory_global_hooks.py").touch()
        (tmp_path / "memory_core" / "ownership.py").touch()

        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text('{"entries": []}')

        result = audit_project("memory-core", tmp_path, {})

        assert "note" in result
        assert "源仓库" in result["note"]
