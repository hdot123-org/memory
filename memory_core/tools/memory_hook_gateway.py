#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPT_PATH = Path(__file__).resolve()
try:
    from .memory_root_discovery import discover_roots
except ImportError:
    from memory_core.tools.memory_root_discovery import discover_roots
REPO_ROOT, WORKSPACE_ROOT = discover_roots(Path.cwd())
ARTIFACT_ROOT = WORKSPACE_ROOT / "artifacts" / "memory-hook"
CONTEXT_ROOT = ARTIFACT_ROOT / "contexts"
EVENT_LOG = ARTIFACT_ROOT / "events.jsonl"
ERROR_LOG = WORKSPACE_ROOT / "memory" / "system" / "errors.log"
CLAUDE_HOOK_STATE_DIR = Path.home() / ".agents" / "skills" / "cmux" / "scripts"
try:
    from .cmux_hook_state import default_hook_state_path, record_hook_event
except ImportError:
    pass  # type: ignore  # noqa: E402

try:
    from .memory_hook_adapters.workbot_policy import WorkbotGatewayBusinessPolicy
    from .memory_hook_adapters.workbot_runtime_profile import build_workbot_runtime_profile
    from .memory_hook_config import CoreConfig
    from .memory_hook_core import build_context_package_core, build_context_package_from_config
    from .memory_hook_impls import (
        ArtifactSinkImpl,
        ArtifactWriter,
        ClaudeDelegate,
        CodexDelegate,
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
    from memory_hook_adapters.workbot_policy import WorkbotGatewayBusinessPolicy  # type: ignore
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

_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "workbot")
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
    "default": (".memory_hook_adapters.default_runtime_profile", "build_default_runtime_profile"),
}


def _load_adapter_profile(adapter_name: str, repo_root: Path, workspace_root: Path):
    """Load adapter profile with fallback to workbot on import failure.

    Raises:
        KeyError: If adapter_name is not in _ADAPTER_REGISTRY.
    """
    if adapter_name not in _ADAPTER_REGISTRY:
        raise KeyError(f"unknown adapter: {adapter_name}")

    _mod_path, _fn_name = _ADAPTER_REGISTRY[adapter_name]
    try:
        _mod = importlib.import_module(_mod_path, package="memory_core.tools")
        _fn = getattr(_mod, _fn_name)
        return _fn(repo_root, workspace_root)
    except ImportError:
        # Fallback to workbot adapter
        from memory_core.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile as _fn_fallback,  # type: ignore
        )
        return _fn_fallback(repo_root, workspace_root)


# Adapter configuration store (replaces globals().update injection).
_adapter_config: dict[str, Any] = {}


def load_adapter_config(profile: dict[str, Any]) -> None:
    """Load adapter runtime profile into _adapter_config.

    Also writes keys into globals() for backward compatibility with
    existing code that reads module-level attributes directly.
    """
    _adapter_config.clear()
    _adapter_config.update(profile)
    # Backward-compat: expose keys as module globals so hasattr() checks
    # and direct attribute reads from existing callers still work.
    globals().update(profile)


# Load adapter profile once; feed both new config store and legacy globals.
_adapter_profile = _load_adapter_profile(_ADAPTER_NAME, REPO_ROOT, WORKSPACE_ROOT)
load_adapter_config(_adapter_profile)


