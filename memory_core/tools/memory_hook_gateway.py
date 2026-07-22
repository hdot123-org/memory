#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from typing import TypeVar

    _T = TypeVar("_T")

    # Dynamic constants injected via globals().update(profile) at runtime.
    # Declared here for mypy static analysis.
    PROJECT_MAP_ROOT: Path
    PROJECT_MAP_FILES: list[Path]
    PROJECT_MAP_GOVERNANCE: Path
    TRUTH_MODEL: Path
    GLOBAL_CANONICAL: list[Path]
    AUTHORITY_ALLOWED_PATHS: set[Path]
    LOWER_EVIDENCE_ROOTS: list[Path]
    LEGAL_CORE_MARKERS: list[str]
    REQUIRED_REGISTRY_SCOPES: list[str]
    PROJECT_CANONICAL: dict[str, Path]
    PROJECT_RUNTIME_ROOT: dict[str, Path]
    PROJECT_DOC_REFS: dict[str, list[Path]]
    DEFAULT_DECISION_REFS: list[Path]
    PROJECT_DECISION_REFS: dict[str, list[Path]]
    DEFAULT_LESSON_REFS: list[Path]
    PROJECT_LESSON_REFS: dict[str, list[Path]]
    GOVERNANCE_FROZEN_TUPLE_FILES: list[Path]
    EVENT_CONTRACT_FILES: dict[str, Path]
    FROZEN_TUPLE_EXPECTED: set[str]
    FROZEN_TUPLE_LEGACY_MARKERS: set[str]
    FORMAL_SOURCE_TYPES: set[str]
    FORMAL_EVENT_TYPES: set[str]
    FORMAL_EVENT_STATUSES: set[str]
    FORMAL_FIELD_KEYS: set[str]
    LEGACY_FIELD_KEYS: set[str]
    REQUIRED_CANONICAL: list[Path]
    HOOK_CONTRACT_PATH: Path
    DEFAULT_PROJECT_SCOPE: str
    SCOPE_MATCH_HINTS: dict[str, list[Path]]
    POLICY_PACK_PATH: Path
    POLICY_ALLOWED_SCOPES: set[str]
    POLICY_SCOPE_INHERITS: dict[str, str]
    GLOBAL_RULE_PATH: Path
    ROUTE_PROJECT_RUNTIME_SCOPE: str
    REGISTRATION_GIT_SCOPE: list[Path]
    REGISTRATION_COMMIT_PHASE: str
    REGISTRATION_COMMIT_POLICY: str
    LEGALITY_SOURCE_POLICY: str
    GOVERNANCE_BLOCKER_SCOPES: set[str]
    EVENT_CONTRACT_BLOCKER_SCOPES: set[str]
    CORE_EVIDENCE_REFS: list[str]
    MEMORY_SYSTEM_PATH: Path
    GATEWAY_POLICY_CLASS: Any
    ARTIFACT_COMPACTION: dict[str, bool]
    CLAUDE_HOOK_STATE_FILE: str | None
    GLOBAL_KB_ROOT: Path | None
    GLOBAL_KB_ENABLED: bool

# Import file utilities (REF-001 §4.8)
try:
    from ._file_utils import exclusive_lock, now_iso
except ImportError:
    from _file_utils import exclusive_lock, now_iso  # type: ignore

