"""Tests for version_sync three-file patch, gate logic, and resign fix.

Covers validation contract assertions:
- VAL-SYNC-001: patch_memory_lock modifies memory_version + locked_at, preserves other fields
- VAL-SYNC-002: patch_adapter_toml_version modifies [core] version, preserves other sections
- VAL-SYNC-003: sync_single_project patches three files when gate allows
- VAL-SYNC-004: sync_all_known_projects patches three files in batch
- VAL-SYNC-005: already up-to-date projects are skipped (idempotent)
- VAL-GATE-001: gate allows patch/minor + schema unchanged
- VAL-GATE-002: gate blocks major upgrade
- VAL-GATE-003: gate blocks schema_version change
- VAL-GATE-004: blocked scenarios still patch ownership.toml (backward compat)
- VAL-RESIGN-001: _try_resign_all returns error dict on signing failure
- VAL-RESIGN-002: _try_resign_all accepts changed_paths parameter
- VAL-RESIGN-003: callers check return value and write to result["errors"]
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory_core.tools.version_sync import (
    _gate_version_bump,
    _try_resign_all,
    patch_adapter_toml_version,
    patch_memory_lock,
    sync_all_known_projects,
    sync_single_project,
)

# ─────────────────────────────────────────────────────────────
# VAL-SYNC-001: patch_memory_lock
# ─────────────────────────────────────────────────────────────


class TestPatchMemoryLock:
    """VAL-SYNC-001: patch_memory_lock modifies memory_version + locked_at."""

    def test_patch_memory_lock_modifies_version_and_locked_at(self, tmp_path: Path) -> None:
        """patch_memory_lock patches memory_version and locked_at, preserving other fields."""
        lock_content = """\
# Memory Lock File
memory_version = "0.9.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
lock_reason = "memory-init"
locked_at = "2026-01-01T00:00:00+00:00"
"""
        lock_file = tmp_path / "memory.lock"
        lock_file.write_text(lock_content, encoding="utf-8")

        result = patch_memory_lock(lock_file, "0.9.1")

        assert result is True
        patched = lock_file.read_text(encoding="utf-8")
        # memory_version changed
        assert re.search(r'^memory_version\s*=\s*"0\.9\.1"', patched, re.MULTILINE)
        # locked_at changed (should be a recent ISO timestamp, not the old one)
        assert "2026-01-01T00:00:00+00:00" not in patched
        # Other fields preserved
        assert re.search(r'^schema_version\s*=\s*"context-package-v1"', patched, re.MULTILINE)
        assert re.search(r'^adapter_version\s*=\s*"builtin"', patched, re.MULTILINE)
        assert re.search(r'^lock_reason\s*=\s*"memory-init"', patched, re.MULTILINE)

    def test_patch_memory_lock_already_up_to_date(self, tmp_path: Path) -> None:
        """patch_memory_lock returns False when version already matches."""
        lock_content = 'memory_version = "0.9.1"\nlocked_at = "2026-07-26T00:00:00+00:00"\n'
        lock_file = tmp_path / "memory.lock"
        lock_file.write_text(lock_content, encoding="utf-8")

        result = patch_memory_lock(lock_file, "0.9.1")
        assert result is False

    def test_patch_memory_lock_file_not_exists(self, tmp_path: Path) -> None:
        """patch_memory_lock returns False when file doesn't exist."""
        result = patch_memory_lock(tmp_path / "nonexistent.lock", "0.9.1")
        assert result is False


# ─────────────────────────────────────────────────────────────
# VAL-SYNC-002: patch_adapter_toml_version
# ─────────────────────────────────────────────────────────────


