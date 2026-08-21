#!/usr/bin/env python3.12
"""Gateway 门面 — 所有符号从拆分模块 re-export。

M3: Gateway 拆分为 6 个单一职责模块，此文件仅做向后兼容的 re-export 层。

拆分模块：
- _gateway_config:     路径常量、适配器存储、IF-5 门面、完整性检查（最底层）
- _gateway_artifacts:  artifact/error 写入、只读 source-repo package
- _gateway_policy:     core builder 解析、业务策略委托、build_context_package
- _gateway_telemetry:  PostHog 遥测同步、prompt 日志
- _gateway_dispatch:   CWD 发现、delegate 执行、输出格式化
- _gateway_handlers:   事件处理器、main 入口、excepthook

兼容性：
- 包内导入使用相对导入（``from ._gateway_config import ...``）
- 裸模块导入（validate_memory_system 等把 tools 目录加进 sys.path 的场景）
  回退到绝对导入（``from memory_core.tools._gateway_config import ...``）
"""

from __future__ import annotations

import os
import signal
import socket as socket  # noqa: F401 — 测试 patch 目标（re-export）
import sys
from datetime import datetime as datetime  # noqa: F401 — 测试 patch 目标（re-export）
from pathlib import Path as Path  # noqa: F401 — 测试 patch 目标（re-export）

# ---------------------------------------------------------------------------
# Boot timeout handlers (VAL-SIGINT-003/005: 必须先于重量级 import 注册)
# ---------------------------------------------------------------------------
_BOOT_TIMEOUT = 8


def _boot_timeout_handler(_signum: int, _frame: object) -> None:
    os._exit(0)


def _sigint_handler(_signum: int, _frame: object) -> None:
    os._exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, _boot_timeout_handler)
    signal.alarm(_BOOT_TIMEOUT)
    signal.signal(signal.SIGINT, _sigint_handler)

if __package__:
    # ── 包内导入（正常路径）──────────────────────────────────────────
    from ._gateway_artifacts import (  # noqa: E402
        _build_readonly_source_repo_package,
        _ensure_artifact_dirs,
        _inject_health_alert,
        _launch_async_health_check,
        _update_state_dynamic_fields,
        append_error_log,
        write_artifacts,
    )
    from ._gateway_config import (  # noqa: E402
        _ADAPTER_NAME,
        _FORCE_HOOK,
        ARTIFACT_ROOT,
        BATCH_SIZE,
        CONTEXT_ROOT,
        ERROR_LOG,
        EVENT_LOG,
        NON_INJECTION_EVENTS,
        PROJECT_LIFECYCLE_ROOT,
        REPO_ROOT,
        WORKSPACE_ROOT,
        _adapter_config,
        _adapter_profile,
        _apply_hook_runtime_write_targets,
        _collect_changed_paths,
        _configured_artifact_root,
        _configured_error_log,
        _configured_invalid_memory_root,
        _configured_project_lifecycle_root,
        _existing_paths,
        _get_artifact_sink,
        _get_error_sink,
        _get_gateway_business_policy,
        _get_policy_pack_via_registry,
        _get_policy_registry,
        _get_route_policy,
        _get_write_policy,
        _get_write_targets_dict,
        _integrity_sign,
        _integrity_verify,
        _json_object_keys,
        _json_string_values,
        _load_adapter_profile,
        _logger,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _resolve_policy_conflict_via_registry,
        _resolve_route_target_via_policy,
        _section_body,
        _section_bullets,
        _write_targets_via_policy,
        exclusive_lock,
        get_config,
        get_config_dict,
        get_source_repo_mode,
        is_denied_project_root,
        is_memory_core_source_repo,
        load_adapter_config,
        now_iso,
        record_project_lifecycle,
        reload_adapter,
    )
    from ._gateway_dispatch import (  # noqa: E402
        _build_degraded_package_with_error,
        _build_factory_hook_output,
        _canonicalize_cmux_refs,
        _delegate_claude,
        _delegate_codex,
        _delegate_noop_response,
        _discover_cwd,
        _emit_fast_path_metrics,
        _environment_cwd,
        _execute_delegate,
        _execute_delegate_via_facade,
        _get_host_delegate,
        _original_cwd,
        _parse_args,
        _path_within_repo,
        _payload_cwd,
        _read_payload,
        _record_event_log_minimal,
        _record_project_lifecycle_event,
        _require_env,
        _should_noop_for_external_context,
    )
    from ._gateway_handlers import (  # noqa: E402
        HookTimeoutError,
        _dispatch_output,
        _gateway_excepthook,
        _handle_pretooluse_guard,
        _handle_source_repo_check,
        main,
    )
    from ._gateway_patch_redirect import install_redirect as install_redirect  # noqa: E402
    from ._gateway_policy import (  # noqa: E402
        _append_error_log_via_sink,
        _apply_artifact_compaction,
        _extract_excerpt,
        _git_name_only,
        _git_registration_probe,
        _load_external_core_builder,
        _normalize_repo_scope_entry,
        _path_matches_scope,
        _registration_payload_paths,
        _resolve_core_builder,
        _write_artifacts_via_sink,
        build_context_package,
        build_context_package_simple,
        decision_refs_for_scope,
        determine_project_scope,
        docs_refs_for_scope,
        event_contract_blocker_errors,
        governance_frozen_tuple_blocker_errors,
        lesson_refs_for_scope,
        project_map_refs,
        read_text_if_exists,
        resolve_route_target,
        truth_basis_for_scope,
        validate_project_map_files,
        validate_unique_legal_system_contract,
        write_targets,
    )
    from ._gateway_telemetry import (  # noqa: E402
        _log_prompt_submit,
        _maybe_sync_telemetry,
        _read_last_user_message_from_transcript,
        _sanitize_for_log,
        _write_sync_status,
    )
    from ._redaction import redact as redact  # noqa: E402
    from .memory_hook_config import CoreConfig as CoreConfig  # noqa: E402
    from .memory_hook_core import (  # noqa: E402
        build_context_package_core,
        build_context_package_from_config,
    )
    from .memory_hook_impls import ArtifactWriter as ArtifactWriter  # noqa: E402
