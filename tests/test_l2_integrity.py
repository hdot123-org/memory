#!/usr/bin/env python3
"""L2 Integrity Layer — Tests for key management, manifest signing, and verification."""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
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
        assert SCHEMA_VERSION == "integrity-manifest-v1"

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
            memory_dir = root / ".memory"
            memory_dir.mkdir()
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
            (root / ".memory").mkdir()
            # No canonical files created

            key = generate_key()
            manifest = sign_project(root, key)

            # Should still create manifest (empty or with just previous manifest)
            assert manifest["schema_version"] == SCHEMA_VERSION

    def test_sign_project_includes_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            # Create date-partitioned artifacts
            art_dir = root / "artifacts" / "memory-hook" / "contexts" / "2026-05-11"
            art_dir.mkdir(parents=True)
            (art_dir / "snapshot.json").write_text("{}")

            key = generate_key()
            manifest = sign_project(root, key)

            paths = [e["rel_path"] for e in manifest["entries"]]
            assert any("snapshot.json" in p for p in paths)

    def test_sign_project_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            m1 = sign_project(root, key)
            m2 = sign_project(root, key)

            # Second run should include the first manifest
            assert m2["entry_count"] >= m1["entry_count"]


# --- Verification Tests ---

class TestVerification:
    def test_verify_fresh_project_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
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
            memory_dir = root / ".memory"
            memory_dir.mkdir()
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
            memory_dir = root / ".memory"
            memory_dir.mkdir()
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
            (root / ".memory").mkdir()

            key = generate_key()
            result = verify_project(root, key)
            assert not result.ok
            assert any(e["kind"] == "missing_manifest" for e in result.errors)

    def test_verify_corrupt_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "manifest.json").write_text("not json{")

            key = generate_key()
            result = verify_project(root, key)
            assert not result.ok
            assert any(e["kind"] == "manifest_corrupt" for e in result.errors)

    def test_verify_wrong_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "manifest.json").write_text(
                json.dumps({"schema_version": "old-v0"})
            )

            key = generate_key()
            result = verify_project(root, key)
            assert not result.ok
            assert any(e["kind"] == "schema_mismatch" for e in result.errors)

    def test_verify_key_fingerprint_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
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
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            sign_project(root, key)

            assert quick_check(root, key) is True

    def test_quick_check_false_on_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
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