__all__ = [
    'build_context_package',
    'build_context_package_simple',
    'ArtifactWriter',
    'DelegateRouter',
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
    _policy_class = _adapter_config.get("GATEWAY_POLICY_CLASS", WorkbotGatewayBusinessPolicy)
    return _policy_class(config=config)


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
    return builder


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


def _write_targets_via_policy() -> dict[str, Any]:
    """IF-5: Get write targets via Policy facade."""
    return _get_write_policy().get_targets()


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
    parser.add_argument("--host", required=True, choices=("codex", "claude", "factory"))
    parser.add_argument("--event", required=True, choices=("session-start", "prompt-submit", "stop", "notification"))
    parser.add_argument("--no-delegate", action="store_true", help="Generate gateway artifacts only.")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_payload(raw_payload: str) -> dict[str, Any]:
    if not raw_payload.strip():
        return {}
    try:
        loaded = json.loads(raw_payload)
    except json.JSONDecodeError:
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


def _path_within_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _discover_cwd(payload: dict[str, Any]) -> Path:
    provided_cwd = _payload_cwd(payload)
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
    if os.environ.get("MEMORY_HOOK_FORCE") or os.environ.get("WORKBOT_FORCE_HOOK"):
        return False
    env_cwd = _environment_cwd()
    provided_cwd = _payload_cwd(payload)
    env_in_repo = bool(env_cwd and _path_within_repo(env_cwd))
    payload_in_repo = bool(provided_cwd and _path_within_repo(provided_cwd))
    return not env_in_repo and not payload_in_repo


def _delegate_noop_response(host: str) -> int:
    """M2: delegate-owned bypass instead of gateway host-dispatch."""
    delegate = _get_host_delegate(host)
    result = delegate.noop_response()
    if result.stdout:
        sys.stdout.write(result.stdout)
    return result.returncode



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


def _section_bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    bullets: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == heading or stripped.endswith(heading.replace("## ", "").replace("### ", "")):
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            break
        if in_section and line.strip().startswith("- "):
            bullets.append(line.strip()[2:].strip().strip("`"))
    return bullets


def _section_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start_idx = idx + 1
            break
    if start_idx is None:
        return ""
    body: list[str] = []
    for line in lines[start_idx:]:
        if line.strip().startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _markdown_code_tokens(text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"`([^`]+)`", text)}


def _json_string_values(text: str, key: str) -> set[str]:
    pattern = rf'"{re.escape(key)}"\s*:\s*"([^"]+)"'
    return {match.group(1) for match in re.finditer(pattern, text)}


def _json_object_keys(text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r'"([^"]+)"\s*:', text)}


def governance_frozen_tuple_blocker_errors() -> list[str]:
    return _get_gateway_business_policy().governance_frozen_tuple_blocker_errors()


def event_contract_blocker_errors() -> list[str]:
    return _get_gateway_business_policy().event_contract_blocker_errors()


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _classify_truth_ref(path: Path) -> str:
    if path == PROJECT_MAP_ROOT / "legal-core-map.md":
        return "legal-core"
    if path == PROJECT_MAP_ROOT / "INDEX.md":
        return "project-map-index"
    if path in GLOBAL_CANONICAL:
        return "global-canonical"
    if _path_is_under(path, WORKSPACE_ROOT / "memory" / "kb" / "global" / "projects"):
        return "compatibility-only"
    if _path_is_under(path, WORKSPACE_ROOT / "memory" / "kb" / "projects"):
        return "project-canonical"
    if _path_is_under(path, WORKSPACE_ROOT / "memory" / "docs"):
        return "docs"
    if _path_is_under(path, WORKSPACE_ROOT / "projects"):
        return "project-runtime"
    if _path_is_under(path, WORKSPACE_ROOT / "artifacts"):
        return "artifact"
    if _path_is_under(path, WORKSPACE_ROOT / "tools"):
        return "tooling"
    if _path_is_under(path, WORKSPACE_ROOT / "memory" / "log"):
        return "log"
    if _path_is_under(path, WORKSPACE_ROOT / "memory" / "system"):
        return "system"
    if _path_is_under(path, REPO_ROOT / "app"):
        return "app"
    if _path_is_under(path, REPO_ROOT / "agents"):
        return "agents"
    if _path_is_under(path, REPO_ROOT / "gpt-web-to"):
        return "gpt-web-to"
    if path == REPO_ROOT / "AGENTS.md":
        return "repo-policy"
    if path == WORKSPACE_ROOT / "INDEX.md":
        return "workspace-entry"
    return "other"


