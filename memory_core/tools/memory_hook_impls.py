#!/usr/bin/env python3
"""M2 Default Implementations for memory-hook-gateway interfaces.

This module provides default implementations for:
- HostDelegateImpl (Codex/Claude delegates)
- PolicyRegistryImpl
- RouteTargetPolicyImpl / WriteTargetPolicyImpl
- ArtifactSinkImpl / ErrorSinkImpl
"""


import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Import shared rule helpers (consolidation REF-001 §4.3)
try:
    from ._rule_helpers import (
        _existing_paths,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )
    from ._scope_resolver_base import ScopeResolverBase
except ImportError:
    from _rule_helpers import (  # type: ignore
        _existing_paths,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )
    from _scope_resolver_base import ScopeResolverBase  # type: ignore

try:
    from .memory_hook_interfaces import (
        ArtifactSink,
        ErrorSink,
        GatewayBusinessPolicy,
        HostDelegate,
        PolicyRegistry,
        RegistrationCommitGate,
        RouteTargetPolicy,
        TruthBasis,
        WriteTargetPolicy,
    )
except ImportError:
    from memory_hook_interfaces import (  # type: ignore
        ArtifactSink,
        ErrorSink,
        GatewayBusinessPolicy,
        HostDelegate,
        PolicyRegistry,
        RegistrationCommitGate,
        RouteTargetPolicy,
        TruthBasis,
        WriteTargetPolicy,
    )

try:
    from ._validation_constants import (
        MKR_ABSORBED_STATUS,
        MKR_ACTIVE_LEGAL_MAP_ONLY,
        MKR_ATOMIC_REGISTRATION_GIT_COMMIT,
        MKR_COMPATIBILITY_ONLY,
        MKR_CORE_ACTIVE_LEGAL,
        MKR_CORE_MAP_ONLY,
        MKR_DOCS_UNABSORBED,
        MKR_GIT_COMMIT_GATE,
        MKR_GOVERNANCE_MAP_GRANTS_LEGALITY,
        MKR_HOOK_MAP_ONLY_CONTEXT,
        MKR_HOOK_REGISTRATION_GATE,
        MKR_INCOMING_RAW,
        MKR_INGESTION_REGISTRY_REF,
        MKR_NON_LEGAL_MATERIAL,
        MKR_REGISTRY_GIT_COMMIT_GATE,
        MKR_RETIRED_STATUS,
        MKR_UNIQUE_LEGAL_ENTRY,
        MKR_UNWASHED_NOT_LEGAL,
        MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY,
        MKR_WORKSPACE_GIT_COMMIT_RULE,
        MKR_WORKSPACE_PROJECT_MAP_REF,
    )
except ImportError:
    pass

# Import domain exceptions (REF-001 §4.8)
try:
    from ._rule_errors import (
        UnknownHostError,
        UnknownRouteKindError,
        UnsupportedScopeError,
    )
except ImportError:
    from _rule_errors import (  # type: ignore
        UnknownHostError,
        UnknownRouteKindError,
        UnsupportedScopeError,
    )

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore


# ---------------------------------------------------------------------------
# IF-1: HostDelegate Implementations
# ---------------------------------------------------------------------------

class FactoryDelegate(HostDelegate):
    """Neutral delegate for Factory host: returns empty JSON for all events.

    Factory hooks don't require cmux integration. This delegate provides
    a neutral pass-through response that doesn't block session creation.
    """

    def can_handle(self) -> bool:
        return True

    def execute(
        self,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        return self.noop_response()

    def noop_response(self) -> subprocess.CompletedProcess[str]:
        """Return neutral empty JSON response for Factory hooks."""
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="{}\n", stderr="")

    @property
    def host_unavailable(self) -> bool:
        return False


class NoopHostDelegate(HostDelegate):
    """Noop delegate: always handles, always returns empty JSON.

    5b.6: Returns host_unavailable=True to separate policy_decision
    from delegate availability. Consumers should check host_unavailable
    before interpreting the policy_decision.
    """

    def can_handle(self) -> bool:
        return True

    def execute(
        self,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        return self.noop_response()

    def noop_response(self) -> subprocess.CompletedProcess[str]:
        """Return response with host_unavailable=True marker.

        The stdout JSON includes:
        - host_unavailable: True (delegate is a noop, host not present)
        - policy_decision: "no_host" (separate from delegate availability)
        """
        result_json = json.dumps({
            "host_unavailable": True,
            "policy_decision": "no_host",
        }) + "\n"
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=result_json, stderr="")

    @property
    def host_unavailable(self) -> bool:
        return True


