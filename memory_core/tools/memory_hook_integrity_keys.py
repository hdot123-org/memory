#!/usr/bin/env python3
"""L2 Integrity Layer — Key Management.

Generates, stores, and loads HMAC-SHA256 keys for project memory integrity.
Key location: ~/.memory-core/keys/project-integrity.key
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

DEFAULT_KEY_ROOT = Path.home() / ".memory-core" / "keys"
DEFAULT_KEY_PATH = DEFAULT_KEY_ROOT / "project-integrity.key"

KEY_ENV_VAR = "MEMORY_INTEGRITY_KEY_PATH"


def _resolve_key_path() -> Path:
    env = os.environ.get(KEY_ENV_VAR)
    if env:
        return Path(env).expanduser()
    return DEFAULT_KEY_PATH


def generate_key() -> bytes:
    """Generate a 256-bit random key for HMAC-SHA256."""
    return secrets.token_bytes(32)


def load_or_create_key(path: Path | None = None) -> bytes:
    """Load existing key or generate + persist a new one.

    Returns:
        32-byte HMAC key
    """
    key_path = path or _resolve_key_path()
    if key_path.exists():
        raw = key_path.read_bytes()
        if len(raw) == 32:
            return raw
        # Corrupted key — regenerate
        key_path.unlink()
    key = generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    # Restrict permissions to owner-only
    key_path.chmod(0o600)
    return key


def load_key(path: Path | None = None) -> bytes | None:
    """Load existing key without creating. Returns None if missing."""
    key_path = path or _resolve_key_path()
    if not key_path.exists():
        return None
    raw = key_path.read_bytes()
    if len(raw) != 32:
        return None
    return raw


def key_info(path: Path | None = None) -> dict[str, Any]:
    """Return metadata about the current key."""
    key_path = path or _resolve_key_path()
    exists = key_path.exists()
    return {
        "path": str(key_path),
        "exists": exists,
        "size_bytes": key_path.stat().st_size if exists else 0,
        "permissions": oct(key_path.stat().st_mode & 0o777) if exists else None,
    }
