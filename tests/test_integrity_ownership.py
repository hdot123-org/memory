#!/usr/bin/env python3
"""M4 tests: Integrity ownership-aware signing, verify fail no re-sign, readonly zero side-effects."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_core.tools.memory_hook_integrity_keys import generate_key
from memory_core.tools.memory_hook_integrity_manifest import (
    MANIFEST_FILENAME,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V2,
    _classify_entry,
    _compute_ownership_digest,
    sign_project,
)
from memory_core.tools.memory_hook_integrity_verify import (
    SUPPORTED_SCHEMA_VERSIONS,
    IntegrityResult,
    verify_project,
)


class TestManifestV2Schema:
    """4.2: Manifest v2 schema includes ownership metadata."""

    def test_schema_version_is_v2(self):
        assert SCHEMA_VERSION == SCHEMA_VERSION_V2

    def test_v2_supported_in_verify(self):
        assert "integrity-manifest-v2" in SUPPORTED_SCHEMA_VERSIONS

    def test_v1_supported_in_verify(self):
        assert "integrity-manifest-v1" in SUPPORTED_SCHEMA_VERSIONS

    def test_sign_produces_v2_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")
            (memory_dir / "STATE.md").write_text("# State\n")

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest is not None
            assert manifest["schema_version"] == SCHEMA_VERSION_V2

    def test_manifest_entry_has_ownership_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest is not None
            for entry in manifest["entries"]:
                assert "ownership_id" in entry
                assert "protection_level" in entry
                assert "classification_source" in entry

    def test_manifest_has_ownership_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest is not None
            assert "ownership_digest" in manifest
            assert len(manifest["ownership_digest"]) == 64  # SHA-256 hex


class TestOwnershipDerivedSigningScope:
    """4.1: Signing scope derived from ownership domains/resources."""

    def test_signs_owned_domain_files(self):
        """Files under ownership domains should be signed."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create a file in an owned domain
            docs_dir = root / "memory" / "docs"
            docs_dir.mkdir(parents=True)
            (docs_dir / "INDEX.md").write_text("# Docs Index\n")
            design_dir = docs_dir / "design"
            design_dir.mkdir()
            (design_dir / "arch.md").write_text("# Architecture\n")

            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest is not None
            rel_paths = [e["rel_path"] for e in manifest["entries"]]
            # memory/docs files should be discovered via ownership domain
            assert any("memory/docs" in p for p in rel_paths)

    def test_signs_owned_resources(self):
        """Owned resource files should be signed."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")
            (root / "AGENTS.md").write_text("# Agents\n")

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest is not None
            rel_paths = [e["rel_path"] for e in manifest["entries"]]
            assert "AGENTS.md" in rel_paths

    def test_signs_ownership_toml(self):
        """ownership.toml should be included in signing scope."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")
            (memory_dir / "ownership.toml").write_text('[policy]\nmode = "strict"\n')

            key = generate_key()
            manifest = sign_project(root, key)

            assert manifest is not None
            rel_paths = [e["rel_path"] for e in manifest["entries"]]
            assert "memory/system/ownership.toml" in rel_paths

    def test_classify_entry_owned_resource(self):
        """_classify_entry should return resource metadata for owned paths."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # AGENTS.md is an owned resource
            (root / "AGENTS.md").write_text("# Agents\n")

            oid, pl, cs = _classify_entry("AGENTS.md", root)
            assert oid == "agents_md"
            assert pl == "critical"
            assert cs == "resource"

    def test_classify_entry_owned_domain(self):
        """_classify_entry should return domain metadata for domain paths."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs_dir = root / "memory" / "docs"
            docs_dir.mkdir(parents=True)
            (docs_dir / "test.md").write_text("# Test\n")

            oid, pl, cs = _classify_entry("memory/docs/test.md", root)
            assert oid == "memory_docs"
            assert pl == "critical"
            assert cs == "domain"

    def test_classify_entry_not_owned(self):
        """_classify_entry should return none for unowned paths."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            oid, pl, cs = _classify_entry("some/random/file.txt", root)
            assert oid == "none"
            assert pl == "none"
            assert cs == "none"

    def test_ownership_digest_changes_on_config_change(self):
        """Ownership digest should change when ownership.toml changes."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)

            digest1 = _compute_ownership_digest(root)

            (memory_dir / "ownership.toml").write_text(
                '[policy]\nmode = "strict"\n'
            )

            digest2 = _compute_ownership_digest(root)

            assert digest1 != digest2


