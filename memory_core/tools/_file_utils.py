# -*- coding: utf-8 -*-
"""
File utility functions for exclusive locking and ISO timestamps.

Consolidates 4 independent fcntl.flock implementations and 8 _now_iso copies.

Part of REF-001 strangler fig scaffold phase.

Note: fcntl is POSIX-only. Windows support is not added (memory-core has
never supported Windows).
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from datetime import datetime
from typing import IO, Iterator


@contextmanager
def exclusive_lock(file_obj: IO[str], *, label: str = "") -> Iterator[None]:
    """POSIX exclusive file lock context manager (blocking).

    Usage:
        with open(path, "a") as f:
            with exclusive_lock(f, label="metrics"):
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

    Args:
        file_obj: File object to lock
        label: Optional label for debugging/logging
    """
    fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


@contextmanager
def try_exclusive_lock(file_obj: IO[str], *, label: str = "") -> Iterator[bool]:
    """Non-blocking POSIX exclusive file lock.

    Yields True if the lock was acquired, False if contended (another process
    holds it). Callers should check the yielded value and skip work on False.
    Designed for lossy-tolerant writers (e.g. telemetry/metrics) where blocking
    under contention is worse than dropping one record.

    Usage:
        with open(path, "a") as f:
            with try_exclusive_lock(f) as acquired:
                if not acquired:
                    return  # contended, drop this record
                f.write(data)

    Args:
        file_obj: File object to lock
        label: Optional label for debugging/logging
    """
    try:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Lock contended (EWOULDBLOCK) — caller should skip
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def now_iso() -> str:
    """Unified ISO timestamp (resolves 8 _now_iso copies).

    Returns:
        Current local time as ISO 8601 string with timezone
    """
    return datetime.now().astimezone().isoformat(timespec="seconds")
