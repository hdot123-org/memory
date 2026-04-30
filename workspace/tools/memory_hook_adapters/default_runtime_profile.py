"""Generic default runtime profile for memory-hook gateway wiring.

This module builds a host-neutral, project-agnostic runtime profile
from the ``.memory/adapter.toml`` configuration present in a target
project.  It contains no host-specific or project-specific literal
bindings and is intended to serve as the default
profile for any new memory-enabled project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .neutral_policy import NeutralGatewayBusinessPolicy
except ImportError:  # pragma: no cover - script-mode fallback
    NeutralGatewayBusinessPolicy = None  # type: ignore[assignment,misc]

try:
    from workspace.tools.adapter_toml_schema import load_adapter_toml
except ImportError:  # pragma: no cover
    from ..adapter_toml_schema import load_adapter_toml  # type: ignore[no-redef]


def build_default_runtime_profile(project_root: Path) -> dict[str, Any]:
    """Build a generic runtime profile from ``.memory/adapter.toml``.

    Parameters
    ----------
    project_root:
        Root directory of the target project (the directory that
        contains ``.memory/adapter.toml``).

    Returns
    -------
    dict[str, Any]
        A mapping with exactly 15 generic keys suitable for driving
        the memory-hook gateway context construction.
    """
    memory_root = project_root / ".memory"
    adapter_path = memory_root / "adapter.toml"
    config = load_adapter_toml(adapter_path)

    # Resolve the project scope from adapter.toml (routing.project_scope).
    project_scope: str = config.project_scope or "default"

    # Standard .memory/ paths ───────────────────────────────────────
    kb_root = memory_root / "kb"
    projects_root = kb_root / "projects"
    global_root = kb_root / "global"

    project_map_root = projects_root
    truth_model = global_root / "truth-model.md"
    memory_system_path = global_root / "memory-system.md"
    global_rule_path = global_root / "memory-routing.md"

    # Canonical file lists ──────────────────────────────────────────
    required_canonical = [
        memory_root / "CANONICAL.md",
        memory_root / "PLAN.md",
        memory_root / "STATE.md",
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

    return {
        "PROJECT_MAP_ROOT": project_map_root,
        "TRUTH_MODEL": truth_model,
        "REQUIRED_CANONICAL": required_canonical,
        "PROJECT_CANONICAL": project_canonical,
        "GLOBAL_CANONICAL": global_canonical,
        "LEGALITY_SOURCE_POLICY": legality_source_policy,
        "REGISTRATION_COMMIT_POLICY": registration_commit_policy,
        "REGISTRATION_COMMIT_PHASE": registration_commit_phase,
        "GATEWAY_POLICY_CLASS": gateway_policy_class,
        "ARTIFACT_COMPACTION": artifact_compaction,
        "DEFAULT_PROJECT_SCOPE": project_scope,
        "POLICY_ALLOWED_SCOPES": policy_allowed_scopes,
        "POLICY_SCOPE_INHERITS": policy_scope_inherits,
        "GOVERNANCE_BLOCKER_SCOPES": governance_blocker_scopes,
        "EVENT_CONTRACT_BLOCKER_SCOPES": event_contract_blocker_scopes,
    }
