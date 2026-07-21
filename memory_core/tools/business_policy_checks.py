#!/usr/bin/env python3
"""Independent business-policy check classes extracted from GatewayBusinessPolicyImpl.

Each class handles one responsibility group and keeps method signatures
compatible with the original GatewayBusinessPolicyImpl interface.
"""


from pathlib import Path
from typing import Any

try:
    from ._rule_helpers import (
        _existing_paths,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,  # noqa: F401  re-exported for tests
        _section_body,
        _section_bullets,
    )
    from ._rule_types import RuleContext, RuleResult
    from ._scope_resolver_base import ScopeResolverBase
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
    from .memory_hook_impls import GatewayBusinessPolicyConfig
    from .memory_hook_interfaces import TruthBasis
except ImportError:
    from _rule_helpers import (  # type: ignore
        _existing_paths,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,  # noqa: F401  re-exported for tests
        _section_body,
        _section_bullets,
    )
    from _rule_types import RuleContext, RuleResult  # type: ignore
    from _scope_resolver_base import ScopeResolverBase  # type: ignore
    from _validation_constants import (  # type: ignore
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
    from memory_hook_impls import GatewayBusinessPolicyConfig  # type: ignore
    from memory_hook_interfaces import TruthBasis  # type: ignore


# ---------------------------------------------------------------------------
# Shared helpers — imported from _rule_helpers.py (consolidation REF-001 §4.3)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 0. PolicyValidatorBase — 共享 evaluate() 模板
# ---------------------------------------------------------------------------

class PolicyValidatorBase:
    """Base class for policy validators with shared evaluate() template.

    Subclasses implement _get_errors() to return validation errors.
    The evaluate() method builds a RuleResult from those errors.
    """

    _error_type: str = "validation"
    _pass_label: str = "Validation passed"

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

    def _get_errors(self) -> list[str]:
        raise NotImplementedError

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        """Evaluate rule by collecting errors and building RuleResult.

        Returns RuleResult with:
        - matched: True if validation errors found
        - severity: 'error' if errors, 'info' if pass
        - message: summary of validation
        - detail: {'errors': list[str]}
        """
        errors = self._get_errors()
        return RuleResult(
            matched=len(errors) > 0,
            severity="error" if errors else "info",
            message=f"Found {len(errors)} {self._error_type} errors" if errors else self._pass_label,
            detail={"errors": errors}
        )


# ---------------------------------------------------------------------------
# 1. ProjectMapValidator — project-map 校验相关方法
# ---------------------------------------------------------------------------

class ProjectMapValidator(PolicyValidatorBase):
    """Validates project-map contract files and related legal-system contracts."""

    rule_name = "project_map_validation"
    _error_type = "validation"
    _pass_label = "Validation passed"

    def _get_errors(self) -> list[str]:
        return self.validate_project_map_files()

    def _read_text_if_exists(self, path: Path) -> str:
        return self._config.read_text_if_exists_fn(path)

    def validate_project_map_files(self) -> list[str]:
        cfg = self._config
        errors: list[str] = []
        index_text = self._read_text_if_exists(cfg.project_map_files[0])
        core_text = self._read_text_if_exists(cfg.project_map_files[1])
        registry_text = self._read_text_if_exists(cfg.project_map_files[2])
        governance_text = self._read_text_if_exists(cfg.project_map_governance)

        if MKR_UNIQUE_LEGAL_ENTRY not in index_text:
            errors.append("project-map index does not declare the unique legal entry")
        if MKR_ACTIVE_LEGAL_MAP_ONLY not in index_text:
            errors.append("project-map index does not declare active-legal map-only legality")
        if MKR_GIT_COMMIT_GATE not in index_text:
            errors.append("project-map index does not declare the future registration git-commit gate")
        if "round-" in index_text or "waves/" in index_text:
            errors.append("project-map index still references transition round files")
        if MKR_CORE_ACTIVE_LEGAL not in core_text:
            errors.append("legal-core-map does not declare active-legal status")
        if MKR_CORE_MAP_ONLY not in core_text:
            errors.append("legal-core-map does not declare map-only legality")
        if "round-" in core_text or "waves/" in core_text:
            errors.append("legal-core-map still references transition round files")
        if MKR_INCOMING_RAW not in registry_text or MKR_COMPATIBILITY_ONLY not in registry_text:
            errors.append("ingestion-registry-map does not classify raw and compatibility-only scopes")
        if MKR_ABSORBED_STATUS not in registry_text or MKR_RETIRED_STATUS not in registry_text:
            errors.append("ingestion-registry-map does not define absorbed and retired statuses")
        if MKR_REGISTRY_GIT_COMMIT_GATE not in registry_text:
            errors.append("ingestion-registry-map does not declare the future registration git-commit gate")
        if MKR_UNWASHED_NOT_LEGAL not in governance_text:
            errors.append("project-map governance does not declare the legality cleaning rule")
        if MKR_GOVERNANCE_MAP_GRANTS_LEGALITY not in governance_text:
            errors.append("project-map governance does not declare that the map grants legality")
        if MKR_ATOMIC_REGISTRATION_GIT_COMMIT not in governance_text:
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

        if MKR_WORKSPACE_PROJECT_MAP_REF not in workspace_index:
            errors.append("workspace index does not load the project-map entry")
        if MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY not in workspace_index:
            errors.append("workspace index does not declare active-legal map-only legality")
        if MKR_WORKSPACE_GIT_COMMIT_RULE not in workspace_index:
            errors.append("workspace index does not declare the future registration git-commit rule")
        try:
            truth_model_ref = cfg.truth_model.resolve().relative_to(cfg.repo_root.resolve()).as_posix()
        except ValueError:
            truth_model_ref = str(cfg.truth_model)
        if truth_model_ref not in workspace_index:
            errors.append("workspace index does not reference the truth model canonical")
        if MKR_WORKSPACE_PROJECT_MAP_REF not in overview_doc:
            errors.append("overview doc does not reference the project-map entry")
        if MKR_INCOMING_RAW not in docs_index or MKR_DOCS_UNABSORBED not in docs_index:
            errors.append("docs index does not demote docs subtrees to project-map controlled raw material")
        if MKR_NON_LEGAL_MATERIAL not in global_index or MKR_INGESTION_REGISTRY_REF not in global_index:
            errors.append("global index does not demote non-local-canonical files into the legality registry")
        if cfg.truth_model.name not in global_index:
            errors.append("global index does not register the truth model canonical")
        for marker in cfg.legal_core_markers:
            if marker not in core_text:
                errors.append(f"legal-core-map is missing legal core marker: {marker}")
        for scope in cfg.required_registry_scopes:
            if scope not in registry_text:
                errors.append(f"ingestion-registry-map is missing scope: {scope}")
        if MKR_HOOK_MAP_ONLY_CONTEXT not in hook_contract:
            errors.append("hook contract does not declare map-only legal context sources")
        if MKR_HOOK_REGISTRATION_GATE not in hook_contract:
            errors.append("hook contract does not declare the future registration git-commit gate")
        return errors


# ---------------------------------------------------------------------------
# 2. LegalContractChecker — legal contract 校验
# ---------------------------------------------------------------------------

class LegalContractChecker:
    """Checks legal contract consistency across workspace docs."""

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

    def validate_unique_legal_system_contract(self) -> list[str]:
        """Validate unique legal system contract (delegates to ProjectMapValidator logic)."""
        validator = ProjectMapValidator(self._config)
        return validator.validate_unique_legal_system_contract()


# ---------------------------------------------------------------------------
# 3. FrozenTupleChecker — frozen tuple 校验
# ---------------------------------------------------------------------------

class FrozenTupleChecker(PolicyValidatorBase):
    """Checks governance frozen tuple markers."""

    rule_name = "frozen_tuple_check"
    _error_type = "frozen tuple"
    _pass_label = "Frozen tuple check passed"

    def _get_errors(self) -> list[str]:
        return self.governance_frozen_tuple_blocker_errors()

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


# ---------------------------------------------------------------------------
# 4. EventContractChecker — event contract blocker 校验
# ---------------------------------------------------------------------------

class EventContractChecker(PolicyValidatorBase):
    """Checks event contract files for formal/informal consistency."""

    rule_name = "event_contract_check"
    _error_type = "event contract"
    _pass_label = "Event contract check passed"

    def _get_errors(self) -> list[str]:
        return self.event_contract_blocker_errors()

    def event_contract_blocker_errors(self) -> list[str]:
        cfg = self._config
        if not cfg.event_contract_files:
            return []
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
                    _markdown_code_tokens(_section_body(upstream_standard, "## 3. 正式输入源")) & cfg.formal_source_types
                ),
                "event_types": sorted(
                    _markdown_code_tokens(_section_body(upstream_standard, "## 4. 正式事件类型")) & cfg.formal_event_types
                ),
                "event_statuses": sorted(
                    _markdown_code_tokens(_section_body(upstream_standard, "## 6. event_status 标准")) & cfg.formal_event_statuses
                ),
            },
            "upstream_mapping": {
                "source_types": sorted(
                    _markdown_code_tokens(_section_body(upstream_mapping, "## 2. 正式输入源范围")) & cfg.formal_source_types
                ),
                "event_types": sorted(
                    _markdown_code_tokens(_section_body(upstream_mapping, "## 3. 输入源到正式事件的映射主表")) & cfg.formal_event_types
                ),
                "event_statuses": sorted(
                    (
                        _markdown_code_tokens(_section_body(upstream_mapping, "## 4. 主路由规则"))
                        | _markdown_code_tokens(_section_body(upstream_mapping, "## 5. 错误码与原因码"))
                    )
                    & cfg.formal_event_statuses
                ),
            },
            "formal_contract": {
                "source_types": sorted(
                    _markdown_code_tokens(_section_body(formal_contract, "## 3. source_type 正式白名单")) & cfg.formal_source_types
                ),
                "event_types": sorted(
                    _markdown_code_tokens(_section_body(formal_contract, "## 4. event_type 正式清单")) & cfg.formal_event_types
                ),
                "event_statuses": sorted(
                    _markdown_code_tokens(_section_body(formal_contract, "## 6. event_status 正式取值")) & cfg.formal_event_statuses
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
                "source_types": sorted(_json_string_values(upstream_samples, "source_type")),
                "event_types": sorted(_json_string_values(upstream_samples, "event_type")),
                "event_statuses": sorted(_json_string_values(upstream_samples, "event_status")),
                "field_keys": sorted(_json_object_keys(upstream_samples) & (cfg.formal_field_keys | cfg.legacy_field_keys)),
            },
            "downstream_samples": {
                "source_types": sorted(_json_string_values(downstream_samples, "source_type")),
                "event_types": sorted(_json_string_values(downstream_samples, "event_type")),
                "event_statuses": sorted(_json_string_values(downstream_samples, "event_status")),
                "field_keys": sorted(_json_object_keys(downstream_samples) & (cfg.formal_field_keys | cfg.legacy_field_keys)),
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


# ---------------------------------------------------------------------------
# 5. TruthBasisResolver — truth-basis 校验
# ---------------------------------------------------------------------------

class TruthBasisResolver:
    """Resolves and validates truth-basis for a given project scope."""

    rule_name = "truth_basis_resolution"

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        """Evaluate truth basis resolution rule.

        Returns RuleResult with:
        - matched: True if validation errors found
        - severity: 'error' if errors, 'info' if pass
        - message: summary of validation
        - detail: {'truth_basis': TruthBasis dict}
        """
        # Extract project_scope from context extra dict
        project_scope = ctx.extra.get("project_scope", "")
        if not project_scope:
            return RuleResult(
                matched=False,
                severity="info",
                message="No project_scope provided",
                detail={"truth_basis": None}
            )

        truth_basis = self.truth_basis_for_scope(project_scope)
        errors = truth_basis.get("errors", [])
        return RuleResult(
            matched=len(errors) > 0,
            severity="error" if errors else "info",
            message=f"Truth basis validation {'failed' if errors else 'passed'}",
            detail={"truth_basis": truth_basis}
        )

    def _read_text_if_exists(self, path: Path) -> str:
        """Read file content via injected callback (I/O separated from rule logic)."""
        return self._config.read_text_if_exists_fn(path)

    # -- scope helpers --

    def get_project_canonical(self) -> dict[str, Path]:
        return dict(self._config.project_canonical)

    # -- truth-basis helpers --

    def _classify_truth_ref(self, path: Path) -> str:
        cfg = self._config
        if path == cfg.project_map_root / "legal-core-map.md":
            return "legal-core"
        if path == cfg.project_map_root / "INDEX.md":
            return "project-map-index"
        if path in cfg.global_canonical:
            return "global-canonical"
        if _path_is_under(path, cfg.workspace_root / "memory" / "kb" / "global" / "projects"):
            return "compatibility-only"
        if _path_is_under(path, cfg.workspace_root / "memory" / "kb" / "projects"):
            return "project-canonical"
        if _path_is_under(path, cfg.workspace_root / "memory" / "docs"):
            return "docs"
        if _path_is_under(path, cfg.workspace_root / "projects"):
            return "project-runtime"
        if _path_is_under(path, cfg.workspace_root / "memory" / "artifacts"):
            return "artifact"
        if _path_is_under(path, cfg.workspace_root / "tools"):
            return "tooling"
        if _path_is_under(path, cfg.workspace_root / "memory" / "log"):
            return "log"
        if _path_is_under(path, cfg.workspace_root / "memory" / "system"):
            return "system"
        if _path_is_under(path, cfg.repo_root / "app"):
            return "app"
        if _path_is_under(path, cfg.repo_root / "agents"):
            return "agents"
        if _path_is_under(path, cfg.repo_root / "gpt-web-to"):
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
        return any(_path_is_under(path, root) for root in self._config.lower_evidence_roots)

    def _truth_basis_sections_for(self, path: Path, content: str) -> dict[str, Any]:
        return {
            "source_refs": _section_bullets(content, "### Source Refs"),
            "authority_refs": _section_bullets(content, "### Authority Refs"),
            "evidence_refs": _section_bullets(content, "### Evidence Refs"),
            "conflict_status": _section_bullets(content, "### Conflict Status"),
        }

    def _resolve_ref_paths(self, refs: list[str]) -> list[Path]:
        """Resolve reference strings to absolute Path objects."""
        return [
            (self._config.repo_root / Path(item).expanduser()).resolve()
            if not Path(item).expanduser().is_absolute()
            else Path(item).expanduser()
            for item in refs
        ]

    def _validate_section_presence(self, sections: dict[str, list[str]], path: Path) -> list[str]:
        """Validate that all required sections are present."""
        errors: list[str] = []
        if not sections["source_refs"]:
            errors.append(f"source refs missing: {path}")
        if not sections["authority_refs"]:
            errors.append(f"authority refs missing: {path}")
        if not sections["evidence_refs"]:
            errors.append(f"evidence refs missing: {path}")
        if not sections["conflict_status"]:
            errors.append(f"conflict status missing: {path}")
        return errors

    def _validate_conflict_status(self, conflict: list[str], path: Path) -> list[str]:
        """Validate that conflict status is resolved."""
        if conflict and conflict != ["resolved"]:
            return [f"conflict status unresolved: {path}"]
        return []

    def _validate_path_existence(self, paths: list[Path]) -> list[str]:
        """Validate that all paths are within repo and exist on disk."""
        errors: list[str] = []
        for ref_path in paths:
            if not _path_is_under(ref_path, self._config.repo_root):
                errors.append(f"truth ref outside repository: {ref_path}")
            if not ref_path.exists():
                errors.append(f"truth ref missing on disk: {ref_path}")
        return errors

    def _validate_no_overlaps(self, source_refs: list[str], authority_refs: list[str], evidence_refs: list[str], path: Path) -> list[str]:
        """Validate that ref types don't overlap."""
        errors: list[str] = []
        if set(source_refs) == set(evidence_refs):
            errors.append(f"source refs and evidence refs must not be identical: {path}")
        if set(source_refs) & set(authority_refs):
            errors.append(f"source refs overlap authority refs: {path}")
        if set(authority_refs) & set(evidence_refs):
            errors.append(f"authority refs overlap evidence refs: {path}")
        return errors

    def _validate_authority_allowed(self, authority_paths: list[Path]) -> list[str]:
        """Validate that all authority paths are allowed."""
        errors: list[str] = []
        for authority_path in authority_paths:
            if not self._authority_ref_allowed(authority_path):
                errors.append(f"authority ref is not formal canonical: {authority_path}")
        return errors

    def _validate_source_diversity(self, source_paths: list[Path], path: Path) -> list[str]:
        """Validate that source paths include at least one non-canonical origin."""
        if source_paths and all(
            self._classify_truth_ref(sp) in {"global-canonical", "legal-core", "project-map-index"}
            for sp in source_paths
        ):
            return [f"source refs do not include a non-canonical origin: {path}"]
        return []

    def _validate_evidence_diversity(self, evidence_paths: list[Path], path: Path) -> list[str]:
        """Validate that evidence paths include at least one lower-layer source."""
        if evidence_paths and not any(self._lower_evidence_ref(ep) for ep in evidence_paths):
            return [f"evidence refs do not include lower-layer support: {path}"]
        return []

    def _truth_basis_errors_for(self, path: Path, content: str | None) -> list[str]:
        errors: list[str] = []
        if content is None:
            return [f"missing truth canonical: {path}"]
        if "Truth Basis" not in content:
            return [f"truth basis section missing: {path}"]

        sections = self._truth_basis_sections_for(path, content)
        source_refs = sections["source_refs"]
        authority_refs = sections["authority_refs"]
        evidence_refs = sections["evidence_refs"]
        conflict = sections["conflict_status"]

        # Phase 1: section presence
        errors.extend(self._validate_section_presence(sections, path))

        # Phase 2: conflict status
        errors.extend(self._validate_conflict_status(conflict, path))

        # Phase 3: resolve paths
        source_paths = self._resolve_ref_paths(source_refs)
        authority_paths = self._resolve_ref_paths(authority_refs)
        evidence_paths = self._resolve_ref_paths(evidence_refs)

        # Phase 4: path existence
        errors.extend(self._validate_path_existence([*source_paths, *authority_paths, *evidence_paths]))

        # Phase 5: no overlaps
        errors.extend(self._validate_no_overlaps(source_refs, authority_refs, evidence_refs, path))

        # Phase 6: authority allowed
        errors.extend(self._validate_authority_allowed(authority_paths))

        # Phase 7: source diversity
        errors.extend(self._validate_source_diversity(source_paths, path))

        # Phase 8: evidence diversity
        errors.extend(self._validate_evidence_diversity(evidence_paths, path))

        return errors

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
            content = self._read_text_if_exists(path)
            if not content:
                errors.append(f"missing truth canonical: {path}")
                continue
            errors.extend(self._truth_basis_errors_for(path, content))
        project_content = self._read_text_if_exists(project_file)
        if project_content:
            project_sections = self._truth_basis_sections_for(project_file, project_content)
            errors.extend(self._truth_basis_errors_for(project_file, project_content))
        else:
            project_sections = {
                "source_refs": [],
                "authority_refs": [],
                "evidence_refs": [],
                "conflict_status": [],
            }
            errors.append(f"missing truth canonical: {project_file}")
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
# 6. ScopeResolver — scope 解析
# ---------------------------------------------------------------------------

class ScopeResolver(ScopeResolverBase):
    """Resolves project scope from cwd and manages scope overrides."""

    def decision_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_decision_refs + self._config.project_decision_refs.get(project_scope, [])
        return _existing_paths(refs)

    def lesson_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_lesson_refs + self._config.project_lesson_refs.get(project_scope, [])
        return _existing_paths(refs)

    def docs_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.project_doc_refs.get(project_scope, [])
        return _existing_paths(refs)
