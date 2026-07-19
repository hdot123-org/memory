"""Shared utility functions for memory_core tools.

This module contains common functions that were previously duplicated
across multiple modules (DRY principle).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    """
    Compute SHA-256 hash of a file's contents.

    Returns the hex digest string, or None if the file cannot be read.

    Args:
        path: Path to the file to hash

    Returns:
        Hex digest string or None on read error
    """
    try:
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError):
        return None
