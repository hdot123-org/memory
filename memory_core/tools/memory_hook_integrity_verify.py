#!/usr/bin/env python3
"""L2 Integrity Layer — Verification Engine.

Reads manifest.json and verifies SHA-256 + HMAC signatures against
current file contents. Reports tampering, missing files, and new files.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
from pathlib import Path
from typing import Any

from memory_core.tools.denied_project_roots import is_denied_project_root

MANIFEST_FILENAME = "manifest.json"

# Lazy import to avoid circular dependency
_discover_fn = None

def _get_discover_fn():
    global _discover_fn
    if _discover_fn is None:
        try:
            from .memory_hook_integrity_manifest import _discover_canonical_files
            _discover_fn = _discover_canonical_files
        except ImportError:
            from memory_hook_integrity_manifest import _discover_canonical_files  # type: ignore
            _discover_fn = _discover_canonical_files
    return _discover_fn


class IntegrityResult:
    """Result of an integrity verification."""

    def __init__(self) -> None:
        self.ok = True
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.summary: dict[str, int] = {
            "total_signed": 0,
            "verified_ok": 0,
            "tampered": 0,
            "missing": 0,
            "new_unsigned": 0,
        }

    def add_error(self, rel_path: str, kind: str, detail: str) -> None:
        self.ok = False
        self.errors.append({"rel_path": rel_path, "kind": kind, "detail": detail})
        if kind == "tampered":
            self.summary["tampered"] += 1
        elif kind == "missing":
            self.summary["missing"] += 1

    def add_warning(self, rel_path: str, kind: str, detail: str) -> None:
        self.warnings.append({"rel_path": rel_path, "kind": kind, "detail": detail})
        if kind == "new_unsigned":
            self.summary["new_unsigned"] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def verify_project(
    project_root: Path,
    key: bytes,
) -> IntegrityResult:
    """Verify integrity of a project's canonical files against manifest.

    Args:
        project_root: Absolute path to project root
        key: 32-byte HMAC key

    Returns:
        IntegrityResult with ok/errors/warnings
    """
    result = IntegrityResult()
    resolved_root = project_root.resolve()
    if is_denied_project_root(resolved_root):
        return result

    manifest_path = resolved_root / ".memory" / MANIFEST_FILENAME

    if not manifest_path.exists():
        result.add_error("", "missing_manifest", "No manifest.json found in .memory/")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result.add_error("", "manifest_corrupt", f"Cannot parse manifest: {exc}")
        return result

    if manifest.get("schema_version") != "integrity-manifest-v1":
        result.add_error(
            "", "schema_mismatch",
            f"Expected integrity-manifest-v1, got {manifest.get('schema_version')}"
        )
        return result

    # Check key fingerprint
    expected_fp = "sha256:" + hashlib.sha256(key).hexdigest()[:8]
    if manifest.get("key_fingerprint") != expected_fp:
        result.add_warning(
            "", "key_mismatch",
            f"Key fingerprint mismatch: manifest={manifest.get('key_fingerprint')}, current={expected_fp}"
        )

    entries = manifest.get("entries", [])
    result.summary["total_signed"] = len(entries)

    signed_paths = set()
    for entry in entries:
        rel = entry.get("rel_path", "")
        abs_path = resolved_root / rel
        signed_paths.add(abs_path.resolve())

        expected_sha = entry.get("sha256", "")
        expected_hmac = entry.get("hmac_sha256", "")

        if not abs_path.exists():
            result.add_error(rel, "missing", "Signed file no longer exists")
            continue

        try:
            raw = abs_path.read_bytes()
        except OSError as exc:
            result.add_error(rel, "unreadable", f"Cannot read file: {exc}")
            continue

        actual_sha = hashlib.sha256(raw).hexdigest()
        actual_hmac = _hmac.new(key, raw, hashlib.sha256).hexdigest()

        if actual_sha != expected_sha:
            result.add_error(rel, "tampered", f"SHA-256 mismatch: expected {expected_sha[:16]}..., got {actual_sha[:16]}...")
        elif actual_hmac != expected_hmac:
            result.add_error(rel, "tampered", "HMAC mismatch (content may have been replayed)")
        else:
            result.summary["verified_ok"] += 1

    # Check for new unsigned files (exclude manifest.json itself to avoid chicken-egg)
    discover_fn = _get_discover_fn()
    if discover_fn is not None:
        current_files = set(discover_fn(resolved_root))
        for fpath in current_files:
            if fpath.name == MANIFEST_FILENAME and fpath.parent.name == ".memory":
                continue  # Skip manifest.json itself
            if fpath not in signed_paths:
                rel = str(fpath.relative_to(resolved_root))
                result.add_warning(rel, "new_unsigned", "File exists but not in manifest")

    return result


def quick_check(project_root: Path, key: bytes) -> bool:
    """Fast check: return True if project integrity is OK."""
    result = verify_project(project_root, key)
    return result.ok
