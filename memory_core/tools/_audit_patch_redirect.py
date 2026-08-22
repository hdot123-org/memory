#!/usr/bin/env python3.12
"""daily_kb_audit 拆分后的 monkeypatch 目标重定向（兼容层）。

背景：daily_kb_audit.py 已拆分为 5 个单一职责模块（_audit_project /
_audit_checks / _audit_infra / _audit_server / _audit_report / _audit_cli）。
测试历史上通过 ``patch("memory_core.tools.daily_kb_audit.X", mock)`` /
``monkeypatch.setattr("memory_core.tools.daily_kb_audit.X", ...)`` 打桩，
但拆分后运行时在各子模块自己的命名空间查找符号，直接改门面属性不再生效。

方案：将门面模块的类替换为 ``_RedirectModule``，其 ``__setattr__`` 会把
「拆分后仍被子模块本地引用的符号」写入到所有消费它的子模块命名空间，
使旧的打桩目标语义保持不变（不改测试、不改断言）。

与 _gateway_patch_redirect 同构，仅目标表不同：
- 未知的新属性仍正常写到门面自身（保持普通模块行为）。
- ``del``（monkeypatch 还原）同理撤销所有写入点。
"""

from __future__ import annotations

import contextlib
import sys
import types
from typing import Any

# 符号 → 拆分后运行时实际查找该符号的模块（可多个）。
# 维护规则：新增子模块消费某符号时，在此登记。
_REDIRECT_TARGETS: dict[str, tuple[str, ...]] = {
    # ---- _audit_cli 查找的符号（main / _run_infra_check / _handle_no_projects 等）----
    "main": ("_audit_cli",),
    "_run_infra_check": ("_audit_cli",),
    "_handle_no_projects": ("_audit_cli",),
    "_audit_all_projects": ("_audit_cli",),
    "_summarize_to_console": ("_audit_cli",),
    "_count_critical_infra": ("_audit_cli",),
    "_count_warning_infra": ("_audit_cli",),
    "check_infrastructure": ("_audit_cli",),
    "load_registered_projects": ("_audit_cli",),
    "build_global_kb_fingerprints": ("_audit_cli",),
    "audit_project": ("_audit_cli",),
    "build_report": ("_audit_cli",),
    "write_report": ("_audit_cli",),
    "notify_via_lark": ("_audit_cli",),
    "LIFECYCLE_INDEX": ("_audit_cli", "_audit_project"),
    "_make_violation": ("_audit_cli",),
    # ---- _audit_server 查找的符号（check_server / check_database / audit_project）----
    "check_server": ("_audit_server",),
    "check_database": ("_audit_server",),
    "_load_infra_inventory": ("_audit_server",),
    "check_ssh_reachable": ("_audit_server",),
    "_run_ssh": ("_audit_server", "_audit_infra"),
    "_tcp_connect_ok": ("_audit_server", "_audit_infra"),
    "_check_systemd_services": ("_audit_server",),
    "check_disk_space": ("_audit_server",),
    "is_memory_core_source_repo": ("_audit_server",),
    "check_manifest_integrity": ("_audit_server",),
    "check_unsigned_files": ("_audit_server",),
    "check_global_residue": ("_audit_server",),
    "check_large_or_db_files": ("_audit_server",),
    "check_version_consistency": ("_audit_server",),
    # ---- _audit_checks 查找的符号（检查 1-5 内部）----
    "_sha256_file": ("_audit_checks",),
    "CURRENT_MEMORY_VERSION": ("_audit_checks",),
    # ---- _audit_infra 查找的符号（清单加载 / SSH）----
    "_HAS_YAML": ("_audit_infra",),
    "INFRA_INVENTORY": ("_audit_infra",),
    "yaml": ("_audit_infra",),
    # ---- _audit_report 查找的符号（报告/通知）----
    "AUDIT_DIR": ("_audit_report",),
    # ---- _audit_project 查找的符号（常量与项目加载）----
    "GLOBAL_KB_ROOT": ("_audit_project",),
    "GLOBAL_KB_DOMAINS": ("_audit_project",),
    "GLOBAL_KB_SKIP": ("_audit_project",),
}

# 门面自身持有的属性在重定向模块中不拦截写入（避免 import 期递归）。
_HANDLED_ATTRS = frozenset(_REDIRECT_TARGETS)

# 锚点函数：目标模块中的代表函数。测试 purge 并重新 import 子模块后，
# 旧模块对象可能已从 sys.modules 移除、但仍被门面引用，通过锚点函数的
# __globals__ 定位这些「孤儿」命名空间。
_MODULE_ANCHORS: dict[str, tuple[str, ...]] = {
    "_audit_project": ("load_registered_projects", "build_global_kb_fingerprints"),
    "_audit_checks": ("check_manifest_integrity", "check_version_consistency"),
    "_audit_infra": ("_load_infra_inventory", "_run_ssh"),
    "_audit_server": ("check_server", "audit_project"),
    "_audit_report": ("build_report", "notify_via_lark"),
    "_audit_cli": ("main",),
}


class _RedirectModule(types.ModuleType):
    """把符号写入同步到拆分子模块的模块类。"""

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        self._redirect_set(name, value)

    def __delattr__(self, name: str) -> None:
        super().__delattr__(name)
        self._redirect_del(name)

    def _redirect_set(self, name: str, value: object) -> None:
        targets = _REDIRECT_TARGETS.get(name)
        if targets is None:
            return
        parent = __name__.rsplit(".", 1)[0]
        for mod_name in targets:
            for ns in _resolve_target_dicts(self, parent, mod_name):
                if ns.get(name) is not value:
                    ns[name] = value

    def _redirect_del(self, name: str) -> None:
        targets = _REDIRECT_TARGETS.get(name)
        if targets is None:
            return
        parent = __name__.rsplit(".", 1)[0]
        for mod_name in targets:
            for ns in _resolve_target_dicts(self, parent, mod_name):
                if name in ns:
                    with contextlib.suppress(KeyError):
                        del ns[name]


def _resolve_target_dicts(gateway_module: types.ModuleType, parent: str, mod_name: str) -> list[dict[str, Any]]:
    """解析目标模块命名空间的所有存活实例（sys.modules + 孤儿模块）。

    返回可直接写入的命名空间 dict：
    - sys.modules 中登记的模块 ``__dict__``
    - 孤儿模块：已从 sys.modules 移除、但旧门面仍持有其函数引用的模块。
      通过门面属性（或 sys.modules 模块）中锚点函数的 ``__globals__`` 定位。
    """
    full = f"{parent}.{mod_name}"
    dicts: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _try_add(ns: Any) -> None:
        if isinstance(ns, dict) and ns.get("__name__") == full and id(ns) not in seen:
            dicts.append(ns)
            seen.add(id(ns))

    mod = sys.modules.get(full)
    if mod is not None:
        _try_add(mod.__dict__)

    for anchor_name in _MODULE_ANCHORS.get(mod_name, ()):
        # 门面自身属性（可能是孤儿模块的函数）与 sys.modules 模块的属性
        for holder in (gateway_module, mod):
            anchor_fn = getattr(holder, anchor_name, None)
            if anchor_fn is not None:
                _try_add(getattr(anchor_fn, "__globals__", None))
    return dicts


def install_redirect(gateway_module: types.ModuleType) -> None:
    """把门面模块的类替换为重定向模块类（幂等）。"""
    gateway_module.__class__ = _RedirectModule


__all__ = ["install_redirect", "_REDIRECT_TARGETS", "_HANDLED_ATTRS"]
