"""Version synchronization CLI wrapper (M3, INFRA-576).

The implementation lives in ``infra_core.engine.version_sync`` (migrated in
M3).  This module is a thin CLI adapter that keeps the historical
``memory-sync-versions`` console script working and injects memory-core
protocol constants (``CURRENT_MEMORY_VERSION`` / ``CANONICAL_MEMORY_LOCK_SCHEMA``)
that infra-core deliberately does not hardcode.

Manual CLI tool invoked via `memory-sync-versions`.

Design note — path-index key limitation (SPEC-013):
    The path-index (``~/.memory-core/project-lifecycle/path-index.json``) uses
    the project's *cwd* as its key, which makes global mode
    (``sync_all_known_projects``) subject to stale/missing entries.  See
    ``docs/specs/PATH_INDEX_SPEC.md`` for the full rationale of why the
    gateway session-start probe must use single-project mode only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Re-exports: the migrated implementation symbols (kept importable from this
# historical location for existing callers; listed in __all__ intentionally).
from infra_core.engine.version_sync import (  # noqa: F401  (re-export)
    SYNC_LOCK_STALE_SECONDS,
    SYNC_LOCK_WAIT_SECONDS,
    _gate_version_bump,
    _read_adapter_version,
    _read_lock_schema_version,
    _sync_lock,
    _try_resign_all,
    load_path_index,
    patch_adapter_toml_version,
    patch_memory_lock,
    patch_ownership_memory_version,
    probe_version_and_sync,
    read_ownership_memory_version,
    set_resign_hook,
    sync_all_known_projects,
    sync_single_project,
)

from memory_core.constants import CANONICAL_MEMORY_LOCK_SCHEMA, CURRENT_MEMORY_VERSION

__all__ = [
    "SYNC_LOCK_STALE_SECONDS",
    "SYNC_LOCK_WAIT_SECONDS",
    "_gate_version_bump",
    "_read_adapter_version",
    "_read_lock_schema_version",
    "_sync_lock",
    "_try_resign_all",
    "load_path_index",
    "patch_adapter_toml_version",
    "patch_memory_lock",
    "patch_ownership_memory_version",
    "probe_version_and_sync",
    "probe_version_and_sync_compat",
    "read_ownership_memory_version",
    "set_resign_hook",
    "sync_all_known_projects",
    "sync_single_project",
    "main",
]


def probe_version_and_sync_compat(project_path: Path) -> dict[str, Any] | None:
    """Backward-compat probe wrapper binding CURRENT_MEMORY_VERSION.

    The infra-core signature is ``probe_version_and_sync(path, current_version)``
    (caller-supplied protocol constant).  Callers that only have a project path
    can use this wrapper to probe against memory-core's CURRENT_MEMORY_VERSION.

    pin ≥ v0.5.1: infra-core 已为该函数标注精确返回类型
    ``dict[str, Any] | None``，历史过渡期 cast 已冗余（mypy --strict redundant-cast）。
    """
    from infra_core.engine.version_sync import probe_version_and_sync as _probe

    return _probe(project_path, CURRENT_MEMORY_VERSION)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: delegate to infra-core with memory-core protocol constants.

    The infra-core CLI requires ``--target-version``; when the operator omits
    it we default to memory-core's ``CURRENT_MEMORY_VERSION`` to preserve the
    historical ``memory-sync-versions`` UX.
    """
    args = [*argv] if argv is not None else sys.argv[1:]
    if "--target-version" not in args:
        args = [*args, "--target-version", CURRENT_MEMORY_VERSION]
    if "--canonical-schema" not in args:
        args = [*args, "--canonical-schema", CANONICAL_MEMORY_LOCK_SCHEMA]

    from infra_core.engine.version_sync import main as infra_main

    return int(infra_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
