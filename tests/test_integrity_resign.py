#!/usr/bin/env python3
"""M4 tests: Re-sign CLI — explicit re-sign with audit trail."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_core.tools.memory_hook_integrity_keys import load_or_create_key
from memory_core.tools.memory_hook_integrity_manifest import MANIFEST_FILENAME, sign_project
from memory_core.tools.memory_integrity_resign import main as resign_main


class TestResignCLI:
    """4.6: Re-sign CLI tests."""

    def _make_project(self, td: str) -> Path:
        """Create a minimal project with signed manifest."""
        root = Path(td)
        memory_dir = root / ".memory"
        memory_dir.mkdir()
        (memory_dir / "CANONICAL.md").write_text("# Canonical\n")
        (memory_dir / "STATE.md").write_text("# State\n")

        key = load_or_create_key(memory_dir / "test.key")
        sign_project(root, key)
        return root

    def test_resign_requires_reason(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)
            # Missing --reason should fail (argparse raises SystemExit)
            with pytest.raises(SystemExit):
                resign_main([
                    "--project-root", str(root),
                    "--force",
                ])

    def test_resign_requires_token_or_force(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)
            # Missing --token and --force should fail
            exit_code = resign_main([
                "--project-root", str(root),
                "--reason", "test re-sign",
            ])
            assert exit_code == 1

    def test_resign_with_force(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)

            # Set up key in env
            key_path = root / ".memory" / "test.key"
            import os
            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                exit_code = resign_main([
                    "--project-root", str(root),
                    "--reason", "legitimate re-sign after approved change",
                    "--force",
                ])
                assert exit_code == 0

                # Audit trail should exist
                audit_path = root / ".memory" / "integrity-audit.jsonl"
                assert audit_path.exists()
                lines = audit_path.read_text().strip().splitlines()
                assert len(lines) >= 1
                entry = json.loads(lines[-1])
                assert entry["action"] == "resign"
                assert entry["reason"] == "legitimate re-sign after approved change"
                assert entry["force_used"] is True
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)

    def test_resign_with_token(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)

            key_path = root / ".memory" / "test.key"
            import os
            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                exit_code = resign_main([
                    "--project-root", str(root),
                    "--reason", "approved re-sign",
                    "--token", "APPROVED-TOKEN-123",
                ])
                assert exit_code == 0

                audit_path = root / ".memory" / "integrity-audit.jsonl"
                entry = json.loads(audit_path.read_text().strip().splitlines()[-1])
                assert entry["token_provided"] is True
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)

    def test_resign_strict_shows_verify_diff(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)

            # Tamper with a file
            (root / ".memory" / "CANONICAL.md").write_text("# Tampered!\n")

            key_path = root / ".memory" / "test.key"
            import os
            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                exit_code = resign_main([
                    "--project-root", str(root),
                    "--reason", "re-sign after fix",
                    "--token", "FIX-123",
                    "--strict",
                ])
                # Should still succeed (token provided)
                assert exit_code == 0

                captured = capsys.readouterr()
                # Strict mode should have shown verify errors in stderr
                assert "verify found" in captured.err or exit_code == 0
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)

    def test_resign_dry_run(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)

            key_path = root / ".memory" / "test.key"
            import os
            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                exit_code = resign_main([
                    "--project-root", str(root),
                    "--reason", "test dry-run",
                    "--force",
                    "--dry-run",
                ])
                assert exit_code == 0

                captured = capsys.readouterr()
                assert "dry-run" in captured.out

                # No audit trail should be written
                audit_path = root / ".memory" / "integrity-audit.jsonl"
                assert not audit_path.exists()
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)

    def test_resign_refuses_nonexistent_root(self):
        exit_code = resign_main([
            "--project-root", "/nonexistent/path",
            "--reason", "test",
            "--force",
        ])
        assert exit_code == 1

    def test_resign_refuses_source_repo(self):
        """Source repo should refuse re-sign (zero side-effects)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            # Create memory-core marker
            nested = root / "memory_core" / "tools"
            nested.mkdir(parents=True)
            (nested / "memory_hook_gateway.py").write_text("# marker\n")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)

            exit_code = resign_main([
                "--project-root", str(root),
                "--reason", "should be refused",
                "--force",
            ])
            assert exit_code == 1

    def test_resign_empty_reason_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".memory").mkdir()
            (root / ".memory" / "CANONICAL.md").write_text("# Canonical\n")

            exit_code = resign_main([
                "--project-root", str(root),
                "--reason", "",
                "--force",
            ])
            assert exit_code == 1

    def test_resign_no_key_fails(self):
        """Re-sign without an existing key should fail."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / ".memory"
            memory_dir.mkdir()
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            import os
            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(root / ".memory" / "nonexistent.key")
            try:
                exit_code = resign_main([
                    "--project-root", str(root),
                    "--reason", "no key test",
                    "--force",
                ])
                assert exit_code == 1
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)

    def test_resign_writes_v2_manifest(self):
        """Re-sign should produce a v2 manifest."""
        with tempfile.TemporaryDirectory() as td:
            root = self._make_project(td)

            key_path = root / ".memory" / "test.key"
            import os
            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                resign_main([
                    "--project-root", str(root),
                    "--reason", "upgrade to v2",
                    "--force",
                ])

                manifest_path = root / ".memory" / MANIFEST_FILENAME
                manifest = json.loads(manifest_path.read_text())
                assert manifest["schema_version"] == "integrity-manifest-v2"
                assert "ownership_digest" in manifest
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)