def resolve_host_delegate(host: str, mode: str = "auto") -> HostDelegate:
    """Resolve a HostDelegate by host name and mode.

    Only factory is supported (INV-6).

    Modes:
        "auto": try factory delegate, fallback to NoopHostDelegate
        "noop": always return NoopHostDelegate
        "cmux": always return factory delegate (may have can_handle=False)
    """
    if host == "factory":
        cmux_delegate: HostDelegate = FactoryDelegate()
    else:
        return NoopHostDelegate()

    if mode == "noop":
        return NoopHostDelegate()
    elif mode == "cmux":
        return cmux_delegate
    else:
        # "auto" or unknown mode
        if cmux_delegate.can_handle():
            return cmux_delegate
        return NoopHostDelegate()


# ---------------------------------------------------------------------------
# IF-2: PolicyRegistry Implementation
# ---------------------------------------------------------------------------

class PolicyRegistryImpl(PolicyRegistry):
    """Default policy registry implementation with policy-pack support."""

    SCHEMA_VERSION = "m3-policy-pack-v1"
    POLICY_PACK_PATH_ENV = "MEMORY_HOOK_POLICY_PACK_PATH"
    DEFAULT_POLICY_PACK_PATH = (
        Path(__file__).resolve().parents[1] / "memory" / "kb" / "global" / "memory-hook-policy-pack.json"
    )

    # Repository-agnostic fallback policies. Project-specific policy packs
    # should be injected by the gateway/runtime profile instead.
    DEFAULT_POLICIES: dict[str, str] = {
        "registration_phase": "declared-not-enforced",
        "truth_basis_policy": "source-authority-evidence-conflict",
        "kb_write_mode": "read-first-CRUD",
        "kb_overwrite_allowed": "false",
    }

    # Conflict resolution strategies
    CONFLICT_STRATEGIES: dict[str, str] = {
        "legality_source": "fail-fast",
        "registration_commit": "preserve-and-escalate",
        "registration_phase": "prefer-strict",
        "truth_basis_policy": "prefer-strict",
        "kb_write_mode": "prefer-strict",
        "kb_overwrite_allowed": "prefer-strict",
        "default": "preserve-and-escalate",
    }

    def __init__(
        self,
        policy_pack_path: Path | None = None,
        *,
        config: "GatewayBusinessPolicyConfig | None" = None,
        allowed_scopes: set[str] | None = None,
        scope_inherits: dict[str, str] | None = None,
        default_policies: dict[str, str] | None = None,
        conflict_strategies: dict[str, str] | None = None,
    ):
        # Priority: config.policy_pack_path > direct param > env var > default file > None
        if config is not None and config.policy_pack_path is not None:
            resolved_policy_pack_path = config.policy_pack_path
        elif policy_pack_path is not None:
            resolved_policy_pack_path = policy_pack_path
        else:
            env_path = os.environ.get(self.POLICY_PACK_PATH_ENV)
            if env_path:
                resolved_policy_pack_path = Path(env_path).expanduser()
            elif self.DEFAULT_POLICY_PACK_PATH.exists():
                resolved_policy_pack_path = self.DEFAULT_POLICY_PACK_PATH
            else:
                resolved_policy_pack_path = None
        self._policy_pack_path = resolved_policy_pack_path
        self._schema_version = self.SCHEMA_VERSION
        self._policies: dict[str, str] = dict(self.DEFAULT_POLICIES if default_policies is None else default_policies)
        self._conflict_strategies: dict[str, str] = dict(
            self.CONFLICT_STRATEGIES if conflict_strategies is None else conflict_strategies
        )
        self._allowed_scopes = set(allowed_scopes or ())
        self._scope_inherits = dict(scope_inherits or {})
        self._load_dynamic_policy_pack()

    def _load_dynamic_policy_pack(self) -> None:
        """Load dynamic policy pack from disk when present.

        M4 capability: repository-local policy pack can override defaults
        without changing gateway code.
        """
        path = self._policy_pack_path
        if path is None or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return

        schema_version = raw.get("schema_version")
        if isinstance(schema_version, str) and schema_version:
            self._schema_version = schema_version

        policies = raw.get("policies")
        if isinstance(policies, dict):
            for key, value in policies.items():
                if isinstance(key, str) and isinstance(value, str):
                    self._policies[key] = value

        conflict_strategies = raw.get("conflict_strategies")
        if isinstance(conflict_strategies, dict):
            for key, value in conflict_strategies.items():
                if isinstance(key, str) and isinstance(value, str):
                    self._conflict_strategies[key] = value

    def get_policy(self, key: str) -> str | None:
        return self._policies.get(key)

    def validate(self, context: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        # Basic validation - can be extended
        if self._allowed_scopes and context.get("project_scope") not in self._allowed_scopes:
            errors.append(f"invalid project_scope: {context.get('project_scope')}")
        return errors

    def get_policy_pack(self, scope: str) -> dict[str, Any]:
        """Get a policy pack for the given scope.

        Returns:
            Dict containing policy pack with schema_version, policies, conflict_strategy
        """
        if self._allowed_scopes and scope not in self._allowed_scopes:
            raise UnsupportedScopeError(f"unsupported scope: {scope}")
        result: dict[str, Any] = {
            "schema_version": self._schema_version,
            "scope": scope,
            "policies": dict(self._policies),
            "conflict_strategies": dict(self._conflict_strategies),
            "default_strategy": self._conflict_strategies["default"],
        }
        inherited_scope = self._scope_inherits.get(scope)
        if inherited_scope:
            result["inherits"] = inherited_scope
        return result

    def resolve_conflict(self, policy_key: str, values: list[str], strategy: str) -> str:
        """Resolve conflicting policy values using the given strategy.

        Args:
            policy_key: The policy key in conflict
            values: List of conflicting values
            strategy: Conflict resolution strategy

        Returns:
            Resolved policy value

        Raises:
            ValueError: If conflict cannot be resolved
        """
        if not values:
            raise ValueError(f"no values provided for conflict resolution: {policy_key}")

        if len(values) == 1:
            return values[0]

        # Get strategy for this policy key
        effective_strategy = strategy or self._conflict_strategies.get(
            policy_key, self._conflict_strategies["default"]
        )

        if effective_strategy == "fail-fast":
            raise ValueError(
                f"conflict on {policy_key} with values {values!r}: strategy={effective_strategy}"
            )
        elif effective_strategy == "preserve-and-escalate":
            # Return first value but mark as escalated
            return values[0]
        elif effective_strategy == "prefer-strict":
            # Prefer stricter/more restrictive value
            # For boolean-like policies, prefer "false" over "true"
            # For phase policies, prefer "declared-not-enforced" over "enforced"
            if policy_key == "kb_overwrite_allowed":
                return "false" if "false" in values else values[0]
            elif policy_key == "registration_phase":
                return "declared-not-enforced" if "declared-not-enforced" in values else values[0]
            else:
                return values[0]
        else:
            # Default: return first value
            return values[0]

    # --- Validation and scope lookup stubs (delegate to GatewayBusinessPolicy in production) ---

    def validate_project_map(self) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []

    def validate_unique_legal_system_contract(self) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []

    def governance_frozen_tuple_errors(self) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []

    def event_contract_blocker_errors(self) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []

    def git_registration_probe(self, event: str, payload: dict[str, Any]) -> RegistrationCommitGate:
        """Stub: return empty dict. Real impl delegates to GatewayBusinessPolicy."""
        return {}

    def truth_basis_for_scope(self, scope: str) -> TruthBasis:
        """Stub: return empty dict. Real impl delegates to GatewayBusinessPolicy."""
        return {}

    def decision_refs_for_scope(self, scope: str) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []

    def lesson_refs_for_scope(self, scope: str) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []

    def docs_refs_for_scope(self, scope: str) -> list[str]:
        """Stub: return empty list. Real impl delegates to GatewayBusinessPolicy."""
        return []


# ---------------------------------------------------------------------------
# IF-3: RouteTargetPolicy / WriteTargetPolicy Implementations
# ---------------------------------------------------------------------------

class RouteTargetPolicyImpl(RouteTargetPolicy):
    """Default route target policy implementation."""

    def __init__(
        self,
        workspace_root: Path,
        repo_root: Path,
        *,
        global_rule_path: Path | None = None,
        project_runtime_path: Path | None = None,
        global_kb_root: Path | None = None,
        global_kb_enabled: bool = True,
    ):
        self._workspace_root = workspace_root
        self._repo_root = repo_root
        # Global KB 配置 (v0.8.0+)
        self._global_kb_root = global_kb_root
        self._global_kb_enabled = global_kb_enabled
        self._routes: dict[str, str | None] = {
            "fact": None,  # evaluated lazily in resolve() to avoid stale date across midnight
            "global-rule": str(global_rule_path or (workspace_root / "memory" / "kb" / "global" / "memory-routing.md")),
            "source-material": str(workspace_root / "memory" / "docs" / "references"),
            "project-runtime": str(project_runtime_path or (workspace_root / "projects")),
            "system-error": str(workspace_root / "memory" / "system" / "errors.log"),
            "invalid-memory": str(workspace_root / "memory" / "archive" / "invalid"),
        }

    def resolve(self, kind: str) -> str:
        if kind == "fact":
            return str(self._workspace_root / "memory" / "log" / f"{datetime.now().date().isoformat()}.md")
        try:
            value = self._routes[kind]
            if value is None:
                raise ValueError(f"route {kind!r} is not configured")
            return value
        except KeyError:
            raise UnknownRouteKindError(f"unsupported route kind: {kind}")

    def resolve_kb_file(self, domain: str, filename: str) -> Path | None:
        """Resolve a knowledge base file with layered fallback.

        读取链: 项目 memory/kb/<domain>/ 优先 → 未命中 fallback 到 global_kb_root/<domain>/。
        全局源不存在/不可达时优雅降级(只用项目层,不报错,不输出 stderr)。
        enabled=false 时不 fallback。

        Args:
            domain: 知识域名称 (operations/engineering/collaboration/lessons/decisions)
            filename: 文件名

        Returns:
            文件路径,如果两层都无则返回 None
        """
        # 1. 项目层优先
        project_file = self._workspace_root / "memory" / "kb" / domain / filename
        if project_file.exists():
            return project_file

        # 2. Fallback 到全局层 (仅当 enabled 且 global_kb_root 可达时)
        if self._global_kb_enabled and self._global_kb_root is not None:
            global_file = self._global_kb_root / domain / filename
            # 优雅降级: 全局源不存在/不可达时不报错
            if global_file.exists():
                return global_file

        # 3. 两层都无,返回 None
        return None


class WriteTargetPolicyImpl(WriteTargetPolicy):
    """Default write target policy implementation."""

    def __init__(self, workspace_root: Path):
        self._workspace_root = workspace_root
        self._targets: dict[str, Any] = {
            "fact": None,  # evaluated lazily in get_targets() to avoid stale date across midnight,
            "global_canonical": str(workspace_root / "memory" / "kb" / "global"),
            "project_canonical": str(workspace_root / "memory" / "kb" / "projects"),
            "decision": str(workspace_root / "memory" / "kb" / "decisions"),
            "lesson": str(workspace_root / "memory" / "kb" / "lessons"),
            "docs": str(workspace_root / "memory" / "docs"),
            "action": str(workspace_root / "memory" / "inbox.md"),
            "project_runtime": str(workspace_root / "projects"),
            "artifacts": str(workspace_root / "memory" / "artifacts"),
            "system_error": str(workspace_root / "memory" / "system" / "errors.log"),
            "invalid_memory": str(workspace_root / "memory" / "archive" / "invalid"),
            "kb_policy": {
                "mode": "read-first-CRUD",
                "overwrite_allowed": False,
                "conflict_strategy": "preserve-and-escalate",
            },
        }

    def get_targets(self) -> dict[str, Any]:
        result = dict(self._targets)
        if result.get('fact') is None:
            result['fact'] = str(self._workspace_root / 'memory' / 'log' / f'{datetime.now().date().isoformat()}.md')
        return result


# ---------------------------------------------------------------------------
# IF-3.5: GatewayBusinessPolicy Implementation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatewayBusinessPolicyConfig:
    """Configuration payload for gateway business policy implementation."""

    repo_root: Path
    workspace_root: Path
    project_map_root: Path
    project_map_files: list[Path]
    project_map_governance: Path
    truth_model: Path
    global_canonical: list[Path]
    authority_allowed_paths: set[Path]
    lower_evidence_roots: list[Path]
    legal_core_markers: list[str]
    required_registry_scopes: list[str]
    project_canonical: dict[str, Path]
    project_runtime_root: dict[str, Path]
    project_doc_refs: dict[str, list[Path]]
    default_decision_refs: list[Path]
    project_decision_refs: dict[str, list[Path]]
    default_lesson_refs: list[Path]
    project_lesson_refs: dict[str, list[Path]]
    governance_frozen_tuple_files: list[Path]
    event_contract_files: dict[str, Path]
    frozen_tuple_expected: set[str]
    frozen_tuple_legacy_markers: set[str]
    formal_source_types: set[str]
    formal_event_types: set[str]
    formal_event_statuses: set[str]
    formal_field_keys: set[str]
    legacy_field_keys: set[str]
    required_canonical: list[Path]
    workspace_index_path: Path
    docs_index_path: Path
    overview_doc_path: Path
    global_index_path: Path
    hook_contract_path: Path
    default_project_scope: str
    scope_match_hints: dict[str, list[Path]]
    read_text_if_exists_fn: Callable[[Path], str]
    policy_pack_path: Path | None = None


class GatewayBusinessPolicyImpl(ScopeResolverBase, GatewayBusinessPolicy):
    """Adapter/business policy implementation for memory hook gateway.

    Inherits from GatewayBusinessPolicy (interface) and ScopeResolverBase
    (scope resolution logic shared with ScopeResolver).
    """

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
    ):
        # Explicitly initialize ScopeResolverBase
        ScopeResolverBase.__init__(self, config, scope_config_path=scope_config_path)

    def _read_text_if_exists(self, path: Path) -> str:
        return self._config.read_text_if_exists_fn(path)

    def validate_project_map_files(self) -> list[str]:
        """Delegate to ProjectMapValidator from business_policy_checks."""
        try:
            from .business_policy_checks import ProjectMapValidator
        except ImportError:
            from business_policy_checks import ProjectMapValidator  # type: ignore
        validator = ProjectMapValidator(self._config)
        return validator.validate_project_map_files()

    def validate_unique_legal_system_contract(self) -> list[str]:
        """Delegate to ProjectMapValidator from business_policy_checks."""
        try:
            from .business_policy_checks import ProjectMapValidator
        except ImportError:
            from business_policy_checks import ProjectMapValidator  # type: ignore
        validator = ProjectMapValidator(self._config)
        return validator.validate_unique_legal_system_contract()

    def governance_frozen_tuple_blocker_errors(self) -> list[str]:
        """Delegate to FrozenTupleChecker from business_policy_checks."""
        try:
            from .business_policy_checks import FrozenTupleChecker
        except ImportError:
            from business_policy_checks import FrozenTupleChecker  # type: ignore
        checker = FrozenTupleChecker(self._config)
        return checker.governance_frozen_tuple_blocker_errors()

    def event_contract_blocker_errors(self) -> list[str]:
        """Delegate to EventContractChecker from business_policy_checks."""
        try:
            from .business_policy_checks import EventContractChecker
        except ImportError:
            from business_policy_checks import EventContractChecker  # type: ignore
        checker = EventContractChecker(self._config)
        return checker.event_contract_blocker_errors()

    def decision_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_decision_refs + self._config.project_decision_refs.get(project_scope, [])
        return _existing_paths(refs)

    def lesson_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_lesson_refs + self._config.project_lesson_refs.get(project_scope, [])
        return _existing_paths(refs)

    def docs_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.project_doc_refs.get(project_scope, [])
        return _existing_paths(refs)

    def truth_basis_for_scope(self, project_scope: str) -> TruthBasis:
        """Delegate to TruthBasisResolver from business_policy_checks."""
        try:
            from .business_policy_checks import TruthBasisResolver
        except ImportError:
            from business_policy_checks import TruthBasisResolver  # type: ignore
        resolver = TruthBasisResolver(self._config)
        return resolver.truth_basis_for_scope(project_scope)


