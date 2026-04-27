"""CoreConfig dataclass for structured core assembly.

Replaces the 37 keyword-only parameters of build_context_package_core()
with a single typed configuration object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Collection


if TYPE_CHECKING:
    from memory_hook_interfaces import PathUtils, PolicyRegistry


@dataclass
class CoreConfig:
    """Structured configuration for the memory-hook core assembly pipeline.

    Fields are grouped by concern area to aid readability and maintenance.
    """

    # ------------------------------------------------------------------
    # Group 1: Environment (7 fields)
    # ------------------------------------------------------------------
    host: str
    event: str
    payload: dict[str, Any]
    cwd: Path
    project_scope: str
    workspace_root: Path
    repo_root: Path

    # ------------------------------------------------------------------
    # Group 2: Paths (7 fields)
    # ------------------------------------------------------------------
    required_canonical: list[Path]
    project_canonical: dict[str, Path]
    project_runtime_root: dict[str, Path]
    global_canonical: list[Path]
    project_map_governance: Path
    event_log: Path
    hook_contract_path: Path

    # ------------------------------------------------------------------
    # Group 3: Policy config (6 required + 3 optional fields)
    # ------------------------------------------------------------------
    legality_source_policy: str
    registration_commit_policy: str
    registration_commit_phase: str
    project_map_refs: list[str]
    surface_id: str
    workspace_id: str

    # ------------------------------------------------------------------
    # Group 4: Callbacks (13 fields)
    # ------------------------------------------------------------------
    extract_excerpt_fn: Callable[[Path], list[str]]
    now_iso_fn: Callable[[], str]
    write_targets_fn: Callable[[], dict[str, Any]]
    validate_project_map_fn: Callable[[], list[str]]
    validate_unique_legal_system_contract_fn: Callable[[], list[str]]
    policy_validate_fn: Callable[[dict[str, Any]], list[str]]
    get_policy_pack_fn: Callable[[str], dict[str, Any]]
    governance_frozen_tuple_errors_fn: Callable[[], list[str]]
    event_contract_blocker_errors_fn: Callable[[], list[str]]
    git_registration_probe_fn: Callable[[str, dict[str, Any]], dict[str, Any]]
    truth_basis_for_scope_fn: Callable[[str], dict[str, Any]]
    decision_refs_for_scope_fn: Callable[[str], list[str]]
    lesson_refs_for_scope_fn: Callable[[str], list[str]]
    docs_refs_for_scope_fn: Callable[[str], list[str]]

    # ------------------------------------------------------------------
    # Group 5: Interface objects & optional policy fields
    # ------------------------------------------------------------------
    policy_registry: PolicyRegistry | None = field(default=None)
    path_utils: PathUtils | None = field(default=None)
    governance_blocker_scopes: Collection[str] | None = field(default=None)
    event_contract_blocker_scopes: Collection[str] | None = field(default=None)
    core_evidence_refs: list[str] | None = field(default=None)

    @property
    def uses_interfaces(self) -> bool:
        return (
            self.policy_registry is not None
            and self.path_utils is not None
        )

    def __post_init__(self) -> None:
        if self.host not in ("codex", "claude"):
            raise ValueError(
                f"host must be 'codex' or 'claude', got {self.host!r}"
            )
        if not isinstance(self.event, str) or not self.event:
            raise ValueError("event must be a non-empty string")
        if not isinstance(self.workspace_root, Path):
            raise TypeError(
                f"workspace_root must be a Path, got {type(self.workspace_root).__name__}"
            )
        if not isinstance(self.repo_root, Path):
            raise TypeError(
                f"repo_root must be a Path, got {type(self.repo_root).__name__}"
            )
        if not isinstance(self.payload, dict):
            raise TypeError(
                f"payload must be a dict, got {type(self.payload).__name__}"
            )
        if not isinstance(self.cwd, Path):
            raise TypeError(
                f"cwd must be a Path, got {type(self.cwd).__name__}"
            )
        if not isinstance(self.project_scope, str) or not self.project_scope:
            raise ValueError("project_scope must be a non-empty string")
        if not isinstance(self.required_canonical, list):
            raise TypeError(
                f"required_canonical must be a list, got {type(self.required_canonical).__name__}"
            )
        if not isinstance(self.project_map_refs, list):
            raise TypeError(
                f"project_map_refs must be a list, got {type(self.project_map_refs).__name__}"
            )
        for _name in ("now_iso_fn", "write_targets_fn", "extract_excerpt_fn"):
            if not callable(getattr(self, _name)):
                raise TypeError(
                    f"{_name} must be callable, got {type(getattr(self, _name)).__name__}"
                )
        if not isinstance(self.surface_id, str):
            raise TypeError(
                f"surface_id must be a string, got {type(self.surface_id).__name__}"
            )
        if not isinstance(self.workspace_id, str):
            raise TypeError(
                f"workspace_id must be a string, got {type(self.workspace_id).__name__}"
            )

    def to_gateway_kwargs(self) -> dict[str, Any]:
        """Return a dict suitable for passing to legacy **kwargs providers."""
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_gateway_kwargs(
        cls,
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
        policy_registry: PolicyRegistry | None = None,
        path_utils: PathUtils | None = None,
    ) -> CoreConfig:
        """Bridge: accept the current 37 kwargs and return a CoreConfig."""
        return cls(
            host=host,
            event=event,
            payload=payload,
            cwd=cwd,
            project_scope=project_scope,
            workspace_root=workspace_root,
            repo_root=repo_root,
            required_canonical=required_canonical,
            project_canonical=project_canonical,
            project_runtime_root=project_runtime_root,
            global_canonical=global_canonical,
            project_map_governance=project_map_governance,
            event_log=event_log,
            legality_source_policy=legality_source_policy,
            registration_commit_policy=registration_commit_policy,
            registration_commit_phase=registration_commit_phase,
            project_map_refs=project_map_refs,
            extract_excerpt_fn=extract_excerpt_fn,
            now_iso_fn=now_iso_fn,
            write_targets_fn=write_targets_fn,
            validate_project_map_fn=validate_project_map_fn,
            validate_unique_legal_system_contract_fn=validate_unique_legal_system_contract_fn,
            policy_validate_fn=policy_validate_fn,
            get_policy_pack_fn=get_policy_pack_fn,
            governance_frozen_tuple_errors_fn=governance_frozen_tuple_errors_fn,
            event_contract_blocker_errors_fn=event_contract_blocker_errors_fn,
            git_registration_probe_fn=git_registration_probe_fn,
            truth_basis_for_scope_fn=truth_basis_for_scope_fn,
            decision_refs_for_scope_fn=decision_refs_for_scope_fn,
            lesson_refs_for_scope_fn=lesson_refs_for_scope_fn,
            docs_refs_for_scope_fn=docs_refs_for_scope_fn,
            hook_contract_path=hook_contract_path,
            surface_id=surface_id,
            workspace_id=workspace_id,
            governance_blocker_scopes=governance_blocker_scopes,
            event_contract_blocker_scopes=event_contract_blocker_scopes,
            core_evidence_refs=core_evidence_refs,
            policy_registry=policy_registry,
            path_utils=path_utils,
        )