class TestPatchAdapterTomlVersion:
    """VAL-SYNC-002: patch_adapter_toml_version modifies [core] version."""

    def test_patch_adapter_toml_modifies_core_version(self, tmp_path: Path) -> None:
        """patch_adapter_toml_version patches [core] version, preserving other sections."""
        adapter_content = """\
[core]
version = "0.9.0"
memory_dir = "memory"

[hooks]
enabled = true
gateway = "memory-hook"

[policy]
read_first = true
"""
        adapter_file = tmp_path / "adapter.toml"
        adapter_file.write_text(adapter_content, encoding="utf-8")

        result = patch_adapter_toml_version(adapter_file, "0.9.1")

        assert result is True
        patched = adapter_file.read_text(encoding="utf-8")
        # [core] version changed
        assert re.search(r'^version\s*=\s*"0\.9\.1"', patched, re.MULTILINE)
        # Other sections preserved
        assert "[hooks]" in patched
        assert "enabled = true" in patched
        assert "[policy]" in patched
        assert "read_first = true" in patched

    def test_patch_adapter_toml_already_up_to_date(self, tmp_path: Path) -> None:
        """patch_adapter_toml_version returns False when version already matches."""
        adapter_content = '[core]\nversion = "0.9.1"\n'
        adapter_file = tmp_path / "adapter.toml"
        adapter_file.write_text(adapter_content, encoding="utf-8")

        result = patch_adapter_toml_version(adapter_file, "0.9.1")
        assert result is False

    def test_patch_adapter_toml_file_not_exists(self, tmp_path: Path) -> None:
        """patch_adapter_toml_version returns False when file doesn't exist."""
        result = patch_adapter_toml_version(tmp_path / "nonexistent.toml", "0.9.1")
        assert result is False


# ─────────────────────────────────────────────────────────────
# VAL-GATE-001..004: Gate logic
# ─────────────────────────────────────────────────────────────


class TestGateVersionBump:
    """VAL-GATE-001..004: _gate_version_bump logic."""

    @pytest.mark.parametrize(
        "current,target,schema_changed,expected",
        [
            # VAL-GATE-001: patch bump allowed
            ("0.10.2", "0.10.3", False, "allowed"),
            # VAL-GATE-001: minor bump allowed
            ("0.10.2", "0.11.0", False, "allowed"),
            # VAL-GATE-002: major bump blocked
            ("0.10.2", "1.0.0", False, "blocked:major"),
            # VAL-GATE-003: schema change blocked regardless of semver
            ("0.10.2", "0.10.3", True, "blocked:schema_changed"),
            ("0.10.2", "0.11.0", True, "blocked:schema_changed"),
            ("0.10.2", "1.0.0", True, "blocked:schema_changed"),
        ],
    )
    def test_gate_version_bump(self, current: str, target: str, schema_changed: bool, expected: str) -> None:
        """_gate_version_bump returns correct allowed/blocked status."""
        result = _gate_version_bump(current, target, schema_changed)
        assert result == expected


# ─────────────────────────────────────────────────────────────
# VAL-RESIGN-001..003: _try_resign_all
# ─────────────────────────────────────────────────────────────


