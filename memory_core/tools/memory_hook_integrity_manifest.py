#!/usr/bin/env python3
"""L2 Integrity Layer — Manifest Generation & Signing.

Computes SHA-256 + HMAC-SHA256 signatures for project canonical files
and writes a manifest.json to each project's .memory/ directory.

manifest.json structure:
{
  "schema_version": "integrity-manifest-v1",
  "project_root": "/abs/path/to/project",
  "generated_at": "2026-05-11T12:00:00+08:00",
  "key_fingerprint": "sha256:<first-8-hex-of-key-hash>",
  "entries": [
    {
      "path": ".memory/CANONICAL.md",
      "rel_path": "CANONICAL.md",
      "sha256": "<hex>",
      "hmac_sha256": "<hex>",
      "size_bytes": 1234,
      "signed_at": "2026-05-11T12:00:00+08:00"
    }
  ]
}
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "manifest.json"
SCHEMA_VERSION = "integrity-manifest-v1"

# Default canonical file patterns to sign within a project
CANONICAL_PATTERNS = [
    ".memory/CANONICAL.md",
    ".memory/STATE.md",
    ".memory/PLAN.md",
    ".memory/TASKS.md",
    ".memory/adapter.toml",
    "memory/system/errors.log",
]

# Date-partitioned artifact paths (sign the daily files too)
ARTIFACT_PATTERNS = [
    "artifacts/memory-hook/contexts",
    "artifacts/memory-hook/events",
]


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

    # Note: do NOT sign the current manifest.json to avoid chicken-egg problem.
    # The manifest is a one-way snapshot; next signing run captures new state.

    # Deduplicate and sort
    seen = set()
    unique = []
    for p in sorted(found):
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def sign_project(
    project_root: Path,
    key: bytes,
    *,
    now_iso: Any | None = None,
) -> dict[str, Any]:
    """Sign all canonical files in a project and write manifest.json.

    Args:
        project_root: Absolute path to project root (git root)
        key: 32-byte HMAC key
        now_iso: Optional callable returning ISO timestamp string

    Returns:
        The manifest dict that was written
    """
    if now_iso is None:
        def now_iso():
            return datetime.now(timezone.utc).isoformat(timespec="seconds")

    resolved_root = project_root.resolve()
    files = _discover_canonical_files(resolved_root)
    timestamp = now_iso()
    entries: list[dict[str, Any]] = []

    for fpath in files:
        if not fpath.exists():
            continue
        rel = fpath.relative_to(resolved_root)
        raw = fpath.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        hm = _hmac.new(key, raw, hashlib.sha256).hexdigest()
        entries.append({
            "path": str(fpath),
            "rel_path": str(rel),
            "sha256": sha,
            "hmac_sha256": hm,
            "size_bytes": fpath.stat().st_size,
            "signed_at": timestamp,
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(resolved_root),
        "generated_at": timestamp,
        "key_fingerprint": _key_fingerprint(key),
        "entry_count": len(entries),
        "entries": entries,
    }

    # Write manifest to .memory/
    memory_dir = resolved_root / ".memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = memory_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return manifest
