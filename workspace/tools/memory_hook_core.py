#!/usr/bin/env python3
"""M4 core helpers extracted from memory_hook_gateway.

This module keeps policy-driven registration gate evaluation in one place
so gateway wiring can stay thin without changing external behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Collection


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
) -> dict[str, Any]:
    """M5 core assembly for context package.

    Gateway should only wire dependencies and environment values.
    """

    missing_paths = [str(path) for path in required_canonical if not path.exists()]
    project_map_errors = validate_project_map_fn()
    contract_errors = validate_unique_legal_system_contract_fn()

    try:
        policy_errors = policy_validate_fn(
            {
                "host": host,
                "event": event,
                "cwd": str(cwd),
                "project_scope": project_scope,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        policy_errors = [f"policy validation failed: {exc}"]

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

    project_file = project_canonical.get(project_scope)
    if project_file is None:
        policy_errors.append(f"unsupported project_scope: {project_scope}")
        project_file = workspace_root / "projects" / project_scope / "PROJECT.md"
    elif not project_file.exists():
        missing_paths.append(str(project_file))

    decisions = decision_refs_for_scope_fn(project_scope)
    lessons = lesson_refs_for_scope_fn(project_scope)
    docs_refs = docs_refs_for_scope_fn(project_scope)
    truth_basis = truth_basis_for_scope_fn(project_scope)
    truth_basis_refs = truth_basis["refs"]
    truth_basis_errors = list(truth_basis["errors"])

    reads = [
        str(workspace_root / "NOW.md"),
        *project_map_refs,
        str(workspace_root / "memory" / "kb" / "INDEX.md"),
        str(workspace_root / "memory" / "docs" / "INDEX.md"),
        *truth_basis_refs,
        *decisions,
        *lessons,
        *docs_refs,
    ]
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

    blocker_errors = [*governance_tuple_errors, *event_contract_errors, *registration_gate_errors]
    status = (
        "ok"
        if not missing_paths
        and not project_map_errors
        and not contract_errors
        and not policy_errors
        and not truth_basis_errors
        and not blocker_errors
        else "degraded"
    )
    project_truth_status = "truth-ready" if truth_basis["validation"] == "pass" and not truth_basis_errors else "truth-incomplete"
    runtime_root = project_runtime_root.get(project_scope, workspace_root / "projects" / project_scope)
    evidence_refs = [
        *project_map_refs,
        *(core_evidence_refs or []),
        str(project_map_governance),
        str(event_log),
    ]

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
        "validation_errors": [
            *project_map_errors,
            *contract_errors,
            *policy_errors,
            *truth_basis_errors,
            *blocker_errors,
        ],
        "system_context": {
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
            "truth_basis_policy": truth_basis["policy"],
            "truth_basis_validation": truth_basis["validation"] if not truth_basis_errors else "fail",
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
        },
        "project_context": {
            "scope": project_scope,
            "canonical": str(project_file),
            "truth_basis_canonical": truth_basis["project_ref"],
            "truth_status": project_truth_status,
            "runtime_root": str(runtime_root),
            "source_refs": truth_basis["source_refs"],
            "authority_refs": truth_basis["authority_refs"],
            "evidence_refs": truth_basis["evidence_refs"],
            "conflict_status": truth_basis["conflict_status"],
        },
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