# Import shared rule helpers (consolidation REF-001 §4.3)
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
    from _rule_helpers import (  # type: ignore
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

SCRIPT_PATH = Path(__file__).resolve()
try:
    # Consolidated: import from denylist instead of denied_project_roots
    import memory_core.tools.denylist as _denylist

    from ..constants import SYSTEM_DIR
    from .memory_root_discovery import discover_roots
    from .project_lifecycle import record_project_lifecycle
    is_denied_project_root = _denylist.is_denied_project_root
except ImportError:
    # Consolidated: import from denylist instead of denied_project_roots
    import memory_core.tools.denylist as _denylist
    from memory_core.constants import SYSTEM_DIR
    from memory_core.tools.memory_root_discovery import discover_roots
    from memory_core.tools.project_lifecycle import record_project_lifecycle
    is_denied_project_root = _denylist.is_denied_project_root
REPO_ROOT, WORKSPACE_ROOT = discover_roots(Path.cwd())
_FORCE_HOOK = bool(os.environ.get("MEMORY_HOOK_FORCE") or os.environ.get("WORKBOT_FORCE_HOOK"))

# Batch size for telemetry sync
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
try:
    from .cmux_hook_state import default_hook_state_path, record_hook_event
except ImportError:
    pass  # noqa: E402

# M3: Import is_memory_core_source_repo from ownership module
try:
    from ..ownership import get_source_repo_mode, is_memory_core_source_repo
except ImportError:
    from memory_core.ownership import get_source_repo_mode, is_memory_core_source_repo

try:
    from .memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy
    from .memory_hook_config import CoreConfig
    from .memory_hook_core import build_context_package_core, build_context_package_from_config
    from .memory_hook_impls import (
        ArtifactSinkImpl,
        ArtifactWriter,
        DelegateRouter,
        ErrorSinkImpl,
        GatewayBusinessPolicyConfig,
        PolicyRegistryImpl,
        RouteTargetPolicyImpl,
        WriteTargetPolicyImpl,
        resolve_host_delegate,
    )
    from .memory_hook_interfaces import (
        ArtifactSink,
        ErrorSink,
        GatewayBusinessPolicy,
        HostDelegate,
        PolicyRegistry,
        RouteTargetPolicy,
        WriteTargetPolicy,
    )
    from .memory_hook_schema import convert_legacy_to_memory_v1, convert_to_v1
except ImportError:
    from memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy  # type: ignore
    from memory_hook_config import CoreConfig  # type: ignore
    from memory_hook_core import build_context_package_core, build_context_package_from_config  # type: ignore
    from memory_hook_impls import (  # type: ignore
        ArtifactSinkImpl,
        ArtifactWriter,
        DelegateRouter,
        ErrorSinkImpl,
        GatewayBusinessPolicyConfig,
        PolicyRegistryImpl,
        RouteTargetPolicyImpl,
        WriteTargetPolicyImpl,
        resolve_host_delegate,
    )
    from memory_hook_interfaces import (  # type: ignore
        ArtifactSink,
        ErrorSink,
        GatewayBusinessPolicy,
        HostDelegate,
        PolicyRegistry,
        RouteTargetPolicy,
        WriteTargetPolicy,
    )
    from memory_hook_schema import convert_legacy_to_memory_v1, convert_to_v1  # type: ignore


import importlib  # noqa: E402
import logging  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402

_logger = logging.getLogger(__name__)

# L2 Integrity — lazy-loaded to avoid circular imports
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
    """F3: Compare manifest SHA-256 entries with on-disk files to find changes.

    Returns a set of relative paths whose content hash differs from the manifest,
    or that are missing from disk but present in the manifest.

    Args:
        project_root: Absolute path to project root
        manifest: Loaded manifest dict with 'entries' list

    Returns:
        Set of relative paths that have changed
    """
    resolved_root = project_root.resolve()
    changed: set[str] = set()

    for entry in manifest.get("entries", []):
        rel_path = entry.get("rel_path", "")
        expected_sha = entry.get("sha256", "")
        if not rel_path or not expected_sha:
            continue

        abs_path = resolved_root / rel_path
        if not abs_path.exists():
            # File was deleted — report as changed
            changed.add(rel_path)
            continue

        # Compute on-disk SHA-256
        try:
            raw = abs_path.read_bytes()
            actual_sha = hashlib.sha256(raw).hexdigest()
            if actual_sha != expected_sha:
                changed.add(rel_path)
        except OSError as exc:
            _logger.warning("_collect_changed_paths: cannot read %s: %s", rel_path, exc)
            changed.add(rel_path)

    return changed

# 并发限制：本模块在导入时根据 MEMORY_HOOK_ADAPTER 环境变量初始化全局状态
# （_ADAPTER_NAME / _adapter_config / module globals）。
# - 同一进程内切换 adapter：调用 reload_adapter(name)
# - 多项目并发执行：每项目独立进程；同进程库导入并发不安全
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
_ADAPTER_REGISTRY = {
    "default": (".memory_hook_adapters.default_runtime_profile", "build_default_runtime_profile"),
}


def _load_adapter_profile(adapter_name: str, repo_root: Path, workspace_root: Path) -> dict[str, Any]:
    """Load adapter profile.

    Raises:
        KeyError: If adapter_name is not in _ADAPTER_REGISTRY.
        ImportError: If the adapter module cannot be imported. The caller
            sees the real error rather than a silent fallback to workbot,
            because workbot kb files now live in archive/legacy-workbot/
            and selecting workbot implicitly would degrade silently.
    """
    if adapter_name not in _ADAPTER_REGISTRY:
        raise KeyError(f"unknown adapter: {adapter_name}")

    _mod_path, _fn_name = _ADAPTER_REGISTRY[adapter_name]
    _mod = importlib.import_module(_mod_path, package="memory_core.tools")
    _fn = getattr(_mod, _fn_name)
    return cast(dict[str, Any], _fn(repo_root, workspace_root))


import threading

# Adapter configuration store (replaces globals().update injection).
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
    """Load adapter runtime profile into _adapter_config.

    Also writes keys into globals() for backward compatibility with
    existing code that reads module-level attributes directly.
    """
    with _config_lock:
        _adapter_config.clear()
        _adapter_config.update(profile)
    # Backward-compat: expose keys as module globals so hasattr() checks
    # and direct attribute reads from existing callers still work.
    globals().update(profile)


# Load adapter profile once; feed both new config store and legacy globals.
_adapter_profile = _load_adapter_profile(_ADAPTER_NAME, REPO_ROOT, WORKSPACE_ROOT)
load_adapter_config(_adapter_profile)


def reload_adapter(adapter_name: str | None = None) -> None:
    """Reload adapter configuration in the current process.

    Replaces the module-level adapter state (_ADAPTER_NAME / _adapter_config
    / module globals) with the profile for *adapter_name*.

    Args:
        adapter_name: Adapter name to load.  If ``None``, reads from
            ``os.environ["MEMORY_HOOK_ADAPTER"]`` (falls back to ``"default"``).

    Raises:
        KeyError: If the adapter name is not in ``_ADAPTER_REGISTRY``.
        ImportError: If the adapter module cannot be imported.

    并发安全：本函数在同一进程内切换 adapter 时可用，但非并发安全。
    多项目并发执行场景请每项目独立进程。
    """
    global _adapter_profile, _adapter_config, _ADAPTER_NAME

    if adapter_name is None:
        adapter_name = os.environ.get("MEMORY_HOOK_ADAPTER", "default")

    new_profile = _load_adapter_profile(adapter_name, REPO_ROOT, WORKSPACE_ROOT)
    _adapter_profile = new_profile

    # Reset adapter config and reload with new profile.
    with _config_lock:
        _adapter_config.clear()
        _adapter_config.update(new_profile)
    globals().update(new_profile)

    _ADAPTER_NAME = adapter_name


__all__ = [
    'build_context_package',
    'build_context_package_simple',
    'ArtifactWriter',
    'DelegateRouter',
    'reload_adapter',
]


# ---------------------------------------------------------------------------
# M2 Interface Adapters (IF-5: Gateway Facade)
# ---------------------------------------------------------------------------

_default_policy_registry: PolicyRegistry | None = None
_default_route_policy: RouteTargetPolicy | None = None
_default_write_policy: WriteTargetPolicy | None = None


def _build_gateway_business_policy() -> GatewayBusinessPolicy:
    config = GatewayBusinessPolicyConfig(
        repo_root=REPO_ROOT,
        workspace_root=WORKSPACE_ROOT,
        project_map_root=PROJECT_MAP_ROOT,
        project_map_files=PROJECT_MAP_FILES,
        project_map_governance=PROJECT_MAP_GOVERNANCE,
        truth_model=TRUTH_MODEL,
        global_canonical=GLOBAL_CANONICAL,
        authority_allowed_paths=AUTHORITY_ALLOWED_PATHS,
        lower_evidence_roots=LOWER_EVIDENCE_ROOTS,
        legal_core_markers=LEGAL_CORE_MARKERS,
        required_registry_scopes=REQUIRED_REGISTRY_SCOPES,
        project_canonical=PROJECT_CANONICAL,
        project_runtime_root=PROJECT_RUNTIME_ROOT,
        project_doc_refs=PROJECT_DOC_REFS,
        default_decision_refs=DEFAULT_DECISION_REFS,
        project_decision_refs=PROJECT_DECISION_REFS,
        default_lesson_refs=DEFAULT_LESSON_REFS,
        project_lesson_refs=PROJECT_LESSON_REFS,
        governance_frozen_tuple_files=GOVERNANCE_FROZEN_TUPLE_FILES,
        event_contract_files=EVENT_CONTRACT_FILES,
        frozen_tuple_expected=FROZEN_TUPLE_EXPECTED,
        frozen_tuple_legacy_markers=FROZEN_TUPLE_LEGACY_MARKERS,
        formal_source_types=FORMAL_SOURCE_TYPES,
        formal_event_types=FORMAL_EVENT_TYPES,
        formal_event_statuses=FORMAL_EVENT_STATUSES,
        formal_field_keys=FORMAL_FIELD_KEYS,
        legacy_field_keys=LEGACY_FIELD_KEYS,
        required_canonical=REQUIRED_CANONICAL,
        workspace_index_path=WORKSPACE_ROOT / "INDEX.md",
        docs_index_path=WORKSPACE_ROOT / "memory" / "docs" / "INDEX.md",
        overview_doc_path=WORKSPACE_ROOT / "memory" / "docs" / "记忆系统全景文档.md",
        global_index_path=WORKSPACE_ROOT / "memory" / "kb" / "global" / "INDEX.md",
        hook_contract_path=HOOK_CONTRACT_PATH,
        default_project_scope=DEFAULT_PROJECT_SCOPE,
        scope_match_hints=SCOPE_MATCH_HINTS,
        read_text_if_exists_fn=read_text_if_exists,
    )
    _policy_class = _adapter_config.get("GATEWAY_POLICY_CLASS", NeutralGatewayBusinessPolicy)
    return cast(GatewayBusinessPolicy, _policy_class(config=config))


def _get_gateway_business_policy() -> GatewayBusinessPolicy:
    # No singleton caching here so tests and runtime can monkeypatch constants
    # and immediately observe fresh adapter config injection.
    return _build_gateway_business_policy()


CoreBuilder = Callable[..., dict[str, Any]]


def _load_external_core_builder() -> CoreBuilder:
    module_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "memory_core.tools.memory_hook_core")
    func_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "build_context_package_from_config")
    # If using default module/func, return the locally imported function
    # to ensure monkeypatching works correctly in tests
    if module_name == "memory_core.tools.memory_hook_core" and func_name == "build_context_package_from_config":
        return build_context_package_from_config
    module = __import__(module_name, fromlist=[func_name])
    builder = getattr(module, func_name)
    if not callable(builder):
        raise TypeError(f"external core builder is not callable: {module_name}.{func_name}")
    return cast(Callable[..., dict[str, Any]], builder)


def _resolve_core_builder(provider: str, *, allow_fallback: bool = True) -> tuple[str, CoreBuilder, list[str]]:
    if provider == "external-core":
        try:
            return "external-core", _load_external_core_builder(), []
        except Exception as exc:
            if not allow_fallback:
                raise
            return "legacy", build_context_package_from_config, [f"external-core load failed, fallback to legacy: {exc}"]
    return "legacy", build_context_package_from_config, []


def _get_policy_registry() -> PolicyRegistry:
    global _default_policy_registry
    if _default_policy_registry is None:
        _default_policy_registry = PolicyRegistryImpl(
            policy_pack_path=POLICY_PACK_PATH,
            allowed_scopes=set(POLICY_ALLOWED_SCOPES),
            scope_inherits=dict(POLICY_SCOPE_INHERITS),
        )
    return _default_policy_registry


