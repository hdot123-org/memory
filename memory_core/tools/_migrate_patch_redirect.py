#!/usr/bin/env python3.12
"""migrate_project_memory 拆分后的 monkeypatch 目标重定向（M3 兼容层）。

背景：migrate_project_memory.py 已拆分为单一职责模块
（_migrate_constants / _migrate_hooks / _migrate_v05 / _migrate_registry /
_migrate_rollback / _migrate_orchestration / _migrate_cli）。测试历史上通过
``monkeypatch.setattr(mod, "MIGRATION_REGISTRY", {...})`` /
``monkeypatch.setattr(mod, "_create_backup", ...)`` /
``monkeypatch.setattr(mod, "execute_rollback", ...)`` 在门面上打桩，但拆分
后运行时在各子模块自己的命名空间查找符号，直接改门面属性不再生效。

方案（与 _gateway_patch_redirect / _audit_patch_redirect 同构；机制实现
收敛于 _patch_redirect_shared，本文件只维护 migrate 特有的目标表）：
将门面模块的类替换为 ``_RedirectModule``，其 ``__setattr__`` 会把
「拆分后仍被子模块本地引用的符号」写入到所有消费它的子模块命名空间，
使旧的打桩目标语义保持不变（不改测试、不改断言）。

- 未知的新属性仍正常写到门面自身（保持普通模块行为）。
- ``del``（monkeypatch 还原）同理撤销所有写入点。
"""

from __future__ import annotations

import types

from ._patch_redirect_shared import install_redirect as _install_redirect_shared

# 符号 → 拆分后运行时实际查找该符号的模块（可多个）。
# 维护规则：新增子模块消费某符号时，在此登记。
_REDIRECT_TARGETS: dict[str, tuple[str, ...]] = {
    # _migrate_orchestration 查找的符号（discover_migrations / MIGRATION_REGISTRY /
    # _create_backup / execute_rollback 是 test_migrate_idempotent_rollback 的打桩目标）
    "MIGRATION_REGISTRY": ("_migrate_registry", "_migrate_orchestration"),
    "discover_migrations": ("_migrate_orchestration",),
    "_create_backup": ("_migrate_orchestration",),
    "execute_rollback": ("_migrate_orchestration", "_migrate_cli"),
    "append_migration_log": ("_migrate_orchestration",),
    "_append_migrations_log": ("_migrate_orchestration", "_migrate_rollback"),
    "plan_rollback": ("_migrate_orchestration", "_migrate_cli"),
    "_find_v05_backup": ("_migrate_cli",),
    "migrate_project_memory": ("_migrate_cli",),
    "_check_evidence_refs": ("_migrate_orchestration",),
    # _migrate_registry 查找的符号（迁移函数本体）
    "migrate_v010_to_v020": ("_migrate_registry",),
    "migrate_v040_to_v050": ("_migrate_registry",),
    "migrate_v070_to_v080": ("_migrate_registry",),
}

# 门面自身持有的属性在重定向模块中不拦截写入（避免 import 期递归）。
_HANDLED_ATTRS = frozenset(_REDIRECT_TARGETS)

# 锚点函数：目标模块中的代表函数。测试 purge 并重新 import 子模块后，
# 旧模块对象可能已从 sys.modules 移除、但仍被门面引用，通过锚点函数的
# __globals__ 定位这些「孤儿」命名空间。
_MODULE_ANCHORS: dict[str, tuple[str, ...]] = {
    "_migrate_constants": ("_parse_version_tuple", "_write_toml_memory_lock"),
    "_migrate_hooks": ("_generate_default_ownership_toml", "_upgrade_manifest_v1_to_v2"),
    "_migrate_v05": ("migrate_v040_to_v050",),
    "_migrate_registry": ("migrate_v010_to_v020", "migrate_v070_to_v080"),
    "_migrate_rollback": ("_create_backup", "execute_rollback"),
    "_migrate_orchestration": ("migrate_project_memory", "_handle_migration_exception"),
    "_migrate_cli": ("main", "_handle_rollback"),
}


def install_redirect(gateway_module: types.ModuleType) -> None:
    """把门面模块的类替换为重定向模块类（幂等）。"""
    _install_redirect_shared(gateway_module, _REDIRECT_TARGETS, _MODULE_ANCHORS)


__all__ = ["install_redirect", "_REDIRECT_TARGETS", "_HANDLED_ATTRS"]
