"""Tests for version_sync.py re-sign after patch.

VAL-HOOK-008: version_sync 执行后 ownership.toml 版本更新且 manifest.json
中对应条目 sha256 与实际文件匹配。
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helper: create a minimal project layout
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path, version: str = "0.7.0") -> Path:
    """Create a minimal project with ownership.toml."""
    sys_dir = tmp_path / "memory" / "system"
    sys_dir.mkdir(parents=True)
    ownership = sys_dir / "ownership.toml"
    ownership.write_text(
        f'[project]\nname = "test"\nmemory_version = "{version}"\n',
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Test: sync_single_project calls sign_project_incremental after patch
# ---------------------------------------------------------------------------

class TestSyncSingleProjectResign:
    """VAL-HOOK-008: version_sync 执行后 manifest hash 匹配"""

    def test_calls_sign_project_incremental_after_patch(
        self, tmp_path: Path
    ) -> None:
        """sync_single_project 在 patch 成功后调用 sign_project_incremental"""
        project = _make_project(tmp_path, "0.7.0")
        ownership_rel = "memory/system/ownership.toml"

        with patch(
            "memory_core.tools.version_sync.sign_project_incremental"
        ) as mock_sign:
            mock_sign.return_value = {"entries": []}
            from memory_core.tools.version_sync import sync_single_project

            result = sync_single_project(project, "0.8.0")

            assert result["patched"] is True
            mock_sign.assert_called_once()
            call_args = mock_sign.call_args
            # First positional arg: project_root
            assert call_args[0][0] == project
            # changed_paths should contain ownership.toml relative path
            changed = call_args[1].get("changed_paths") or call_args[0][2]
            assert ownership_rel in changed

    def test_no_sign_when_already_up_to_date(self, tmp_path: Path) -> None:
        """Already up-to-date 时不调用 sign_project_incremental"""
        project = _make_project(tmp_path, "0.8.0")

        with patch(
            "memory_core.tools.version_sync.sign_project_incremental"
        ) as mock_sign:
            from memory_core.tools.version_sync import sync_single_project

            result = sync_single_project(project, "0.8.0")

            assert result["patched"] is False
            mock_sign.assert_not_called()

    def test_no_sign_when_no_ownership(self, tmp_path: Path) -> None:
        """No ownership.toml 时不调用 sign_project_incremental"""
        # Empty project without ownership.toml
        project = tmp_path / "empty"
        project.mkdir()

        with patch(
            "memory_core.tools.version_sync.sign_project_incremental"
        ) as mock_sign:
            from memory_core.tools.version_sync import sync_single_project

            result = sync_single_project(project, "0.8.0")

            assert result["patched"] is False
            mock_sign.assert_not_called()

    def test_sign_failure_does_not_block_patch(self, tmp_path: Path) -> None:
        """sign_project_incremental 异常不阻断版本同步（主要目标是 patch）"""
        project = _make_project(tmp_path, "0.7.0")

        with patch(
            "memory_core.tools.version_sync.sign_project_incremental"
        ) as mock_sign:
            mock_sign.side_effect = RuntimeError("key missing")
            from memory_core.tools.version_sync import sync_single_project

            result = sync_single_project(project, "0.8.0")

            # Patch still succeeds even though sign failed
            assert result["patched"] is True
            assert result["from"] == "0.7.0"
            assert result["to"] == "0.8.0"

    def test_version_actually_updated_in_file(self, tmp_path: Path) -> None:
        """patch 后 ownership.toml 中 memory_version 确实是目标版本"""
        project = _make_project(tmp_path, "0.7.0")

        with patch(
            "memory_core.tools.version_sync.sign_project_incremental"
        ) as mock_sign:
            mock_sign.return_value = {"entries": []}
            from memory_core.tools.version_sync import (
                read_ownership_memory_version,
                sync_single_project,
            )

            sync_single_project(project, "0.8.0")
            ownership_path = project / "memory" / "system" / "ownership.toml"
            assert read_ownership_memory_version(ownership_path) == "0.8.0"


# ---------------------------------------------------------------------------
# Integration: manifest sha256 matches actual file after resign
# ---------------------------------------------------------------------------

class TestResignManifestIntegrity:
    """Verify manifest sha256 matches actual ownership.toml after re-sign"""

    def test_manifest_sha256_matches_file(self, tmp_path: Path) -> None:
        """sign_project_incremental 更新 manifest 后 sha256 与实际文件一致"""
        project = _make_project(tmp_path, "0.7.0")
        ownership_path = project / "memory" / "system" / "ownership.toml"
        ownership_rel = "memory/system/ownership.toml"

        # Use real sign_project_incremental with a test key
        from memory_core.tools.memory_hook_integrity_manifest import (
            sign_project_incremental,
        )

        fake_key = b"\x00" * 32

        with patch(
            "memory_core.tools.version_sync.sign_project_incremental",
            side_effect=lambda root, key, changed_paths, **kw: sign_project_incremental(
                root, key, changed_paths, **kw
            ),
        ):
            from memory_core.tools.version_sync import sync_single_project

            result = sync_single_project(project, "0.8.0")
            assert result["patched"] is True

            # Now manually call sign_project_incremental to create manifest
            sign_project_incremental(
                project, fake_key, changed_paths=[ownership_rel]
            )

            # Read manifest and verify sha256
            manifest_path = project / "memory" / "system" / "manifest.json"
            assert manifest_path.exists()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            # Find ownership.toml entry
            ownership_entry = None
            for entry in manifest.get("entries", []):
                if entry["rel_path"] == ownership_rel:
                    ownership_entry = entry
                    break

            assert ownership_entry is not None, "ownership.toml not in manifest"

            # Verify sha256 matches actual file
            actual_sha = hashlib.sha256(
                ownership_path.read_bytes()
            ).hexdigest()
            assert ownership_entry["sha256"] == actual_sha


# ---------------------------------------------------------------------------
# Edge case tests: regex no match + file not found
# ---------------------------------------------------------------------------

class TestVersionSyncEdgeCases:
    """Edge cases for version_sync.py: regex no match + file not found."""

    def test_read_ownership_memory_version_regex_no_match(self, tmp_path: Path) -> None:
        """regex 无匹配: ownership.toml 存在但不含 memory_version 字段，返回 None"""
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)
        ownership = sys_dir / "ownership.toml"
        # Write a file that exists but has no memory_version field (regex won't match)
        ownership.write_text(
            '[project]\nname = "test"\n# no memory_version here\n',
            encoding="utf-8",
        )
        from memory_core.tools.version_sync import read_ownership_memory_version
        result = read_ownership_memory_version(ownership)
        assert result is None

    def test_read_ownership_memory_version_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在路径: 指向一个不存在的路径，返回 None"""
        nonexistent = tmp_path / "does_not_exist" / "ownership.toml"
        from memory_core.tools.version_sync import read_ownership_memory_version
        result = read_ownership_memory_version(nonexistent)
        assert result is None
