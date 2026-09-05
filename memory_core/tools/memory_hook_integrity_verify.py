#!/usr/bin/env python3.12
"""L2 Integrity Layer — Verification Engine.

Reads manifest.json and verifies SHA-256 + HMAC signatures against
current file contents. Reports tampering, missing files, and new files.

M4: No auto re-sign on failure. Returns (ok=False, errors=[...]) only.
Source repo: zero file side-effects (returns empty result without reading).
Supports both v1 and v2 manifest schemas.

Append-only runtime-class entries (heartbeat session logs, the integrity
audit trail, the pattern registry) are skipped at verify time: they are
appended by the gateway by design, so a hash mismatch on them is drift,
not tampering. This also covers existing manifests that still carry such
entries with stale hashes from before the runtime classification.
"""

import hashlib
import hmac as _hmc
import json
from pathlib import Path
from typing import Any

from memory_core.constants import SYSTEM_DIR
from memory_core.tools.denylist import is_denied_project_root

MANIFEST_FILENAME = "manifest.json"

# Supported schema versions (M4: accept both v1 and v2)
SUPPORTED_SCHEMA_VERSIONS = {"integrity-manifest-v1", "integrity-manifest-v2"}

# M4: Import source repo detection for zero side-effects
try:
    from memory_core.ownership import is_memory_core_source_repo
except ImportError:
    is_memory_core_source_repo = None  # type: ignore

# Lazy import to avoid circular dependency
_discover_fn = None


def _get_discover_fn() -> Any:
    global _discover_fn
    if _discover_fn is None:
        try:
            from .memory_hook_integrity_manifest import _discover_canonical_files

            _discover_fn = _discover_canonical_files
        except ImportError:
            from memory_hook_integrity_manifest import _discover_canonical_files  # type: ignore

            _discover_fn = _discover_canonical_files
    return _discover_fn


# Lazy import of the append-only runtime classifier (same pattern as above)
_runtime_class_fn = None


def _get_runtime_class_fn() -> Any:
    global _runtime_class_fn
    if _runtime_class_fn is None:
        try:
            from .memory_hook_integrity_manifest import _is_runtime_append_only

            _runtime_class_fn = _is_runtime_append_only
        except ImportError:
            from memory_hook_integrity_manifest import _is_runtime_append_only  # type: ignore

            _runtime_class_fn = _is_runtime_append_only
    return _runtime_class_fn


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
            "runtime_skipped": 0,
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


def _verify_single_entry(entry: dict[str, Any], resolved_root: Path, key: bytes, result: IntegrityResult) -> None:
    """Verify a single manifest entry, recording errors/summary into result.

    Note: membership in the manifest (signed_paths) is tracked by the caller
    for every entry regardless of verification outcome — a tampered file is
    still a signed file, not an unsigned one.
    """
    rel: str = entry.get("rel_path", "")
    expected_sha: str = entry.get("sha256", "")
    expected_hmac: str = entry.get("hmac_sha256", "")
    abs_path = resolved_root / rel

    if not abs_path.exists():
        result.add_error(rel, "missing", "Signed file no longer exists")
        return

    try:
        raw = abs_path.read_bytes()
    except OSError as exc:
        result.add_error(rel, "unreadable", f"Cannot read file: {exc}")
        return

    actual_sha = hashlib.sha256(raw).hexdigest()
    actual_hmac = _hmc.new(key, raw, hashlib.sha256).hexdigest()

    if actual_sha != expected_sha:
        result.add_error(
            rel, "tampered", f"SHA-256 mismatch: expected {expected_sha[:16]}..., got {actual_sha[:16]}..."
        )
    elif actual_hmac != expected_hmac:
        result.add_error(rel, "tampered", "HMAC mismatch (content may have been replayed)")
    else:
        result.summary["verified_ok"] += 1


def _check_unsigned_files(resolved_root: Path, signed_paths: set[Path], result: IntegrityResult) -> None:
    """Check for new unsigned files and add warnings to result."""
    discover_fn = _get_discover_fn()
    if discover_fn is None:
        return

    current_files = set(discover_fn(resolved_root))
    for fpath in current_files:
        if fpath.name == MANIFEST_FILENAME and fpath.parent.name == SYSTEM_DIR.split("/")[-1]:
            continue  # Skip manifest.json itself
        if fpath not in signed_paths:
            rel = str(fpath.relative_to(resolved_root))
            result.add_warning(rel, "new_unsigned", "File exists but not in manifest")


def verify_project(
    project_root: Path,
    key: bytes,
) -> IntegrityResult:
    """Verify integrity of a project's canonical files against manifest.

    M4: No auto re-sign on failure. Returns IntegrityResult with ok=False
    and errors list. Source repo: zero file side-effects.

    Args:
        project_root: Absolute path to project root
        key: 32-byte HMAC key

    Returns:
        IntegrityResult with ok/errors/warnings
    """
    result = IntegrityResult()
    resolved_root = project_root.resolve()

    # M4.5: Source repo readonly — zero file side-effects
    if is_memory_core_source_repo is not None and is_memory_core_source_repo(resolved_root):
        return result

    if is_denied_project_root(resolved_root):
        return result

    manifest_path = resolved_root / SYSTEM_DIR / MANIFEST_FILENAME

    if not manifest_path.exists():
        result.add_error("", "missing_manifest", f"No manifest.json found in {SYSTEM_DIR}/")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result.add_error("", "manifest_corrupt", f"Cannot parse manifest: {exc}")
        return result

    # M4: Accept both v1 and v2 schemas
    schema_version = manifest.get("schema_version", "")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        result.add_error("", "schema_mismatch", f"Unsupported schema version: {schema_version!r}")
        return result

    # Check key fingerprint
    expected_fp = "sha256:" + hashlib.sha256(key).hexdigest()[:8]
    if manifest.get("key_fingerprint") != expected_fp:
        result.add_warning(
            "",
            "key_mismatch",
            f"Key fingerprint mismatch: manifest={manifest.get('key_fingerprint')}, current={expected_fp}",
        )

    entries = manifest.get("entries", [])
    result.summary["total_signed"] = len(entries)

    # Append-only runtime class (heartbeat session logs, the integrity audit
    # trail, the pattern registry) is appended by the gateway itself — these
    # are by-design mutations, not tamper targets. Stale-hash entries in
    # existing manifests (signed before this classification) are skipped
    # here; the next full re-sign rebuilds the manifest without them.
    runtime_class_fn = _get_runtime_class_fn()

    signed_paths = set()
    for entry in entries:
        rel = entry.get("rel_path", "")
        if runtime_class_fn is not None and runtime_class_fn(rel):
            result.summary["runtime_skipped"] += 1
            continue
        _verify_single_entry(entry, resolved_root, key, result)
        # Membership is tracked for every manifest entry, even failed ones:
        # a tampered file is still signed, not unsigned.
        abs_path = resolved_root / rel
        if abs_path.exists():
            signed_paths.add(abs_path.resolve())

    # Check for new unsigned files (exclude manifest.json itself to avoid chicken-egg)
    _check_unsigned_files(resolved_root, signed_paths, result)

    # M4: On failure, return (ok=False, errors=[...]) only — NO auto re-sign.
    # Caller must use memory_integrity_resign.py CLI for explicit re-sign.
    return result


def quick_check(project_root: Path, key: bytes) -> bool:
    """Fast check: return True if project integrity is OK."""
    result = verify_project(project_root, key)
    return result.ok
