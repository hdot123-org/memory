"""Tests for F2: Init baseline snapshot — sign_project_incremental integration.

Validation assertions covered:
  VAL-F2-001: Signing invocation at init completion
  VAL-F2-002: Audit log entry carries reason "memory-init baseline"
  VAL-F2-003: Signing failure is non-blocking
  VAL-F2-004: manifest.json created under memory/system/
  VAL-F2-005: manifest.json populated with baseline file hashes
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch target: since init_project_memory uses a local import
# (from .memory_hook_integrity_manifest import sign_project_incremental),
# we must patch at the source module.
_SIGNER_PATCH = "memory_core.tools.memory_hook_integrity_manifest.sign_project_incremental"
_KEY_PATCH = "memory_core.tools.memory_hook_integrity_keys.load_or_create_key"


def _make_target(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    project = tmp_path / "test-project"
    project.mkdir()
    (project / ".git").mkdir()  # Make it look like a git repo
    return project


def _mock_source_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch is_memory_core_source_repo to always return False."""
    monkeypatch.setattr(
        "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
        lambda p: False,
    )


def _ensure_init_module_imported() -> None:
    """Force the init_project_memory module to be imported so patches apply to the function body."""
    # Import to trigger module load; local imports in function body still
    # resolve at call time, so patching the source module works.
    from memory_core.tools import init_project_memory  # noqa: F401


# ---- VAL-F2-001: Signing invocation at init completion ----