class TestVerifyNoResign:
    """4.3: Verify failure returns (ok=False, errors) only — no auto re-sign."""

    def test_verify_fail_returns_errors_no_resign(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Original\n")

            key = generate_key()
            sign_project(root, key)

            # Tamper
            canonical.write_text("# Tampered!\n")

            # Record manifest before verify
            manifest_path = memory_dir / MANIFEST_FILENAME
            manifest_before = manifest_path.read_text()

            result = verify_project(root, key)

            # Should fail
            assert result.ok is False
            assert len(result.errors) >= 1

            # Manifest should be unchanged (no auto re-sign)
            manifest_after = manifest_path.read_text()
            assert manifest_before == manifest_after

    def test_verify_fail_does_not_create_new_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Original\n")

            key = generate_key()
            sign_project(root, key)

            canonical.write_text("# Tampered!\n")

            # List all files before verify
            before_files = set(root.rglob("*"))

            verify_project(root, key)

            # List all files after verify
            after_files = set(root.rglob("*"))

            # No new files should be created
            assert before_files == after_files

    def test_result_to_dict_no_resign_flag(self):
        """Verify IntegrityResult has no re-sign capability."""
        result = IntegrityResult()
        result.add_error("test.md", "tampered", "hash mismatch")
        d = result.to_dict()

        assert d["ok"] is False
        assert "re_signed" not in d
        assert "resign" not in d


class TestV1Compatibility:
    """M4: v1 manifests should still verify correctly."""

    def test_v1_manifest_verifies_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()

            # Write a v1-style manifest manually
            raw = (memory_dir / "CANONICAL.md").read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            import hmac as _hmac

            hm = _hmac.new(key, raw, hashlib.sha256).hexdigest()
            fp = "sha256:" + hashlib.sha256(key).hexdigest()[:8]
            timestamp = "2026-05-14T00:00:00+00:00"

            v1_manifest = {
                "schema_version": "integrity-manifest-v1",
                "project_root": str(root.resolve()),
                "generated_at": timestamp,
                "key_fingerprint": fp,
                "entry_count": 1,
                "entries": [
                    {
                        "path": str((memory_dir / "CANONICAL.md").resolve()),
                        "rel_path": "memory/system/CANONICAL.md",
                        "sha256": sha,
                        "hmac_sha256": hm,
                        "size_bytes": len(raw),
                        "signed_at": timestamp,
                    }
                ],
            }
            (memory_dir / MANIFEST_FILENAME).write_text(
                json.dumps(v1_manifest) + "\n"
            )

            result = verify_project(root, key)
            assert result.ok
            assert result.summary["verified_ok"] == 1

    def test_v1_manifest_tampered_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Original\n")

            key = generate_key()
            raw = canonical.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            import hmac as _hmac

            hm = _hmac.new(key, raw, hashlib.sha256).hexdigest()
            fp = "sha256:" + hashlib.sha256(key).hexdigest()[:8]

            v1_manifest = {
                "schema_version": "integrity-manifest-v1",
                "project_root": str(root.resolve()),
                "generated_at": "2026-05-14T00:00:00+00:00",
                "key_fingerprint": fp,
                "entry_count": 1,
                "entries": [
                    {
                        "path": str(canonical.resolve()),
                        "rel_path": "memory/system/CANONICAL.md",
                        "sha256": sha,
                        "hmac_sha256": hm,
                        "size_bytes": len(raw),
                        "signed_at": "2026-05-14T00:00:00+00:00",
                    }
                ],
            }
            (memory_dir / MANIFEST_FILENAME).write_text(
                json.dumps(v1_manifest) + "\n"
            )

            # Tamper
            canonical.write_text("# Tampered!\n")

            result = verify_project(root, key)
            assert result.ok is False
            assert result.summary["tampered"] >= 1


class TestSourceRepoZeroSideEffects:
    """4.5: Source repo sign/verify must have zero file side-effects."""

    def test_sign_returns_none_for_source_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            # Create memory-core marker
            nested = root / "memory_core" / "tools"
            nested.mkdir(parents=True)
            (nested / "memory_hook_gateway.py").write_text("# marker\n")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)

            key = generate_key()
            result = sign_project(root, key)

            assert result is None
            # No manifest.json created
            assert not (memory_dir / MANIFEST_FILENAME).exists()

    def test_verify_returns_empty_result_for_source_repo(self):
        """Verify on source repo returns ok=True without reading any files."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            # Create memory-core marker
            nested = root / "memory_core" / "tools"
            nested.mkdir(parents=True)
            (nested / "memory_hook_gateway.py").write_text("# marker\n")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)

            key = generate_key()
            result = verify_project(root, key)

            # Returns empty ok result (no side effects)
            assert result.ok is True
            assert len(result.errors) == 0