def _get_route_policy() -> RouteTargetPolicy:
    global _default_route_policy
    if _default_route_policy is None:
        _default_route_policy = RouteTargetPolicyImpl(
            WORKSPACE_ROOT,
            REPO_ROOT,
            global_rule_path=GLOBAL_RULE_PATH,
            project_runtime_path=PROJECT_RUNTIME_ROOT.get(ROUTE_PROJECT_RUNTIME_SCOPE),
        )
    return _default_route_policy


def _get_write_policy() -> WriteTargetPolicy:
    global _default_write_policy
    if _default_write_policy is None:
        _default_write_policy = WriteTargetPolicyImpl(WORKSPACE_ROOT)
    return _default_write_policy


def _get_artifact_sink() -> ArtifactSink:
    return ArtifactSinkImpl(CONTEXT_ROOT, EVENT_LOG, datetime_module=datetime)


def _get_error_sink() -> ErrorSink:
    return ErrorSinkImpl(ERROR_LOG, now_iso_fn=now_iso)


def _get_host_delegate(host: str) -> HostDelegate:
    return resolve_host_delegate(host, mode="auto")


# IF-5 adapters for existing functions

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


def _write_artifacts_via_sink(package: dict[str, Any]) -> dict[str, str]:
    """IF-5: Write artifacts via Sink facade."""
    return _get_artifact_sink().write(package)


def _append_error_log_via_sink(component: str, message: str, context: dict[str, Any]) -> None:
    """IF-5: Log error via Sink facade."""
    _get_error_sink().log(component, message, context)


