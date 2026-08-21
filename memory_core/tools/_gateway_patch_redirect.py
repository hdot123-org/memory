"""Gateway 拆分后的 monkeypatch 目标重定向（M3 兼容层）。

背景：memory_hook_gateway.py 已拆分为 6 个子模块。测试历史上通过
``monkeypatch.setattr(gw, "X", mock)`` / ``patch.object(gw, "X", ...)`` 打桩，
但拆分后运行时在各子模块自己的命名空间查找符号，直接改门面属性不再生效。

方案：将门面模块的类替换为 ``_RedirectModule``，其 ``__setattr__`` 会把
「拆分后仍被子模块本地引用的符号」写入到所有消费它的子模块命名空间，
使旧的打桩目标语义保持不变（不改测试、不改断言）。

- 未知的新属性仍正常写到门面自身（保持普通模块行为）。
- 已存在于门面的属性被替换时，同步写门面 + 对应子模块。
- ``del``（monkeypatch 还原）同理撤销所有写入点。
- 目标命名空间解析同时覆盖 sys.modules 中的模块与「孤儿」模块
  （被测试 purge 出 sys.modules 但仍被旧门面引用），后者通过锚点
  函数的 ``__globals__`` 定位。
"""

from __future__ import annotations

import contextlib
import sys
import types
from typing import Any

# 符号 → 拆分后运行时实际查找该符号的模块（可多个）。
# 维护规则：新增子模块消费某符号时，在此登记。
_REDIRECT_TARGETS: dict[str, tuple[str, ...]] = {
    # _gateway_handlers.main() 及各 handler 查找的符号
    "main": ("_gateway_handlers",),
    "_handle_source_repo_check": ("_gateway_handlers",),
    "_handle_pretooluse_guard": ("_gateway_handlers",),
    "_dispatch_output": ("_gateway_handlers",),
    "_gateway_excepthook": ("_gateway_handlers",),
    "_parse_args": ("_gateway_handlers",),
    "_read_payload": ("_gateway_handlers", "_gateway_dispatch"),
    "_discover_cwd": ("_gateway_handlers", "_gateway_policy", "_gateway_dispatch"),
    "_should_noop_for_external_context": ("_gateway_handlers", "_gateway_dispatch"),
    "_delegate_noop_response": ("_gateway_handlers", "_gateway_dispatch"),
    "is_denied_project_root": ("_gateway_handlers", "_gateway_config"),
    "is_memory_core_source_repo": (
        "_gateway_handlers",
        "_gateway_policy",
        "_gateway_config",
    ),
    "get_source_repo_mode": ("_gateway_handlers", "_gateway_config"),
    "build_context_package": ("_gateway_handlers", "_gateway_policy"),
    "_record_project_lifecycle_event": (
        "_gateway_handlers",
        "_gateway_policy",
        "_gateway_dispatch",
    ),
    "_emit_fast_path_metrics": ("_gateway_handlers", "_gateway_dispatch"),
    "_record_event_log_minimal": ("_gateway_handlers", "_gateway_dispatch"),
    "_execute_delegate": ("_gateway_handlers",),
    "determine_project_scope": ("_gateway_handlers", "_gateway_policy"),
    "_launch_async_health_check": ("_gateway_handlers",),
    "_update_state_dynamic_fields": ("_gateway_handlers",),
    "_maybe_sync_telemetry": ("_gateway_handlers",),
    "_log_prompt_submit": ("_gateway_handlers",),
    "ArtifactWriter": ("_gateway_handlers",),
    "_integrity_verify": ("_gateway_handlers",),
    "_integrity_sign": ("_gateway_handlers",),
    "_inject_health_alert": ("_gateway_handlers",),
    "append_error_log": ("_gateway_handlers", "_gateway_dispatch", "_gateway_artifacts"),
    "_build_readonly_source_repo_package": ("_gateway_handlers",),
    "ARTIFACT_ROOT": (
        "_gateway_handlers",
        "_gateway_dispatch",
        "_gateway_telemetry",
        "_gateway_config",
    ),
    "CONTEXT_ROOT": ("_gateway_handlers", "_gateway_artifacts", "_gateway_config"),
    "ERROR_LOG": ("_gateway_handlers", "_gateway_artifacts", "_gateway_config"),
    "EVENT_LOG": ("_gateway_handlers", "_gateway_dispatch", "_gateway_config"),
    # _gateway_dispatch 内部查找
    "_delegate_codex": ("_gateway_dispatch",),
    "_delegate_claude": ("_gateway_dispatch",),
    "_get_host_delegate": ("_gateway_dispatch",),
    "_execute_delegate_via_facade": ("_gateway_dispatch",),
    "_build_degraded_package_with_error": ("_gateway_dispatch",),
    "_build_factory_hook_output": ("_gateway_dispatch",),
    "PROJECT_LIFECYCLE_ROOT": ("_gateway_dispatch", "_gateway_config"),
    # _gateway_policy 内部查找
    "_adapter_config": ("_gateway_policy", "_gateway_config"),
    "_get_gateway_business_policy": ("_gateway_policy", "_gateway_config"),
    "project_map_refs": ("_gateway_policy",),
    "write_targets": ("_gateway_policy",),
    "validate_project_map_files": ("_gateway_policy",),
    "validate_unique_legal_system_contract": ("_gateway_policy",),
    "governance_frozen_tuple_blocker_errors": ("_gateway_policy",),
    "event_contract_blocker_errors": ("_gateway_policy",),
    "_git_registration_probe": ("_gateway_policy",),
    "truth_basis_for_scope": ("_gateway_policy",),
    "decision_refs_for_scope": ("_gateway_policy",),
    "lesson_refs_for_scope": ("_gateway_policy",),
    "docs_refs_for_scope": ("_gateway_policy",),
    "_resolve_core_builder": ("_gateway_policy",),
    "_load_external_core_builder": ("_gateway_policy",),
    "build_context_package_from_config": ("_gateway_policy",),
    "CoreConfig": ("_gateway_policy",),
    "WORKSPACE_ROOT": (
        "_gateway_policy",
        "_gateway_config",
        "_gateway_dispatch",
    ),
    "_resolve_route_target_via_policy": ("_gateway_policy",),
    # _gateway_telemetry 内部查找
    "BATCH_SIZE": ("_gateway_telemetry",),
    "socket": ("_gateway_telemetry",),
    "datetime": ("_gateway_telemetry",),
    # _gateway_config 内部查找
    "_load_adapter_profile": ("_gateway_config",),
    "_default_write_policy": ("_gateway_config",),
    "_default_route_policy": ("_gateway_config",),
    "_default_policy_registry": ("_gateway_config",),
    "_adapter_profile": ("_gateway_config",),
    # _gateway_artifacts 内部查找
    "_get_artifact_sink": ("_gateway_artifacts", "_gateway_config", "_gateway_policy"),
    "_get_error_sink": ("_gateway_artifacts", "_gateway_config", "_gateway_policy"),
    "_write_artifacts_via_sink": ("_gateway_artifacts",),
    "_append_error_log_via_sink": ("_gateway_artifacts",),
    "_get_route_policy": ("_gateway_config", "_gateway_policy"),
    "_get_policy_registry": ("_gateway_config", "_gateway_policy"),
    "_get_write_policy": ("_gateway_config",),
    "_get_policy_pack_via_registry": ("_gateway_config", "_gateway_policy"),
    "_resolve_policy_conflict_via_registry": ("_gateway_config",),
    "_write_targets_via_policy": ("_gateway_config", "_gateway_policy"),
    "_apply_hook_runtime_write_targets": ("_gateway_config", "_gateway_policy"),
}

