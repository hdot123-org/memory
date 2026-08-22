#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：迁移编排（Phase 1-8 主流程）。

M3 拆分（与 _gateway_* / _audit_* 同构）：持有 migrate_project_memory
主入口及其各阶段——memory root 解析、版本校验、幂等/降级检查、迁移前
备份、顺序执行、post-migration hook、evidence ref 校验与异常自动回滚。

注意：``_check_evidence_refs`` 的实现保留在门面
migrate_project_memory.py 中（tests/test_migrate_project_memory_silent_swallow.py
对门面源码做静态检查），本模块通过 ``_check_evidence_refs_via_facade``
在运行期解析门面并调用，保持单一实现。
"""

from __future__ import annotations

import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memory_core.constants import _BACKUP_FAILED

from ._migrate_constants import (
    _CURRENT_NEWER_THAN_TARGET,
    _DOWNGRADE_NOT_SUPPORTED,
    BACKUPS_DIR_NAME,
    MIGRATIONS_LOG_NAME,
    V05_SYSTEM_DIR,
    _parse_version_tuple,
)
from ._migrate_hooks import (
    _generate_default_ownership_toml,
    _upgrade_manifest_v1_to_v2,
)
from ._migrate_registry import (
    MIGRATION_REGISTRY,
    _append_migrations_log,
    append_migration_log,
    discover_migrations,
)
from ._migrate_rollback import (
    _create_backup,
    _read_current_version,
    _write_backup_manifest,
    execute_rollback,
    plan_rollback,
)

__all__ = [
    "_check_evidence_refs_via_facade",
    "_check_idempotency_and_downgrade",
    "_execute_migrations",
    "_handle_migration_exception",
    "_perform_backup",
    "_resolve_memory_root",
    "_run_post_migration_hooks",
    "_validate_versions",
    "migrate_project_memory",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main migration logic
# ---------------------------------------------------------------------------


def _resolve_memory_root(
    target: Path,
    from_version: str,
    to_version: str,
    result: dict[str, Any],
) -> tuple[Path, bool] | None:
    """Phase 1: Resolve memory root location.

    Returns (memory_root, is_v05_plus_layout) on success, or None if an
    early-return result was written into *result* (caller should return result).
    """
    memory_root = target / ".memory"
    is_v05_plus_layout = False

    if not memory_root.is_dir():
        system_dir = target / V05_SYSTEM_DIR
        if from_version == "0.4.0" and to_version == "0.5.0" and system_dir.is_dir():
            result["success"] = True
            result["noop"] = True
            result["reason"] = "already migrated to 0.5.0"
            return None
        elif system_dir.is_dir():
            memory_root = system_dir
            is_v05_plus_layout = True
        else:
            result["errors"].append(f".memory/ directory not found at {memory_root}")
            return None

    return memory_root, is_v05_plus_layout


def _validate_versions(
    from_version: str,
    to_version: str,
    memory_root: Path,
    result: dict[str, Any],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...] | None] | None:
    """Phase 2: Parse version tuples and read current version.

    Returns (from_tuple, to_tuple, current_tuple) on success, or None on error
    (error details written into *result*).
    """
    try:
        to_tuple = _parse_version_tuple(to_version)
        from_tuple = _parse_version_tuple(from_version)
    except (ValueError, AttributeError) as exc:
        result["errors"].append(
            f"Invalid version format for migration: from={from_version!r} "
            f"to={to_version!r} ({exc}); expected SemVer-like 'MAJOR.MINOR.PATCH'"
        )
        result["error"] = "invalid_version_format"
        return None

    current_version = _read_current_version(memory_root)
    current_tuple: tuple[int, ...] | None = None
    if current_version is not None:
        try:
            current_tuple = _parse_version_tuple(current_version)
        except (ValueError, AttributeError):
            current_tuple = None

    return from_tuple, to_tuple, current_tuple


def _check_idempotency_and_downgrade(
    from_tuple: tuple[int, ...],
    to_tuple: tuple[int, ...],
    current_tuple: tuple[int, ...] | None,
    from_version: str,
    to_version: str,
    result: dict[str, Any],
) -> bool:
    """Phase 3: Check idempotency and downgrade rejection.

    Returns True if the caller should return *result* immediately (early exit),
    or False to continue with the migration.
    """
    if current_tuple is not None and current_tuple == to_tuple:
        result["success"] = True
        result["noop"] = True
        result["reason"] = "already at target version"
        return True

    if to_tuple < from_tuple:
        result["success"] = False
        result["error"] = _DOWNGRADE_NOT_SUPPORTED
        result["message"] = f"Downgrade not supported: from={from_version} to={to_version}"
        result["errors"].append(result["message"])
        return True

    if current_tuple is not None and current_tuple > to_tuple:
        current_version = ".".join(str(x) for x in current_tuple)
        result["success"] = False
        result["error"] = _CURRENT_NEWER_THAN_TARGET
        result["message"] = f"Current version ({current_version}) is newer than target ({to_version})"
        result["errors"].append(result["message"])
        return True

    return False


def _perform_backup(
    memory_root: Path,
    from_version: str,
    to_version: str,
    is_v05_plus_layout: bool,
    is_v04_to_v05: bool,
    dry_run: bool,
    result: dict[str, Any],
) -> bool:
    """Phase 4: Create pre-migration backup.

    Returns True if the caller should return *result* immediately (backup failed),
    or False to continue.
    """
    if dry_run or is_v04_to_v05:
        return False

    try:
        if is_v05_plus_layout:
            backups_dir = memory_root / BACKUPS_DIR_NAME
            backups_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            backup_dest = backups_dir / ts
            source_files_count = 0
            for p in memory_root.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(memory_root)
                    if rel.parts[0] != BACKUPS_DIR_NAME:
                        dst_path = backup_dest / rel
                        dst_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(p), str(dst_path))
                        source_files_count += 1
            _write_backup_manifest(backup_dest, from_version, to_version, source_files_count, layout="v05+")
        else:
            _create_backup(memory_root, from_version, to_version)
    except Exception as exc:
        log_path = memory_root / MIGRATIONS_LOG_NAME
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = (
            f"{now} | {from_version} | {to_version} | failed_backup_failed"
            f" | Backup creation failed: memory_root={memory_root} exc={exc}"
        )
        if log_path.is_file():
            _append_migrations_log(log_path, line)
        else:
            log_path.write_text(f"# Migrations Log\n{line}\n", encoding="utf-8")
        result["success"] = False
        result["error"] = _BACKUP_FAILED
        result["errors"].append(f"Backup creation failed for {memory_root}: {exc}")
        return True

    return False


def _execute_migrations(
    migrations: list[dict[str, Any]],
    memory_root: Path,
    target: Path,
    is_v04_to_v05: bool,
    dry_run: bool,
    result: dict[str, Any],
) -> bool:
    """Phase 5: Execute discovered migrations sequentially.

    Returns True if all migrations succeeded, False otherwise.
    """
    all_success = True
    for mig in migrations:
        mig_desc = f"{mig['from']}->{mig['to']}"

        if dry_run:
            result["migrations_executed"].append({"key": mig_desc, "status": "would_execute"})
            log_entry = append_migration_log(
                memory_root,
                mig["from"],
                mig["to"],
                "pending (dry-run)",
                f"Would migrate {mig['from']} to {mig['to']}",
                dry_run=True,
            )
            result["log_entries"].append(log_entry)
            continue

        mig_result = mig["fn"](memory_root)
        status = "success" if mig_result["success"] else "failed"
        log_root = target / V05_SYSTEM_DIR if is_v04_to_v05 else memory_root
        log_entry = append_migration_log(
            log_root,
            mig["from"],
            mig["to"],
            status,
            mig_result.get("detail", ""),
            dry_run=False,
        )
        result["log_entries"].append(log_entry)
        result["migrations_executed"].append(
            {
                "key": mig_desc,
                "status": status,
                "detail": mig_result.get("detail", ""),
            }
        )

        if mig_result.get("residue"):
            result["residue"].extend(mig_result["residue"])

        if not mig_result["success"]:
            all_success = False
            result["errors"].append(f"Migration {mig_desc} failed: {mig_result.get('detail', 'unknown')}")
            if mig_result.get("error"):
                result["error"] = mig_result["error"]
            break

    return all_success


def _run_post_migration_hooks(
    memory_root: Path,
    target: Path,
    is_v04_to_v05: bool,
    result: dict[str, Any],
) -> None:
    """Phase 6: Run post-migration hooks (ownership, manifest upgrade, rollback plan)."""
    effective_root = target / V05_SYSTEM_DIR if is_v04_to_v05 else memory_root
    if not effective_root.exists():
        effective_root = memory_root

    ownership_result = _generate_default_ownership_toml(effective_root)
    if ownership_result["success"]:
        result["residue"].append(f"ownership: {ownership_result['detail']}")
    else:
        result["residue"].append(f"ownership generation failed: {ownership_result['detail']}")

    manifest_result = _upgrade_manifest_v1_to_v2(effective_root)
    if manifest_result["success"]:
        result["residue"].append(f"manifest: {manifest_result['detail']}")
    else:
        result["residue"].append(f"manifest upgrade failed: {manifest_result['detail']}")

    rb_memory_root = target / V05_SYSTEM_DIR if (is_v04_to_v05 and not memory_root.exists()) else memory_root
    result["rollback"] = plan_rollback(rb_memory_root)


def _check_evidence_refs_via_facade(target: Path, result: dict[str, Any]) -> None:
    """Phase 7 dispatcher: run the facade-owned ``_check_evidence_refs``.

    The implementation lives in migrate_project_memory.py (the facade) because
    tests/test_migrate_project_memory_silent_swallow.py statically inspects the
    facade source for the INFRA-261 regression shape. Resolving the facade at
    call time keeps a single implementation regardless of import order:

    - package import → sys.modules["memory_core.tools.migrate_project_memory"]
    - bare-script run (tools/ on sys.path) → the facade is ``__main__``
    """
    facade = sys.modules.get("memory_core.tools.migrate_project_memory")
    if facade is None:
        main_mod = sys.modules.get("__main__")
        if main_mod is not None and hasattr(main_mod, "_check_evidence_refs") and hasattr(main_mod, "main"):
            facade = main_mod
    if facade is not None:
        facade._check_evidence_refs(target, result)  # noqa: SLF001 — 同拆分层级内部调用


def _handle_migration_exception(
    exc: Exception,
    memory_root: Path,
    target: Path,
    is_v04_to_v05: bool,
    from_version: str,
    to_version: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Phase 8: Auto-rollback on migration exception and log the outcome."""
    rb_memory_root = target / V05_SYSTEM_DIR if (is_v04_to_v05 and not memory_root.exists()) else memory_root
    try:
        rb_result = execute_rollback(rb_memory_root)
        rb_succeeded = rb_result.get("success", False)
    except Exception as rb_exc:
        rb_succeeded = False
        rb_result = {"success": False, "error": str(rb_exc)}

    log_path = memory_root / MIGRATIONS_LOG_NAME
    if not log_path.is_file():
        log_path = (target / V05_SYSTEM_DIR) / MIGRATIONS_LOG_NAME
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if rb_succeeded:
        line = f"{now} | {from_version} | {to_version} | failed_rolled_back | {exc}"
    else:
        line = (
            f"{now} | {from_version} | {to_version} | failed_rollback_failed"
            f" | Original migration error: {exc};"
            f" Rollback also failed: {rb_result.get('error', 'unknown')}"
        )

    if log_path.is_file():
        _append_migrations_log(log_path, line)

    result["success"] = False
    result["rollback_attempted"] = True
    result["rollback_succeeded"] = rb_succeeded

    if rb_succeeded:
        result["errors"].append(f"Migration failed and rolled back: {exc}")
    else:
        result["errors"].append(
            f"Migration failed and rollback also failed."
            f" Original error: {exc};"
            f" Rollback error: {rb_result.get('error', 'unknown')}"
        )
    return result


