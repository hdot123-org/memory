#!/usr/bin/env python3
"""L2 Integrity Layer — Tests for key management, manifest signing, and verification."""

import hashlib
import hmac as _hmac
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Add memory_core to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_core.tools.memory_hook_integrity_keys import (
    generate_key,
    key_info,
    load_key,
    load_or_create_key,
)
from memory_core.tools.memory_hook_integrity_manifest import (
    MANIFEST_FILENAME,
    SCHEMA_VERSION,
    _hmac_sha256,
    _is_runtime_append_only,
    _key_fingerprint,
    _sha256_file,
    sign_project,
)
from memory_core.tools.memory_hook_integrity_verify import (
    IntegrityResult,
    quick_check,
    verify_project,
)

# --- Key Management Tests ---


class TestKeyManagement:
    def test_generate_key_length(self):
        key = generate_key()
        assert len(key) == 32
        # Should be random
        assert generate_key() != generate_key()

    def test_load_or_create_key_creates_new(self):
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "test.key"
            key = load_or_create_key(kp)
            assert len(key) == 32
            assert kp.exists()
            # Permissions should be 0o600
            assert kp.stat().st_mode & 0o777 == 0o600

    def test_load_or_create_key_loads_existing(self):
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "test.key"
            original = generate_key()
            kp.write_bytes(original)
            loaded = load_or_create_key(kp)
            assert loaded == original

    def test_load_or_create_key_regenerates_corrupted(self):
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "test.key"
            kp.write_bytes(b"short")
            key = load_or_create_key(kp)
            assert len(key) == 32
            assert kp.read_bytes() == key

    def test_load_key_returns_none_if_missing(self):
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "nonexistent.key"
            assert load_key(kp) is None

    def test_load_key_returns_none_if_wrong_size(self):
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "test.key"
            kp.write_bytes(b"wrong-size")
            assert load_key(kp) is None

    def test_key_info(self):
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "test.key"
            info = key_info(kp)
            assert not info["exists"]
            assert info["path"] == str(kp)

            load_or_create_key(kp)
            info = key_info(kp)
            assert info["exists"]
            assert info["size_bytes"] == 32


# --- Manifest Tests ---


