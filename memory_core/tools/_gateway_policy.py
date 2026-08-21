#!/usr/bin/env python3.12
"""Gateway 策略层：IF-5 门面、业务策略函数、上下文包构建。

依赖层级：依赖 _gateway_config 和 _gateway_artifacts。
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ._gateway_config import (
    REPO_ROOT,
    WORKSPACE_ROOT,
    PROJECT_LIFECYCLE_ROOT,
    get_config,
    get_config_dict,
    _adapter_config,
    _get_gateway_business_policy,
    _get_policy_registry,
    _get_route_policy,
    _get_write_policy,
    _get_artifact_sink,
    _get_error_sink,
    _resolve_route_target_via_policy,
    _apply_hook_runtime_write_targets,
    _write_targets_via_policy,
    _get_policy_pack_via_registry,
    _resolve_policy_conflict_via_registry,
    is_memory_core_source_repo,
    is_denied_project_root,
    record_project_lifecycle,
    _get_write_targets_dict,
)
from ._gateway_artifacts import (
    append_error_log,
    write_artifacts,
)
from ._gateway_telemetry import (
    _maybe_sync_telemetry,
)

# Import for build_context_package
from .memory_hook_config import CoreConfig
from .memory_hook_core import build_context_package_from_config
from .memory_hook_impls import (
    ArtifactWriter,
    resolve_host_delegate,
)
from .memory_hook_schema import convert_legacy_to_memory_v1, convert_to_v1


# ---------------------------------------------------------------------------
# Core Builder 解析
# ---------------------------------------------------------------------------

CoreBuilder = Callable[..., dict[str, Any]]


def _load_external_core_builder() -> CoreBuilder:
    """加载外部 core builder。"""
    module_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "memory_core.tools.memory_hook_core")
    func_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "build_context_package_from_config")
    
    if module_name == "memory_core.tools.memory_hook_core" and func_name == "build_context_package_from_config":
        return build_context_package_from_config
    
    module = __import__(module_name, fromlist=[func_name])
    builder = getattr(module, func_name)
    if not callable(builder):
        raise TypeError(f"external core builder is not callable: {module_name}.{func_name}")
    return cast(Callable[..., dict[str, Any]], builder)


def _resolve_core_builder(provider: str, *, allow_fallback: bool = True) -> tuple[str, CoreBuilder, list[str]]:
    """解析 core builder provider。"""
    if provider == "external-core":
        try:
            return "external-core", _load_external_core_builder(), []
        except Exception as exc:
            if not allow_fallback:
                raise
            return "legacy", build_context_package_from_config, [f"external-core load failed, fallback to legacy: {exc}"]
    return "legacy", build_context_package_from_config, []


# ---------------------------------------------------------------------------
# 业务策略函数
# ---------------------------------------------------------------------------

def determine_project_scope(cwd: Path) -> str:
    """确定项目 scope。"""
    return _get_gateway_business_policy().determine_project_scope(cwd)


def project_map_refs() -> list[str]:
    """获取 project map refs。"""
    return _get_gateway_business_policy().project_map_refs()


def validate_project_map_files() -> list[str]:
    """验证 project map 文件。"""
    return _get_gateway_business_policy().validate_project_map_files()


def validate_unique_legal_system_contract() -> list[str]:
    """验证唯一 legal system contract。"""
    return _get_gateway_business_policy().validate_unique_legal_system_contract()


def decision_refs_for_scope(project_scope: str) -> list[str]:
    """获取 decision refs for scope。"""
    return _get_gateway_business_policy().decision_refs_for_scope(project_scope)


def lesson_refs_for_scope(project_scope: str) -> list[str]:
    """获取 lesson refs for scope。"""
    return _get_gateway_business_policy().lesson_refs_for_scope(project_scope)


def docs_refs_for_scope(project_scope: str) -> list[str]:
    """获取 docs refs for scope。"""
    return _get_gateway_business_policy().docs_refs_for_scope(project_scope)


def truth_basis_for_scope(project_scope: str) -> dict[str, Any]:
    """获取 truth basis for scope。"""
    return cast(dict[str, Any], _get_gateway_business_policy().truth_basis_for_scope(project_scope))


def write_targets() -> dict[str, Any]:
    """获取 write targets。"""
    try:
        return _write_targets_via_policy()
    except Exception:
        return _apply_hook_runtime_write_targets(_get_write_targets_dict(WORKSPACE_ROOT))


def resolve_route_target(kind: str) -> str:
    """解析 route target。"""
    try:
        return _resolve_route_target_via_policy(kind)
    except (KeyError, AttributeError, TypeError) as exc:
        from ._gateway_config import _logger
        _logger.warning("route target fallback triggered: %s", exc)
        targets = write_targets()
        project_runtime_root = _get_gateway_business_policy().get_project_runtime_root()
        route_map = {
            "fact": targets["fact"],
            "global-rule": str(get_config("GLOBAL_RULE_PATH")),
            "source-material": str(WORKSPACE_ROOT / "memory" / "docs" / "references"),
            "project-runtime": str(
                project_runtime_root.get(
                    get_config("ROUTE_PROJECT_RUNTIME_SCOPE"),
                    WORKSPACE_ROOT / "projects" / get_config("ROUTE_PROJECT_RUNTIME_SCOPE"),
                )
            ),
            "system-error": targets["system_error"],
            "invalid-memory": targets["invalid_memory"],
        }
        try:
            return str(route_map[kind])
        except KeyError as exc:
            raise ValueError(f"unsupported route kind: {kind}") from exc


def governance_frozen_tuple_blocker_errors() -> list[str]:
    """获取 governance frozen tuple blocker 错误。"""
    return _get_gateway_business_policy().governance_frozen_tuple_blocker_errors()


def event_contract_blocker_errors() -> list[str]:
    """获取 event contract blocker 错误。"""
    return _get_gateway_business_policy().event_contract_blocker_errors()


def read_text_if_exists(path: Path) -> str:
    """读取文件内容，不存在返回空字符串。"""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _extract_excerpt(path: Path, max_lines: int = 12) -> list[str]:
    """提取文件前几行作为 excerpt。"""
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= max_lines:
            break
    return lines


# ---------------------------------------------------------------------------
# Git Registration Probe
# ---------------------------------------------------------------------------

def _normalize_repo_scope_entry(value: str | Path) -> str | None:
    """规范化 repo scope entry。"""
    path = Path(value).expanduser()
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _registration_payload_paths(payload: dict[str, Any]) -> list[str]:
    """从 payload 提取 registration paths。"""
    raw = payload.get("registration_paths")
    if isinstance(raw, str):
        raw_values = [raw]
    elif isinstance(raw, list):
        raw_values = [item for item in raw if isinstance(item, str)]
    else:
        return []
    
    normalized: list[str] = []
    for item in raw_values:
        normalized_item = _normalize_repo_scope_entry(item)
        if normalized_item and normalized_item not in normalized:
            normalized.append(normalized_item)
    return normalized


def _git_name_only(*args: str) -> list[str]:
    """执行 git name-only 命令。"""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _path_matches_scope(candidate: str, scope_entry: str) -> bool:
    """检查路径是否匹配 scope。"""
    normalized_scope = scope_entry.rstrip("/")
    return candidate == normalized_scope or candidate.startswith(f"{normalized_scope}/")


def _git_registration_probe(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """执行 git registration probe。"""
    map_scope = [str(path) for path in get_config("REGISTRATION_GIT_SCOPE")]
    registration_paths = _registration_payload_paths(payload)
    tracked_scope = map_scope + [str(REPO_ROOT / item) for item in registration_paths]
    
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--short", "--", *tracked_scope],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        entries = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    except subprocess.TimeoutExpired:
        entries = []
    
    try:
        head_commit = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        latest_commit = (head_commit.stdout or "").strip()
    except subprocess.TimeoutExpired:
        latest_commit = ""
    
    commit_scope: list[str] = [
        path for path in (_normalize_repo_scope_entry(p) for p in get_config("REGISTRATION_GIT_SCOPE")) if path
    ]
    commit_scope.extend(registration_paths)
    
    head_touched = _git_name_only("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", "--", *commit_scope)
    map_touched = any(
        any(_path_matches_scope(item, scope) for scope in commit_scope[: len(get_config("REGISTRATION_GIT_SCOPE"))])
        for item in head_touched
    )
    registration_touched = any(
        any(_path_matches_scope(item, scope) for scope in registration_paths)
        for item in head_touched
    )
    
    if entries:
        status = "pending-commit"
    elif not registration_paths:
        status = "awaiting-registration-payload"
    elif map_touched and registration_touched:
        status = "committed-coupled"
    else:
        status = "committed-not-proven"
    
    return {
        "phase": get_config("REGISTRATION_COMMIT_PHASE"),
        "policy": get_config("REGISTRATION_COMMIT_POLICY"),
        "gate_event": "stop",
        "triggered_on_current_event": event == "stop",
        "status": status,
        "tracked_scope": tracked_scope,
        "registration_paths": registration_paths,
        "changed_entries": entries,
        "latest_commit": latest_commit,
        "latest_commit_touched": head_touched,
        "map_scope_touched_in_latest_commit": map_touched,
        "registration_scope_touched_in_latest_commit": registration_touched,
        "scope_clean": not entries,
        "would_pass_if_enforced": status == "committed-coupled",
        "probe_ok": proc.returncode == 0,
        "stderr": proc.stderr.strip(),
    }


# ---------------------------------------------------------------------------
# 上下文包构建
# ---------------------------------------------------------------------------

def build_context_package(
    host: str,
    event: str,
    payload: dict[str, Any],
    lifecycle_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 context package。"""
    from ._gateway_dispatch import _discover_cwd, _record_project_lifecycle_event
    from ._gateway_config import EVENT_LOG, ARTIFACT_ROOT
    
    cwd = _discover_cwd(payload)
    
    if lifecycle_record is None:
        lifecycle_record = _record_project_lifecycle_event(
            host=host, event=event, payload=payload, cwd=cwd
        )
    
    project_scope = determine_project_scope(cwd)
    business_policy = _get_gateway_business_policy()
    
    config = CoreConfig(
        host=host,
        event=event,
        payload=payload,
        cwd=cwd,
        project_scope=project_scope,
        workspace_root=WORKSPACE_ROOT,
        repo_root=REPO_ROOT,
        required_canonical=business_policy.get_required_canonical(),
        project_canonical=business_policy.get_project_canonical(),
        project_runtime_root=business_policy.get_project_runtime_root(),
        global_canonical=business_policy.get_global_canonical(),
        project_map_governance=get_config("PROJECT_MAP_GOVERNANCE"),
        event_log=EVENT_LOG,
        legality_source_policy=get_config("LEGALITY_SOURCE_POLICY"),
        registration_commit_policy=get_config("REGISTRATION_COMMIT_POLICY"),
        registration_commit_phase=get_config("REGISTRATION_COMMIT_PHASE"),
        project_map_refs=project_map_refs(),
        extract_excerpt_fn=_extract_excerpt,
        now_iso_fn=lambda: datetime.now().isoformat(),
        write_targets_fn=write_targets,
        validate_project_map_fn=validate_project_map_files,
        validate_unique_legal_system_contract_fn=validate_unique_legal_system_contract,
        policy_validate_fn=lambda context: _get_policy_registry().validate(context),
        get_policy_pack_fn=_get_policy_pack_via_registry,
        governance_frozen_tuple_errors_fn=governance_frozen_tuple_blocker_errors,
        event_contract_blocker_errors_fn=event_contract_blocker_errors,
        git_registration_probe_fn=_git_registration_probe,
        truth_basis_for_scope_fn=truth_basis_for_scope,
        decision_refs_for_scope_fn=decision_refs_for_scope,
        lesson_refs_for_scope_fn=lesson_refs_for_scope,
        docs_refs_for_scope_fn=docs_refs_for_scope,
        hook_contract_path=get_config("HOOK_CONTRACT_PATH"),
        surface_id=os.environ.get("CMUX_SURFACE_ID", ""),
        workspace_id=os.environ.get("CMUX_WORKSPACE_ID", ""),
        governance_blocker_scopes=get_config("GOVERNANCE_BLOCKER_SCOPES"),
        event_contract_blocker_scopes=get_config("EVENT_CONTRACT_BLOCKER_SCOPES"),
        core_evidence_refs=get_config("CORE_EVIDENCE_REFS"),
    )
    
    requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", "legacy").strip() or "legacy"
    provider_name, provider_builder, provider_errors = _resolve_core_builder(
        requested_provider, allow_fallback=True
    )
    package = provider_builder(config) if provider_builder is not None else build_context_package_from_config(config)
    
    # Bug 3 fix: Source-repo in develop mode should not get consumer-project
    # validation errors. Skip validation layers for source-repo.
    if is_memory_core_source_repo(cwd):
        package["status"] = "ok"
        package["validation_errors"] = []
        if "missing_paths" in package:
            package["missing_paths"] = []
        if isinstance(package.get("system_context"), dict):
            package["system_context"]["source_repo_skip_validation"] = True
    
    system_context = package.setdefault("system_context", {})
    if isinstance(system_context, dict):
        system_context["core_provider"] = provider_name
        system_context["core_provider_requested"] = requested_provider
        if lifecycle_record:
            system_context["project_lifecycle"] = lifecycle_record
        if provider_errors:
            system_context["core_provider_fallback_errors"] = provider_errors
    
    if provider_errors and not is_memory_core_source_repo(cwd):
        package.setdefault("validation_errors", [])
        validation_errors = package.get("validation_errors")
        if isinstance(validation_errors, list):
            validation_errors.extend(provider_errors)
        if package.get("status") == "ok":
            package["status"] = "degraded"
    
    if os.environ.get("MEMORY_HOOK_SHADOW_RUN"):
        shadow_provider = "external-core" if provider_name == "legacy" else "legacy"
        shadow_result: dict[str, Any]
        try:
            _, shadow_builder, _ = _resolve_core_builder(shadow_provider, allow_fallback=True)
            if shadow_builder is not None:
                shadow_package = shadow_builder(config)
            else:
                shadow_package = build_context_package_from_config(config)
            shadow_result = {
                "provider": shadow_provider,
                "status": shadow_package.get("status"),
                "validation_error_count": len(shadow_package.get("validation_errors", []) or []),
                "ok": True,
            }
        except Exception as exc:
            shadow_result = {
                "provider": shadow_provider,
                "ok": False,
                "error": str(exc),
            }
        if isinstance(system_context, dict):
            system_context["shadow_run"] = shadow_result
    
    # M2: adapter-level artifact compaction policy
    _apply_artifact_compaction(package)
    
    return package