# ---------------------------------------------------------------------------
# IF-4: ArtifactSink / ErrorSink Implementations
# ---------------------------------------------------------------------------

class ArtifactSinkImpl(ArtifactSink):
    """Default artifact sink implementation."""

    def __init__(
        self,
        context_root: Path,
        event_log: Path,
        datetime_module: Any = datetime,
    ):
        self._context_root = context_root
        self._event_log = event_log
        self._datetime = datetime_module

    def ensure_dirs(self) -> None:
        self._context_root.mkdir(parents=True, exist_ok=True)
        (self._event_log.parent / "events").mkdir(parents=True, exist_ok=True)

    def write(self, package: dict[str, Any]) -> dict[str, str]:
        self.ensure_dirs()
        now = self._datetime.now()
        day = now.date().isoformat()
        timestamp = now.strftime("%Y%m%dT%H%M%S%f")
        daily_context_root = self._context_root / day
        daily_context_root.mkdir(parents=True, exist_ok=True)
        snapshot_path = daily_context_root / f"{timestamp}-{package['host']}-{package['event']}.json"
        suffix = 1
        while snapshot_path.exists():
            snapshot_path = daily_context_root / f"{timestamp}-{suffix:02d}-{package['host']}-{package['event']}.json"
            suffix += 1
        latest_path = self._context_root / f"latest-{package['host']}-{package['event']}.json"
        daily_latest_path = daily_context_root / f"latest-{package['host']}-{package['event']}.json"
        daily_event_log = self._event_log.parent / "events" / f"{day}.jsonl"

        package["artifact_refs"] = {
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "daily_latest": str(daily_latest_path),
            "event_log": str(daily_event_log),
            "legacy_event_log": str(self._event_log),
        }
        rendered = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        snapshot_path.write_text(rendered, encoding="utf-8")
        latest_path.write_text(rendered, encoding="utf-8")
        daily_latest_path.write_text(rendered, encoding="utf-8")

        event_line = json.dumps(package, ensure_ascii=False) + "\n"
        daily_event_log.parent.mkdir(parents=True, exist_ok=True)
        with daily_event_log.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        with self._event_log.open("a", encoding="utf-8") as handle:
            handle.write(event_line)

        return {"snapshot": str(snapshot_path), "latest": str(latest_path), "event_log": str(daily_event_log)}


