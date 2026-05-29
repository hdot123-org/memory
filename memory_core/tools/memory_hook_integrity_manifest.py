#!/usr/bin/env python3
"""L2 Integrity Layer — Manifest Generation & Signing.

Computes SHA-256 + HMAC-SHA256 signatures for project canonical files
and writes a manifest.json to each project's memory/system/ directory.

M4: Signing scope is now derived from ownership domains/resources via
load_memory_ownership(). Manifest entries include ownership metadata
(ownership_id, protection_level, classification_source). Source repo
sign/verify have zero file side-effects.

manifest.json structure (v2):
{
  "schema_version": "integrity-manifest-v2",
  "project_root": "/abs/path/to/project",
  "generated_at": "2026-05-11T12:00:00+08:00",
  "key_fingerprint": "sha256:<first-8-hex-of-key-hash>",
  "ownership_digest": "<sha256-of-ownership-config>",
  "entries": [
    {
      "path": "memory/system/CANONICAL.md",
      "rel_path": "CANONICAL.md",
      "sha256": "<hex>",
      "hmac_sha256": "<hex>",
      "size_bytes": 1234,
      "signed_at": "2026-05-11T12:00:00+08:00",
      "ownership_id": "<domain-or-resource-name>",
      "protection_level": "critical|standard|recommended",
      "classification_source": "domain|resource|none"
    }
  ]
}
"""
from __future__ import annotations

import fcntl
import fnmatch
import hashlib
import hmac as _hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_core.constants import SYSTEM_DIR
from memory_core.tools.denied_project_roots import is_denied_project_root

_logger = logging.getLogger(__name__)

# M3: Import is_memory_core_source_repo from ownership module
try:
    from memory_core.ownership import is_memory_core_source_repo
except ImportError:
    is_memory_core_source_repo = None  # type: ignore

# M4: Import ownership APIs for signing scope
try:
    from memory_core.ownership import (
        NotOwned,
        Owned,
        classify_owned_path,
        load_memory_ownership,
    )
except ImportError:
    load_memory_ownership = None  # type: ignore
    classify_owned_path = None  # type: ignore
    Owned = None  # type: ignore
    NotOwned = None  # type: ignore

MANIFEST_FILENAME = "manifest.json"
SCHEMA_VERSION_V1 = "integrity-manifest-v1"
SCHEMA_VERSION_V2 = "integrity-manifest-v2"
SCHEMA_VERSION = SCHEMA_VERSION_V2

# Default canonical file patterns to sign within a project (legacy fallback)
CANONICAL_PATTERNS = [
    f"{SYSTEM_DIR}/adapter.toml",
    f"{SYSTEM_DIR}/ownership.toml",
    f"{SYSTEM_DIR}/memory.lock",
    f"{SYSTEM_DIR}/migrations.log",
    f"{SYSTEM_DIR}/manifest.json",
    f"{SYSTEM_DIR}/integrity-audit.jsonl",
]

# Date-partitioned artifact paths (sign the daily files too)
ARTIFACT_PATTERNS = [
    "memory/artifacts/memory-hook/contexts",
    "memory/artifacts/memory-hook/events",
]

# Volatile file patterns that are rewritten on every hook invocation.
# These must be excluded from integrity signing because they naturally
# change between signing and verification, causing constant mismatch.
# Matched against the relative path (forward slashes).
VOLATILE_PATTERNS = [
    "memory/system/errors.log",
    "memory/system/errors-readable.log",
    "memory/system/health-report.json",
    "memory/system/errors/",  # date-partitioned error logs
]


def _is_volatile(rel_path: str) -> bool:
    """Check if a relative path matches a volatile pattern."""
    # Normalize to forward slashes
    normalized = rel_path.replace("\\", "/")
    for pattern in VOLATILE_PATTERNS:
        if pattern.endswith("/"):
            # Directory prefix match
            if normalized.startswith(pattern):
                return True
        else:
            if normalized == pattern:
                return True
    return False


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _hmac_sha256(data: bytes, key: bytes) -> str:
    """Compute HMAC-SHA256 hex digest."""
    return _hmac.new(key, data, hashlib.sha256).hexdigest()


def _key_fingerprint(key: bytes) -> str:
    """Short fingerprint of the key (first 8 hex of SHA-256 of key)."""
    return "sha256:" + hashlib.sha256(key).hexdigest()[:8]


