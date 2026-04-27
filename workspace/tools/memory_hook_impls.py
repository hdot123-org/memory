#!/usr/bin/env python3
"""M2 Default Implementations for memory-hook-gateway interfaces.

This module provides default implementations for:
- HostDelegateImpl (Codex/Claude delegates)
- PolicyRegistryImpl
- RouteTargetPolicyImpl / WriteTargetPolicyImpl
- ArtifactSinkImpl / ErrorSinkImpl
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from .memory_hook_interfaces import (
        RegistrationCommitGate,
        TruthBasis,
        ArtifactSink,
        ErrorSink,
        GatewayBusinessPolicy,
        HostDelegate,
        PolicyRegistry,
        RouteTargetPolicy,
        WriteTargetPolicy,
    )
except ImportError:
    from memory_hook_interfaces import (  # type: ignore
        RegistrationCommitGate,
        TruthBasis,
        ArtifactSink,
        ErrorSink,
        GatewayBusinessPolicy,
        HostDelegate,
        PolicyRegistry,
        RouteTargetPolicy,
        WriteTargetPolicy,
    )


# ---------------------------------------------------------------------------
# IF-1: HostDelegate Implementations
# ---------------------------------------------------------------------------

class CodexDelegate(HostDelegate):
    """Delegate for Codex host."""

    def __init__(
        self,
        surface_id: str | None = None,
        which_cmd: Callable[[str], str | None] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ):
        self.surface_id = surface_id or os.environ.get("CMUX_SURFACE_ID")
        self._which = which_cmd or shutil.which
        self._runner = runner or subprocess.run

    def can_handle(self) -> bool:
        return self._which("cmux") is not None and bool(self.surface_id)

    def execute(
        self,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        if self._which("cmux") is None:
            raise RuntimeError("cmux not found in PATH")
        if not self.surface_id:
            raise RuntimeError("missing required env: CMUX_SURFACE_ID")

        return self._runner(
            ["cmux", "codex-hook", event],
            input=raw_payload,
            text=True,
            capture_output=True,
            check=False,
        )

    def noop_response(self) -> subprocess.CompletedProcess[str]:
        """Codex bypass: return empty JSON when formal cmux is unavailable."""
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="{}\n", stderr="")


class ClaudeDelegate(HostDelegate):
    """Delegate for Claude host."""

    def __init__(
        self,
        workspace_id: str | None = None,
        surface_id: str | None = None,
        state_file: str | None = None,
        repo_root: Path | None = None,
        which_cmd: Callable[[str], str | None] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        state_path_factory: Callable[[Path], Path] | None = None,
        canonicalizer: Callable[[str, str], tuple[str, str]] | None = None,
        state_recorder: Callable[..., Any] | None = None,
    ):
        self.workspace_id = workspace_id or os.environ.get("CMUX_WORKSPACE_ID")
        self.surface_id = surface_id or os.environ.get("CMUX_SURFACE_ID")
        # M2: state_file must be injected by adapter policy, not read from env directly.
        # Adapters resolve CMUX_HOOK_STATE_FILE through their own policy layer.
        self._state_file = state_file
        self._repo_root = repo_root
        self._which = which_cmd or shutil.which
        self._runner = runner or subprocess.run
        self._state_path_factory = state_path_factory
        self._canonicalizer = canonicalizer
        self._state_recorder = state_recorder

    def can_handle(self) -> bool:
        return (
            self._which("cmux") is not None
            and bool(self.workspace_id)
            and bool(self.surface_id)
        )

    def execute(
        self,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        if self._which("cmux") is None:
            raise RuntimeError("cmux not found in PATH")
        if not self.workspace_id:
            raise RuntimeError("missing required env: CMUX_WORKSPACE_ID")
        if not self.surface_id:
            raise RuntimeError("missing required env: CMUX_SURFACE_ID")

        # State file resolution
        if self._state_file:
            state_file = self._state_file
        else:
            if self._state_path_factory is None:
                try:
                    from .cmux_hook_state import default_hook_state_path
                except ImportError:
                    from cmux_hook_state import default_hook_state_path  # type: ignore
                state_file = str(default_hook_state_path(self._repo_root or Path.cwd()))
            else:
                state_file = str(self._state_path_factory(self._repo_root or Path.cwd()))

        if self._canonicalizer is None:
            workspace_ref = self.workspace_id
            surface_ref = self.surface_id
        else:
            workspace_ref, surface_ref = self._canonicalizer(self.workspace_id, self.surface_id)

        recorder = self._state_recorder
        if recorder is None:
            try:
                from .cmux_hook_state import record_hook_event
            except ImportError:
                from cmux_hook_state import record_hook_event  # type: ignore
            recorder = record_hook_event

        recorder(
            Path(state_file),
            event_name=event,
            workspace_ref=workspace_ref,
            surface_ref=surface_ref,
            payload=payload,
        )

        return self._runner(
            ["cmux", "claude-hook", event, "--workspace", workspace_ref, "--surface", surface_ref],
            input=raw_payload or "{}",
            text=True,
            capture_output=True,
            check=False,
        )

    def noop_response(self) -> subprocess.CompletedProcess[str]:
        """Claude bypass: return empty response when formal cmux is unavailable."""
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


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
        config: GatewayBusinessPolicyConfig | None = None,
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
            raise ValueError(f"unsupported scope: {scope}")
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
    ):
        self._workspace_root = workspace_root
        self._repo_root = repo_root
        self._routes: dict[str, str] = {
            "fact": str(workspace_root / "memory" / "log" / f"{datetime.now().date().isoformat()}.md"),
            "global-rule": str(global_rule_path or (workspace_root / "memory" / "kb" / "global" / "memory-routing.md")),
            "source-material": str(workspace_root / "memory" / "docs" / "references"),
            "project-runtime": str(project_runtime_path or (workspace_root / "projects")),
            "system-error": str(workspace_root / "memory" / "system" / "errors.log"),
            "invalid-memory": str(workspace_root / "memory" / "archive" / "invalid"),
        }

    def resolve(self, kind: str) -> str:
        try:
            return self._routes[kind]
        except KeyError:
            raise ValueError(f"unsupported route kind: {kind}")


class WriteTargetPolicyImpl(WriteTargetPolicy):
    """Default write target policy implementation."""

    def __init__(self, workspace_root: Path):
        self._workspace_root = workspace_root
        self._targets: dict[str, Any] = {
            "fact": str(workspace_root / "memory" / "log" / f"{datetime.now().date().isoformat()}.md"),
            "global_canonical": str(workspace_root / "memory" / "kb" / "global"),
            "project_canonical": str(workspace_root / "memory" / "kb" / "projects"),
            "decision": str(workspace_root / "memory" / "kb" / "decisions"),
            "lesson": str(workspace_root / "memory" / "kb" / "lessons"),
            "docs": str(workspace_root / "memory" / "docs"),
            "action": str(workspace_root / "memory" / "inbox.md"),
            "project_runtime": str(workspace_root / "projects"),
            "artifacts": str(workspace_root / "artifacts"),
            "system_error": str(workspace_root / "memory" / "system" / "errors.log"),
            "invalid_memory": str(workspace_root / "memory" / "archive" / "invalid"),
            "kb_policy": {
                "mode": "read-first-CRUD",
                "overwrite_allowed": False,
                "conflict_strategy": "preserve-and-escalate",
            },
        }

    def get_targets(self) -> dict[str, Any]:
        return dict(self._targets)


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


class GatewayBusinessPolicyImpl(GatewayBusinessPolicy):
    """Adapter/business policy implementation for memory hook gateway."""

    SCOPE_CONFIG_PATH_ENV = "MEMORY_HOOK_SCOPE_CONFIG_PATH"

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
    ):
        self._config = config
        if scope_config_path is not None:
            self._scope_config_path = scope_config_path
        else:
            env_path = os.environ.get(self.SCOPE_CONFIG_PATH_ENV)
            self._scope_config_path = Path(env_path).expanduser() if env_path else None
        self._scope_overrides: dict[str, dict[str, str]] = self._load_scope_overrides()

    def _load_scope_overrides(self) -> dict[str, dict[str, str]]:
        path = self._scope_config_path
        if path is None or not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}

        result: dict[str, dict[str, str]] = {}
        for key in ("project_canonical", "project_runtime_root"):
            raw = payload.get(key)
            if not isinstance(raw, dict):
                continue
            scoped: dict[str, str] = {}
            for scope, value in raw.items():
                if isinstance(scope, str) and isinstance(value, str):
                    scoped[scope] = value
            if scoped:
                result[key] = scoped
        return result

    def _resolve_override_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        if path.is_absolute():
            return path
        return (self._config.repo_root / path).resolve()

    @staticmethod
    def _path_is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _path_is_under_lexical(path: Path, root: Path) -> bool:
        """Check lexical containment without following symlinks."""
        try:
            path.expanduser().absolute().relative_to(root.expanduser().absolute())
            return True
        except ValueError:
            return False

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _markdown_code_tokens(text: str) -> set[str]:
        return {match.group(1) for match in re.finditer(r"`([^`]+)`", text)}

    @staticmethod
    def _json_string_values(text: str, key: str) -> set[str]:
        pattern = rf'"{re.escape(key)}"\s*:\s*"([^"]+)"'
        return {match.group(1) for match in re.finditer(pattern, text)}

    @staticmethod
    def _json_object_keys(text: str) -> set[str]:
        return {match.group(1) for match in re.finditer(r'"([^"]+)"\s*:', text)}

    def _read_text_if_exists(self, path: Path) -> str:
        return self._config.read_text_if_exists_fn(path)

    @staticmethod
    def _existing_paths(paths: list[Path]) -> list[str]:
        return [str(path) for path in paths if path.exists()]

    def _classify_truth_ref(self, path: Path) -> str:
        cfg = self._config
        if path == cfg.project_map_root / "legal-core-map.md":
            return "legal-core"
        if path == cfg.project_map_root / "INDEX.md":
            return "project-map-index"
        if path in cfg.global_canonical:
            return "global-canonical"
        if self._path_is_under(path, cfg.workspace_root / "memory" / "kb" / "global" / "projects"):
            return "compatibility-only"
        if self._path_is_under(path, cfg.workspace_root / "memory" / "kb" / "projects"):
            return "project-canonical"
        if self._path_is_under(path, cfg.workspace_root / "memory" / "docs"):
            return "docs"
        if self._path_is_under(path, cfg.workspace_root / "projects"):
            return "project-runtime"
        if self._path_is_under(path, cfg.workspace_root / "artifacts"):
            return "artifact"
        if self._path_is_under(path, cfg.workspace_root / "tools"):
            return "tooling"
        if self._path_is_under(path, cfg.workspace_root / "memory" / "log"):
            return "log"
        if self._path_is_under(path, cfg.workspace_root / "memory" / "system"):
            return "system"
        if self._path_is_under(path, cfg.repo_root / "app"):
            return "app"
        if self._path_is_under(path, cfg.repo_root / "agents"):
            return "agents"
        if self._path_is_under(path, cfg.repo_root / "gpt-web-to"):
            return "gpt-web-to"
        if path == cfg.repo_root / "AGENTS.md":
            return "repo-policy"
        if path == cfg.workspace_root / "INDEX.md":
            return "workspace-entry"
        return "other"

    def _authority_ref_allowed(self, path: Path) -> bool:
        cfg = self._config
        return path in cfg.authority_allowed_paths or path in cfg.global_canonical

    def _lower_evidence_ref(self, path: Path) -> bool:
        return any(self._path_is_under(path, root) for root in self._config.lower_evidence_roots)

    def _truth_basis_sections_for(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        return {
            "source_refs": self._section_bullets(text, "### Source Refs"),
            "authority_refs": self._section_bullets(text, "### Authority Refs"),
            "evidence_refs": self._section_bullets(text, "### Evidence Refs"),
            "conflict_status": self._section_bullets(text, "### Conflict Status"),
        }

    def _truth_basis_errors_for(self, path: Path) -> list[str]:
        errors: list[str] = []
        if not path.exists():
            return [f"missing truth canonical: {path}"]
        text = path.read_text(encoding="utf-8")
        if "Truth Basis" not in text:
            return [f"truth basis section missing: {path}"]
        sections = self._truth_basis_sections_for(path)
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
        source_paths = [(self._config.repo_root / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in source_refs]
        authority_paths = [(self._config.repo_root / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in authority_refs]
        evidence_paths = [(self._config.repo_root / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in evidence_refs]
        for ref_path in [*source_paths, *authority_paths, *evidence_paths]:
            if not self._path_is_under(ref_path, self._config.repo_root):
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
            if not self._authority_ref_allowed(authority_path):
                errors.append(f"authority ref is not formal canonical: {authority_path}")
        if source_paths and all(
            self._classify_truth_ref(source_path) in {"global-canonical", "legal-core", "project-map-index"}
            for source_path in source_paths
        ):
            errors.append(f"source refs do not include a non-canonical origin: {path}")
        if evidence_paths and not any(self._lower_evidence_ref(evidence_path) for evidence_path in evidence_paths):
            errors.append(f"evidence refs do not include lower-layer support: {path}")
        return errors

    def determine_project_scope(self, cwd: Path) -> str:
        cfg = self._config
        if not self._path_is_under_lexical(cwd, cfg.repo_root):
            return cfg.default_project_scope
        for scope, roots in cfg.scope_match_hints.items():
            for root in roots:
                if self._path_is_under_lexical(cwd, root):
                    return scope
        return cfg.default_project_scope

    def get_project_canonical(self) -> dict[str, Path]:
        merged = dict(self._config.project_canonical)
        overrides = self._scope_overrides.get("project_canonical", {})
        for scope, raw in overrides.items():
            merged[scope] = self._resolve_override_path(raw)
        return merged

    def get_project_runtime_root(self) -> dict[str, Path]:
        merged = dict(self._config.project_runtime_root)
        overrides = self._scope_overrides.get("project_runtime_root", {})
        for scope, raw in overrides.items():
            merged[scope] = self._resolve_override_path(raw)
        return merged

    def get_required_canonical(self) -> list[Path]:
        return list(self._config.required_canonical)

    def get_global_canonical(self) -> list[Path]:
        return list(self._config.global_canonical)

    def project_map_refs(self) -> list[str]:
        return [str(path) for path in self._config.project_map_files]

    def validate_project_map_files(self) -> list[str]:
        cfg = self._config
        errors: list[str] = []
        index_text = self._read_text_if_exists(cfg.project_map_files[0])
        core_text = self._read_text_if_exists(cfg.project_map_files[1])
        registry_text = self._read_text_if_exists(cfg.project_map_files[2])
        governance_text = self._read_text_if_exists(cfg.project_map_governance)

        if "唯一合法入口" not in index_text:
            errors.append("project-map index does not declare the unique legal entry")
        if "只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。" not in index_text:
            errors.append("project-map index does not declare active-legal map-only legality")
        if "同次 `git commit` 提交后才生效" not in index_text:
            errors.append("project-map index does not declare the future registration git-commit gate")
        if "round-" in index_text or "waves/" in index_text:
            errors.append("project-map index still references transition round files")
        if "active-legal" not in core_text:
            errors.append("legal-core-map does not declare active-legal status")
        if "只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。" not in core_text:
            errors.append("legal-core-map does not declare map-only legality")
        if "round-" in core_text or "waves/" in core_text:
            errors.append("legal-core-map still references transition round files")
        if "incoming-raw" not in registry_text or "compatibility-only" not in registry_text:
            errors.append("ingestion-registry-map does not classify raw and compatibility-only scopes")
        if "`absorbed`" not in registry_text or "`retired`" not in registry_text:
            errors.append("ingestion-registry-map does not define absorbed and retired statuses")
        if "同次 `git commit` 提交后才生效" not in registry_text:
            errors.append("ingestion-registry-map does not declare the future registration git-commit gate")
        if "未经过唯一真相系统清洗" not in governance_text:
            errors.append("project-map governance does not declare the legality cleaning rule")
        if "只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。" not in governance_text:
            errors.append("project-map governance does not declare that the map grants legality")
        if "未完成同次 `git commit` 的目录登记，不得视为生效。" not in governance_text:
            errors.append("project-map governance does not declare the future atomic registration git-commit rule")
        if "按 wave 推进" in governance_text or "round-" in governance_text:
            errors.append("project-map governance still references transition wave files")
        return errors

    def validate_unique_legal_system_contract(self) -> list[str]:
        cfg = self._config
        errors: list[str] = []
        workspace_index = self._read_text_if_exists(cfg.workspace_index_path)
        docs_index = self._read_text_if_exists(cfg.docs_index_path)
        overview_doc = self._read_text_if_exists(cfg.overview_doc_path)
        global_index = self._read_text_if_exists(cfg.global_index_path)
        core_text = self._read_text_if_exists(cfg.project_map_files[1])
        registry_text = self._read_text_if_exists(cfg.project_map_files[2])
        hook_contract = self._read_text_if_exists(cfg.hook_contract_path)

        if "project-map/INDEX.md" not in workspace_index:
            errors.append("workspace index does not load the project-map entry")
        if "只有被地图标为 `active-legal` 的条目或目录，才是合法资料；仅进入登记册不授予合法性。" not in workspace_index:
            errors.append("workspace index does not declare active-legal map-only legality")
        if "目录登记和目录状态迁移必须与相关文件同次 `git commit` 才生效。" not in workspace_index:
            errors.append("workspace index does not declare the future registration git-commit rule")
        try:
            truth_model_ref = cfg.truth_model.resolve().relative_to(cfg.repo_root.resolve()).as_posix()
        except ValueError:
            truth_model_ref = str(cfg.truth_model)
        if truth_model_ref not in workspace_index:
            errors.append("workspace index does not reference the truth model canonical")
        if "project-map/INDEX.md" not in overview_doc:
            errors.append("overview doc does not reference the project-map entry")
        if "incoming-raw" not in docs_index or "未被地图明确吸收" not in docs_index:
            errors.append("docs index does not demote docs subtrees to project-map controlled raw material")
        if "Non-Legal Material" not in global_index or "ingestion-registry-map.md" not in global_index:
            errors.append("global index does not demote non-local-canonical files into the legality registry")
        if cfg.truth_model.name not in global_index:
            errors.append("global index does not register the truth model canonical")
        for marker in cfg.legal_core_markers:
            if marker not in core_text:
                errors.append(f"legal-core-map is missing legal core marker: {marker}")
        for scope in cfg.required_registry_scopes:
            if scope not in registry_text:
                errors.append(f"ingestion-registry-map is missing scope: {scope}")
        if "gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。" not in hook_contract:
            errors.append("hook contract does not declare map-only legal context sources")
        if "未完成提交的登记不得生效" not in hook_contract:
            errors.append("hook contract does not declare the future registration git-commit gate")
        return errors

    def governance_frozen_tuple_blocker_errors(self) -> list[str]:
        cfg = self._config
        texts: dict[Path, str] = {}
        missing_files: list[str] = []
        for path in cfg.governance_frozen_tuple_files:
            if not path.exists():
                missing_files.append(str(path))
                continue
            texts[path] = path.read_text(encoding="utf-8")
        if missing_files:
            return ["missing governance files: " + ", ".join(missing_files)]
        combined_text = "\n".join(texts.values())
        errors: list[str] = []
        missing_expected = sorted(marker for marker in cfg.frozen_tuple_expected if marker not in combined_text)
        if missing_expected:
            errors.append("missing expected tuple markers: " + ", ".join(missing_expected))
        legacy_hits = {
            str(path): sorted(marker for marker in cfg.frozen_tuple_legacy_markers if marker in text)
            for path, text in texts.items()
            if any(marker in text for marker in cfg.frozen_tuple_legacy_markers)
        }
        if legacy_hits:
            rendered = ", ".join(f"{path} -> {', '.join(hits)}" for path, hits in legacy_hits.items())
            errors.append("legacy frozen tuple markers still present: " + rendered)
        return errors

    def event_contract_blocker_errors(self) -> list[str]:
        cfg = self._config
        texts: dict[str, str] = {}
        missing_files: list[str] = []
        for name, path in cfg.event_contract_files.items():
            if not path.exists():
                missing_files.append(str(path))
                continue
            texts[name] = path.read_text(encoding="utf-8")
        if missing_files:
            return ["missing event contract files: " + ", ".join(missing_files)]

        upstream_standard = texts["upstream_standard"]
        upstream_mapping = texts["upstream_mapping"]
        formal_contract = texts["formal_contract"]
        upstream_samples = texts["upstream_samples"]
        downstream_samples = texts["downstream_samples"]

        formal_sets = {
            "upstream_standard": {
                "source_types": sorted(
                    self._markdown_code_tokens(self._section_body(upstream_standard, "## 3. 正式输入源")) & cfg.formal_source_types
                ),
                "event_types": sorted(
                    self._markdown_code_tokens(self._section_body(upstream_standard, "## 4. 正式事件类型")) & cfg.formal_event_types
                ),
                "event_statuses": sorted(
                    self._markdown_code_tokens(self._section_body(upstream_standard, "## 6. event_status 标准")) & cfg.formal_event_statuses
                ),
            },
            "upstream_mapping": {
                "source_types": sorted(
                    self._markdown_code_tokens(self._section_body(upstream_mapping, "## 2. 正式输入源范围")) & cfg.formal_source_types
                ),
                "event_types": sorted(
                    self._markdown_code_tokens(self._section_body(upstream_mapping, "## 3. 输入源到正式事件的映射主表")) & cfg.formal_event_types
                ),
                "event_statuses": sorted(
                    (
                        self._markdown_code_tokens(self._section_body(upstream_mapping, "## 4. 主路由规则"))
                        | self._markdown_code_tokens(self._section_body(upstream_mapping, "## 5. 错误码与原因码"))
                    )
                    & cfg.formal_event_statuses
                ),
            },
            "formal_contract": {
                "source_types": sorted(
                    self._markdown_code_tokens(self._section_body(formal_contract, "## 3. source_type 正式白名单")) & cfg.formal_source_types
                ),
                "event_types": sorted(
                    self._markdown_code_tokens(self._section_body(formal_contract, "## 4. event_type 正式清单")) & cfg.formal_event_types
                ),
                "event_statuses": sorted(
                    self._markdown_code_tokens(self._section_body(formal_contract, "## 6. event_status 正式取值")) & cfg.formal_event_statuses
                ),
            },
        }

        expected_formal_sets = {
            "source_types": sorted(cfg.formal_source_types),
            "event_types": sorted(cfg.formal_event_types),
            "event_statuses": sorted(cfg.formal_event_statuses),
        }
        errors: list[str] = []
        for doc_name, observed in formal_sets.items():
            for key, expected in expected_formal_sets.items():
                if observed[key] != expected:
                    errors.append(f"{doc_name} {key} mismatch: expected {expected}, got {observed[key]}")

        sample_sets = {
            "upstream_samples": {
                "source_types": sorted(self._json_string_values(upstream_samples, "source_type")),
                "event_types": sorted(self._json_string_values(upstream_samples, "event_type")),
                "event_statuses": sorted(self._json_string_values(upstream_samples, "event_status")),
                "field_keys": sorted(self._json_object_keys(upstream_samples) & (cfg.formal_field_keys | cfg.legacy_field_keys)),
            },
            "downstream_samples": {
                "source_types": sorted(self._json_string_values(downstream_samples, "source_type")),
                "event_types": sorted(self._json_string_values(downstream_samples, "event_type")),
                "event_statuses": sorted(self._json_string_values(downstream_samples, "event_status")),
                "field_keys": sorted(self._json_object_keys(downstream_samples) & (cfg.formal_field_keys | cfg.legacy_field_keys)),
            },
        }
        for doc_name, observed in sample_sets.items():
            unknown_source_types = sorted(set(observed["source_types"]) - cfg.formal_source_types)
            unknown_event_types = sorted(set(observed["event_types"]) - cfg.formal_event_types)
            unknown_event_statuses = sorted(set(observed["event_statuses"]) - cfg.formal_event_statuses)
            missing_formal_fields = sorted(cfg.formal_field_keys - set(observed["field_keys"]))
            legacy_fields = sorted(set(observed["field_keys"]) & cfg.legacy_field_keys)
            if unknown_source_types:
                errors.append(f"{doc_name} contains out-of-contract source_type values: " + ", ".join(unknown_source_types))
            if unknown_event_types:
                errors.append(f"{doc_name} contains out-of-contract event_type values: " + ", ".join(unknown_event_types))
            if unknown_event_statuses:
                errors.append(f"{doc_name} contains out-of-contract event_status values: " + ", ".join(unknown_event_statuses))
            if missing_formal_fields:
                errors.append(f"{doc_name} sample JSON missing formal field keys: " + ", ".join(missing_formal_fields))
            if legacy_fields:
                errors.append(f"{doc_name} sample JSON still uses legacy field keys: " + ", ".join(legacy_fields))
        return errors

    def decision_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_decision_refs + self._config.project_decision_refs.get(project_scope, [])
        return self._existing_paths(refs)

    def lesson_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_lesson_refs + self._config.project_lesson_refs.get(project_scope, [])
        return self._existing_paths(refs)

    def docs_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.project_doc_refs.get(project_scope, [])
        return self._existing_paths(refs)

    def truth_basis_for_scope(self, project_scope: str) -> TruthBasis:
        project_canonical = self.get_project_canonical()
        project_file = project_canonical.get(project_scope)
        if project_file is None:
            return {
                "policy": "source-authority-evidence-conflict",
                "refs": [str(path) for path in self._config.global_canonical],
                "global_refs": [str(path) for path in self._config.global_canonical],
                "project_ref": "",
                "source_refs": [],
                "authority_refs": [],
                "evidence_refs": [],
                "conflict_status": ["unresolved"],
                "errors": [f"unsupported project scope: {project_scope}"],
                "validation": "fail",
            }
        truth_basis_refs = [str(path) for path in self._config.global_canonical] + [str(project_file)]
        errors: list[str] = []
        for path in self._config.global_canonical:
            errors.extend(self._truth_basis_errors_for(path))
        project_sections = self._truth_basis_sections_for(project_file) if project_file.exists() else {
            "source_refs": [],
            "authority_refs": [],
            "evidence_refs": [],
            "conflict_status": [],
        }
        errors.extend(self._truth_basis_errors_for(project_file))
        return {
            "policy": "source-authority-evidence-conflict",
            "refs": truth_basis_refs,
            "global_refs": [str(path) for path in self._config.global_canonical],
            "project_ref": str(project_file),
            "source_refs": project_sections["source_refs"],
            "authority_refs": project_sections["authority_refs"],
            "evidence_refs": project_sections["evidence_refs"],
            "conflict_status": project_sections["conflict_status"],
            "errors": errors,
            "validation": "pass" if not errors else "fail",
        }


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

    def write(self, package: dict[str, Any]) -> dict[str, str]:
        self.ensure_dirs()
        timestamp = self._datetime.now().strftime("%Y%m%dT%H%M%S%f")
        snapshot_path = self._context_root / f"{timestamp}-{package['host']}-{package['event']}.json"
        suffix = 1
        while snapshot_path.exists():
            snapshot_path = self._context_root / f"{timestamp}-{suffix:02d}-{package['host']}-{package['event']}.json"
            suffix += 1
        latest_path = self._context_root / f"latest-{package['host']}-{package['event']}.json"

        package["artifact_refs"] = {
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "event_log": str(self._event_log),
        }
        rendered = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        snapshot_path.write_text(rendered, encoding="utf-8")
        latest_path.write_text(rendered, encoding="utf-8")

        with self._event_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(package, ensure_ascii=False) + "\n")

        return {"snapshot": str(snapshot_path), "latest": str(latest_path)}


class ErrorSinkImpl(ErrorSink):
    """Default error sink implementation."""

    def __init__(
        self,
        error_log: Path,
        now_iso_fn: Callable[[], str] | None = None,
    ):
        self._error_log = error_log
        self._now_iso = now_iso_fn or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def log(self, component: str, message: str, context: dict[str, Any]) -> None:
        self._error_log.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(context, ensure_ascii=False, sort_keys=True)
        with self._error_log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{self._now_iso()}] [{component}] [error] {message} | context={rendered}\n")


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
        timestamp = self.datetime_module.now().strftime("%Y%m%dT%H%M%S")
        with self.error_log.open("a", encoding="utf-8") as handle:
            handle.write(
                f"[{timestamp}] [ArtifactWriter] [error] "
                f"artifact write failed | context={rendered}\n"
            )


class DelegateRouter:
    """Routes context packages to the appropriate host delegate.

    Dispatches to ``CodexDelegate`` or ``ClaudeDelegate`` based on the
    host name, and provides a ``noop`` fallback for each.
    """

    def __init__(
        self,
        codex_delegate: CodexDelegate,
        claude_delegate: ClaudeDelegate,
    ):
        self.codex_delegate = codex_delegate
        self.claude_delegate = claude_delegate

    def route(
        self,
        host: str,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        """Route to the correct delegate based on host."""
        if host == "codex":
            return self.codex_delegate.execute(event, raw_payload, payload)
        elif host == "claude":
            return self.claude_delegate.execute(event, raw_payload, payload)
        else:
            raise ValueError(f"unknown host: {host}")

    def noop(self, host: str) -> subprocess.CompletedProcess[str]:
        """Execute noop response for the given host."""
        if host == "codex":
            return self.codex_delegate.noop_response()
        elif host == "claude":
            return self.claude_delegate.noop_response()
        else:
            raise ValueError(f"unknown host: {host}")


# ---------------------------------------------------------------------------
# IF-6: PathUtils Implementation
# ---------------------------------------------------------------------------

try:
    from .memory_hook_interfaces import PathUtils
except ImportError:
    from memory_hook_interfaces import PathUtils  # type: ignore


class PathUtilsImpl(PathUtils):
    """Default path utilities implementation."""

    def __init__(self, workspace_root: Path):
        self._workspace_root = workspace_root

    def extract_excerpt(self, path: Path, max_lines: int = 12) -> list[str]:
        """Extract a brief excerpt from a file.

        Mirrors the gateway's extract_excerpt: reads the file, strips each
        line, skips blank lines, and returns up to max_lines non-empty lines.
        """
        if not path.exists():
            return []
        lines: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lines.append(stripped)
            if len(lines) >= max_lines:
                break
        return lines

    def write_targets(self) -> dict[str, Any]:
        """Return the current write target map.

        Mirrors the gateway's write_targets fallback dict, which is also
        identical to WriteTargetPolicyImpl's internal targets structure.
        """
        return {
            "fact": str(self._workspace_root / "memory" / "log" / f"{datetime.now().date().isoformat()}.md"),
            "global_canonical": str(self._workspace_root / "memory" / "kb" / "global"),
            "project_canonical": str(self._workspace_root / "memory" / "kb" / "projects"),
            "decision": str(self._workspace_root / "memory" / "kb" / "decisions"),
            "lesson": str(self._workspace_root / "memory" / "kb" / "lessons"),
            "docs": str(self._workspace_root / "memory" / "docs"),
            "action": str(self._workspace_root / "memory" / "inbox.md"),
            "project_runtime": str(self._workspace_root / "projects"),
            "artifacts": str(self._workspace_root / "artifacts"),
            "system_error": str(self._workspace_root / "memory" / "system" / "errors.log"),
            "invalid_memory": str(self._workspace_root / "memory" / "archive" / "invalid"),
            "kb_policy": {
                "mode": "read-first-CRUD",
                "overwrite_allowed": False,
                "conflict_strategy": "preserve-and-escalate",
            },
        }
