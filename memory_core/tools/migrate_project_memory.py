#!/usr/bin/env python3.12
"""Migrate a project's .memory/ directory between schema versions.

M3 拆分：本文件仅做向后兼容的 re-export 门面，全部实现移入单一职责模块：

- _migrate_constants:      名称/路径常量、降级拒绝常量、版本解析、TOML 写入工具（最底层）
- _migrate_hooks:          M6 ownership.toml 默认生成、manifest v1→v2 升级
- _migrate_v05:            0.4.0→0.5.0 目录布局迁移（备份/scope/搬迁/清理/版本重写）
- _migrate_registry:       0.1.0→0.2.0 与 0.7.0→0.8.0 迁移、MIGRATION_REGISTRY、
                           discover_migrations、migrations.log 原子追加
- _migrate_rollback:       迁移前备份、备份发现、plan/execute 软回滚、当前版本读取
- _migrate_orchestration:  migrate_project_memory 主流程（Phase 1-8 编排）
- _migrate_cli:            参数解析、--rollback 处理、输出格式化、main 入口

注意：``_check_evidence_refs`` 的实现保留在本门面文件中
（tests/test_migrate_project_memory_silent_swallow.py 对本文件做静态源码
检查），编排模块通过 sys.modules 反查门面调用，保持单一实现。

Usage:
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0 --dry-run
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0 --json

Features:
    - from/to version parameters
    - Idempotent: already at target → noop
    - Downgrade explicit reject
    - Pre-migration backup
    - migrations.log atomic append (fcntl on POSIX)
    - Soft rollback (plan + execute)
    - Auto-rollback on failure
    - Dry-run mode

Exit codes:
    0 — migration succeeded (or dry-run completed)
    1 — migration failed
    2 — usage error (bad args, missing files, etc.)

兼容性：
- 包内导入使用相对导入（``from ._migrate_constants import ...``）
- 裸模块导入（把 tools 目录加进 sys.path 的场景）回退到绝对导入
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# consistency_check.check_required_imports_from_constants 要求本文件从
# memory_core.constants 导入；版本常量同时供 docstring 版本输出使用。
from memory_core.constants import CURRENT_MEMORY_VERSION

if __package__:
    # ── 包内导入（正常路径）──────────────────────────────────────────
    from ._migrate_cli import (  # noqa: F401
        _build_migrate_parser,
        _emit_json_output,
        _emit_text_output,
        _handle_rollback,
        main,
    )
    from ._migrate_constants import (  # noqa: F401
        _CURRENT_NEWER_THAN_TARGET,
        _DOWNGRADE_NOT_SUPPORTED,
        ADAPTER_TOML_NAME,
        BACKUP_MANIFEST_NAME,
        BACKUPS_DIR_NAME,
        MEMORY_LOCK_NAME,
        MIGRATIONS_LOG_NAME,
        V05_BACKUP_LABEL,
        V05_SYSTEM_DIR,
        _parse_version_tuple,
        _serialize_adapter_toml,
        _write_toml_memory_lock,
    )
    from ._migrate_hooks import (  # noqa: F401
        MANIFEST_FILENAME,
        OWNERSHIP_TOML_NAME,
        _generate_default_ownership_toml,
        _upgrade_manifest_v1_to_v2,
    )
    from ._migrate_orchestration import (  # noqa: F401
        _check_evidence_refs_via_facade,
        _check_idempotency_and_downgrade,
        _execute_migrations,
        _handle_migration_exception,
        _perform_backup,
        _resolve_memory_root,
        _run_post_migration_hooks,
        _validate_versions,
        migrate_project_memory,
    )
    from ._migrate_patch_redirect import install_redirect as install_redirect  # noqa: F401
    from ._migrate_registry import (  # noqa: F401
        MIGRATION_REGISTRY,
        _append_migrations_log,
        append_migration_log,
        discover_migrations,
        migrate_v010_to_v020,
        migrate_v070_to_v080,
    )
    from ._migrate_rollback import (  # noqa: F401
        _create_backup,
        _find_v05_backup,
        _read_current_version,
        execute_rollback,
        plan_rollback,
    )
    from ._migrate_v05 import (  # noqa: F401
        migrate_v040_to_v050,
    )
else:
    # ── 裸模块导入回退（tools 目录在 sys.path 上时）─────────────────
    from memory_core.tools._migrate_cli import (  # noqa: F401
        _build_migrate_parser,
        _emit_json_output,
        _emit_text_output,
        _handle_rollback,
        main,
    )
    from memory_core.tools._migrate_constants import (  # noqa: F401
        _CURRENT_NEWER_THAN_TARGET,
        _DOWNGRADE_NOT_SUPPORTED,
        ADAPTER_TOML_NAME,
        BACKUP_MANIFEST_NAME,
        BACKUPS_DIR_NAME,
        MEMORY_LOCK_NAME,
        MIGRATIONS_LOG_NAME,
        V05_BACKUP_LABEL,
        V05_SYSTEM_DIR,
        _parse_version_tuple,
        _serialize_adapter_toml,
        _write_toml_memory_lock,
    )
    from memory_core.tools._migrate_hooks import (  # noqa: F401
        MANIFEST_FILENAME,
        OWNERSHIP_TOML_NAME,
        _generate_default_ownership_toml,
        _upgrade_manifest_v1_to_v2,
    )
    from memory_core.tools._migrate_orchestration import (  # noqa: F401
        _check_evidence_refs_via_facade,
        _check_idempotency_and_downgrade,
        _execute_migrations,
        _handle_migration_exception,
        _perform_backup,
        _resolve_memory_root,
        _run_post_migration_hooks,
        _validate_versions,
        migrate_project_memory,
    )
    from memory_core.tools._migrate_patch_redirect import (  # noqa: F401
        install_redirect as install_redirect,
    )
    from memory_core.tools._migrate_registry import (  # noqa: F401
        MIGRATION_REGISTRY,
        _append_migrations_log,
        append_migration_log,
        discover_migrations,
        migrate_v010_to_v020,
        migrate_v070_to_v080,
    )
    from memory_core.tools._migrate_rollback import (  # noqa: F401
        _create_backup,
        _find_v05_backup,
        _read_current_version,
        execute_rollback,
        plan_rollback,
    )
    from memory_core.tools._migrate_v05 import (  # noqa: F401
        migrate_v040_to_v050,
    )

# ---------------------------------------------------------------------------
# Phase 7: evidence ref 校验（实现保留在门面，见模块 docstring）
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def _check_evidence_refs(
    target: Path,
    result: dict[str, Any],
) -> None:
    """Phase 7: Best-effort post-migration evidence ref validation."""
    try:
        from memory_core.tools.evidence_ref_validator import validate_evidence_refs_on_disk

        ref_errors = validate_evidence_refs_on_disk(target)
        if ref_errors:
            result["warnings"] = result.get("warnings", [])
            for err in ref_errors:
                result["warnings"].append(f"evidence ref check: {err.kb_file} has {len(err.missing_refs)} missing refs")
    except Exception as exc:
        logger.debug("migrate_project_memory._check_evidence_refs: validation failed: %s", exc)


# ---------------------------------------------------------------------------
# __all__（re-export 声明）与 monkeypatch 目标重定向安装
# ---------------------------------------------------------------------------
__all__ = [
    # _migrate_constants 常量
    "MIGRATIONS_LOG_NAME",
    "MEMORY_LOCK_NAME",
    "ADAPTER_TOML_NAME",
    "BACKUPS_DIR_NAME",
    "BACKUP_MANIFEST_NAME",
    "V05_SYSTEM_DIR",
    "V05_BACKUP_LABEL",
    "_DOWNGRADE_NOT_SUPPORTED",
    "_CURRENT_NEWER_THAN_TARGET",
    # _migrate_constants 工具函数
    "_parse_version_tuple",
    "_write_toml_memory_lock",
    "_serialize_adapter_toml",
    # _migrate_hooks（M6）
    "OWNERSHIP_TOML_NAME",
    "MANIFEST_FILENAME",
    "_generate_default_ownership_toml",
    "_upgrade_manifest_v1_to_v2",
    # _migrate_v05
    "migrate_v040_to_v050",
    # _migrate_registry
    "migrate_v010_to_v020",
    "migrate_v070_to_v080",
    "MIGRATION_REGISTRY",
    "discover_migrations",
    "_append_migrations_log",
    "append_migration_log",
    # _migrate_rollback
    "_create_backup",
    "_find_v05_backup",
    "plan_rollback",
    "execute_rollback",
    "_read_current_version",
    # _migrate_orchestration
    "_resolve_memory_root",
    "_validate_versions",
    "_check_idempotency_and_downgrade",
    "_perform_backup",
    "_execute_migrations",
    "_run_post_migration_hooks",
    "_handle_migration_exception",
    "migrate_project_memory",
    # 门面自有
    "_check_evidence_refs",
    "_check_evidence_refs_via_facade",
    # _migrate_cli
    "_build_migrate_parser",
    "_handle_rollback",
    "_emit_json_output",
    "_emit_text_output",
    "main",
    # 重导出
    "CURRENT_MEMORY_VERSION",
    # 兼容层
    "install_redirect",
]

# ---------------------------------------------------------------------------
# M3 兼容层：把对门面符号的 monkeypatch/patch.object 写入重定向到实际
# 查找该符号的子模块（保持旧测试打桩语义，详见 _migrate_patch_redirect）。
# ---------------------------------------------------------------------------
install_redirect(sys.modules[__name__])

if __name__ == "__main__":
    raise SystemExit(main())