def migrate_project_memory(
    target: Path,
    from_version: str,
    to_version: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute migration on a project's .memory/ directory."""
    result: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "target": str(target.resolve()),
        "from_version": from_version,
        "to_version": to_version,
        "migrations_executed": [],
        "migrations_skipped": [],
        "log_entries": [],
        "residue": [],
        "rollback": {},
        "errors": [],
    }

    # Phase 1: Resolve memory root
    resolved = _resolve_memory_root(target, from_version, to_version, result)
    if resolved is None:
        return result
    memory_root, is_v05_plus_layout = resolved

    # Phase 2: Validate versions
    version_data = _validate_versions(from_version, to_version, memory_root, result)
    if version_data is None:
        return result
    from_tuple, to_tuple, current_tuple = version_data

    # Phase 3: Idempotency and downgrade check
    if _check_idempotency_and_downgrade(
        from_tuple,
        to_tuple,
        current_tuple,
        from_version,
        to_version,
        result,
    ):
        return result

    # Discover migrations
    migrations = discover_migrations(from_version, to_version)
    if not migrations:
        result["errors"].append(
            f"No migration path found from {from_version} to {to_version}. Available: {list(MIGRATION_REGISTRY.keys())}"
        )
        return result

    is_v04_to_v05 = any(m["from"] == "0.4.0" and m["to"] == "0.5.0" for m in migrations)

    # Phase 4: Backup
    if _perform_backup(
        memory_root,
        from_version,
        to_version,
        is_v05_plus_layout,
        is_v04_to_v05,
        dry_run,
        result,
    ):
        return result

    # Phase 5-8: Execute migrations with auto-rollback on failure
    try:
        all_success = _execute_migrations(
            migrations,
            memory_root,
            target,
            is_v04_to_v05,
            dry_run,
            result,
        )

        if all_success and not dry_run:
            _run_post_migration_hooks(memory_root, target, is_v04_to_v05, result)

        # Phase 7: evidence ref check — implementation lives in the facade
        # (static source test inspects it there); dispatch via sys.modules so
        # a patched facade implementation is honored.
        _check_evidence_refs_via_facade(target, result)

        result["success"] = all_success
        return result

    except Exception as exc:
        return _handle_migration_exception(
            exc,
            memory_root,
            target,
            is_v04_to_v05,
            from_version,
            to_version,
            result,
        )