def _execute_delegate_via_facade(
    host: str,
    event: str,
    raw_payload: str,
    payload: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    """IF-5: Execute delegate via Facade."""
    delegate = _get_host_delegate(host)
    return delegate.execute(event, raw_payload, payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Workbot memory hook gateway.")
    parser.add_argument("--host", required=True, choices=("factory",))
    parser.add_argument("--event", required=True, choices=(
        "session-start", "prompt-submit", "stop", "notification",
        "pre-tool-use", "post-tool-use", "subagent-stop",
        "pre-compact", "session-end",
    ))
    parser.add_argument("--no-delegate", action="store_true", help="Generate gateway artifacts only.")
    return parser.parse_args()


def _read_payload(raw_payload: str) -> dict[str, Any]:
    if not raw_payload.strip():
        return {}
    try:
        loaded = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        _logger.warning("payload JSON parse failed: %s", exc)
        return {}
    return loaded if isinstance(loaded, dict) else {"payload": loaded}


def _payload_cwd(payload: dict[str, Any]) -> Path | None:
    value = payload.get("cwd")
    if isinstance(value, str) and value:
        return Path(value).expanduser()
    return None


def _environment_cwd() -> Path | None:
    env_pwd = os.environ.get("PWD")
    return Path(env_pwd).expanduser() if env_pwd else None


def _original_cwd() -> Path | None:
    value = os.environ.get("MEMORY_HOOK_ORIGINAL_CWD")
    return Path(value).expanduser() if value else None


def _path_within_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _discover_cwd(payload: dict[str, Any]) -> Path:
    provided_cwd = _payload_cwd(payload)
    original_cwd = _original_cwd()
    if os.environ.get("MEMORY_HOOK_PREFER_EXTERNAL_CWD") and original_cwd:
        return original_cwd
    if provided_cwd and _path_within_repo(provided_cwd):
        return provided_cwd
    env_cwd = _environment_cwd()
    if env_cwd and _path_within_repo(env_cwd):
        return env_cwd
    if env_cwd:
        return env_cwd
    if provided_cwd:
        return provided_cwd
    return REPO_ROOT


def _should_noop_for_external_context(payload: dict[str, Any]) -> bool:
    if _FORCE_HOOK or os.environ.get("MEMORY_HOOK_FORCE") or os.environ.get("WORKBOT_FORCE_HOOK"):
        return False
    env_cwd = _environment_cwd()
    provided_cwd = _payload_cwd(payload)
    original_cwd = _original_cwd()
    env_in_repo = bool(env_cwd and _path_within_repo(env_cwd))
    payload_in_repo = bool(provided_cwd and _path_within_repo(provided_cwd))
    original_in_repo = bool(original_cwd and _path_within_repo(original_cwd))
    return not env_in_repo and not payload_in_repo and not original_in_repo


def _delegate_noop_response(host: str) -> int:
    """M2: delegate-owned bypass instead of gateway host-dispatch."""
    delegate = _get_host_delegate(host)
    result = delegate.noop_response()
    if result.stdout:
        sys.stdout.write(result.stdout)
    return result.returncode


def _record_project_lifecycle_event(
    *,
    host: str,
    event: str,
    payload: dict[str, Any],
    cwd: Path,
) -> dict[str, Any] | None:
    if os.environ.get("MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE") != "1":
        return None
    try:
        return record_project_lifecycle(
            lifecycle_root=PROJECT_LIFECYCLE_ROOT,
            cwd=cwd,
            host=host,
            event=event,
            payload=payload,
            now_iso_fn=now_iso,
        )
    except Exception as exc:  # pragma: no cover - lifecycle tracking must not block hooks
        append_error_log(
            "memory-hook-gateway",
            "project lifecycle record failed",
            {"host": host, "event": event, "cwd": str(cwd), "error": str(exc)},
        )
        return None



def determine_project_scope(cwd: Path) -> str:
    return _get_gateway_business_policy().determine_project_scope(cwd)


def _extract_excerpt(path: Path, max_lines: int = 12) -> list[str]:
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


def governance_frozen_tuple_blocker_errors() -> list[str]:
    return _get_gateway_business_policy().governance_frozen_tuple_blocker_errors()


def event_contract_blocker_errors() -> list[str]:
    return _get_gateway_business_policy().event_contract_blocker_errors()


def _normalize_repo_scope_entry(value: str | Path) -> str | None:
    path = Path(value).expanduser()
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _registration_payload_paths(payload: dict[str, Any]) -> list[str]:
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
    normalized_scope = scope_entry.rstrip("/")
    return candidate == normalized_scope or candidate.startswith(f"{normalized_scope}/")


def _git_registration_probe(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    map_scope = [str(path) for path in REGISTRATION_GIT_SCOPE]
    registration_paths = _registration_payload_paths(payload)
    tracked_scope = map_scope + [str(REPO_ROOT / item) for item in registration_paths]
    # git calls are bounded by timeout=5 to guard the ~10s hook budget; on
    # timeout they degrade to empty results rather than blocking or crashing.
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
    commit_scope: list[str] = [path for path in (_normalize_repo_scope_entry(p) for p in REGISTRATION_GIT_SCOPE) if path]
    commit_scope.extend(registration_paths)
    head_touched = _git_name_only("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", "--", *commit_scope)
    map_touched = any(any(_path_matches_scope(item, scope) for scope in commit_scope[: len(REGISTRATION_GIT_SCOPE)]) for item in head_touched)
    registration_touched = any(any(_path_matches_scope(item, scope) for scope in registration_paths) for item in head_touched)
    if entries:
        status = "pending-commit"
    elif not registration_paths:
        status = "awaiting-registration-payload"
    elif map_touched and registration_touched:
        status = "committed-coupled"
    else:
        status = "committed-not-proven"
    return {
        "phase": REGISTRATION_COMMIT_PHASE,
        "policy": REGISTRATION_COMMIT_POLICY,
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


def project_map_refs() -> list[str]:
    return _get_gateway_business_policy().project_map_refs()


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def validate_project_map_files() -> list[str]:
    return _get_gateway_business_policy().validate_project_map_files()


def validate_unique_legal_system_contract() -> list[str]:
    return _get_gateway_business_policy().validate_unique_legal_system_contract()


def decision_refs_for_scope(project_scope: str) -> list[str]:
    return _get_gateway_business_policy().decision_refs_for_scope(project_scope)


def lesson_refs_for_scope(project_scope: str) -> list[str]:
    return _get_gateway_business_policy().lesson_refs_for_scope(project_scope)


def docs_refs_for_scope(project_scope: str) -> list[str]:
    return _get_gateway_business_policy().docs_refs_for_scope(project_scope)


def truth_basis_for_scope(project_scope: str) -> dict[str, Any]:
    return cast(dict[str, Any], _get_gateway_business_policy().truth_basis_for_scope(project_scope))


def write_targets() -> dict[str, Any]:
    try:
        return _write_targets_via_policy()
    except Exception:
        return _apply_hook_runtime_write_targets(_get_write_targets_dict(WORKSPACE_ROOT))


def resolve_route_target(kind: str) -> str:
    try:
        return _resolve_route_target_via_policy(kind)
    except (KeyError, AttributeError, TypeError) as exc:
        _logger.warning("route target fallback triggered: %s", exc)
        targets = write_targets()
        project_runtime_root = _get_gateway_business_policy().get_project_runtime_root()
        route_map = {
            "fact": targets["fact"],
            "global-rule": str(GLOBAL_RULE_PATH),
            "source-material": str(WORKSPACE_ROOT / "memory" / "docs" / "references"),
            "project-runtime": str(
                project_runtime_root.get(
                    ROUTE_PROJECT_RUNTIME_SCOPE,
                    WORKSPACE_ROOT / "projects" / ROUTE_PROJECT_RUNTIME_SCOPE,
                )
            ),
            "system-error": targets["system_error"],
            "invalid-memory": targets["invalid_memory"],
        }
        try:
            return str(route_map[kind])
        except KeyError as exc:
            raise ValueError(f"unsupported route kind: {kind}") from exc


def _apply_artifact_compaction(package: dict[str, Any]) -> None:
    """M2: strip context package sections according to adapter compaction policy."""
    policy = _adapter_config.get("ARTIFACT_COMPACTION")
    if not isinstance(policy, dict):
        return
    if not policy.get("include_system_context", True):
        package.pop("system_context", None)
    if not policy.get("include_project_context", True):
        package.pop("project_context", None)
    if not policy.get("include_task_context", True):
        package.pop("task_context", None)
    if not policy.get("include_evidence_refs", True):
        package.pop("evidence_refs", None)
    if not policy.get("include_allowed_reads", True):
        package.pop("allowed_reads", None)
    if not policy.get("include_allowed_writes", True):
        package.pop("allowed_writes", None)


def build_context_package(host: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    cwd = _discover_cwd(payload)
    lifecycle_record = _record_project_lifecycle_event(host=host, event=event, payload=payload, cwd=cwd)
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
        project_map_governance=PROJECT_MAP_GOVERNANCE,
        event_log=EVENT_LOG,
        legality_source_policy=LEGALITY_SOURCE_POLICY,
        registration_commit_policy=REGISTRATION_COMMIT_POLICY,
        registration_commit_phase=REGISTRATION_COMMIT_PHASE,
        project_map_refs=project_map_refs(),
        extract_excerpt_fn=_extract_excerpt,
        now_iso_fn=now_iso,
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
        hook_contract_path=HOOK_CONTRACT_PATH,
        surface_id=os.environ.get("CMUX_SURFACE_ID", ""),
        workspace_id=os.environ.get("CMUX_WORKSPACE_ID", ""),
        governance_blocker_scopes=GOVERNANCE_BLOCKER_SCOPES,
        event_contract_blocker_scopes=EVENT_CONTRACT_BLOCKER_SCOPES,
        core_evidence_refs=CORE_EVIDENCE_REFS,
    )
    requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", "legacy").strip() or "legacy"
    provider_name, provider_builder, provider_errors = _resolve_core_builder(requested_provider, allow_fallback=True)
    if provider_builder is not None:
        package = provider_builder(config)
    else:
        package = build_context_package_from_config(config)

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
        except Exception as exc:  # pragma: no cover - defensive path
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
    """Simplified 3-parameter entry point returning a schema-converted package.

    Args:
        host: "codex", "claude", or "factory"
        event: event name (e.g. "session-start", "prompt-submit")
        payload: event payload dict (default: empty dict)
        adapter: adapter name override (default: from MEMORY_HOOK_ADAPTER env var)
        schema: output schema — "context-package-v1" (default) or "memory-v1"

    Returns:
        Context package in the requested schema format.
    """
    if payload is None:
        payload = {}
    v2_package = build_context_package(host, event, payload)
    if schema == "memory-v1":
        v1_package = convert_to_v1(v2_package)
        return convert_legacy_to_memory_v1(v1_package)
    return convert_to_v1(v2_package)


def _ensure_artifact_dirs() -> None:
    try:
        _get_artifact_sink().ensure_dirs()
    except RuntimeError:
        # Fallback only for synthetic sink failure (e.g., not implemented)
        CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)


def append_error_log(component: str, message: str, context: dict[str, Any]) -> None:
    try:
        _append_error_log_via_sink(component, message, context)
    except RuntimeError:
        # Fallback only for synthetic sink failure (e.g., not implemented)
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        timestamp = now_iso()
        day = timestamp[:10]
        daily_error_log = ERROR_LOG.parent / "errors" / f"{day}.log"
        daily_error_log.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(context, ensure_ascii=False, sort_keys=True)
        line = f"[{timestamp}] [{component}] [error] {message} | context={rendered}\n"
        with daily_error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)
        with ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line)


def write_artifacts(package: dict[str, Any]) -> dict[str, str]:
    try:
        return _write_artifacts_via_sink(package)
    except RuntimeError:
        # Fallback only for synthetic sink failure (e.g., not implemented)
        _ensure_artifact_dirs()
        now = datetime.now()
        day = now.date().isoformat()
        timestamp = now.strftime("%Y%m%dT%H%M%S%f")
        daily_context_root = CONTEXT_ROOT / day
        daily_context_root.mkdir(parents=True, exist_ok=True)
        snapshot_path = daily_context_root / f"{timestamp}-{package['host']}-{package['event']}.json"
        suffix = 1
        while snapshot_path.exists():
            snapshot_path = daily_context_root / f"{timestamp}-{suffix:02d}-{package['host']}-{package['event']}.json"
            suffix += 1
        latest_path = CONTEXT_ROOT / f"latest-{package['host']}-{package['event']}.json"
        daily_latest_path = daily_context_root / f"latest-{package['host']}-{package['event']}.json"
        daily_event_log = EVENT_LOG.parent / "events" / f"{day}.jsonl"
        package["artifact_refs"] = {
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "daily_latest": str(daily_latest_path),
            "event_log": str(daily_event_log),
            "legacy_event_log": str(EVENT_LOG),
        }
        rendered = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        snapshot_path.write_text(rendered, encoding="utf-8")
        latest_path.write_text(rendered, encoding="utf-8")
        daily_latest_path.write_text(rendered, encoding="utf-8")
        event_line = json.dumps(package, ensure_ascii=False) + "\n"
        daily_event_log.parent.mkdir(parents=True, exist_ok=True)
        with daily_event_log.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        return {"snapshot": str(snapshot_path), "latest": str(latest_path), "event_log": str(daily_event_log)}


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing required env: {name}")
    return value


def _canonicalize_cmux_refs(workspace_ref: str, surface_ref: str) -> tuple[str, str]:
    proc = subprocess.run(
        ["cmux", "identify", "--workspace", workspace_ref, "--surface", surface_ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return workspace_ref, surface_ref
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return workspace_ref, surface_ref
    caller = payload.get("caller")
    if not isinstance(caller, dict):
        return workspace_ref, surface_ref
    return (
        str(caller.get("workspace_ref") or workspace_ref),
        str(caller.get("surface_ref") or surface_ref),
    )


def _delegate_codex(event: str, raw_payload: str) -> subprocess.CompletedProcess[str]:
    return _execute_delegate_via_facade("codex", event, raw_payload, {})


def _delegate_claude(event: str, raw_payload: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return _execute_delegate_via_facade("claude", event, raw_payload, payload)


def _build_degraded_package_with_error(
    host: str,
    event: str,
    cwd: Path,
    error: str,
    error_type: str = "delegate_preflight_failed",
) -> dict[str, Any]:
    """M3: Build a degraded context-package with error info.

    Instead of returning noop success, return a structured degraded package
    that includes error information for observability.
    """
    return {
        "package_kind": "degraded-context",
        "mode": "degraded",
        "status": "degraded",
        "host": host,
        "event": event,
        "project_root": str(cwd),
        "cwd": str(cwd),
        "error": {
            "type": error_type,
            "message": error,
        },
        "validation_errors": [error],
    }


def _execute_delegate(
    args: argparse.Namespace,
    raw_payload: str,
    payload: dict[str, Any],
    cwd: Path,
    package: dict[str, Any] | None = None,
) -> int:
    """Execute the host-specific delegate and return an exit code.

    Handles preflight errors, delegate process output forwarding,
    and degraded fallback for all paths.
    """
    try:
        if args.host == "codex":
            proc = _delegate_codex(args.event, raw_payload)
        elif args.host == "claude":
            proc = _delegate_claude(args.event, raw_payload, payload)
        else:
            # factory and others: no delegate
            proc = None
    except RuntimeError as exc:
        # M3: Return degraded package with error info instead of noop success
        append_error_log(
            "memory-hook-gateway",
            "delegate preflight failed",
            {"host": args.host, "event": args.event, "error": str(exc), "cwd": str(cwd)},
        )
        degraded_package = _build_degraded_package_with_error(
            args.host, args.event, cwd, str(exc), error_type="delegate_preflight_failed"
        )
        sys.stdout.write(json.dumps(degraded_package, ensure_ascii=False) + "\n")
        return 0

    if proc is not None:
        if proc.returncode != 0:
            append_error_log(
                "memory-hook-gateway",
                "delegate command failed",
                {
                    "host": args.host,
                    "event": args.event,
                    "returncode": proc.returncode,
                    "stderr": proc.stderr,
                    "stdout": proc.stdout,
                    "artifact_latest": None,
                },
            )

        if proc.stdout:
            sys.stdout.write(proc.stdout)
        else:
            # M2: delegate owns bypass output format via noop_response()
            noop = _get_host_delegate(args.host).noop_response()
            if noop.stdout:
                sys.stdout.write(noop.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return proc.returncode
    else:
        # factory and others: skip delegate, output full context-package
        if package is not None:
            sys.stdout.write(json.dumps(package, ensure_ascii=False) + "\n")
        return 0



def _update_state_dynamic_fields(project_root: Path, scope: str) -> None:
    """Update dynamic fields in STATE.md during session-start.

    Updates the '当前工作区' section to reflect the current git branch and
    latest commit. Only modifies dynamic fields; never overwrites static
    fields (主语言/工具链/etc.) filled by init.

    Writes to memory/kb/projects/{scope}/STATE.md.

    Non-blocking: gracefully handles missing git, missing STATE.md, or
    any errors by silently skipping.
    """
    state_path = project_root / "memory" / "kb" / "projects" / scope / "STATE.md"
    if not state_path.exists():
        return

    try:
        # Gather git info — fail gracefully if not a git repo
        branch_proc = subprocess.run(
            ["git", "-C", str(project_root), "branch", "--show-current"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if branch_proc.returncode != 0:
            return
        branch = branch_proc.stdout.strip()
        if not branch:
            return

        commit_proc = subprocess.run(
            ["git", "-C", str(project_root), "log", "-1", "--format=%h %s"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        commit_info = commit_proc.stdout.strip() if commit_proc.returncode == 0 else ""

        content = state_path.read_text(encoding="utf-8")

        # Build the replacement text
        workspace_line = f"当前分支: {branch}"
        if commit_info:
            workspace_line += f" | 最近提交: {commit_info}"

        # Pattern 1: placeholder (未填写) — init has not filled yet
        new_content = re.sub(
            r'(## 当前工作区\n\n)（待填写[^\n]*）',
            rf'\g<1>{workspace_line}',
            content,
        )

        # Pattern 2: already filled — idempotent refresh
        # Matches lines after "## 当前工作区\n\n" that start with "当前分支:"
        new_content = re.sub(
            r'(## 当前工作区\n\n)当前分支: [^\n]+',
            rf'\g<1>{workspace_line}',
            new_content,
        )

        if new_content != content:
            state_path.write_text(new_content, encoding="utf-8")
    except (subprocess.TimeoutExpired, OSError):
        pass  # Non-blocking


def _launch_async_health_check(cwd: Path) -> None:
    """Launch a background process to perform deep memory health validation.

    This prevents heavy validation (reading many files, git commands,
    and running the full context package build) from blocking the hook startup.

    Results are written to: memory/system/health-report.json

    On launch failure, writes a structured failure record to health-report.json
    with launch_status=failed for observability.
    """
    report_path = cwd / "memory" / "system" / "health-report.json"
    try:
        health_script = str((Path(__file__).parent / "memory_health_report.py").resolve())

        # Output path for the report
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Launch detached subprocess (cwd is critical for discovery)
        # Child process writes to report_path directly.
        subprocess.Popen(
            [sys.executable, health_script, "--target", str(cwd)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent
            cwd=str(cwd),            # Set working directory
        )

        _logger.info("Launched async health check for %s", cwd)
    except Exception as e:
        _logger.debug("Failed to launch async health check: %s", e)
        # P2 observability: Write structured failure record for async health check launch failure
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            failure_report = {
                "status": "error",
                "launch_status": "failed",
                "last_launch_error": str(e),
                "checked_at": now_iso(),
                "missing_paths": [],
                "validation_errors": [],
            }
            report_path.write_text(json.dumps(failure_report, indent=2, ensure_ascii=False))
        except Exception as write_err:
            # Fallback: use append_error_log if writing health report fails
            append_error_log(
                "memory-hook-gateway",
                "failed to launch async health check and write health report",
                {
                    "cwd": str(cwd),
                    "launch_error": str(e),
                    "write_error": str(write_err),
                },
            )


# ---------------------------------------------------------------------------
# F4: PromptSubmit real-time logging
# ---------------------------------------------------------------------------

def _read_last_user_message_from_transcript(transcript_path: str | None) -> str | None:
    """F4: Fallback — read the last user message from the transcript file.

    The transcript is a JSONL file where each line is a JSON object with
    at least ``role`` and ``content`` keys.  Returns the content of the
    last line whose role is ``"user"``, or ``None`` if no such line exists.
    """
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.exists():
        return None
    try:
        last_user: str | None = None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("role") == "user":
                    content = entry.get("content", "")
                    if isinstance(content, str) and content:
                        last_user = content
        return last_user
    except OSError:
        return None


# Sentinel for timeout handler — not part of public API
class HookTimeoutError(Exception):
    pass


def _sanitize_for_log(text: str, max_len: int = 2000) -> str:
    """Strip sensitive patterns from text before writing to log files.

    Replaces API keys, tokens, and secrets with ``[REDACTED]`` while
    preserving the surrounding context so the log entry remains useful.

    Patterns covered:
    - OpenAI-style keys (sk-*, *-openai-*)
    - Anthropic-style keys (sk-ant-*, cla-*)
    - Linear API tokens (lin_api_*)
    - AWS keys (AKIA*)
    - Bearer tokens (Authorization: Bearer <token>)
    - Generic API key patterns (api_key=<value>, api-key: <value>)
    - JSON string values for keys containing ``key``, ``secret``, ``token``,
      ``password``, ``credential``, ``auth``
    """
    if not text:
        return text

    # Limit to avoid processing enormous strings
    text = text[:max_len]

    # Bearer tokens in headers or env vars
    text = re.sub(
        r'(Authorization:\s*Bearer\s+)[^\s"\']+[\s"\']',
        r'\1[REDACTED]',
        text,
        flags=re.IGNORECASE,
    )

    # Common API key patterns
    text = re.sub(
        r'((?:api[_-]?key|api[_-]?token|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*)["\']?([^\s"\',}\]]+)',
        r'\1[REDACTED]',
        text,
        flags=re.IGNORECASE,
    )

    # Known token formats
    text = re.sub(r'sk-[A-Za-z0-9]{10,}', '[REDACTED]', text)
    text = re.sub(r'sk-ant-[A-Za-z0-9\-]{10,}', '[REDACTED]', text)
    text = re.sub(r'lin_api_[A-Za-z0-9]{10,}', '[REDACTED]', text)
    text = re.sub(r'AKIA[A-Za-z0-9]{12,}', '[REDACTED]', text)
    text = re.sub(r'ghp_[A-Za-z0-9]{20,}', '[REDACTED]', text)
    text = re.sub(r'glpat-[A-Za-z0-9\-]{10,}', '[REDACTED]', text)

    # JWT-like tokens (three base64 segments separated by dots)
    text = re.sub(
        r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
        '[REDACTED]',
        text,
    )

    return text


def _log_prompt_submit(project_root: Path, payload: dict[str, Any]) -> None:
    """F4: Write a heartbeat entry for a prompt-submit event.

    Writes to ``{project_root}/memory/log/{YYYY-MM-DD}-sessions.md`` with
    format::

        #### {HH:MM:SS} — {session_id[:8]} [heartbeat]
        - **用户消息**: {prompt[:100]}
        - **累计 prompt 数**: {count}
        ---

    Uses ``exclusive_lock`` for exclusive lock during append.
    Protected by a 2-second SIGALRM timeout.

    Fallback: if payload lacks ``prompt``, reads ``transcript_path`` last
    user message.  If still unavailable, writes ``(no prompt captured)``.

    Args:
        project_root: Absolute path to project root
        payload: Factory event payload dict
    """
    # ── Extract fields ──────────────────────────────────────────────
    session_id: str = payload.get("session_id", "unknown")
    transcript_path: str | None = payload.get("transcript_path")

    # Extract prompt with fallback chain
    prompt: str | None = payload.get("prompt")
    if not prompt:
        prompt = _read_last_user_message_from_transcript(transcript_path)
    if not prompt:
        prompt = "(no prompt captured)"

    # ── Build heartbeat content ─────────────────────────────────────
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    session_prefix = session_id[:8]

    # Determine cumulative prompt count for this session
    log_dir = project_root / "memory" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{date_str}-sessions.md"

    prompt_count = 1
    if log_file.exists():
        try:
            content = log_file.read_text(encoding="utf-8")
            # Count heartbeat entries for this session_id
            pattern = re.compile(rf"#### [^\n]+— {re.escape(session_prefix)} \[?heartbeat")
            matches = pattern.findall(content)
            prompt_count = len(matches) + 1
        except OSError:
            pass

    # ── Sanitize prompt before logging ──────────────────────────────
    preview = _sanitize_for_log(prompt)[:100]

    heartbeat = (
        f"#### {time_str} — {session_prefix} [heartbeat]\n"
        f"- **用户消息**: {preview}\n"
        f"- **累计 prompt 数**: {prompt_count}\n"
        "---\n"
    )

    # ── Write with file lock and timeout ────────────────────────────
    def _write_handler(_signum, _frame):  # type: ignore[no-untyped-def]
        raise HookTimeoutError("prompt-submit log write timed out")

    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, _write_handler)
        signal.alarm(2)  # 2-second timeout

        with log_file.open("a", encoding="utf-8") as fh:
            with exclusive_lock(fh):
                fh.write(heartbeat)
                fh.flush()
    except HookTimeoutError:
        _logger.warning("_log_prompt_submit: write timed out for session %s", session_prefix)
    finally:
        signal.alarm(0)
        if old_handler is not None:
            signal.signal(signal.SIGALRM, old_handler)


# ---------------------------------------------------------------------------
# M3: Build a readonly context-package for the memory-core source repo.
# ---------------------------------------------------------------------------

def _build_readonly_source_repo_package(cwd: Path, host: str, event: str) -> dict[str, Any]:
    """M3: Build a readonly context-package for the memory-core source repo.

    Instead of short-circuiting with empty JSON, return a proper context-package
    that declares the repo is in read-only mode with no allowed writes.
    """
    # Get ownership domains/resources for rules
    from ..ownership import DEFAULT_OWNERSHIP_DOMAINS, DEFAULT_OWNERSHIP_RESOURCES

    ownership_domains = [
        {
            "name": d.name,
            "path": d.path,
            "level": d.level.name.lower(),
            "recursive": d.recursive,
            "description": d.description,
        }
        for d in DEFAULT_OWNERSHIP_DOMAINS
    ]
    protected_paths = [
        "memory/docs/**",
        "memory/kb/**",
        "memory/system/**",
        "memory/project-map/**",
        "AGENTS.md",
    ]

    # Source-repo-specific domains (not in DEFAULT_OWNERSHIP_DOMAINS)
    ownership_domains.extend([
        {
            "name": "source_repo_docs",
            "path": "docs",
            "level": "critical",
            "recursive": True,
            "description": "Source repo documentation domain (source-repo-readonly only)",
        },
        {
            "name": "source_repo_factory",
            "path": ".factory",
            "level": "critical",
            "recursive": True,
            "description": "Source repo Factory config domain (source-repo-readonly only)",
        },
    ])
    return {
        "package_kind": "source-repo-rules",
        "mode": "read-only",
        "allowed_writes": {},
        "rules": {
            "description": "memory-core source repository - all writes blocked",
            "ownership_domains": ownership_domains,
            "protected_paths": protected_paths,
            "note": "This is the memory-core source repository. Hooks run in readonly mode to prevent self-pollution.",
        },
        "project_root": str(cwd),
        "cwd": str(cwd),
        "host": host,
        "event": event,
        "status": "ok",
    }


def _read_sync_timestamp(file_path: Path) -> float:
    """Read timestamp from file, returning 0.0 on any error."""
    if not file_path.exists():
        return 0.0
    try:
        return float(file_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0.0


def _should_skip_sync(now: float, last_success: float, last_attempt: float) -> bool:
    """Check if sync should be skipped based on backoff windows."""
    # Skip if within 1-hour success window
    if (now - last_success) < 3600:
        return True
    # Skip if within 5-minute backoff after recent attempt
    if (now - last_attempt) < 300:
        return True
    return False


def _normalize_posthog_host() -> str:
    """Normalize PostHog host URL to ingestion endpoint and extract hostname."""
    posthog_host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com").strip()
    _trimmed = posthog_host.rstrip("/")
    if _trimmed in ("https://app.posthog.com", "https://us.posthog.com"):
        posthog_host = "https://us.i.posthog.com"
    elif _trimmed == "https://eu.posthog.com":
        posthog_host = "https://eu.i.posthog.com"
    # Extract hostname from URL
    if "://" in posthog_host:
        return posthog_host.split("://", 1)[1].rstrip("/")
    return posthog_host.rstrip("/")


def _probe_posthog_network(hostname: str) -> bool:
    """Probe network connectivity to PostHog host. Returns True if reachable."""
    try:
        sock = socket.create_connection((hostname, 443), timeout=2)
        sock.close()
        return True
    except (socket.error, OSError):
        return False


def _read_pending_records(metrics_file: Path, offset: int) -> list[tuple[int, dict[str, Any]]]:
    """Read incremental records from metrics.jsonl starting after offset.

    Returns list of (line_number, record) tuples to handle blank/malformed lines.
    """
    records_with_lines = []
    current_line = 0
    with metrics_file.open("r", encoding="utf-8") as f:
        for line in f:
            current_line += 1
            if current_line <= offset:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    records_with_lines.append((current_line, record))
            except json.JSONDecodeError:
                continue
    return records_with_lines


def _batch_send_records(
    records_with_lines: list[tuple[int, dict[str, Any]]],
    batch_size: int,
    offset_file: Path
) -> tuple[int, int]:
    """Batch send records via telemetry_bridge. Returns (synced_count, last_synced_line)."""
    from memory_core.tools.telemetry_bridge import telemetry

    synced_records = 0
    last_synced_line = 0

    for chunk_start in range(0, len(records_with_lines), batch_size):
        chunk = records_with_lines[chunk_start:chunk_start + batch_size]
        events = []
        for line_num, record in chunk:
            event_name = str(record.get("event") or "memory.replayed_event")
            events.append({"event_name": event_name, "properties": {**record}})

        chunk_success = telemetry.batch_capture(events)
        if not chunk_success:
            break  # stop on first failure

        synced_records += len(chunk)
        last_synced_line = chunk[-1][0]
        offset_file.write_text(str(last_synced_line), encoding="utf-8")

    return synced_records, last_synced_line


def _compact_metrics_jsonl(metrics_file: Path, last_synced_line: int, offset_file: Path) -> None:
    """Compact metrics.jsonl after successful sync, keeping only unsent records."""
    try:
        remaining_lines = []
        with metrics_file.open("r", encoding="utf-8") as f:
            line_num = 0
            for line in f:
                line_num += 1
                if line_num > last_synced_line:
                    remaining_lines.append(line)

        with metrics_file.open("w", encoding="utf-8") as f:
            with exclusive_lock(f):
                f.writelines(remaining_lines)
                f.flush()
                os.fsync(f.fileno())

        offset_file.write_text("0", encoding="utf-8")
    except OSError as exc:
        _logger.debug("metrics.jsonl compaction failed: %s", exc)


def _record_sync_outcome(
    artifact_root: Path,
    success: bool,
    pending_count: int,
    now: float,
    attempt_file: Path
) -> None:
    """Record sync outcome: update timestamps and write status."""
    if success:
        success_file = artifact_root / ".last_sync_success"
        try:
            success_file.write_text(str(now), encoding="utf-8")
        except OSError:
            pass
    else:
        try:
            attempt_file.write_text(str(now), encoding="utf-8")
        except OSError:
            pass
    _write_sync_status(artifact_root, success, pending_count)


def _maybe_sync_telemetry(artifact_root: Path) -> None:
    """Synchronize local telemetry metrics to PostHog during session-start.

    Implements a lightweight sync mechanism with separate backoff for failures:
    1. Check .last_sync_success; skip if < 3600s ago (hourly sync window)
    2. Check .last_sync_attempt; skip if < 300s ago (short backoff after failure)
    3. Probe network connectivity to PostHog host (socket timeout=2s)
    4. If probe fails, update .last_sync_attempt and exit
    5. If probe succeeds, read .offset sidecar and incremental records from metrics.jsonl
    6. Batch send via telemetry_bridge.batch_capture (passes all record fields)
    7. On success: update .offset and .last_sync_success, compact metrics.jsonl
       On failure: update .last_sync_attempt (not .offset, retry next time)
    8. Write .sync_status.json with lifecycle tracking fields
    9. All operations wrapped in try/except (exceptions never propagate)

    Args:
        artifact_root: Path to the artifacts directory containing metrics.jsonl
    """
    try:
        metrics_file = artifact_root / "metrics.jsonl"
        last_sync_success_file = artifact_root / ".last_sync_success"
        last_sync_attempt_file = artifact_root / ".last_sync_attempt"
        offset_file = artifact_root / ".offset"

        # Step 1-2: Check backoff windows
        now = time.time()
        last_sync_success = _read_sync_timestamp(last_sync_success_file)
        last_sync_attempt = _read_sync_timestamp(last_sync_attempt_file)

        if _should_skip_sync(now, last_sync_success, last_sync_attempt):
            return

        # Step 3: Probe network connectivity
        posthog_hostname = _normalize_posthog_host()
        if not _probe_posthog_network(posthog_hostname):
            # Network unreachable: update attempt and exit
            _record_sync_outcome(artifact_root, False, 0, now, last_sync_attempt_file)
            return

        # Step 4: Read offset and incremental records
        if not metrics_file.exists():
            return

        offset = 0
        if offset_file.exists():
            try:
                offset = int(offset_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                offset = 0

        records_with_lines = _read_pending_records(metrics_file, offset)
        if not records_with_lines:
            return

        pending_count = len(records_with_lines)

        # Step 5-8: Batch send and handle outcome
        try:
            synced_count, last_synced_line = _batch_send_records(
                records_with_lines, BATCH_SIZE, offset_file
            )

            all_synced = (synced_count == len(records_with_lines))
            if all_synced:
                # Success path: update success timestamp and compact
                _record_sync_outcome(artifact_root, True, 0, now, last_sync_attempt_file)
                _compact_metrics_jsonl(metrics_file, last_synced_line, offset_file)
            else:
                # Partial success: update attempt (not success) and record remaining
                remaining = len(records_with_lines) - synced_count
                _record_sync_outcome(artifact_root, False, remaining, now, last_sync_attempt_file)

        except Exception as exc:
            # Send failed: update attempt and record failure
            _logger.debug("telemetry sync send failed: %s", exc)
            _record_sync_outcome(artifact_root, False, pending_count, now, last_sync_attempt_file)

    except Exception as exc:
        # Top-level catch: sync must never break gateway flow
        _logger.debug("_maybe_sync_telemetry failed: %s", exc)


def _write_sync_status(artifact_root: Path, success: bool, pending_count: int) -> None:
    """Write .sync_status.json with lifecycle tracking fields.

    Args:
        artifact_root: Path to the artifacts directory
        success: Whether the sync succeeded
        pending_count: Number of records waiting to be synced
    """
    status_file = artifact_root / ".sync_status.json"
    now_iso_val = now_iso()

    # Read existing status
    status: dict[str, Any] = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}

    if success:
        status["last_success_ts"] = now_iso_val
        status["failure_count"] = 0
    else:
        status["last_failure_ts"] = now_iso_val
        status["failure_count"] = int(status.get("failure_count", 0)) + 1

    status["pending_count"] = pending_count

    try:
        status_file.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _handle_source_repo_check(cwd: Path, host: str, event: str) -> int | None:
    """Handle source repo readonly mode. Returns exit code if handled, None to continue."""
    if is_memory_core_source_repo(cwd):
        mode = get_source_repo_mode(cwd)
        if mode != "develop":
            readonly_package = _build_readonly_source_repo_package(cwd, host, event)
            sys.stdout.write(json.dumps(readonly_package, ensure_ascii=False) + "\n")
            return 0
    return None


def _emit_pretooluse_metrics(host: str, event: str, status: str, start_time: float) -> None:
    """Emit metrics for pre-tool-use branch before returning."""
    try:
        from .memory_hook_metrics import emit_metrics
        duration_ms = max(1, int((time.time() - start_time) * 1000))
        minimal_package = {"status": status}
        emit_metrics(ARTIFACT_ROOT, host, event, minimal_package, duration_ms=duration_ms)
    except Exception as exc:
        _logger.debug("pre-tool-use metrics emit skipped: %s", exc)


def _handle_pretooluse_guard(
    args: argparse.Namespace, raw_payload: str, cwd: Path, start_time: float
) -> int | None:
    """Handle pre-tool-use event: intercept write operations via guard script.

    Returns exit code if handled, None to continue to normal flow.
    """
    if args.event != "pre-tool-use":
        return None

    guard_script = Path(__file__).parent / "pretooluse_guard.py"
    if guard_script.exists():
        try:
            guard_env = {**os.environ, "MEMORY_HOOK_ORIGINAL_CWD": str(cwd)}
            proc = subprocess.run(
                [sys.executable, str(guard_script)],
                input=raw_payload,
                text=True,
                capture_output=True,
                timeout=5,
                env=guard_env,
            )
            if proc.stdout:
                sys.stdout.write(proc.stdout)
            if proc.stderr:
                sys.stderr.write(proc.stderr)
            status = "ok" if proc.returncode == 0 else "error"
            _emit_pretooluse_metrics(args.host, args.event, status, start_time)
            return proc.returncode
        except subprocess.TimeoutExpired:
            append_error_log("pretooluse-guard", "guard timed out after 5s", {"cwd": str(cwd)})
        except Exception as exc:
            append_error_log("pretooluse-guard", "guard execution failed", {"error": str(exc)})

    # Fallback: allow if guard unavailable or failed
    print(json.dumps({"decision": "allow", "reason": "guard unavailable, allowing by default"}))
    _emit_pretooluse_metrics(args.host, args.event, "ok", start_time)
    return 0


def _handle_session_start_setup(cwd: Path) -> None:
    """Handle session-start side effects: health check, state update, telemetry sync."""
    _launch_async_health_check(cwd)
    project_scope = determine_project_scope(cwd)
    _update_state_dynamic_fields(cwd, project_scope)
    try:
        _maybe_sync_telemetry(ARTIFACT_ROOT)
    except Exception as exc:
        _logger.debug("telemetry sync skipped: %s", exc)


def _handle_prompt_submit_logging(cwd: Path, payload: dict[str, Any]) -> None:
    """Handle prompt-submit real-time logging."""
    try:
        _log_prompt_submit(cwd, payload)
    except Exception as exc:
        _logger.warning("_log_prompt_submit failed: %s", exc)


def _inject_health_alert(cwd: Path, package: dict[str, Any]) -> None:
    """Inject previous session's health report if degraded (session-start only)."""
    prev_health_report = cwd / "memory" / "system" / "health-report.json"
    if not prev_health_report.exists():
        return
    try:
        report_text = prev_health_report.read_text()
        report_data = json.loads(report_text)
        if report_data.get("status") == "degraded":
            package.setdefault("system_context", {})
            package["system_context"]["previous_health_alert"] = {
                "status": "degraded",
                "errors": report_data.get("validation_errors", [])[:5],
                "note": "Detected from previous session startup health check",
            }
            append_error_log("health-check", "Project health degraded (from previous check)", report_data)
    except Exception as e:
        _logger.debug("Failed to read previous health report: %s", e)


def _handle_integrity_check(
    cwd: Path, package: dict[str, Any], host: str, event: str
) -> None:
    """Verify project integrity on session-start. May set package status to 'blocked'."""
    integrity_result = _integrity_verify(cwd)
    if not integrity_result or integrity_result.get("ok", True):
        return
    if integrity_result.get("skipped_reason") == "key_not_found":
        _logger.info("Integrity protection skipped: key not found")
        return
    append_error_log(
        "memory-hook-integrity",
        "project integrity check failed",
        {"host": host, "event": event, "cwd": str(cwd), "integrity": integrity_result},
    )
    package["status"] = "blocked"
    package.setdefault("validation_errors", [])
    if isinstance(package.get("validation_errors"), list):
        package["validation_errors"].append("integrity-check-failed")
        for err in integrity_result.get("errors", []):
            detail = err.get("detail", str(err))
            package["validation_errors"].append(f"integrity-error: {detail}")


def _write_artifacts_and_emit_metrics(
    args: argparse.Namespace, writer: Any, package: dict[str, Any], cwd: Path, start_time: float
) -> bool:
    """Write artifacts, re-sign manifest, and emit metrics. Returns write_ok status."""
    write_ok = writer.write(args.host, args.event, package)
    if not write_ok:
        append_error_log(
            "memory-hook-gateway",
            "artifact write failed",
            {"host": args.host, "event": args.event, "error": writer.last_error},
        )
        print(f"[memory-hook-gateway] artifact write failed: {writer.last_error}", file=sys.stderr)
    if write_ok:
        _integrity_sign(cwd)
    try:
        from .memory_hook_metrics import emit_metrics
        duration_ms = max(1, int((time.time() - start_time) * 1000))
        emit_metrics(ARTIFACT_ROOT, args.host, args.event, package, duration_ms=duration_ms)
    except Exception as exc:
        _logger.debug("metrics emit skipped: %s", exc)
    return bool(write_ok)


def _compute_exit_code(args: argparse.Namespace, package: dict[str, Any]) -> int:
    """Determine exit code based on package status."""
    if package["status"] != "ok":
        append_error_log(
            "memory-hook-gateway",
            "missing canonical prerequisites or project-map validation failed",
            {
                "host": args.host,
                "event": args.event,
                "missing_paths": package["missing_paths"],
                "validation_errors": package.get("validation_errors", []),
            },
        )
        print(
            "[memory-hook-gateway] degraded: "
            f"missing canonical paths: {', '.join(package['missing_paths']) or 'none'}; "
            f"project-map errors: {', '.join(package.get('validation_errors', [])) or 'none'}",
            file=sys.stderr,
        )
        return 1
    return 0


def _dispatch_output(args: argparse.Namespace, package: dict[str, Any],
                     raw_payload: str, payload: dict[str, Any], cwd: Path,
                     exit_code: int) -> int:
    """Handle final output dispatch: no-delegate JSON or delegate execution."""
    if args.no_delegate:
        sys.stdout.write(json.dumps(package, ensure_ascii=False) + "\n")
        return exit_code
    return _execute_delegate(args, raw_payload, payload, cwd, package=package)


def main() -> int:
    start_time = time.time()
    args = _parse_args()
    raw_payload = sys.stdin.read()
    payload = _read_payload(raw_payload)
    cwd = _discover_cwd(payload)

    # M3: Anti-pollution - source repo gets readonly context-package instead of noop
    source_result = _handle_source_repo_check(cwd, args.host, args.event)
    if source_result is not None:
        return source_result

    if is_denied_project_root(cwd):
        sys.stdout.write("{}\n")
        return 0

    if _should_noop_for_external_context(payload):
        return _delegate_noop_response(args.host)

    # ── PreToolUse guard: intercept write operations ──
    guard_result = _handle_pretooluse_guard(args, raw_payload, cwd, start_time)
    if guard_result is not None:
        return guard_result

    # Async: Launch health check in background for session-start
    if args.event == "session-start":
        _handle_session_start_setup(cwd)

    # F4: PromptSubmit real-time logging
    if args.event == "prompt-submit":
        _handle_prompt_submit_logging(cwd, payload)

    writer = ArtifactWriter(CONTEXT_ROOT, ERROR_LOG, datetime_module=datetime)
    package = build_context_package(args.host, args.event, payload)

    # Health Alert: Inject previous session's health report if available
    if args.event == "session-start":
        _inject_health_alert(cwd, package)

    # L2: Verify integrity on session-start (after package is built)
    if args.event == "session-start":
        _handle_integrity_check(cwd, package, args.host, args.event)

    _write_artifacts_and_emit_metrics(args, writer, package, cwd, start_time)

    exit_code = _compute_exit_code(args, package)
    return _dispatch_output(args, package, raw_payload, payload, cwd, exit_code)


def _gateway_excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
    """Top-level exception hook: capture unexpected gateway crashes to JSONL."""
    try:
        metrics_dir = ARTIFACT_ROOT
        metrics_dir.mkdir(parents=True, exist_ok=True)
        metrics_file = metrics_dir / "metrics.jsonl"
        # Calculate duration_ms if we have a start_time (from main())
        # Otherwise use 0 for unexpected crashes before main() starts
        duration_ms = 0
        if hasattr(sys, '_gateway_start_time'):
            duration_ms = int((time.time() - sys._gateway_start_time) * 1000)
        record = {
            "event": "hook_error",
            "error_type": exc_type.__name__,
            "error_message": str(exc_value)[:500],
            "hook_version": "memory-hook-gateway-v1",
            "timestamp": now_iso(),
            "duration_ms": duration_ms,
            "status": "error",
        }
        with metrics_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Call the default handler to preserve standard traceback behavior
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _gateway_excepthook


if __name__ == "__main__":
    raise SystemExit(main())