def _compute_ownership_digest(project_root: Path) -> str:
    """M4: Compute a SHA-256 digest of the ownership configuration.

    If ownership.toml exists, hash its raw bytes. Otherwise hash the
    default ownership configuration JSON for reproducibility.
    """
    ownership_path = project_root / SYSTEM_DIR / "ownership.toml"
    if ownership_path.exists():
        return hashlib.sha256(ownership_path.read_bytes()).hexdigest()

    # No ownership file — hash the default config
    if load_memory_ownership is not None:
        ownership = load_memory_ownership(project_root)
        config_json = json.dumps(ownership.to_dict(), sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()

    # Fallback: hash empty string
    return hashlib.sha256(b"").hexdigest()


def _classify_entry(
    rel_path_str: str,
    project_root: Path,
) -> tuple[str, str, str]:
    """M4: Classify a path for manifest entry metadata.

    Returns:
        (ownership_id, protection_level, classification_source) tuple.
    """
    if classify_owned_path is not None:
        ownership = load_memory_ownership(project_root) if load_memory_ownership is not None else None
        result = classify_owned_path(rel_path_str, ownership, project_root)

        if isinstance(result, Owned):
            if result.resource is not None:
                return (
                    result.resource.name,
                    result.level.name.lower(),
                    "resource",
                )
            if result.domain is not None:
                return (
                    result.domain.name,
                    result.level.name.lower(),
                    "domain",
                )

    return ("none", "none", "none")


def _discover_canonical_files(project_root: Path) -> list[Path]:
    """Discover all signable files in a project.

    Returns list of absolute paths that exist.
    """
    resolved_root = project_root.resolve()
    found: list[Path] = []
    for pattern in CANONICAL_PATTERNS:
        p = resolved_root / pattern
        if p.exists() and p.is_file():
            found.append(p.resolve())

    # Also sign date-partitioned artifact files
    for art_pattern in ARTIFACT_PATTERNS:
        art_root = resolved_root / art_pattern
        if art_root.exists() and art_root.is_dir():
            for sub in art_root.rglob("*"):
                if sub.is_file() and sub.suffix in (".json", ".jsonl", ".log"):
                    found.append(sub.resolve())

    # M4: Discover owned files from ownership configuration
    if load_memory_ownership is not None:
        try:
            ownership = load_memory_ownership(project_root)
            for domain in ownership.domains:
                if not domain.recursive:
                    # Non-recursive: only the domain directory index itself
                    domain_path = resolved_root / domain.path
                    if domain_path.exists() and domain_path.is_dir():
                        for child in sorted(domain_path.iterdir()):
                            if child.is_file():
                                found.append(child.resolve())
                else:
                    # Recursive: walk the entire domain tree
                    domain_path = resolved_root / domain.path
                    if domain_path.exists() and domain_path.is_dir():
                        for child in sorted(domain_path.rglob("*")):
                            if child.is_file():
                                found.append(child.resolve())
            for resource in ownership.resources:
                # Support glob patterns in resource paths
                if "*" in resource.path or "?" in resource.path:
                    # Find the base directory from the glob pattern
                    parts = resource.path.split("/")
                    base_parts = []
                    for part in parts:
                        if "*" in part or "?" in part:
                            break
                        base_parts.append(part)
                    if base_parts:
                        base_dir = resolved_root / "/".join(base_parts)
                        if base_dir.exists() and base_dir.is_dir():
                            for child in sorted(base_dir.rglob("*")):
                                if child.is_file():
                                    rel_child = str(child.relative_to(resolved_root))
                                    if fnmatch.fnmatch(rel_child, resource.path):
                                        found.append(child.resolve())
                    else:
                        # Glob at root level
                        for child in sorted(resolved_root.rglob("*")):
                            if child.is_file():
                                rel_child = str(child.relative_to(resolved_root))
                                if fnmatch.fnmatch(rel_child, resource.path):
                                    found.append(child.resolve())
                else:
                    res_path = resolved_root / resource.path
                    if res_path.exists() and res_path.is_file():
                        found.append(res_path.resolve())
        except Exception:
            pass  # Fall through to canonical patterns only

    # Note: do NOT sign the current manifest.json to avoid chicken-egg problem.
    # The manifest is a one-way snapshot; next signing run captures new state.

    # Deduplicate and sort, excluding volatile runtime files and manifest itself
    seen = set()
    unique = []
    for p in sorted(found):
        if p not in seen:
            seen.add(p)
            try:
                rel = str(p.relative_to(resolved_root))
            except ValueError:
                rel = str(p)
            # Skip manifest.json itself (chicken-egg problem)
            if rel == f"{SYSTEM_DIR}/{MANIFEST_FILENAME}":
                continue
            if _is_volatile(rel):
                continue
            unique.append(p)
    return unique


# M3: is_memory_core_source_repo now imported from memory_core.ownership


def sign_project(
    project_root: Path,
    key: bytes,
    *,
    now_iso: Any | None = None,
) -> dict[str, Any] | None:
    """Sign all canonical files in a project and write manifest.json.

    M4: Signing scope is now derived from ownership domains/resources.
    Source repo: zero file side-effects (returns None, does not write).

    Args:
        project_root: Absolute path to project root (git root)
        key: 32-byte HMAC key
        now_iso: Optional callable returning ISO timestamp string

    Returns:
        The manifest dict that was written, or None if skipped (anti-pollution)
    """
    # M3 + M4.5: Anti-pollution: Skip if project_root is memory-core source repo
    # Source repo readonly: sign must not read or write any files (zero side-effects)
    if is_memory_core_source_repo is not None and is_memory_core_source_repo(project_root):
        return None

    if is_denied_project_root(project_root):
        return None

    if now_iso is None:
        def now_iso():
            return datetime.now(timezone.utc).isoformat(timespec="seconds")

    resolved_root = project_root.resolve()
    files = _discover_canonical_files(resolved_root)
    timestamp = now_iso()

    # M4: Compute ownership digest for manifest header
    ownership_digest = _compute_ownership_digest(resolved_root)

    entries: list[dict[str, Any]] = []

    for fpath in files:
        if not fpath.exists():
            continue
        rel = fpath.relative_to(resolved_root)
        rel_str = str(rel).replace("\\", "/")
        raw = fpath.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        hm = _hmac.new(key, raw, hashlib.sha256).hexdigest()

        # M4: Classify entry for ownership metadata
        ownership_id, protection_level, classification_source = _classify_entry(
            rel_str, resolved_root
        )

        entries.append({
            "path": str(fpath),
            "rel_path": rel_str,
            "sha256": sha,
            "hmac_sha256": hm,
            "size_bytes": fpath.stat().st_size,
            "signed_at": timestamp,
            # M4: Manifest v2 fields
            "ownership_id": ownership_id,
            "protection_level": protection_level,
            "classification_source": classification_source,
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(resolved_root),
        "generated_at": timestamp,
        "key_fingerprint": _key_fingerprint(key),
        "ownership_digest": ownership_digest,
        "entry_count": len(entries),
        "entries": entries,
    }

    # Write manifest to memory/system/
    memory_dir = resolved_root / SYSTEM_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = memory_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return manifest


AUDIT_LOG_FILENAME = "integrity-audit.jsonl"


def _write_audit_log(
    project_root: Path,
    action: str,
    changed_paths: list[str] | None = None,
    entry_count: int = 0,
    reason: str | None = None,
    now_iso: str | None = None,
) -> None:
    """Append an audit log entry to integrity-audit.jsonl.

    Each signing operation (full or incremental) records one JSON line
    with timestamp, action type, changed paths, and metadata.

    Args:
        project_root: Absolute path to project root
        action: "full-sign", "incremental-sign", or "resign"
        changed_paths: List of relative paths that were re-signed
        entry_count: Number of entries in the resulting manifest
        reason: Optional reason string (e.g., "memory-init baseline")
        now_iso: Optional ISO timestamp string
    """
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    audit_entry = {
        "timestamp": now_iso,
        "action": action,
        "project_root": str(project_root.resolve()),
        "changed_paths": changed_paths or [],
        "entry_count": entry_count,
    }
    if reason is not None:
        audit_entry["reason"] = reason

    memory_dir = project_root.resolve() / SYSTEM_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)
    audit_path = memory_dir / AUDIT_LOG_FILENAME

    line = json.dumps(audit_entry, ensure_ascii=False) + "\n"
    with audit_path.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def sign_project_incremental(
    project_root: Path,
    key: bytes,
    changed_paths: list[str],
    *,
    now_iso: Any | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    """Sign only the changed files in a project and write updated manifest.json.

    Reads the existing manifest, re-computes SHA-256 + HMAC-SHA256 for files
    in changed_paths, and preserves unchanged entries verbatim.

    If no manifest exists, falls back to sign_project() full signing.

    F3: Source repo: zero file side-effects (returns None, does not write).

    Args:
        project_root: Absolute path to project root (git root)
        key: 32-byte HMAC key
        changed_paths: List of relative paths to re-sign
        now_iso: Optional callable returning ISO timestamp string
        reason: Optional reason for audit log (e.g., "memory-init baseline")

    Returns:
        The manifest dict that was written, or None if skipped (anti-pollution)
    """
    # Anti-pollution: Skip if project_root is memory-core source repo
    if is_memory_core_source_repo is not None and is_memory_core_source_repo(project_root):
        return None

    if is_denied_project_root(project_root):
        return None

    if now_iso is None:
        def now_iso_fn():
            return datetime.now(timezone.utc).isoformat(timespec="seconds")
    elif callable(now_iso):
        now_iso_fn = now_iso
    else:
        def _constant_now_iso():
            return now_iso
        now_iso_fn = _constant_now_iso

    resolved_root = project_root.resolve()
    memory_dir = resolved_root / SYSTEM_DIR
    manifest_path = memory_dir / MANIFEST_FILENAME

    # Fallback to full sign if manifest doesn't exist
    if not manifest_path.exists():
        _logger.info(
            "sign_project_incremental: manifest not found, falling back to full sign"
        )
        result = sign_project(resolved_root, key, now_iso=now_iso_fn)
        # Write audit log for the fallback full-sign with reason
        if result is not None:
            _write_audit_log(
                resolved_root,
                action="full-sign",
                changed_paths=list(changed_paths),
                entry_count=result.get("entry_count", 0),
                reason=reason,
                now_iso=now_iso_fn(),
            )
        return result

    # Load existing manifest
    try:
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _logger.warning("sign_project_incremental: failed to load manifest: %s", exc)
        return sign_project(resolved_root, key, now_iso=now_iso_fn)

    # Build a lookup of existing entries by rel_path
    entries_by_rel: dict[str, dict[str, Any]] = {}
    for entry in existing_manifest.get("entries", []):
        entries_by_rel[entry["rel_path"]] = entry

    timestamp = now_iso_fn()
    ownership_digest = _compute_ownership_digest(resolved_root)

    # Re-sign changed files
    for rel_path_str in changed_paths:
        abs_path = resolved_root / rel_path_str
        if not abs_path.exists():
            # File was deleted — remove from manifest
            entries_by_rel.pop(rel_path_str, None)
            continue

        raw = abs_path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        hm = _hmac.new(key, raw, hashlib.sha256).hexdigest()

        # M4: Classify entry for ownership metadata
        ownership_id, protection_level, classification_source = _classify_entry(
            rel_path_str, resolved_root
        )

        entries_by_rel[rel_path_str] = {
            "path": str(abs_path),
            "rel_path": rel_path_str,
            "sha256": sha,
            "hmac_sha256": hm,
            "size_bytes": abs_path.stat().st_size,
            "signed_at": timestamp,
            # M4: Manifest v2 fields
            "ownership_id": ownership_id,
            "protection_level": protection_level,
            "classification_source": classification_source,
        }

    # Rebuild entries list (preserving original order for unchanged entries)
    original_order = [e["rel_path"] for e in existing_manifest.get("entries", [])]
    seen_in_order: set[str] = set()
    new_entries: list[dict[str, Any]] = []

    # First, walk original order to preserve it for unchanged entries
    for rp in original_order:
        if rp in entries_by_rel and rp not in seen_in_order:
            seen_in_order.add(rp)
            new_entries.append(entries_by_rel[rp])

    # Then add any new entries that weren't in original order
    for rp, entry in entries_by_rel.items():
        if rp not in seen_in_order:
            new_entries.append(entry)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(resolved_root),
        "generated_at": timestamp,
        "key_fingerprint": _key_fingerprint(key),
        "ownership_digest": ownership_digest,
        "entry_count": len(new_entries),
        "entries": new_entries,
    }

    # Write manifest with fcntl.flock exclusive lock
    memory_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # Write audit log
    _write_audit_log(
        resolved_root,
        action="incremental-sign",
        changed_paths=list(changed_paths),
        entry_count=len(new_entries),
        reason=reason,
        now_iso=timestamp,
    )

    return manifest