def build_context_package_simple(
    host: str,
    event: str,
    payload: dict[str, Any] | None = None,
    *,
    adapter: str | None = None,
    schema: str = "context-package-v1",
) -> dict[str, Any]:
    """Simplified 3-parameter entry point returning a schema-converted package."""
    if payload is None:
        payload = {}
    
    v2_package = build_context_package(host, event, payload)
    
    if schema == "memory-v1":
        v1_package = convert_to_v1(v2_package)
        return convert_legacy_to_memory_v1(v1_package)
    return convert_to_v1(v2_package)


def _apply_artifact_compaction(package: dict[str, Any]) -> None:
    """M2: strip context package sections according to adapter compaction policy."""
    policy = _adapter_config.get("ARTIFACT_COMPACTION")
    if not isinstance(policy, dict):
        return
    for key in ("system_context", "project_context", "task_context",
                "evidence_refs", "allowed_reads", "allowed_writes"):
        if not policy.get(f"include_{key}", True):
            package.pop(key, None)


# ---------------------------------------------------------------------------
# IF-5 Sink 适配器
# ---------------------------------------------------------------------------

def _write_artifacts_via_sink(package: dict[str, Any]) -> dict[str, str]:
    """IF-5: Write artifacts via Sink facade."""
    return _get_artifact_sink().write(package)


def _append_error_log_via_sink(component: str, message: str, context: dict[str, Any]) -> None:
    """IF-5: Log error via Sink facade."""
    _get_error_sink().log(component, message, context)