class ErrorSinkImpl(ErrorSink):
    """Default error sink implementation.

    Writes two parallel outputs:
      * structured JSON line (existing behavior) for machine consumption
      * human-readable line in *-readable.log* for developer triage

    Readable output is opt-out via MEMORY_HOOK_READABLE_ERRORS_DISABLED=1.
    """

    READABLE_SUFFIX = "-readable.log"
    READABLE_DISABLE_ENV = "MEMORY_HOOK_READABLE_ERRORS_DISABLED"

    def __init__(
        self,
        error_log: Path,
        now_iso_fn: Callable[[], str] | None = None,
    ):
        self._error_log = error_log
        self._now_iso = now_iso_fn or now_iso

    @staticmethod
    def _readable_path(structured_log: Path) -> Path:
        return structured_log.with_name(structured_log.stem + ErrorSinkImpl.READABLE_SUFFIX)

    @staticmethod
    def _format_kv(context: dict[str, Any]) -> str:
        if not isinstance(context, dict) or not context:
            return ""
        parts: list[str] = []
        for key in sorted(context.keys()):
            value = context[key]
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                rendered = str(value)
            if " " in rendered or "\t" in rendered:
                rendered = json.dumps(rendered, ensure_ascii=False)
            parts.append(f"{key}={rendered}")
        return " ".join(parts)

    @classmethod
    def _readable_line(
        cls,
        timestamp: str,
        component: str,
        message: str,
        context: dict[str, Any],
    ) -> str:
        kv = cls._format_kv(context)
        suffix = f" | {kv}" if kv else ""
        return f"[{timestamp}] [ERROR] component={component} {message}{suffix}\n"

    def _readable_enabled(self) -> bool:
        return os.environ.get(self.READABLE_DISABLE_ENV) != "1"

    def log(self, component: str, message: str, context: dict[str, Any]) -> None:
        self._error_log.parent.mkdir(parents=True, exist_ok=True)
        timestamp = self._now_iso()
        day = timestamp[:10]
        daily_error_log = self._error_log.parent / "errors" / f"{day}.log"
        daily_error_log.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(context, ensure_ascii=False, sort_keys=True)
        line = f"[{timestamp}] [{component}] [error] {message} | context={rendered}\n"
        with daily_error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)
        with self._error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)
        if not self._readable_enabled():
            return
        readable_line = self._readable_line(timestamp, component, message, context)
        try:
            readable_daily = daily_error_log.with_name(daily_error_log.stem + self.READABLE_SUFFIX)
            with readable_daily.open("a", encoding="utf-8") as handle:
                handle.write(readable_line)
            readable_primary = self._readable_path(self._error_log)
            with readable_primary.open("a", encoding="utf-8") as handle:
                handle.write(readable_line)
        except OSError:
            # Readable output is best-effort; never block on it.
            pass