class TestManifest:
    def test_schema_version(self):
        assert SCHEMA_VERSION == "integrity-manifest-v2"

    def test_sha256_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            f.flush()
            sha = _sha256_file(Path(f.name))
            expected = hashlib.sha256(b"hello world").hexdigest()
            assert sha == expected

    def test_hmac_sha256(self):
        key = b"k" * 32
        data = b"test data"
        expected = _hmac.new(key, data, hashlib.sha256).hexdigest()
        assert _hmac_sha256(data, key) == expected

    def test_key_fingerprint(self):
        key = b"k" * 32
        fp = _key_fingerprint(key)
        assert fp.startswith("sha256:")
        assert len(fp) == len("sha256:") + 8

    def test_sign_project_creates_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create .memory files
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")
            (memory_dir / "STATE.md").write_text("# State\n")

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest["schema_version"] == SCHEMA_VERSION
            assert manifest["project_root"] == str(root.resolve())
            assert manifest["entry_count"] >= 2
            assert len(manifest["entries"]) >= 2

            # Manifest file should exist
            manifest_path = memory_dir / MANIFEST_FILENAME
            assert manifest_path.exists()
            loaded = json.loads(manifest_path.read_text())
            assert loaded["schema_version"] == SCHEMA_VERSION

    def test_sign_project_skips_missing_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "memory" / "system").mkdir(parents=True)
            # No canonical files created

            key = generate_key()
            manifest = sign_project(root, key)

            # Should still create manifest (empty or with just previous manifest)
            assert manifest["schema_version"] == SCHEMA_VERSION

    def test_sign_project_includes_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            # Create date-partitioned artifacts
            art_dir = root / "memory" / "artifacts" / "memory-hook" / "contexts" / "2026-05-11"
            art_dir.mkdir(parents=True)
            (art_dir / "snapshot.json").write_text("{}")

            key = generate_key()
            manifest = sign_project(root, key, include_runtime=True)

            paths = [e["rel_path"] for e in manifest["entries"]]
            assert any("snapshot.json" in p for p in paths)

    def test_sign_project_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            m1 = sign_project(root, key)
            m2 = sign_project(root, key)

            # Second run should include the first manifest
            assert m2["entry_count"] >= m1["entry_count"]

    def test_sign_project_skips_exact_home_root_but_allows_child(self, monkeypatch):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td) / "home"
            child = fake_home / "tool"
            child_memory = child / "memory" / "system"
            child_memory.mkdir(parents=True)
            (child_memory / "CANONICAL.md").write_text("# Canonical\n")
            fake_home_memory = fake_home / "memory" / "system"
            fake_home_memory.mkdir(parents=True, exist_ok=True)
            (fake_home_memory / "CANONICAL.md").write_text("# Home\n")
            monkeypatch.setenv("HOME", str(fake_home))

            key = generate_key()
            assert sign_project(fake_home, key) is None
            assert not (fake_home_memory / "manifest.json").exists()

            manifest = sign_project(child, key)
            assert manifest is not None
            assert (child_memory / "manifest.json").exists()

    def test_sign_project_skips_memory_core_source_repo(self):
        """Anti-pollution: sign_project should skip memory-core source repo."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            # Create memory-core marker files
            nested = root / "memory_core" / "tools"
            nested.mkdir(parents=True)
            (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
            (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)

            key = generate_key()
            result = sign_project(root, key)

            # Should return None (skipped)
            assert result is None
            # Should NOT create manifest.json
            assert not (memory_dir / "manifest.json").exists()

    def test_is_memory_core_source_repo_detection(self):
        """Test the internal detection function."""
        from memory_core.ownership import is_memory_core_source_repo

        with tempfile.TemporaryDirectory() as td:
            # Normal project
            normal = Path(td) / "normal"
            normal.mkdir()
            subprocess.run(["git", "init"], cwd=normal, check=True, capture_output=True, text=True)
            assert is_memory_core_source_repo(normal) is False

            # Memory-core repo with gateway marker
            memory = Path(td) / "memory"
            nested = memory / "memory_core" / "tools"
            nested.mkdir(parents=True)
            (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=memory, check=True, capture_output=True, text=True)
            assert is_memory_core_source_repo(memory) is True

            # Memory-core repo with factory_global_hooks marker
            memory2 = Path(td) / "memory2"
            nested2 = memory2 / "memory_core" / "tools"
            nested2.mkdir(parents=True)
            (nested2 / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=memory2, check=True, capture_output=True, text=True)
            assert is_memory_core_source_repo(memory2) is True

            # Memory-core repo with ownership.py marker
            memory3 = Path(td) / "memory3"
            nested3 = memory3 / "memory_core"
            nested3.mkdir(parents=True)
            (nested3 / "ownership.py").write_text("# marker\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=memory3, check=True, capture_output=True, text=True)
            assert is_memory_core_source_repo(memory3) is True

            # Subdirectory should also be detected
            subdir = memory / "subdir"
            subdir.mkdir()
            assert is_memory_core_source_repo(subdir) is True


# --- Verification Tests ---


class TestVerification:
    def test_verify_fresh_project_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")
            (memory_dir / "STATE.md").write_text("# State\n")

            key = generate_key()
            sign_project(root, key)

            result = verify_project(root, key)
            assert result.ok
            assert result.summary["verified_ok"] >= 2
            assert result.summary["tampered"] == 0
            assert result.summary["missing"] == 0

    def test_verify_detects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Original\n")

            key = generate_key()
            sign_project(root, key)

            # Tamper with the file
            canonical.write_text("# Tampered!\n")

            result = verify_project(root, key)
            assert not result.ok
            assert result.summary["tampered"] >= 1
            assert any(e["kind"] == "tampered" for e in result.errors)

    def test_verify_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Canonical\n")

            key = generate_key()
            sign_project(root, key)

            # Delete the file
            canonical.unlink()

            result = verify_project(root, key)
            assert not result.ok
            assert result.summary["missing"] >= 1

    def test_verify_missing_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "memory" / "system").mkdir(parents=True)

            key = generate_key()
            result = verify_project(root, key)
            assert not result.ok
            assert any(e["kind"] == "missing_manifest" for e in result.errors)

    def test_verify_corrupt_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "manifest.json").write_text("not json{")

            key = generate_key()
            result = verify_project(root, key)
            assert not result.ok
            assert any(e["kind"] == "manifest_corrupt" for e in result.errors)

    def test_verify_wrong_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "manifest.json").write_text(json.dumps({"schema_version": "old-v0"}))

            key = generate_key()
            result = verify_project(root, key)
            assert not result.ok
            assert any(e["kind"] == "schema_mismatch" for e in result.errors)

    def test_verify_key_fingerprint_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key1 = generate_key()
            sign_project(root, key1)

            # Verify with different key
            key2 = generate_key()
            result = verify_project(root, key2)
            # Should warn about key mismatch
            assert any(w["kind"] == "key_mismatch" for w in result.warnings)
            # HMAC will also fail since key is different
            assert result.summary["tampered"] >= 1

    def test_quick_check_true_on_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            sign_project(root, key)

            assert quick_check(root, key) is True

    def test_quick_check_false_on_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Original\n")

            key = generate_key()
            sign_project(root, key)
            canonical.write_text("# Tampered\n")

            assert quick_check(root, key) is False

    def test_result_to_dict(self):
        r = IntegrityResult()
        r.add_error("test.md", "tampered", "hash mismatch")
        r.add_warning("new.md", "new_unsigned", "not signed")

        d = r.to_dict()
        assert d["ok"] is False
        assert d["summary"]["tampered"] == 1
        assert d["summary"]["new_unsigned"] == 1
        assert len(d["errors"]) == 1
        assert len(d["warnings"]) == 1


# --- Append-Only Runtime Exclusion (2026-09 false-alarm root-cause fix) ---


def _make_append_only_project(root: Path) -> None:
    """Create a consumer-like project containing the three append-only runtime files.

    Mirrors the ZCodeProject false-alarm sample: heartbeat session logs,
    the integrity audit trail, and the pattern registry — plus one real
    kb content file that MUST stay under tamper-detection coverage.
    """
    system_dir = root / "memory" / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "CANONICAL.md").write_text("# Canonical\n")
    (system_dir / "integrity-audit.jsonl").write_text('{"action": "full-sign"}\n')

    log_dir = root / "memory" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "2026-09-04-sessions.md").write_text("# Sessions\n")

    kb_patterns = root / "memory" / "kb" / "patterns"
    kb_patterns.mkdir(parents=True, exist_ok=True)
    (kb_patterns / "registry.jsonl").write_text("")

    kb_lessons = root / "memory" / "kb" / "lessons"
    kb_lessons.mkdir(parents=True, exist_ok=True)
    (kb_lessons / "lesson-001.md").write_text("# Lesson\n")


class TestAppendOnlyRuntimeClassMatchers:
    """The three append-only runtime path patterns are classified as runtime class."""

    def test_sessions_log_matches(self):
        assert _is_runtime_append_only("memory/log/2026-09-04-sessions.md") is True

    def test_integrity_audit_matches(self):
        assert _is_runtime_append_only("memory/system/integrity-audit.jsonl") is True

    def test_pattern_registry_matches(self):
        assert _is_runtime_append_only("memory/kb/patterns/registry.jsonl") is True

    def test_error_log_not_runtime_class(self):
        # error logs are written together with an incremental re-sign in the
        # same operation — they stay under coverage
        assert _is_runtime_append_only("memory/log/2026-09-04-errors.jsonl") is False

    def test_daily_summary_not_runtime_class(self):
        assert _is_runtime_append_only("memory/log/2026-09-04.md") is False

    def test_real_kb_content_not_runtime_class(self):
        assert _is_runtime_append_only("memory/kb/lessons/lesson-001.md") is False
        assert _is_runtime_append_only("memory/kb/patterns/notes.md") is False
        assert _is_runtime_append_only("memory/kb/patterns/other.jsonl") is False


class TestAppendOnlyRuntimeSigningExclusion:
    """Sign side: default manifest collection excludes append-only runtime files."""

    def test_sign_project_excludes_append_only_runtime_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            manifest = sign_project(root, key)

            rels = [e["rel_path"] for e in manifest["entries"]]
            assert "memory/log/2026-09-04-sessions.md" not in rels
            assert "memory/system/integrity-audit.jsonl" not in rels
            assert "memory/kb/patterns/registry.jsonl" not in rels
            # Real kb content stays signed
            assert "memory/kb/lessons/lesson-001.md" in rels

    def test_sign_project_include_runtime_signs_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            manifest = sign_project(root, key, include_runtime=True)

            rels = [e["rel_path"] for e in manifest["entries"]]
            assert "memory/log/2026-09-04-sessions.md" in rels
            assert "memory/system/integrity-audit.jsonl" in rels
            assert "memory/kb/patterns/registry.jsonl" in rels

    def test_verify_ok_after_heartbeat_append_without_resign(self):
        """Exact false-alarm reproduction: prompt-submit heartbeats append to the
        sessions log WITHOUT re-signing; the next session-start verify must pass.

        Pre-fix this flags kind=tampered on the sessions log (3 of the 9
        observed false events).
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            sign_project(root, key)

            # Heartbeat appends (prompt-submit path does NOT re-sign)
            sessions = root / "memory" / "log" / "2026-09-04-sessions.md"
            sessions.write_text(sessions.read_text() + "- **heartbeat append**\n")
            # Audit trail appends (incremental sign writes audit lines)
            audit = root / "memory" / "system" / "integrity-audit.jsonl"
            audit.write_text(audit.read_text() + '{"action": "incremental-sign"}\n')
            # Pattern registry filled after being signed empty
            registry = root / "memory" / "kb" / "patterns" / "registry.jsonl"
            registry.write_text('{"pattern": "retry-with-backoff"}\n')

            result = verify_project(root, key)
            assert result.ok, f"append-only runtime drift must not flag: {result.errors}"
            assert result.summary["tampered"] == 0