def _authority_ref_allowed(path: Path) -> bool:
    return path in AUTHORITY_ALLOWED_PATHS or path in GLOBAL_CANONICAL


def _lower_evidence_ref(path: Path) -> bool:
    return any(_path_is_under(path, root) for root in LOWER_EVIDENCE_ROOTS)


def _truth_basis_sections_for(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "source_refs": _section_bullets(text, "### Source Refs"),
        "authority_refs": _section_bullets(text, "### Authority Refs"),
        "evidence_refs": _section_bullets(text, "### Evidence Refs"),
        "conflict_status": _section_bullets(text, "### Conflict Status"),
    }


def _truth_basis_errors_for(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing truth canonical: {path}"]
    text = path.read_text(encoding="utf-8")
    if "Truth Basis" not in text:
        return [f"truth basis section missing: {path}"]
    sections = _truth_basis_sections_for(path)
    source_refs = sections["source_refs"]
    authority_refs = sections["authority_refs"]
    evidence_refs = sections["evidence_refs"]
    conflict = sections["conflict_status"]
    if not source_refs:
        errors.append(f"source refs missing: {path}")
    if not authority_refs:
        errors.append(f"authority refs missing: {path}")
    if not evidence_refs:
        errors.append(f"evidence refs missing: {path}")
    if not conflict:
        errors.append(f"conflict status missing: {path}")
    elif conflict != ["resolved"]:
        errors.append(f"conflict status unresolved: {path}")
    source_paths = [(REPO_ROOT / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in source_refs]
    authority_paths = [(REPO_ROOT / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in authority_refs]
    evidence_paths = [(REPO_ROOT / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in evidence_refs]
    for ref_path in [*source_paths, *authority_paths, *evidence_paths]:
        if not _path_is_under(ref_path, REPO_ROOT):
            errors.append(f"truth ref outside repository: {ref_path}")
        if not ref_path.exists():
            errors.append(f"truth ref missing on disk: {ref_path}")
    if set(source_refs) == set(evidence_refs):
        errors.append(f"source refs and evidence refs must not be identical: {path}")
    if set(source_refs) & set(authority_refs):
        errors.append(f"source refs overlap authority refs: {path}")
    if set(authority_refs) & set(evidence_refs):
        errors.append(f"authority refs overlap evidence refs: {path}")
    for authority_path in authority_paths:
        if not _authority_ref_allowed(authority_path):
            errors.append(f"authority ref is not formal canonical: {authority_path}")
    if source_paths and all(_classify_truth_ref(source_path) in {"global-canonical", "legal-core", "project-map-index"} for source_path in source_paths):
        errors.append(f"source refs do not include a non-canonical origin: {path}")
    if evidence_paths and not any(_lower_evidence_ref(evidence_path) for evidence_path in evidence_paths):
        errors.append(f"evidence refs do not include lower-layer support: {path}")
    return errors


def _existing_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if path.exists()]


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
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--short", "--", *tracked_scope],
        text=True,
        capture_output=True,
        check=False,
    )
    entries = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    head_commit = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    latest_commit = (head_commit.stdout or "").strip()
    commit_scope = [_normalize_repo_scope_entry(path) for path in REGISTRATION_GIT_SCOPE]
    commit_scope = [path for path in commit_scope if path]
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
    return _get_gateway_business_policy().truth_basis_for_scope(project_scope)


def write_targets() -> dict[str, Any]:
    try:
        return _write_targets_via_policy()
    except Exception:
        today_log = WORKSPACE_ROOT / "memory" / "log" / f"{datetime.now().date().isoformat()}.md"
        return {
            "fact": str(today_log),
            "global_canonical": str(WORKSPACE_ROOT / "memory" / "kb" / "global"),
            "project_canonical": str(WORKSPACE_ROOT / "memory" / "kb" / "projects"),
            "decision": str(WORKSPACE_ROOT / "memory" / "kb" / "decisions"),
            "lesson": str(WORKSPACE_ROOT / "memory" / "kb" / "lessons"),
            "docs": str(WORKSPACE_ROOT / "memory" / "docs"),
            "action": str(WORKSPACE_ROOT / "memory" / "inbox.md"),
            "project_runtime": str(WORKSPACE_ROOT / "projects"),
            "artifacts": str(WORKSPACE_ROOT / "artifacts"),
            "system_error": str(ERROR_LOG),
            "invalid_memory": str(WORKSPACE_ROOT / "memory" / "archive" / "invalid"),
            "kb_policy": {
                "mode": "read-first-CRUD",
                "overwrite_allowed": False,
                "conflict_strategy": "preserve-and-escalate",
            },
        }


def resolve_route_target(kind: str) -> str:
    try:
        return _resolve_route_target_via_policy(kind)
    except Exception:
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
    system_context = package.setdefault("system_context", {})
    if isinstance(system_context, dict):
        system_context["core_provider"] = provider_name
        system_context["core_provider_requested"] = requested_provider
        if provider_errors:
            system_context["core_provider_fallback_errors"] = provider_errors

    if provider_errors:
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
        rendered = json.dumps(context, ensure_ascii=False, sort_keys=True)
        with ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now_iso()}] [{component}] [error] {message} | context={rendered}\n")


