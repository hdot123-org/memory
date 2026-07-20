#!/usr/bin/env python3
"""M4 core helpers extracted from memory_hook_gateway.

This module keeps policy-driven registration gate evaluation in one place
so gateway wiring can stay thin without changing external behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Collection

if TYPE_CHECKING:
    from memory_core.tools.memory_hook_config import CoreConfig


def _resolve_callbacks(config: "CoreConfig") -> dict[str, Callable[..., Any]]:
    """Resolve callbacks from interface objects or individual config fields.

    When config carries composite interface attributes (policy_registry,
    path_utils), extract the bound methods from them. Otherwise fall back
    to the flat callback fields that CoreConfig already exposes.
    """
    # --- policy_registry ------------------------------------------------
    pr = getattr(config, "policy_registry", None)
    if pr is not None:
        validate_project_map_fn = pr.validate_project_map
        validate_unique_legal_system_contract_fn = pr.validate_unique_legal_system_contract
        policy_validate_fn = pr.validate
        get_policy_pack_fn = pr.get_policy_pack
        governance_frozen_tuple_errors_fn = pr.governance_frozen_tuple_errors
        event_contract_blocker_errors_fn = pr.event_contract_blocker_errors
        git_registration_probe_fn = pr.git_registration_probe
        truth_basis_for_scope_fn = pr.truth_basis_for_scope
        decision_refs_for_scope_fn = pr.decision_refs_for_scope
        lesson_refs_for_scope_fn = pr.lesson_refs_for_scope
        docs_refs_for_scope_fn = pr.docs_refs_for_scope
    else:
        validate_project_map_fn = config.validate_project_map_fn
        validate_unique_legal_system_contract_fn = config.validate_unique_legal_system_contract_fn
        policy_validate_fn = config.policy_validate_fn
        get_policy_pack_fn = config.get_policy_pack_fn
        governance_frozen_tuple_errors_fn = config.governance_frozen_tuple_errors_fn
        event_contract_blocker_errors_fn = config.event_contract_blocker_errors_fn
        git_registration_probe_fn = config.git_registration_probe_fn
        truth_basis_for_scope_fn = config.truth_basis_for_scope_fn
        decision_refs_for_scope_fn = config.decision_refs_for_scope_fn
        lesson_refs_for_scope_fn = config.lesson_refs_for_scope_fn
        docs_refs_for_scope_fn = config.docs_refs_for_scope_fn

    # --- path_utils -----------------------------------------------------
    pu = getattr(config, "path_utils", None)
    if pu is not None:
        extract_excerpt_fn = pu.extract_excerpt
        write_targets_fn = pu.write_targets
    else:
        extract_excerpt_fn = config.extract_excerpt_fn
        write_targets_fn = config.write_targets_fn

    return {
        "validate_project_map_fn": validate_project_map_fn,
        "validate_unique_legal_system_contract_fn": validate_unique_legal_system_contract_fn,
        "policy_validate_fn": policy_validate_fn,
        "get_policy_pack_fn": get_policy_pack_fn,
        "governance_frozen_tuple_errors_fn": governance_frozen_tuple_errors_fn,
        "event_contract_blocker_errors_fn": event_contract_blocker_errors_fn,
        "git_registration_probe_fn": git_registration_probe_fn,
        "truth_basis_for_scope_fn": truth_basis_for_scope_fn,
        "decision_refs_for_scope_fn": decision_refs_for_scope_fn,
        "lesson_refs_for_scope_fn": lesson_refs_for_scope_fn,
        "docs_refs_for_scope_fn": docs_refs_for_scope_fn,
        "extract_excerpt_fn": extract_excerpt_fn,
        "write_targets_fn": write_targets_fn,
    }


def registration_phase_from_policy_pack(
    policy_pack: dict[str, Any],
    default_phase: str = "declared-not-enforced",
) -> str:
    """Resolve registration phase from policy pack payload.

    Returns default_phase if policy pack is missing or malformed.
    """
    policies = policy_pack.get("policies")
    if isinstance(policies, dict):
        phase = policies.get("registration_phase")
        if isinstance(phase, str) and phase:
            return phase
    return default_phase


def evaluate_registration_commit_gate(
    policy_pack: dict[str, Any],
    registration_commit_gate: dict[str, Any],
    event: str,
    default_phase: str = "declared-not-enforced",
) -> tuple[dict[str, Any], list[str]]:
    """Evaluate registration commit enforcement against policy+probe state.

    Behavior:
    - If phase is not `enforced`, keep current M3 semantics (no hard block).
    - If phase is `enforced` and current event matches gate_event, require
      `status == committed-coupled`.
    """
    gate = dict(registration_commit_gate)
    phase = registration_phase_from_policy_pack(policy_pack, default_phase=default_phase)
    enforced = phase == "enforced"

    gate["phase"] = phase
    gate["enforced"] = enforced
    gate_event = gate.get("gate_event", "stop")
    triggered = event == gate_event
    gate["triggered_on_current_event"] = triggered

    if not enforced:
        gate["enforcement_result"] = "not-enforced"
        return gate, []
    if not triggered:
        gate["enforcement_result"] = "awaiting-gate-event"
        return gate, []

    status = gate.get("status")
    if status == "committed-coupled":
        gate["enforcement_result"] = "passed"
        return gate, []

    gate["enforcement_result"] = "failed"
    return gate, [f"registration commit enforcement failed: status={status}"]


def _safe_tb(basis: dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely extract a key from a truth_basis dict at runtime."""
    return basis.get(key, default)


