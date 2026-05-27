"""Generic default runtime profile for memory-hook gateway wiring.

This module builds a host-neutral, project-agnostic runtime profile
from the ``memory/system/adapter.toml`` configuration present in a target
project.  It contains no host-specific or project-specific literal
bindings and is intended to serve as the default
profile for any new memory-enabled project.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from .neutral_policy import NeutralGatewayBusinessPolicy
except ImportError:  # pragma: no cover - script-mode fallback
    NeutralGatewayBusinessPolicy = None  # type: ignore[assignment,misc]

try:
    from memory_core.tools.adapter_toml_schema import load_adapter_toml
except ImportError:  # pragma: no cover
    from ..adapter_toml_schema import load_adapter_toml  # type: ignore[no-redef]


def build_default_runtime_profile(
    repo_root: Path, workspace_root: Path | None = None
) -> dict[str, Any]:
    """Build a generic runtime profile from ``memory/system/adapter.toml``.

    Parameters
    ----------
    repo_root:
        Root directory of the repository.
    workspace_root:
        Root directory of the workspace (for adapter resolution).

    Returns
    -------
    dict[str, Any]
        A mapping with generic keys suitable for driving
        the memory-hook gateway context construction.
    """
    # Use workspace_root as the project root for config lookup (fallback to repo_root)
    project_root = workspace_root if workspace_root is not None else repo_root
    adapter_path = project_root / "memory" / "system" / "adapter.toml"
    config = load_adapter_toml(adapter_path)

    # Resolve the project scope from adapter.toml (routing.project_scope).
    project_scope: str = config.project_scope or "default"

    # Standard memory/ paths ─────────────────────────
    kb_root = project_root / "memory" / "kb"
    projects_root = kb_root / "projects"
    global_root = kb_root / "global"

    # Project map lives at project_root / project-map/ (generic)
    project_map_root = project_root / "project-map"

    truth_model = global_root / "truth-model.md"
    memory_system_path = global_root / "memory-system.md"
    global_rule_path = global_root / "memory-routing.md"
    hook_contract_path = global_root / "hook-contract.md"
    project_map_governance = global_root / "project-map-governance.md"
    policy_pack_path = global_root / "policy-pack.json"

    # Project map files — must be ≥ 3 (INDEX + legal-core-map + ingestion-registry-map)
    project_map_files = [
        project_map_root / "INDEX.md",
        project_map_root / "legal-core-map.md",
        project_map_root / "ingestion-registry-map.md",
    ]

    # Canonical file lists ──────────────────────────────────────────
    required_canonical = [
        truth_model,
        memory_system_path,
        global_rule_path,
    ]

    project_canonical: dict[str, Path] = {
        project_scope: projects_root / f"{project_scope}.md",
    }

    global_canonical = [
        truth_model,
        memory_system_path,
        global_rule_path,
        hook_contract_path,
        project_map_governance,
    ]

    # Policy values (from adapter.toml [policy] section) ────────────
    legality_source_policy = config.legality_source_policy
    registration_commit_policy = config.registration_commit_policy
    registration_commit_phase = config.registration_commit_phase

    # Gateway policy class ──────────────────────────────────────────
    gateway_policy_class = NeutralGatewayBusinessPolicy

    # Artifact compaction defaults ──────────────────────────────────
    artifact_compaction: dict[str, bool] = {
        "include_system_context": True,
        "include_project_context": True,
        "include_task_context": True,
        "include_evidence_refs": True,
        "include_allowed_reads": True,
        "include_allowed_writes": True,
    }

    # Scope configuration ───────────────────────────────────────────
    policy_allowed_scopes: set[str] = {project_scope}
    policy_scope_inherits: dict[str, str] = {}
    governance_blocker_scopes: set[str] = set()
    event_contract_blocker_scopes: set[str] = set()

    # Authority and evidence paths ──────────────────────────────────
    authority_allowed_paths: set[Path] = {
        project_map_root / "INDEX.md",
        project_map_root / "legal-core-map.md",
        truth_model,
        memory_system_path,
        hook_contract_path,
        project_map_governance,
        global_rule_path,
    }
    lower_evidence_roots: list[Path] = [
        project_root / "tools",
        repo_root / "tests",
    ]

    # Decision and lesson refs ─────────────────────────────────────
    default_decision_refs: list[Path] = []
    project_decision_refs: dict[str, list[Path]] = {project_scope: []}
    default_lesson_refs: list[Path] = []
    project_lesson_refs: dict[str, list[Path]] = {project_scope: []}

    # Project doc refs ─────────────────────────────────────────────
    project_doc_refs: dict[str, list[Path]] = {project_scope: []}

    # Project runtime root ─────────────────────────────────────────
    project_runtime_root: dict[str, Path] = {
        project_scope: project_root / "projects",
    }

    # Git registration scope ───────────────────────────────────────
    registration_git_scope = [
        project_map_root / "INDEX.md",
        project_map_governance,
        hook_contract_path,
    ]

    # Legal core markers and registry scopes ──────────────────────
    legal_core_markers: list[str] = [
        "active-legal",
        "project-map/INDEX.md",
        "truth-model.md",
        "memory-system.md",
    ]
    required_registry_scopes: list[str] = [
        "memory_core/project-map/**",
        "memory/kb/global/**",
        "memory/kb/projects/**",
        "memory/docs/**",
        "memory/log/**",
        "memory_core/projects/**",
        "memory_core/tools/**",
        "tests/**",
    ]

    # Frozen tuple and event contract config ──────────────────────
    governance_frozen_tuple_files: list[Path] = []
    event_contract_files: dict[str, Path] = {}
    frozen_tuple_expected: set[str] = set()
    frozen_tuple_legacy_markers: set[str] = set()
    formal_source_types: set[str] = set()
    formal_event_types: set[str] = set()
    formal_event_statuses: set[str] = set()
    formal_field_keys: set[str] = set()
    legacy_field_keys: set[str] = set()

    # Route and scope config ──────────────────────────────────────
    route_project_runtime_scope = project_scope
    scope_match_hints: dict[str, list[Path]] = {project_scope: []}
    core_evidence_refs: list[str] = [
        str(memory_system_path),
        str(global_rule_path),
        str(hook_contract_path),
    ]

    return {
        "PROJECT_MAP_ROOT": project_map_root,
        "TRUTH_MODEL": truth_model,
        "PROJECT_MAP_FILES": project_map_files,
        "PROJECT_MAP_GOVERNANCE": project_map_governance,
        "HOOK_CONTRACT_PATH": hook_contract_path,
        "GLOBAL_RULE_PATH": global_rule_path,
        "MEMORY_SYSTEM_PATH": memory_system_path,
        "POLICY_PACK_PATH": policy_pack_path,
        "GATEWAY_POLICY_CLASS": gateway_policy_class,
        "LEGALITY_SOURCE_POLICY": legality_source_policy,
        "REGISTRATION_COMMIT_POLICY": registration_commit_policy,
        "REGISTRATION_COMMIT_PHASE": registration_commit_phase,
        "REGISTRATION_GIT_SCOPE": registration_git_scope,
        "LEGAL_CORE_MARKERS": legal_core_markers,
        "REQUIRED_REGISTRY_SCOPES": required_registry_scopes,
        "REQUIRED_CANONICAL": required_canonical,
        "PROJECT_CANONICAL": project_canonical,
        "PROJECT_RUNTIME_ROOT": project_runtime_root,
        "PROJECT_DOC_REFS": project_doc_refs,
        "GLOBAL_CANONICAL": global_canonical,
        "AUTHORITY_ALLOWED_PATHS": authority_allowed_paths,
        "LOWER_EVIDENCE_ROOTS": lower_evidence_roots,
        "DEFAULT_DECISION_REFS": default_decision_refs,
        "PROJECT_DECISION_REFS": project_decision_refs,
        "GOVERNANCE_FROZEN_TUPLE_FILES": governance_frozen_tuple_files,
        "EVENT_CONTRACT_FILES": event_contract_files,
        "FROZEN_TUPLE_EXPECTED": frozen_tuple_expected,
        "FROZEN_TUPLE_LEGACY_MARKERS": frozen_tuple_legacy_markers,
        "FORMAL_SOURCE_TYPES": formal_source_types,
        "FORMAL_EVENT_TYPES": formal_event_types,
        "FORMAL_EVENT_STATUSES": formal_event_statuses,
        "FORMAL_FIELD_KEYS": formal_field_keys,
        "LEGACY_FIELD_KEYS": legacy_field_keys,
        "DEFAULT_LESSON_REFS": default_lesson_refs,
        "PROJECT_LESSON_REFS": project_lesson_refs,
        "GOVERNANCE_BLOCKER_SCOPES": governance_blocker_scopes,
        "EVENT_CONTRACT_BLOCKER_SCOPES": event_contract_blocker_scopes,
        "DEFAULT_PROJECT_SCOPE": project_scope,
        "ROUTE_PROJECT_RUNTIME_SCOPE": route_project_runtime_scope,
        "SCOPE_MATCH_HINTS": scope_match_hints,
        "CORE_EVIDENCE_REFS": core_evidence_refs,
        "POLICY_ALLOWED_SCOPES": policy_allowed_scopes,
        "CLAUDE_HOOK_STATE_FILE": os.environ.get("CMUX_HOOK_STATE_FILE") or None,
        "POLICY_SCOPE_INHERITS": policy_scope_inherits,
        "ARTIFACT_COMPACTION": artifact_compaction,
    }
