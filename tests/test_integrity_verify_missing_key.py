#!/usr/bin/env python3
"""Tests for _integrity_verify() key-missing warning behavior.

Verifies:
- WARNING log emitted when HMAC key is absent
- Returns {ok: False, skipped_reason: "key_not_found"} not None
- Normal verify still returns {ok: True} when key present and files match
- Tampered verify still returns {ok: False, errors: [...]} when key present but files changed
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_core.tools.memory_hook_gateway import _integrity_verify
from memory_core.tools.memory_hook_integrity_keys import generate_key
from memory_core.tools.memory_hook_integrity_manifest import sign_project


class TestVerifyMissingKey:
    """Tests for _integrity_verify() when the HMAC key is missing."""

    def test_verify_warns_on_missing_key(self, caplog):
        """WARNING log should be emitted when key file is absent."""
        with tempfile.TemporaryDirectory() as td:
            # Point to a non-existent key path
            fake_key = Path(td) / "nonexistent.key"
            assert not fake_key.exists()

            with mock.patch.object(
                os, "environ", {**os.environ, "MEMORY_INTEGRITY_KEY_PATH": str(fake_key)},
            ):
                # Also need to mock load_key so it returns None with the fake path
                with mock.patch(
                    "memory_core.tools.memory_hook_integrity_keys.load_key",
                    return_value=None,
                ):
                    root = Path(td)
                    with caplog.at_level(logging.WARNING):
                        _integrity_verify(root)

                    # WARNING should have been logged
                    assert any(
                        record.levelno == logging.WARNING and "key" in record.message.lower()
                        for record in caplog.records
                    )

    def test_verify_returns_skipped_reason_on_missing_key(self):
        """Should return {ok: False, skipped_reason: 'key_not_found'} not None."""
        with mock.patch(
            "memory_core.tools.memory_hook_integrity_keys.load_key",
            return_value=None,
        ):
            with tempfile.TemporaryDirectory() as td:
                result = _integrity_verify(Path(td))

            # Should NOT return None
            assert result is not None
            assert isinstance(result, dict)
            assert result.get("ok") is False
            assert result.get("skipped_reason") == "key_not_found"

    def test_verify_ok_when_key_present(self):
        """Normal verify should return {ok: True} when key present and files match."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

            key = generate_key()
            # Use a custom key path
            key_path = root / "memory" / "system" / "test.key"
            key_path.write_bytes(key)

            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                sign_project(root, key)
                result = _integrity_verify(root)
                assert result is not None
                assert result.get("ok") is True
                # Should NOT have skipped_reason
                assert "skipped_reason" not in result
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)

    def test_verify_fails_on_tamper(self):
        """Should return {ok: False, errors: [...]} when files are tampered."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory_dir = root / "memory" / "system"
            memory_dir.mkdir(parents=True)
            canonical = memory_dir / "CANONICAL.md"
            canonical.write_text("# Original\n")

            key = generate_key()
            key_path = root / "memory" / "system" / "test.key"
            key_path.write_bytes(key)

            old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
            os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
            try:
                sign_project(root, key)

                # Tamper with the file
                canonical.write_text("# Tampered!\n")

                result = _integrity_verify(root)
                assert result is not None
                assert isinstance(result, dict)
                assert result.get("ok") is False
                assert "errors" in result
                assert len(result["errors"]) >= 1
                assert any(e["kind"] == "tampered" for e in result["errors"])
                # Should NOT have skipped_reason
                assert "skipped_reason" not in result
            finally:
                if old_env is not None:
                    os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
                else:
                    os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)