else:
    # ── 裸模块导入回退（tools 目录在 sys.path 上时）─────────────────
    from memory_core.tools._gateway_artifacts import (  # noqa: E402
        _build_readonly_source_repo_package,
        _ensure_artifact_dirs,
        _inject_health_alert,
        _launch_async_health_check,
        _update_state_dynamic_fields,
        append_error_log,
        write_artifacts,
    )
    from memory_core.tools._gateway_config import (  # noqa: E402
        _ADAPTER_NAME,
        _FORCE_HOOK,
        ARTIFACT_ROOT,
        BATCH_SIZE,
        CONTEXT_ROOT,
        ERROR_LOG,
        EVENT_LOG,
        NON_INJECTION_EVENTS,
        PROJECT_LIFECYCLE_ROOT,
        REPO_ROOT,
        WORKSPACE_ROOT,
        _adapter_config,
        _adapter_profile,
        _apply_hook_runtime_write_targets,
        _collect_changed_paths,
        _configured_artifact_root,
        _configured_error_log,
        _configured_invalid_memory_root,
        _configured_project_lifecycle_root,
        _existing_paths,
        _get_artifact_sink,
        _get_error_sink,
        _get_gateway_business_policy,
        _get_policy_pack_via_registry,
        _get_policy_registry,
        _get_route_policy,
        _get_write_policy,
        _get_write_targets_dict,
        _integrity_sign,
        _integrity_verify,
        _json_object_keys,
        _json_string_values,
        _load_adapter_profile,
        _logger,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _resolve_policy_conflict_via_registry,
        _resolve_route_target_via_policy,
        _section_body,
        _section_bullets,
        _write_targets_via_policy,
        exclusive_lock,
        get_config,
        get_config_dict,
        get_source_repo_mode,
        is_denied_project_root,
        is_memory_core_source_repo,
        load_adapter_config,
        now_iso,
        record_project_lifecycle,
        reload_adapter,
    )
    from memory_core.tools._gateway_dispatch import (  # noqa: E402
        _build_degraded_package_with_error,
        _build_factory_hook_output,
        _canonicalize_cmux_refs,
        _delegate_claude,
        _delegate_codex,
        _delegate_noop_response,
        _discover_cwd,
        _emit_fast_path_metrics,
        _environment_cwd,
        _execute_delegate,
        _execute_delegate_via_facade,
        _get_host_delegate,
        _original_cwd,
        _parse_args,
        _path_within_repo,
        _payload_cwd,
        _read_payload,
        _record_event_log_minimal,
        _record_project_lifecycle_event,
        _require_env,
        _should_noop_for_external_context,
    )
    from memory_core.tools._gateway_handlers import (  # noqa: E402
        HookTimeoutError,
        _dispatch_output,
        _gateway_excepthook,
        _handle_pretooluse_guard,
        _handle_source_repo_check,
        main,
    )
    from memory_core.tools._gateway_patch_redirect import (  # noqa: E402
        install_redirect as install_redirect,
    )
    from memory_core.tools._gateway_policy import (  # noqa: E402
        _append_error_log_via_sink,
        _apply_artifact_compaction,
        _extract_excerpt,
        _git_name_only,
        _git_registration_probe,
        _load_external_core_builder,
        _normalize_repo_scope_entry,
        _path_matches_scope,
        _registration_payload_paths,
        _resolve_core_builder,
        _write_artifacts_via_sink,
        build_context_package,
        build_context_package_simple,
        decision_refs_for_scope,
        determine_project_scope,
        docs_refs_for_scope,
        event_contract_blocker_errors,
        governance_frozen_tuple_blocker_errors,
        lesson_refs_for_scope,
        project_map_refs,
        read_text_if_exists,
        resolve_route_target,
        truth_basis_for_scope,
        validate_project_map_files,
        validate_unique_legal_system_contract,
        write_targets,
    )
    from memory_core.tools._gateway_telemetry import (  # noqa: E402
        _log_prompt_submit,
        _maybe_sync_telemetry,
        _read_last_user_message_from_transcript,
        _sanitize_for_log,
        _write_sync_status,
    )
    from memory_core.tools._redaction import redact as redact  # noqa: E402
    from memory_core.tools.memory_hook_config import CoreConfig as CoreConfig  # noqa: E402
    from memory_core.tools.memory_hook_core import (  # noqa: E402
        build_context_package_core,
        build_context_package_from_config,
    )
    from memory_core.tools.memory_hook_impls import ArtifactWriter as ArtifactWriter  # noqa: E402