def write_artifacts(package: dict[str, Any]) -> dict[str, str]:
    try:
        return _write_artifacts_via_sink(package)
    except RuntimeError:
        # Fallback only for synthetic sink failure (e.g., not implemented)
        _ensure_artifact_dirs()
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        snapshot_path = CONTEXT_ROOT / f"{timestamp}-{package['host']}-{package['event']}.json"
        suffix = 1
        while snapshot_path.exists():
            snapshot_path = CONTEXT_ROOT / f"{timestamp}-{suffix:02d}-{package['host']}-{package['event']}.json"
            suffix += 1
        latest_path = CONTEXT_ROOT / f"latest-{package['host']}-{package['event']}.json"
        package["artifact_refs"] = {
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "event_log": str(EVENT_LOG),
        }
        rendered = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        snapshot_path.write_text(rendered, encoding="utf-8")
        latest_path.write_text(rendered, encoding="utf-8")
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(package, ensure_ascii=False) + "\n")
        return {"snapshot": str(snapshot_path), "latest": str(latest_path)}


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


def main() -> int:
    args = _parse_args()
    raw_payload = sys.stdin.read()
    payload = _read_payload(raw_payload)
    cwd = _discover_cwd(payload)

    if _should_noop_for_external_context(payload):
        return _delegate_noop_response(args.host)

    writer = ArtifactWriter(CONTEXT_ROOT, ERROR_LOG, datetime_module=datetime)
    package = build_context_package(args.host, args.event, payload)
    write_ok = writer.write(args.host, args.event, package)
    if not write_ok:
        append_error_log(
            "memory-hook-gateway",
            "artifact write failed",
            {"host": args.host, "event": args.event, "error": writer.last_error},
        )
        print(f"[memory-hook-gateway] artifact write failed: {writer.last_error}", file=sys.stderr)

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

    if args.no_delegate:
        sys.stdout.write(json.dumps(package, ensure_ascii=False) + "\n")
        return 0

    try:
        if args.host == "codex":
            proc = _delegate_codex(args.event, raw_payload)
        elif args.host == "claude":
            proc = _delegate_claude(args.event, raw_payload, payload)
        else:
            # factory and others: no delegate
            proc = None
    except RuntimeError as exc:
        append_error_log(
            "memory-hook-gateway",
            "delegate preflight failed",
            {"host": args.host, "event": args.event, "error": str(exc), "cwd": str(cwd)},
        )
        noop = _get_host_delegate(args.host).noop_response()
        if noop.stdout:
            sys.stdout.write(noop.stdout)
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
        # factory and others: skip delegate, return success
        noop = _get_host_delegate(args.host).noop_response()
        if noop.stdout:
            sys.stdout.write(noop.stdout)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