# 门面自身持有的属性在重定向模块中不拦截写入（避免 import 期递归）。
_HANDLED_ATTRS = frozenset(_REDIRECT_TARGETS)

# 锚点函数：目标模块中的代表函数。测试 purge 并重新 import 子模块后
# （test_default_adapter_smoke._reset_to_default_adapter），旧模块对象可能
# 已从 sys.modules 移除、但仍被测试文件或旧门面引用。锚点函数的
# __globals__ 即旧模块 __dict__，据此定位这些「孤儿」命名空间。
_MODULE_ANCHORS: dict[str, tuple[str, ...]] = {
    "_gateway_config": ("get_config", "reload_adapter"),
    "_gateway_artifacts": ("append_error_log", "write_artifacts"),
    "_gateway_policy": ("build_context_package", "resolve_route_target"),
    "_gateway_telemetry": ("_maybe_sync_telemetry", "_log_prompt_submit"),
    "_gateway_dispatch": ("_execute_delegate", "_parse_args"),
    "_gateway_handlers": ("main",),
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


def _resolve_target_dicts(
    gateway_module: types.ModuleType, parent: str, mod_name: str
) -> list[dict[str, Any]]:
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
        if (
            isinstance(ns, dict)
            and ns.get("__name__") == full
            and id(ns) not in seen
        ):
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
    """把 gateway 模块的类替换为重定向模块类（幂等）。"""
    gateway_module.__class__ = _RedirectModule


__all__ = ["install_redirect", "_REDIRECT_TARGETS", "_HANDLED_ATTRS"]