_CANONICAL_FILENAMES: frozenset[str] = frozenset({"truth-model.md", "memory-system.md", "memory-routing.md"})


def _collect_canonical_missing(
    required_canonical: list[Path],
) -> tuple[list[str], list[str]]:
    """Split missing canonical paths into error-level and warning-level buckets.

    Paths whose filename is in _CANONICAL_FILENAMES are warnings (missing_canonical_files);
    all other missing paths are errors (missing_paths).
    """
    missing_paths: list[str] = []
    missing_canonical_files: list[str] = []
    for path in required_canonical:
        if not path.exists():
            path_str = str(path)
            if path.name in _CANONICAL_FILENAMES:
                missing_canonical_files.append(path_str)
            else:
                missing_paths.append(path_str)
    return missing_paths, missing_canonical_files


def _resolve_project_file(
    project_scope: str,
    project_canonical: dict[str, Path],
    workspace_root: Path,
    policy_errors: list[str],
    missing_paths: list[str],
) -> Path:
    """Resolve the project file for a given scope.

    Mutates policy_errors (appends unsupported scope) and missing_paths
    (appends non-existent project file) as side effects.
    """
    project_file = project_canonical.get(project_scope)
    if project_file is None:
        policy_errors.append(f"unsupported project_scope: {project_scope}")
        project_file = workspace_root / "projects" / project_scope / "PROJECT.md"
    elif not project_file.exists():
        missing_paths.append(str(project_file))
    return project_file


def _compute_truth_basis_errors(
    truth_basis: dict[str, Any],
    decisions: list[str],
    lessons: list[str],
    docs_refs: list[str],
    workspace_root: Path,
    project_map_refs: list[str],
    global_kb_root: Path | None,
    global_kb_enabled: bool,
) -> tuple[list[str], list[str], list[str]]:
    """Compute truth_basis_refs, truth_basis_errors, and the reads list.

    Returns (truth_basis_refs, truth_basis_errors, reads).
    """
    truth_basis_refs: list[str] = list(_safe_tb(truth_basis, "refs", []))
    truth_basis_errors: list[str] = list(_safe_tb(truth_basis, "errors", []))

    reads: list[str] = [
        str(workspace_root / "NOW.md"),
        *project_map_refs,
        str(workspace_root / "memory" / "kb" / "INDEX.md"),
        str(workspace_root / "memory" / "docs" / "INDEX.md"),
        *truth_basis_refs,
        *decisions,
        *lessons,
        *docs_refs,
    ]

    # 全局知识库 fallback 读取路径 (v0.8.0+)
    if global_kb_enabled and global_kb_root is not None:
        for domain in ("operations", "engineering", "collaboration"):
            domain_dir = global_kb_root / domain
            if domain_dir.exists():
                reads.append(str(domain_dir))

    read_set = set(reads)
    truth_basis_set = set(truth_basis_refs)
    if not truth_basis_set.issubset(read_set):
        truth_basis_errors.append("allowed_reads does not cover all truth basis refs")
    if set(decisions) & truth_basis_set:
        truth_basis_errors.append("decision refs overlap with truth basis refs")
    if set(lessons) & truth_basis_set:
        truth_basis_errors.append("lesson refs overlap with truth basis refs")
    if set(docs_refs) & truth_basis_set:
        truth_basis_errors.append("docs refs overlap with truth basis refs")

    return truth_basis_refs, truth_basis_errors, reads