class TestAppendOnlyRuntimeVerificationFilter:
    """Verify side: stale append-only entries in existing manifests must not flag.

    Existing consumer scopes still carry these entries with stale hashes;
    the verify-side filter silences them until the next full re-sign
    rebuilds the manifest without them.
    """

    def test_verify_ignores_stale_append_only_entries_in_old_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            # Simulate an old-format manifest: signed WITH runtime coverage
            sign_project(root, key, include_runtime=True)

            # Gateway appended after that sign (heartbeat / audit / registry fill)
            sessions = root / "memory" / "log" / "2026-09-04-sessions.md"
            sessions.write_text(sessions.read_text() + "- **heartbeat append**\n")
            audit = root / "memory" / "system" / "integrity-audit.jsonl"
            audit.write_text(audit.read_text() + '{"action": "incremental-sign"}\n')
            registry = root / "memory" / "kb" / "patterns" / "registry.jsonl"
            registry.write_text('{"pattern": "retry-with-backoff"}\n')

            result = verify_project(root, key)
            assert result.ok, f"stale append-only entries must not flag: {result.errors}"
            assert result.summary["runtime_skipped"] == 3

    def test_verify_still_detects_tampered_kb_content(self):
        """REGRESSION PIN: genuine tampering of real kb content must still fail,
        even alongside stale append-only entries."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            # Old-format manifest includes the runtime entries
            sign_project(root, key, include_runtime=True)

            # Stale sessions entry (heartbeat appended, no re-sign)
            sessions = root / "memory" / "log" / "2026-09-04-sessions.md"
            sessions.write_text(sessions.read_text() + "- **heartbeat append**\n")
            # AND genuine tampering of a real kb knowledge file
            (root / "memory" / "kb" / "lessons" / "lesson-001.md").write_text("# Tampered lesson\n")

            result = verify_project(root, key)
            assert not result.ok, "tampered kb content must still fail verification"
            tampered_rels = {e["rel_path"] for e in result.errors if e["kind"] == "tampered"}
            assert "memory/kb/lessons/lesson-001.md" in tampered_rels
            assert "memory/log/2026-09-04-sessions.md" not in tampered_rels

    def test_verify_tampered_kb_with_default_manifest(self):
        """Default manifests (no runtime entries) still detect kb tampering."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            sign_project(root, key)

            (root / "memory" / "kb" / "lessons" / "lesson-001.md").write_text("# Tampered\n")

            result = verify_project(root, key)
            assert not result.ok
            assert any(
                e["kind"] == "tampered" and e["rel_path"] == "memory/kb/lessons/lesson-001.md" for e in result.errors
            )

    def test_verify_no_new_unsigned_warning_for_append_only_files(self):
        """Append-only runtime files must not be reported as new_unsigned either."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_append_only_project(root)

            key = generate_key()
            sign_project(root, key)

            result = verify_project(root, key)
            warning_rels = {w["rel_path"] for w in result.warnings}
            assert "memory/log/2026-09-04-sessions.md" not in warning_rels
            assert "memory/system/integrity-audit.jsonl" not in warning_rels
            assert "memory/kb/patterns/registry.jsonl" not in warning_rels
