#!/usr/bin/env python3.12
"""Gateway 配置层：路径常量、适配器配置存储、日志器、完整性检查。

依赖层级：无内部依赖（最底层）。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import logging
import os
import threading
from pathlib import Path
from typing import Any, cast

# ---------------------------------------------------------------------------
# 路径发现与常量
# ---------------------------------------------------------------------------

_project_cwd_env = os.environ.get("MEMORY_HOOK_PROJECT_CWD", "")
_cwd_seed = Path(_project_cwd_env) if _project_cwd_env else Path.cwd()

try:
    from .memory_root_discovery import discover_roots
except ImportError:
    from memory_core.tools.memory_root_discovery import discover_roots  # type: ignore

REPO_ROOT, WORKSPACE_ROOT = discover_roots(_cwd_seed)
_FORCE_HOOK = bool(os.environ.get("MEMORY_HOOK_FORCE") or os.environ.get("WORKBOT_FORCE_HOOK"))
BATCH_SIZE = 500


def _configured_artifact_root(workspace_root: Path) -> Path:
    artifact_root = os.environ.get("MEMORY_HOOK_ARTIFACT_ROOT")
    if artifact_root:
        return Path(artifact_root).expanduser()
    return workspace_root / "memory" / "artifacts" / "memory-hook"


def _configured_error_log(workspace_root: Path) -> Path:
    error_log = os.environ.get("MEMORY_HOOK_ERROR_LOG")
    if error_log:
        return Path(error_log).expanduser()
    return workspace_root / "memory" / "system" / "errors.log"


def _configured_invalid_memory_root(workspace_root: Path) -> Path:
    return workspace_root / "memory" / "archive" / "invalid"


def _configured_project_lifecycle_root(workspace_root: Path) -> Path:
    global_state_root = os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT")
    if global_state_root:
        return Path(global_state_root).expanduser() / "project-lifecycle"
    return workspace_root / "memory" / "artifacts" / "memory-hook" / "project-lifecycle"


ARTIFACT_ROOT = _configured_artifact_root(WORKSPACE_ROOT)
CONTEXT_ROOT = ARTIFACT_ROOT / "contexts"
EVENT_LOG = ARTIFACT_ROOT / "events.jsonl"
ERROR_LOG = _configured_error_log(WORKSPACE_ROOT)
PROJECT_LIFECYCLE_ROOT = _configured_project_lifecycle_root(WORKSPACE_ROOT)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 文件工具与规则辅助（re-exported for test access）
# ---------------------------------------------------------------------------

try:
    from ._file_utils import exclusive_lock, now_iso
except ImportError:
    from _file_utils import exclusive_lock, now_iso  # type: ignore

try:
    from ._rule_helpers import (
        _existing_paths,
        _get_write_targets_dict,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )
except ImportError:
    from _rule_helpers import (  # type: ignore  # noqa: F401
        _existing_paths,
        _get_write_targets_dict,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )

# ---------------------------------------------------------------------------
# 所有权 / 拒绝列表 / 生命周期
# ---------------------------------------------------------------------------

with contextlib.suppress(ImportError):
    from .cmux_hook_state import default_hook_state_path, record_hook_event  # noqa: F401

try:
    from ..ownership import get_source_repo_mode, is_memory_core_source_repo
except ImportError:
    from memory_core.ownership import get_source_repo_mode, is_memory_core_source_repo  # type: ignore

try:
    from .project_lifecycle import record_project_lifecycle
except ImportError:
    from memory_core.tools.project_lifecycle import record_project_lifecycle  # type: ignore

try:
    import memory_core.tools.denylist as _denylist
    is_denied_project_root = _denylist.is_denied_project_root
except ImportError:
    import memory_core.tools.denylist as _denylist  # type: ignore
    is_denied_project_root = _denylist.is_denied_project_root  # type: ignore

# ---------------------------------------------------------------------------
# 非注入事件集合
# ---------------------------------------------------------------------------

NON_INJECTION_EVENTS: frozenset[str] = frozenset({
    "stop",
    "notification",
    "subagent-stop",
    "post-tool-use",
    "pre-compact",
    "session-end",
})

# ---------------------------------------------------------------------------
# L2 完整性（lazy import 避免循环依赖）
# ---------------------------------------------------------------------------


def _integrity_sign(project_root: Path) -> None:
    """Sign project manifest after artifact write. Non-blocking."""
    try:
        from .memory_hook_integrity_keys import load_or_create_key
        from .memory_hook_integrity_manifest import sign_project
        key = load_or_create_key()
        sign_project(project_root, key)
    except Exception as exc:
        _logger.debug("integrity sign skipped: %s", exc)


def _integrity_verify(project_root: Path) -> dict[str, Any] | None:
    """Verify project manifest on session-start. Returns result dict or None."""
    try:
        from .memory_hook_integrity_keys import load_key
        from .memory_hook_integrity_verify import verify_project
        key = load_key()
        if key is None:
            _logger.warning("Integrity key not found — protection disabled")
            return {"ok": False, "skipped_reason": "key_not_found"}
        result = verify_project(project_root, key)
        return result.to_dict()
    except Exception as exc:
        _logger.debug("integrity verify skipped: %s", exc)
        return None


def _collect_changed_paths(
    project_root: Path,
    manifest: dict[str, Any],
) -> set[str]:
    """F3: Compare manifest SHA-256 entries with on-disk files to find changes."""
    resolved_root = project_root.resolve()
    changed: set[str] = set()
    for entry in manifest.get("entries", []):
        rel_path = entry.get("rel_path", "")
        expected_sha = entry.get("sha256", "")
        if not rel_path or not expected_sha:
            continue
        abs_path = resolved_root / rel_path
        if not abs_path.exists():
            changed.add(rel_path)
            continue
        try:
            raw = abs_path.read_bytes()
            actual_sha = hashlib.sha256(raw).hexdigest()
            if actual_sha != expected_sha:
                changed.add(rel_path)
        except OSError as exc:
            _logger.warning("_collect_changed_paths: cannot read %s: %s", rel_path, exc)
            changed.add(rel_path)
    return changed


# ---------------------------------------------------------------------------
# 适配器配置存储（替代 globals().update 注入）
# ---------------------------------------------------------------------------

_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
_ADAPTER_REGISTRY = {
    "default": (".memory_hook_adapters.default_runtime_profile", "build_default_runtime_profile"),
}


def _load_adapter_profile(adapter_name: str, repo_root: Path, workspace_root: Path) -> dict[str, Any]:
    """Load adapter profile.

    Raises:
        KeyError: If adapter_name is not in _ADAPTER_REGISTRY.
        ImportError: If the adapter module cannot be imported.
    """
    if adapter_name not in _ADAPTER_REGISTRY:
        raise KeyError(f"unknown adapter: {adapter_name}")
    _mod_path, _fn_name = _ADAPTER_REGISTRY[adapter_name]
    _mod = importlib.import_module(_mod_path, package="memory_core.tools")
    _fn = getattr(_mod, _fn_name)
    return cast(dict[str, Any], _fn(repo_root, workspace_root))


_adapter_config: dict[str, Any] = {}
_config_lock = threading.Lock()


def get_config(key: str, default: Any = None) -> Any:
    """Thread-safe read from adapter config."""
    with _config_lock:
        return _adapter_config.get(key, default)


def get_config_dict() -> dict[str, Any]:
    """Return a shallow copy of the current adapter config for safe iteration."""
    with _config_lock:
        return dict(_adapter_config)


def load_adapter_config(profile: dict[str, Any]) -> None:
    """Load adapter runtime profile into _adapter_config."""
    with _config_lock:
        _adapter_config.clear()
        _adapter_config.update(profile)


_adapter_profile = _load_adapter_profile(_ADAPTER_NAME, REPO_ROOT, WORKSPACE_ROOT)
load_adapter_config(_adapter_profile)


def reload_adapter(adapter_name: str | None = None) -> None:
    """Reload adapter configuration in the current process."""
    global _adapter_profile, _adapter_config, _ADAPTER_NAME
    if adapter_name is None:
        adapter_name = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
    new_profile = _load_adapter_profile(adapter_name, REPO_ROOT, WORKSPACE_ROOT)
    _adapter_profile = new_profile
    with _config_lock:
        _adapter_config.clear()
        _adapter_config.update(new_profile)
    _ADAPTER_NAME = adapter_name


# ---------------------------------------------------------------------------
# IF-5 门面函数（基础层）
# ---------------------------------------------------------------------------

from .memory_hook_impls import (
    ArtifactSinkImpl,
    ErrorSinkImpl,
    GatewayBusinessPolicyConfig,
    PolicyRegistryImpl,
    RouteTargetPolicyImpl,
    WriteTargetPolicyImpl,
)
from .memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy

_default_policy_registry: PolicyRegistryImpl | None = None
_default_route_policy: RouteTargetPolicyImpl | None = None
_default_write_policy: WriteTargetPolicyImpl | None = None


def _get_gateway_business_policy():
    """获取业务策略实例。"""
    from datetime import datetime
    
    def _read_text_if_exists(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
    
    config = GatewayBusinessPolicyConfig(
        repo_root=REPO_ROOT,
        workspace_root=WORKSPACE_ROOT,
        project_map_root=get_config("PROJECT_MAP_ROOT"),
        project_map_files=get_config("PROJECT_MAP_FILES"),
        project_map_governance=get_config("PROJECT_MAP_GOVERNANCE"),
        truth_model=get_config("TRUTH_MODEL"),
        global_canonical=get_config("GLOBAL_CANONICAL"),
        authority_allowed_paths=get_config("AUTHORITY_ALLOWED_PATHS"),
        lower_evidence_roots=get_config("LOWER_EVIDENCE_ROOTS"),
        legal_core_markers=get_config("LEGAL_CORE_MARKERS"),
        required_registry_scopes=get_config("REQUIRED_REGISTRY_SCOPES"),
        project_canonical=get_config("PROJECT_CANONICAL"),
        project_runtime_root=get_config("PROJECT_RUNTIME_ROOT"),
        project_doc_refs=get_config("PROJECT_DOC_REFS"),
        default_decision_refs=get_config("DEFAULT_DECISION_REFS"),
        project_decision_refs=get_config("PROJECT_DECISION_REFS"),
        default_lesson_refs=get_config("DEFAULT_LESSON_REFS"),
        project_lesson_refs=get_config("PROJECT_LESSON_REFS"),
        governance_frozen_tuple_files=get_config("GOVERNANCE_FROZEN_TUPLE_FILES"),
        event_contract_files=get_config("EVENT_CONTRACT_FILES"),
        frozen_tuple_expected=get_config("FROZEN_TUPLE_EXPECTED"),
        frozen_tuple_legacy_markers=get_config("FROZEN_TUPLE_LEGACY_MARKERS"),
        formal_source_types=get_config("FORMAL_SOURCE_TYPES"),
        formal_event_types=get_config("FORMAL_EVENT_TYPES"),
        formal_event_statuses=get_config("FORMAL_EVENT_STATUSES"),
        formal_field_keys=get_config("FORMAL_FIELD_KEYS"),
        legacy_field_keys=get_config("LEGACY_FIELD_KEYS"),
        required_canonical=get_config("REQUIRED_CANONICAL"),
        workspace_index_path=WORKSPACE_ROOT / "INDEX.md",
        docs_index_path=WORKSPACE_ROOT / "memory" / "docs" / "INDEX.md",
        overview_doc_path=WORKSPACE_ROOT / "memory" / "docs" / "记忆系统全景文档.md",
        global_index_path=WORKSPACE_ROOT / "memory" / "kb" / "global" / "INDEX.md",
        hook_contract_path=get_config("HOOK_CONTRACT_PATH"),
        default_project_scope=get_config("DEFAULT_PROJECT_SCOPE"),
        scope_match_hints=get_config("SCOPE_MATCH_HINTS"),
        read_text_if_exists_fn=_read_text_if_exists,
    )
    policy_class = _adapter_config.get("GATEWAY_POLICY_CLASS", NeutralGatewayBusinessPolicy)
    return policy_class(config=config)


def _get_policy_registry() -> PolicyRegistryImpl:
    """获取策略注册表。"""
    global _default_policy_registry
    if _default_policy_registry is None:
        _default_policy_registry = PolicyRegistryImpl(
            policy_pack_path=get_config("POLICY_PACK_PATH"),
            allowed_scopes=set(get_config("POLICY_ALLOWED_SCOPES")),
            scope_inherits=dict(get_config("POLICY_SCOPE_INHERITS")),
        )
    return _default_policy_registry


def _get_route_policy() -> RouteTargetPolicyImpl:
    """获取路由策略。"""
    global _default_route_policy
    if _default_route_policy is None:
        _default_route_policy = RouteTargetPolicyImpl(
            WORKSPACE_ROOT,
            REPO_ROOT,
            global_rule_path=get_config("GLOBAL_RULE_PATH"),
            project_runtime_path=get_config("PROJECT_RUNTIME_ROOT").get(get_config("ROUTE_PROJECT_RUNTIME_SCOPE")),
        )
    return _default_route_policy


def _get_write_policy() -> WriteTargetPolicyImpl:
    """获取写入策略。"""
    global _default_write_policy
    if _default_write_policy is None:
        _default_write_policy = WriteTargetPolicyImpl(WORKSPACE_ROOT)
    return _default_write_policy


def _get_artifact_sink():
    """获取 artifact sink。"""
    from datetime import datetime
    return ArtifactSinkImpl(CONTEXT_ROOT, EVENT_LOG, datetime_module=datetime)


def _get_error_sink():
    """获取 error sink。"""
    return ErrorSinkImpl(ERROR_LOG, now_iso_fn=now_iso)


def _resolve_route_target_via_policy(kind: str) -> str:
    """IF-5: Resolve route target via Policy facade."""
    return _get_route_policy().resolve(kind)


def _apply_hook_runtime_write_targets(targets: dict[str, Any]) -> dict[str, Any]:
    """Expose global lifecycle state without redirecting project memory writes."""
    updated = dict(targets)
    if os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT"):
        updated["hook_lifecycle"] = str(PROJECT_LIFECYCLE_ROOT)
        updated["hook_global_state_root"] = str(Path(os.environ["MEMORY_HOOK_GLOBAL_STATE_ROOT"]).expanduser())
    return updated


def _write_targets_via_policy() -> dict[str, Any]:
    """IF-5: Get write targets via Policy facade."""
    return _apply_hook_runtime_write_targets(_get_write_policy().get_targets())


def _get_policy_pack_via_registry(scope: str) -> dict[str, Any]:
    """IF-5: Get policy pack via PolicyRegistry facade."""
    return _get_policy_registry().get_policy_pack(scope)


def _resolve_policy_conflict_via_registry(
    policy_key: str,
    values: list[str],
    strategy: str | None = None,
) -> str:
    """IF-5: Resolve policy conflict via PolicyRegistry facade."""
    return _get_policy_registry().resolve_conflict(policy_key, values, strategy or "default")