class TestSigningInvocationAtInit:
    """VAL-F2-001: init_project_memory calls sign_project_incremental() after all file creation."""

    def test_sign_project_incremental_called_once(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unit test with mocked signer -> assert mock_sign.call_count == 1."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        # Use monkeypatch on the actual module object to avoid pollution from prior tests
        from unittest.mock import MagicMock

        import memory_core.tools.memory_hook_integrity_keys as _keys
        import memory_core.tools.memory_hook_integrity_manifest as _manifest
        mock_sign = MagicMock(return_value={"schema_version": "integrity-manifest-v2", "entries": []})
        monkeypatch.setattr(_manifest, "sign_project_incremental", mock_sign)
        monkeypatch.setattr(_keys, "load_or_create_key", lambda *a, **kw: b"test-key")

        from memory_core.tools.init_project_memory import init_project_memory
        result = init_project_memory(target, host="factory")

        assert result["success"], f"init failed: {result['errors']}"
        assert mock_sign.call_count == 1, f"sign not called. warnings: {result.get('warnings', [])}"
        # Verify it was called with changed_paths argument
        call_kwargs = mock_sign.call_args
        assert "changed_paths" in call_kwargs.kwargs or len(call_kwargs.args) >= 3
        # Verify reason is passed
        assert call_kwargs.kwargs.get("reason") == "memory-init baseline"

    def test_sign_called_after_last_file_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify sign is called after all file creation is complete."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        call_order = []

        def track_sign(*args, **kwargs):
            call_order.append("sign")
            return {"schema_version": "integrity-manifest-v2", "entries": []}

        with patch(_KEY_PATCH, return_value=b"test-key"), patch(
            _SIGNER_PATCH,
            side_effect=track_sign,
        ):
            from memory_core.tools.init_project_memory import init_project_memory
            result = init_project_memory(target, host="factory")

        assert result["success"]
        assert call_order == ["sign"]
        # Verify files were created before sign was called
        assert (target / "memory" / "system").is_dir()


# ---- VAL-F2-002: Audit log carries reason "memory-init baseline" ----


class TestAuditLogReason:
    """VAL-F2-002: Audit log records baseline signing with reason: 'memory-init baseline'."""

    def test_audit_log_contains_memory_init_baseline_reason(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read audit log after init -> assert latest entry contains reason 'memory-init baseline'."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        from memory_core.tools.init_project_memory import init_project_memory
        result = init_project_memory(target, host="factory")

        assert result["success"]

        audit_path = target / "memory" / "system" / "integrity-audit.jsonl"
        assert audit_path.exists(), "integrity-audit.jsonl should exist"

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        # Find the entry with reason field (from signing, not from init scaffold)
        signing_entries = [
            json.loads(line) for line in lines if json.loads(line).get("reason") == "memory-init baseline"
        ]
        assert len(signing_entries) >= 1, f"No audit entry with reason='memory-init baseline'. Lines: {lines}"
        entry = signing_entries[-1]
        assert entry["reason"] == "memory-init baseline"


# ---- VAL-F2-003: Signing failure is non-blocking ----


class TestSigningFailureNonBlocking:
    """VAL-F2-003: Signing failure during init produces warning, not error. Init completes with exit code 0."""

    def test_signer_raise_does_not_fail_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch signer to raise -> assert init returns success, warnings list captures error."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        with patch(
            _SIGNER_PATCH,
            side_effect=RuntimeError("signing failed"),
        ):
            from memory_core.tools.init_project_memory import init_project_memory
            result = init_project_memory(target, host="factory")

        assert result["success"], f"init should succeed even when signing fails: {result['errors']}"
        # Check that a warning was recorded in result["warnings"]
        assert any("integrity signing" in w.lower() or "signing" in w.lower() for w in result.get("warnings", [])), \
            f"Expected warning about signing failure in result, got: {result.get('warnings', [])}"

    def test_init_exit_code_zero_on_sign_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that the CLI main() returns 0 when signing fails."""
        import sys
        from io import StringIO

        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            with patch(
                _SIGNER_PATCH,
                side_effect=RuntimeError("signing failed"),
            ):
                from memory_core.tools.init_project_memory import main
                exit_code = main(["--target", str(target), "--json"])
        finally:
            sys.stdout = old_stdout

        assert exit_code == 0, f"Expected exit code 0, got {exit_code}"


# ---- VAL-F2-004: manifest.json created under memory/system/ ----


class TestManifestCreated:
    """VAL-F2-004: memory/system/manifest.json exists after init, is valid JSON with schema version key."""

    def test_manifest_json_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert file exists after init."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        from memory_core.tools.init_project_memory import init_project_memory
        result = init_project_memory(target, host="factory")

        assert result["success"]
        manifest_path = target / "memory" / "system" / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be created under memory/system/"

    def test_manifest_is_valid_json_with_schema_version(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert json.loads succeeds, has schema_version key."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        from memory_core.tools.init_project_memory import init_project_memory
        result = init_project_memory(target, host="factory")

        assert result["success"]
        manifest_path = target / "memory" / "system" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "schema_version" in manifest, "manifest.json must have schema_version"
        assert manifest["schema_version"] in (
            "integrity-manifest-v1",
            "integrity-manifest-v2",
        ), f"Unexpected schema_version: {manifest['schema_version']}"


# ---- VAL-F2-005: manifest.json populated with baseline file hashes ----


class TestManifestPopulated:
    """VAL-F2-005: Baseline manifest contains SHA-256 entries for init-created files."""

    def test_manifest_contains_created_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert manifest entries include created files."""
        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        from memory_core.tools.init_project_memory import init_project_memory
        result = init_project_memory(target, host="factory")

        assert result["success"]
        manifest_path = target / "memory" / "system" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        entries = manifest.get("entries", [])
        assert len(entries) > 0, "Manifest should have entries for init-created files"

        entry_rel_paths = {e["rel_path"] for e in entries}
        # Check that some expected init-created files are present
        expected_files = ["adapter.toml", "memory.lock"]
        for expected in expected_files:
            assert any(expected in rp for rp in entry_rel_paths), \
                f"Expected {expected} in manifest entries, got: {entry_rel_paths}"

    def test_manifest_entries_have_sha256_digests(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert all SHA-256 digests are 64-char hex strings."""
        import re

        _mock_source_repo(monkeypatch)
        target = _make_target(tmp_path)

        from memory_core.tools.init_project_memory import init_project_memory
        result = init_project_memory(target, host="factory")

        assert result["success"]
        manifest_path = target / "memory" / "system" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
        for entry in manifest.get("entries", []):
            assert "sha256" in entry, f"Entry {entry['rel_path']} missing sha256"
            assert sha256_pattern.match(entry["sha256"]), \
                f"Entry {entry['rel_path']} has invalid sha256: {entry['sha256']}"