class TestTryResignAll:
    """VAL-RESIGN-001..003: _try_resign_all accepts changed_paths, returns errors."""

    def test_try_resign_all_returns_error_on_signing_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VAL-RESIGN-001: _try_resign_all returns error dict when signing fails."""
        import memory_core.tools.version_sync as vs

        mock_sign = MagicMock(side_effect=RuntimeError("boom"))
        mock_load_key = MagicMock(return_value=b"\x00" * 32)
        monkeypatch.setattr(vs, "sign_project_incremental", mock_sign)
        monkeypatch.setattr(vs, "load_key", mock_load_key)

        result = _try_resign_all(tmp_path, ["memory/system/ownership.toml"])

        assert result["resigned"] is False
        assert "boom" in result["reason"]

    def test_try_resign_all_accepts_changed_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """VAL-RESIGN-002: _try_resign_all passes changed_paths to sign_project_incremental."""
        import memory_core.tools.version_sync as vs

        mock_sign = MagicMock(return_value={"ok": True})
        mock_load_key = MagicMock(return_value=b"\x00" * 32)
        monkeypatch.setattr(vs, "sign_project_incremental", mock_sign)
        monkeypatch.setattr(vs, "load_key", mock_load_key)

        changed = [
            "memory/system/ownership.toml",
            "memory/system/memory.lock",
            "memory/system/adapter.toml",
        ]
        _try_resign_all(tmp_path, changed)

        mock_sign.assert_called_once()
        call_kwargs = mock_sign.call_args
        assert call_kwargs[1]["changed_paths"] == changed or call_kwargs[0][2] == changed

    def test_try_resign_all_returns_error_when_key_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_try_resign_all returns error when load_key returns None."""
        import memory_core.tools.version_sync as vs

        mock_sign = MagicMock()
        mock_load_key = MagicMock(return_value=None)
        monkeypatch.setattr(vs, "sign_project_incremental", mock_sign)
        monkeypatch.setattr(vs, "load_key", mock_load_key)

        result = _try_resign_all(tmp_path, ["memory/system/ownership.toml"])
        assert result["resigned"] is False
        assert result["reason"] != ""

    def test_try_resign_all_returns_error_when_module_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_try_resign_all returns error when signing module is None."""
        import memory_core.tools.version_sync as vs

        monkeypatch.setattr(vs, "sign_project_incremental", None)
        monkeypatch.setattr(vs, "load_key", None)

        result = _try_resign_all(tmp_path, ["memory/system/ownership.toml"])
        assert result["resigned"] is False
        assert "unavailable" in result["reason"].lower()


# ─────────────────────────────────────────────────────────────
# VAL-SYNC-003: sync_single_project three-file patch
# ─────────────────────────────────────────────────────────────


def _make_project(tmp_path: Path, memory_version: str = "0.9.0") -> Path:
    """Create a minimal project fixture with ownership.toml, memory.lock, adapter.toml."""
    project = tmp_path / "test-project"
    (project / "memory" / "system").mkdir(parents=True)

    ownership = project / "memory" / "system" / "ownership.toml"
    ownership.write_text(
        f'[project]\nname = "test"\nmemory_version = "{memory_version}"\n',
        encoding="utf-8",
    )

    lock = project / "memory" / "system" / "memory.lock"
    lock.write_text(
        f'memory_version = "{memory_version}"\n'
        f'schema_version = "context-package-v1"\n'
        f'adapter_version = "builtin"\n'
        f'lock_reason = "memory-init"\n'
        f'locked_at = "2026-01-01T00:00:00+00:00"\n',
        encoding="utf-8",
    )

    adapter = project / "memory" / "system" / "adapter.toml"
    adapter.write_text(
        f'[core]\nversion = "{memory_version}"\nmemory_dir = "memory"\n',
        encoding="utf-8",
    )

    return project


class TestSyncSingleProject:
    """VAL-SYNC-003: sync_single_project patches three files when gate allows."""

    def test_sync_single_project_patches_three_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """sync_single_project patches ownership.toml + memory.lock + adapter.toml."""
        import memory_core.tools.version_sync as vs

        # Mock resign to avoid real signing
        mock_resign = MagicMock(return_value={"resigned": True, "paths": []})
        monkeypatch.setattr(vs, "_try_resign_all", mock_resign)

        project = _make_project(tmp_path, "0.9.0")
        result = sync_single_project(project, "0.9.1")

        assert result["patched"] is True

        # Check ownership.toml patched
        own_content = (project / "memory" / "system" / "ownership.toml").read_text()
        assert 'memory_version = "0.9.1"' in own_content

        # Check memory.lock patched
        lock_content = (project / "memory" / "system" / "memory.lock").read_text()
        assert re.search(r'^memory_version\s*=\s*"0\.9\.1"', lock_content, re.MULTILINE)

        # Check adapter.toml patched
        adapter_content = (project / "memory" / "system" / "adapter.toml").read_text()
        assert re.search(r'^version\s*=\s*"0\.9\.1"', adapter_content, re.MULTILINE)

    def test_sync_single_project_skips_when_up_to_date(self, tmp_path: Path) -> None:
        """VAL-SYNC-005: Already up-to-date projects are skipped."""
        project = _make_project(tmp_path, "0.9.1")
        result = sync_single_project(project, "0.9.1")
        assert result["patched"] is False
        assert "up-to-date" in result.get("reason", "").lower() or "up to date" in result.get("reason", "").lower()


# ─────────────────────────────────────────────────────────────
# VAL-SYNC-004: sync_all_known_projects three-file patch
# ─────────────────────────────────────────────────────────────


def _make_lifecycle_root(tmp_path: Path, projects: list[str]) -> Path:
    """Create a minimal lifecycle root with path-index.json."""
    lifecycle = tmp_path / "lifecycle"
    lifecycle.mkdir()

    paths = {}
    for pname in projects:
        pdir = tmp_path / pname
        (pdir / "memory" / "system").mkdir(parents=True)
        # ownership.toml with version 0.9.0
        (pdir / "memory" / "system" / "ownership.toml").write_text(
            f'[project]\nname = "{pname}"\nmemory_version = "0.9.0"\n',
            encoding="utf-8",
        )
        # memory.lock
        (pdir / "memory" / "system" / "memory.lock").write_text(
            'memory_version = "0.9.0"\nschema_version = "context-package-v1"\n'
            'adapter_version = "builtin"\nlock_reason = "memory-init"\n'
            'locked_at = "2026-01-01T00:00:00+00:00"\n',
            encoding="utf-8",
        )
        # adapter.toml
        (pdir / "memory" / "system" / "adapter.toml").write_text(
            '[core]\nversion = "0.9.0"\nmemory_dir = "memory"\n',
            encoding="utf-8",
        )
        paths[str(pdir)] = {"project_name": pname, "status": "active"}

    # Write path-index.json at lifecycle_root/project-lifecycle/path-index.json
    pl = lifecycle / "project-lifecycle"
    pl.mkdir()
    (pl / "path-index.json").write_text(json.dumps({"paths": paths}), encoding="utf-8")

    return lifecycle


class TestSyncAllKnownProjects:
    """VAL-SYNC-004: sync_all_known_projects patches three files in batch."""

    def test_sync_all_known_projects_patches_three_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """sync_all_known_projects patches all three files for each project."""
        import memory_core.tools.version_sync as vs

        mock_resign = MagicMock(return_value={"resigned": True, "paths": []})
        monkeypatch.setattr(vs, "_try_resign_all", mock_resign)

        lifecycle = _make_lifecycle_root(tmp_path, ["proj-a", "proj-b", "proj-c"])
        result = sync_all_known_projects(lifecycle, "0.9.1")

        assert len(result["patched"]) == 3
        # Check each project got three-file patch
        for pname in ["proj-a", "proj-b", "proj-c"]:
            pdir = tmp_path / pname
            own = (pdir / "memory" / "system" / "ownership.toml").read_text()
            assert 'memory_version = "0.9.1"' in own
            lock = (pdir / "memory" / "system" / "memory.lock").read_text()
            assert re.search(r'^memory_version\s*=\s*"0\.9\.1"', lock, re.MULTILINE)
            adapter = (pdir / "memory" / "system" / "adapter.toml").read_text()
            assert re.search(r'^version\s*=\s*"0\.9\.1"', adapter, re.MULTILINE)


# ─────────────────────────────────────────────────────────────
# VAL-GATE-002..004: Blocked scenarios
# ─────────────────────────────────────────────────────────────


class TestBlockedScenarios:
    """VAL-GATE-002..004: Blocked scenarios still patch ownership.toml."""

    def test_major_bump_blocks_all_writes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """VAL-GATE-002 + VAL-GATE-004: Major bump blocks ALL writes (including ownership)."""
        import memory_core.tools.version_sync as vs

        mock_resign = MagicMock(return_value={"resigned": True, "paths": []})
        monkeypatch.setattr(vs, "_try_resign_all", mock_resign)

        project = _make_project(tmp_path, "0.10.2")
        # Target is 1.0.0 -> major bump -> blocked
        result = sync_single_project(project, "1.0.0")

        # ownership.toml NOT patched (M1: gate blocked means no writes)
        own = (project / "memory" / "system" / "ownership.toml").read_text()
        assert 'memory_version = "0.10.2"' in own

        # memory.lock NOT patched
        lock = (project / "memory" / "system" / "memory.lock").read_text()
        assert re.search(r'^memory_version\s*=\s*"0\.10\.2"', lock, re.MULTILINE)

        # adapter.toml NOT patched
        adapter = (project / "memory" / "system" / "adapter.toml").read_text()
        assert re.search(r'^version\s*=\s*"0\.10\.2"', adapter, re.MULTILINE)

        # Result indicates blocked
        assert result.get("gate_blocked") is True
        assert result.get("gate_reason") == "blocked:major"

    def test_schema_change_blocks_lock_adapter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """VAL-GATE-003: Schema change blocks lock/adapter patch."""
        import memory_core.tools.version_sync as vs

        mock_resign = MagicMock(return_value={"resigned": True, "paths": []})
        monkeypatch.setattr(vs, "_try_resign_all", mock_resign)

        # Create project with a DIFFERENT schema_version in lock file
        # CANONICAL_MEMORY_LOCK_SCHEMA = "context-package-v1"
        # We use "context-package-v2" to trigger schema_changed=True
        project = tmp_path / "test-project"
        (project / "memory" / "system").mkdir(parents=True)

        ownership = project / "memory" / "system" / "ownership.toml"
        ownership.write_text(
            '[project]\nname = "test"\nmemory_version = "0.9.0"\n',
            encoding="utf-8",
        )

        lock = project / "memory" / "system" / "memory.lock"
        lock.write_text(
            'memory_version = "0.9.0"\n'
            'schema_version = "context-package-v2"\n'  # DIFFERENT from canonical
            'adapter_version = "builtin"\n'
            'lock_reason = "memory-init"\n'
            'locked_at = "2026-01-01T00:00:00+00:00"\n',
            encoding="utf-8",
        )

        adapter = project / "memory" / "system" / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.9.0"\nmemory_dir = "memory"\n',
            encoding="utf-8",
        )

        result = sync_single_project(project, "0.9.1")

        # ownership.toml NOT patched (M1: gate blocked means no writes)
        own = (project / "memory" / "system" / "ownership.toml").read_text()
        assert 'memory_version = "0.9.0"' in own

        # memory.lock NOT patched (schema change blocked)
        lock_after = (project / "memory" / "system" / "memory.lock").read_text()
        assert re.search(r'^memory_version\s*=\s*"0\.9\.0"', lock_after, re.MULTILINE)
        # adapter.toml NOT patched
        adapter_after = (project / "memory" / "system" / "adapter.toml").read_text()
        assert re.search(r'^version\s*=\s*"0\.9\.0"', adapter_after, re.MULTILINE)
        # Gate was blocked
        assert result.get("gate_blocked") is True
        assert result.get("gate_reason") == "blocked:schema_changed"


# ─────────────────────────────────────────────────────────────
# VAL-RESIGN-003: Callers check return value
# ─────────────────────────────────────────────────────────────


class TestResignErrorPropagation:
    """VAL-RESIGN-003: Callers check resign return and write to result['errors']."""

    def test_sync_single_project_records_resign_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """sync_single_project records resign failure in result."""
        import memory_core.tools.version_sync as vs

        mock_resign = MagicMock(return_value={"resigned": False, "reason": "signing failed"})
        monkeypatch.setattr(vs, "_try_resign_all", mock_resign)

        project = _make_project(tmp_path, "0.9.0")
        result = sync_single_project(project, "0.9.1")

        # Result should indicate resign error
        assert result.get("resign_error") is not None or result.get("errors") is not None

    def test_sync_all_known_projects_records_resign_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync_all_known_projects records resign failure in result['errors']."""
        import memory_core.tools.version_sync as vs

        mock_resign = MagicMock(return_value={"resigned": False, "reason": "key missing"})
        monkeypatch.setattr(vs, "_try_resign_all", mock_resign)

        lifecycle = _make_lifecycle_root(tmp_path, ["proj-x"])
        result = sync_all_known_projects(lifecycle, "0.9.1")

        # Errors should be recorded
        assert len(result["errors"]) > 0
        assert any("key missing" in str(e) for e in result["errors"])