def _derive_status(
    missing_paths: list[str],
    project_map_errors: list[str],
    contract_errors: list[str],
    policy_errors: list[str],
    truth_basis_errors: list[str],
    blocker_errors: list[str],
) -> str:
    """Derive overall context package status from error lists."""
    if (not missing_paths
            and not project_map_errors
            and not contract_errors
            and not policy_errors
            and not truth_basis_errors
            and not blocker_errors):
        return "ok"
    return "degraded"


def _derive_project_truth_status(truth_basis: dict[str, Any], truth_basis_errors: list[str]) -> str:
    """Derive per-project truth status from truth_basis validation state."""
    if _safe_tb(truth_basis, "validation", "unknown") == "pass" and not truth_basis_errors:
        return "truth-ready"
    return "truth-incomplete"


def _assemble_system_context(
    *,
    workspace_root: Path,
    extract_excerpt_fn: Callable[[Path], list[str]],
    project_map_refs: list[str],
    project_map_errors: list[str],
    contract_errors: list[str],
    legality_source_policy: str,
    registration_commit_policy: str,
    registration_commit_gate: dict[str, Any],
    global_canonical: list[Path],
    truth_basis: dict[str, Any],
    truth_basis_refs: list[str],
    truth_basis_errors: list[str],
    governance_tuple_errors: list[str],
    event_contract_errors: list[str],
    decisions: list[str],
    lessons: list[str],
    docs_refs: list[str],
    hook_contract_path: Path,
    policy_pack: dict[str, Any],
) -> dict[str, Any]:
    """Build the system_context sub-dict of the context package."""
    tb_validation = _safe_tb(truth_basis, "validation", "unknown") if not truth_basis_errors else "fail"
    return {
        "boot_entry": str(workspace_root / "INDEX.md"),
        "state_entry": str(workspace_root / "NOW.md"),
        "state_summary": extract_excerpt_fn(workspace_root / "NOW.md"),
        "project_map_refs": project_map_refs,
        "project_map_validation": "pass" if not project_map_errors else "fail",
        "legality_contract_validation": "pass" if not contract_errors else "fail",
        "legality_source_policy": legality_source_policy,
        "registration_commit_policy": registration_commit_policy,
        "registration_commit_gate": registration_commit_gate,
        "registration_commit_enforced": registration_commit_gate.get("enforced", False),
        "registration_commit_enforcement_result": registration_commit_gate.get("enforcement_result", "not-enforced"),
        "global_canonical": [str(path) for path in global_canonical],
        "truth_basis_policy": _safe_tb(truth_basis, "policy", "default"),
        "truth_basis_validation": tb_validation,
        "truth_basis_refs": truth_basis_refs,
        "truth_basis_errors": truth_basis_errors,
        "governance_frozen_tuple_validation": "pass" if not governance_tuple_errors else "fail",
        "governance_frozen_tuple_errors": governance_tuple_errors,
        "event_contract_alignment_validation": "pass" if not event_contract_errors else "fail",
        "event_contract_alignment_errors": event_contract_errors,
        "decision_refs": decisions,
        "lesson_refs": lessons,
        "docs_refs": docs_refs,
        "hook_contract": str(hook_contract_path),
        "policy_pack": policy_pack,
    }


def _assemble_project_context(
    *,
    project_scope: str,
    project_file: Path,
    truth_basis: dict[str, Any],
    project_truth_status: str,
    runtime_root: Path,
) -> dict[str, Any]:
    """Build the project_context sub-dict of the context package."""
    return {
        "scope": project_scope,
        "canonical": str(project_file),
        "truth_basis_canonical": _safe_tb(truth_basis, "project_ref", ""),
        "truth_status": project_truth_status,
        "runtime_root": str(runtime_root),
        "source_refs": _safe_tb(truth_basis, "source_refs", []),
        "authority_refs": _safe_tb(truth_basis, "authority_refs", []),
        "evidence_refs": _safe_tb(truth_basis, "evidence_refs", []),
        "conflict_status": _safe_tb(truth_basis, "conflict_status", ["unknown"]),
    }