# ---------------------------------------------------------------------------
# __all__（re-export 声明）与 excepthook 安装
# ---------------------------------------------------------------------------
__all__ = [
    # _gateway_artifacts
    "_build_readonly_source_repo_package", "_ensure_artifact_dirs", "_inject_health_alert",
    "_launch_async_health_check", "_update_state_dynamic_fields", "append_error_log", "write_artifacts",
    # _gateway_config 路径常量
    "REPO_ROOT", "WORKSPACE_ROOT", "ARTIFACT_ROOT", "CONTEXT_ROOT", "EVENT_LOG", "ERROR_LOG",
    "PROJECT_LIFECYCLE_ROOT", "BATCH_SIZE", "NON_INJECTION_EVENTS", "_FORCE_HOOK",
    # _gateway_config 配置函数
    "_configured_artifact_root", "_configured_error_log", "_configured_project_lifecycle_root",
    "_configured_invalid_memory_root",
    # _gateway_config 文件工具
    "now_iso", "exclusive_lock",
    # _gateway_config 规则辅助
    "_existing_paths", "_get_write_targets_dict", "_json_object_keys", "_json_string_values",
    "_markdown_code_tokens", "_path_is_under", "_path_is_under_lexical", "_section_body", "_section_bullets",
    # _gateway_config 适配器存储
    "load_adapter_config", "reload_adapter", "get_config", "get_config_dict", "_load_adapter_profile",
    "_adapter_config", "_adapter_profile",
    # _gateway_config 所有权/生命周期
    "get_source_repo_mode", "is_memory_core_source_repo", "is_denied_project_root", "record_project_lifecycle",
    # _gateway_config 完整性
    "_integrity_sign", "_integrity_verify", "_collect_changed_paths",
    # _gateway_config IF-5 门面
    "_get_gateway_business_policy", "_get_policy_registry", "_get_route_policy", "_get_write_policy",
    "_get_artifact_sink", "_get_error_sink", "_resolve_route_target_via_policy",
    "_apply_hook_runtime_write_targets", "_write_targets_via_policy", "_get_policy_pack_via_registry",
    "_resolve_policy_conflict_via_registry",
    # _gateway_policy 核心函数
    "build_context_package", "build_context_package_simple", "_resolve_core_builder",
    "_load_external_core_builder", "_apply_artifact_compaction", "_write_artifacts_via_sink",
    "_append_error_log_via_sink",
    # _gateway_policy 业务策略委托
    "determine_project_scope", "project_map_refs", "validate_project_map_files",
    "validate_unique_legal_system_contract", "decision_refs_for_scope", "lesson_refs_for_scope",
    "docs_refs_for_scope", "truth_basis_for_scope", "write_targets", "resolve_route_target",
    "governance_frozen_tuple_blocker_errors", "event_contract_blocker_errors", "read_text_if_exists",
    # _gateway_policy git registration probe 辅助
    "_extract_excerpt", "_normalize_repo_scope_entry", "_registration_payload_paths", "_git_name_only",
    "_path_matches_scope", "_git_registration_probe",
    # _gateway_telemetry
    "_maybe_sync_telemetry", "_write_sync_status", "_read_last_user_message_from_transcript",
    "_log_prompt_submit", "_sanitize_for_log",
    # _redaction
    "redact",
    # _gateway_dispatch
    "_parse_args", "_read_payload", "_payload_cwd", "_environment_cwd", "_original_cwd",
    "_path_within_repo", "_discover_cwd", "_require_env", "_canonicalize_cmux_refs",
    "_execute_delegate_via_facade", "_delegate_codex", "_delegate_claude", "_should_noop_for_external_context",
    "_delegate_noop_response", "_build_factory_hook_output", "_build_degraded_package_with_error",
    "_execute_delegate", "_record_project_lifecycle_event", "_emit_fast_path_metrics",
    "_record_event_log_minimal", "_get_host_delegate",
    # _gateway_handlers
    "main", "_handle_pretooluse_guard", "_dispatch_output", "_gateway_excepthook",
    "_handle_source_repo_check", "HookTimeoutError",
    # 辅助模块重导出
    "_logger", "_ADAPTER_NAME", "ArtifactWriter", "CoreConfig",
    "build_context_package_core", "build_context_package_from_config",
]

sys.excepthook = _gateway_excepthook

# ---------------------------------------------------------------------------
# M3 兼容层：把对门面符号的 monkeypatch/patch.object 写入重定向到实际
# 查找该符号的子模块（保持旧测试打桩语义，详见 _gateway_patch_redirect）。
# ---------------------------------------------------------------------------
install_redirect(sys.modules[__name__])

if __name__ == "__main__":
    signal.alarm(0)
    sys.exit(main())