# ---------------------------------------------------------------------------
# IF-5: ArtifactWriter / DelegateRouter Implementations
# ---------------------------------------------------------------------------

class ArtifactWriter:
    """Handles writing context packages to artifact files.

    Wraps ``ArtifactSinkImpl`` with filename generation and non-blocking
    error handling: write failures are logged to ``error_log`` instead of
    being raised.
    """

    def __init__(
        self,
        context_root: Path,
        error_log: Path,
        datetime_module: Any = None,
    ):
        self.context_root = context_root
        self.error_log = error_log
        self.datetime_module = datetime_module or datetime
        event_log = context_root.parent / "events.jsonl"
        self._sink = ArtifactSinkImpl(
            context_root, event_log, datetime_module=self.datetime_module
        )
        self._last_error: str | None = None

    def write(self, host: str, event: str, package: dict[str, Any]) -> bool:
        """Write a context package to artifact file.

        Non-blocking: errors are logged to ``self.error_log``, not raised.
        """
        self._last_error = None
        try:
            package["host"] = host
            package["event"] = event
            self._sink.write(package)
            return True
        except Exception as exc:
            self._last_error = str(exc)
            self._log_error(host, event, exc)
            return False

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _log_error(self, host: str, event: str, exc: Exception) -> None:
        self.error_log.parent.mkdir(parents=True, exist_ok=True)
        error_ctx = {
            "host": host,
            "event": event,
            "error": str(exc),
            "context_root": str(self.context_root),
        }
        rendered = json.dumps(error_ctx, ensure_ascii=False, sort_keys=True)
        now = self.datetime_module.now()
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        day = now.date().isoformat()
        line = (
            f"[{timestamp}] [ArtifactWriter] [error] "
            f"artifact write failed | context={rendered}\n"
        )
        daily_error_log = self.error_log.parent / "errors" / f"{day}.log"
        daily_error_log.parent.mkdir(parents=True, exist_ok=True)
        with daily_error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)
        with self.error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)


class DelegateRouter:
    """Routes context packages to the factory host delegate.

    Only factory is supported (INV-6).
    """

    def __init__(
        self,
        factory_delegate: FactoryDelegate | None = None,
    ):
        self.factory_delegate = factory_delegate or FactoryDelegate()

    def route(
        self,
        host: str,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        """Route to the factory delegate."""
        if host == "factory":
            return self.factory_delegate.execute(event, raw_payload, payload)
        else:
            raise UnknownHostError(f"unknown host: {host}")

    def noop(self, host: str) -> subprocess.CompletedProcess[str]:
        """Execute noop response for the factory host."""
        if host == "factory":
            return self.factory_delegate.noop_response()
        else:
            raise UnknownHostError(f"unknown host: {host}")