def build_context_package_core(
    *,
    host: str,
    event: str,
    payload: dict[str, Any],
    cwd: Path,
    project_scope: str,
    workspace_root: Path,
    repo_root: Path,
    required_canonical: list[Path],
    project_canonical: dict[str, Path],
    project_runtime_root: dict[str, Path],
    global_canonical: list[Path],
    project_map_governance: Path,
    event_log: Path,
    legality_source_policy: str,
    registration_commit_policy: str,
    registration_commit_phase: str,
    project_map_refs: list[str],
    extract_excerpt_fn: Callable[[Path], list[str]],
    now_iso_fn: Callable[[], str],
    write_targets_fn: Callable[[], dict[str, Any]],
    validate_project_map_fn: Callable[[], list[str]],
    validate_unique_legal_system_contract_fn: Callable[[], list[str]],
    policy_validate_fn: Callable[[dict[str, Any]], list[str]],
    get_policy_pack_fn: Callable[[str], dict[str, Any]],
    governance_frozen_tuple_errors_fn: Callable[[], list[str]],
    event_contract_blocker_errors_fn: Callable[[], list[str]],
    git_registration_probe_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
    truth_basis_for_scope_fn: Callable[[str], dict[str, Any]],
    decision_refs_for_scope_fn: Callable[[str], list[str]],
    lesson_refs_for_scope_fn: Callable[[str], list[str]],
    docs_refs_for_scope_fn: Callable[[str], list[str]],
    hook_contract_path: Path,
    surface_id: str,
    workspace_id: str,
    governance_blocker_scopes: Collection[str] | None = None,
    event_contract_blocker_scopes: Collection[str] | None = None,
    core_evidence_refs: list[str] | None = None,
    global_kb_root: Path | None = None,
    global_kb_enabled: bool = True,
) -> dict[str, Any]:
    """M5 core assembly for context package.

    Gateway should only wire dependencies and environment values.
    """
    # Phase 1: canonical missing
    missing_paths, missing_canonical_files = _collect_canonical_missing(required_canonical)

    # Phase 2: validation errors
    project_map_errors = validate_project_map_fn()
    contract_errors = validate_unique_legal_system_contract_fn()
    try:
        policy_errors = policy_validate_fn(
            {"host": host, "event": event, "cwd": str(cwd), "project_scope": project_scope}
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        policy_errors = [f"policy validation failed: {exc}"]

    # Phase 3: governance / registration
    governance_scopes = set(governance_blocker_scopes or [])
    event_contract_scopes = set(event_contract_blocker_scopes or [])
    governance_tuple_errors = governance_frozen_tuple_errors_fn() if project_scope in governance_scopes else []
    event_contract_errors = event_contract_blocker_errors_fn() if project_scope in event_contract_scopes else []
    registration_commit_gate = git_registration_probe_fn(event, payload)

    try:
        policy_pack = get_policy_pack_fn(project_scope)
    except Exception as exc:
        policy_pack = {"error": str(exc), "scope": project_scope}
        policy_errors.append(f"policy-pack resolution failed: {exc}")

    registration_commit_gate, registration_gate_errors = evaluate_registration_commit_gate(
        policy_pack=policy_pack if isinstance(policy_pack, dict) else {},
        registration_commit_gate=registration_commit_gate,
        event=event,
        default_phase=registration_commit_phase,
    )

    # Phase 4: project file + truth basis
    project_file = _resolve_project_file(project_scope, project_canonical, workspace_root, policy_errors, missing_paths)

    decisions = decision_refs_for_scope_fn(project_scope)
    lessons = lesson_refs_for_scope_fn(project_scope)
    docs_refs = docs_refs_for_scope_fn(project_scope)
    truth_basis = truth_basis_for_scope_fn(project_scope)

    truth_basis_refs, truth_basis_errors, reads = _compute_truth_basis_errors(
        truth_basis, decisions, lessons, docs_refs,
        workspace_root, project_map_refs, global_kb_root, global_kb_enabled,
    )

    # Phase 5: status + assembly
    blocker_errors = [*governance_tuple_errors, *event_contract_errors, *registration_gate_errors]
    status = _derive_status(missing_paths, project_map_errors, contract_errors, policy_errors, truth_basis_errors, blocker_errors)
    project_truth_status = _derive_project_truth_status(truth_basis, truth_basis_errors)
    runtime_root = project_runtime_root.get(project_scope, workspace_root / "projects" / project_scope)
    evidence_refs = [
        *project_map_refs,
        *(core_evidence_refs or []),
        str(project_map_governance),
        str(event_log),
    ]

    system_context = _assemble_system_context(
        workspace_root=workspace_root,
        extract_excerpt_fn=extract_excerpt_fn,
        project_map_refs=project_map_refs,
        project_map_errors=project_map_errors,
        contract_errors=contract_errors,
        legality_source_policy=legality_source_policy,
        registration_commit_policy=registration_commit_policy,
        registration_commit_gate=registration_commit_gate,
        global_canonical=global_canonical,
        truth_basis=truth_basis,
        truth_basis_refs=truth_basis_refs,
        truth_basis_errors=truth_basis_errors,
        governance_tuple_errors=governance_tuple_errors,
        event_contract_errors=event_contract_errors,
        decisions=decisions,
        lessons=lessons,
        docs_refs=docs_refs,
        hook_contract_path=hook_contract_path,
        policy_pack=policy_pack,
    )
    project_context = _assemble_project_context(
        project_scope=project_scope,
        project_file=project_file,
        truth_basis=truth_basis,
        project_truth_status=project_truth_status,
        runtime_root=runtime_root,
    )

    return {
        "schema_version": "wb-hook-v2",
        "generated_at": now_iso_fn(),
        "host": host,
        "event": event,
        "repo_root": str(repo_root),
        "workspace_root": str(workspace_root),
        "cwd": str(cwd),
        "project_scope": project_scope,
        "status": status,
        "missing_paths": missing_paths,
        "warnings": missing_canonical_files,
        "validation_errors": [
            *project_map_errors,
            *contract_errors,
            *policy_errors,
            *truth_basis_errors,
            *blocker_errors,
        ],
        "system_context": system_context,
        "project_context": project_context,
        "task_context": {
            "event": event,
            "task_ref": str(payload.get("task_ref") or f"{project_scope}:{event}"),
            "session_id": str(payload.get("session_id") or ""),
            "surface_id": surface_id,
            "workspace_id": workspace_id,
            "payload_keys": sorted(payload.keys()),
        },
        "allowed_reads": reads,
        "allowed_writes": write_targets_fn(),
        "evidence_refs": evidence_refs,
    }


def build_context_package_from_config(config: "CoreConfig") -> dict[str, Any]:
    """Core assembly using structured CoreConfig.

    Prefer this over build_context_package_core(**kwargs).
    Behavior is identical — only the parameter interface changes.
    """
    cb = _resolve_callbacks(config)
    return build_context_package_core(
        host=config.host,
        event=config.event,
        payload=config.payload,
        cwd=config.cwd,
        project_scope=config.project_scope,
        workspace_root=config.workspace_root,
        repo_root=config.repo_root,
        required_canonical=config.required_canonical,
        project_canonical=config.project_canonical,
        project_runtime_root=config.project_runtime_root,
        global_canonical=config.global_canonical,
        project_map_governance=config.project_map_governance,
        event_log=config.event_log,
        legality_source_policy=config.legality_source_policy,
        registration_commit_policy=config.registration_commit_policy,
        registration_commit_phase=config.registration_commit_phase,
        project_map_refs=config.project_map_refs,
        extract_excerpt_fn=cb["extract_excerpt_fn"],
        now_iso_fn=config.now_iso_fn,
        write_targets_fn=cb["write_targets_fn"],
        validate_project_map_fn=cb["validate_project_map_fn"],
        validate_unique_legal_system_contract_fn=cb["validate_unique_legal_system_contract_fn"],
        policy_validate_fn=cb["policy_validate_fn"],
        get_policy_pack_fn=cb["get_policy_pack_fn"],
        governance_frozen_tuple_errors_fn=cb["governance_frozen_tuple_errors_fn"],
        event_contract_blocker_errors_fn=cb["event_contract_blocker_errors_fn"],
        git_registration_probe_fn=cb["git_registration_probe_fn"],
        truth_basis_for_scope_fn=cb["truth_basis_for_scope_fn"],
        decision_refs_for_scope_fn=cb["decision_refs_for_scope_fn"],
        lesson_refs_for_scope_fn=cb["lesson_refs_for_scope_fn"],
        docs_refs_for_scope_fn=cb["docs_refs_for_scope_fn"],
        hook_contract_path=config.hook_contract_path,
        surface_id=config.surface_id,
        workspace_id=config.workspace_id,
        governance_blocker_scopes=config.governance_blocker_scopes,
        event_contract_blocker_scopes=config.event_contract_blocker_scopes,
        core_evidence_refs=config.core_evidence_refs,
    )
