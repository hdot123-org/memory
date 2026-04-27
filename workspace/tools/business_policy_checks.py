#!/usr/bin/env python3
"""Independent business-policy check classes extracted from GatewayBusinessPolicyImpl.

Each class handles one responsibility group and keeps method signatures
compatible with the original GatewayBusinessPolicyImpl interface.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from .memory_hook_interfaces import TruthBasis
    from .memory_hook_impls import GatewayBusinessPolicyConfig
    from ._validation_constants import (
        MKR_UNIQUE_LEGAL_ENTRY,
        MKR_ACTIVE_LEGAL_MAP_ONLY,
        MKR_GIT_COMMIT_GATE,
        MKR_CORE_ACTIVE_LEGAL,
        MKR_CORE_MAP_ONLY,
        MKR_INCOMING_RAW,
        MKR_COMPATIBILITY_ONLY,
        MKR_ABSORBED_STATUS,
        MKR_RETIRED_STATUS,
        MKR_REGISTRY_GIT_COMMIT_GATE,
        MKR_UNWASHED_NOT_LEGAL,
        MKR_GOVERNANCE_MAP_GRANTS_LEGALITY,
        MKR_ATOMIC_REGISTRATION_GIT_COMMIT,
        MKR_WORKSPACE_PROJECT_MAP_REF,
        MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY,
        MKR_WORKSPACE_GIT_COMMIT_RULE,
        MKR_DOCS_UNABSORBED,
        MKR_NON_LEGAL_MATERIAL,
        MKR_INGESTION_REGISTRY_REF,
        MKR_HOOK_MAP_ONLY_CONTEXT,
        MKR_HOOK_REGISTRATION_GATE,
    )
except ImportError:
    from memory_hook_interfaces import TruthBasis  # type: ignore
    from memory_hook_impls import GatewayBusinessPolicyConfig  # type: ignore
    from _validation_constants import (  # type: ignore
        MKR_UNIQUE_LEGAL_ENTRY,
        MKR_ACTIVE_LEGAL_MAP_ONLY,
        MKR_GIT_COMMIT_GATE,
        MKR_CORE_ACTIVE_LEGAL,
        MKR_CORE_MAP_ONLY,
        MKR_INCOMING_RAW,
        MKR_COMPATIBILITY_ONLY,
        MKR_ABSORBED_STATUS,
        MKR_RETIRED_STATUS,
        MKR_REGISTRY_GIT_COMMIT_GATE,
        MKR_UNWASHED_NOT_LEGAL,
        MKR_GOVERNANCE_MAP_GRANTS_LEGALITY,
        MKR_ATOMIC_REGISTRATION_GIT_COMMIT,
        MKR_WORKSPACE_PROJECT_MAP_REF,
        MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY,
        MKR_WORKSPACE_GIT_COMMIT_RULE,
        MKR_DOCS_UNABSORBED,
        MKR_NON_LEGAL_MATERIAL,
        MKR_INGESTION_REGISTRY_REF,
        MKR_HOOK_MAP_ONLY_CONTEXT,
        MKR_HOOK_REGISTRATION_GATE,
    )


# ---------------------------------------------------------------------------
# Shared helpers (used by multiple checkers)
# ---------------------------------------------------------------------------

def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _path_is_under_lexical(path: Path, root: Path) -> bool:
    """Check lexical containment without following symlinks."""
    try:
        path.expanduser().absolute().relative_to(root.expanduser().absolute())
        return True
    except ValueError:
        return False


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


def _existing_paths(paths: list[Path]) -> list[str]:
    return [str(p) for p in paths if p.exists()]


# ---------------------------------------------------------------------------
# 1. ProjectMapValidator — project-map 校验相关方法
# ---------------------------------------------------------------------------

class ProjectMapValidator:
    """Validates project-map contract files and related legal-system contracts."""

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

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

class FrozenTupleChecker:
    """Checks governance frozen tuple markers."""

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

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

class EventContractChecker:
    """Checks event contract files for formal/informal consistency."""

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

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

    def __init__(self, config: GatewayBusinessPolicyConfig):
        self._config = config

    # -- scope helpers --

    def get_project_canonical(self) -> dict[str, Path]:
        return dict(self._config.project_canonical)

    # -- truth-basis helpers --

    @staticmethod
    def _path_is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

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
            "source_refs": _section_bullets(text, "### Source Refs"),
            "authority_refs": _section_bullets(text, "### Authority Refs"),
            "evidence_refs": _section_bullets(text, "### Evidence Refs"),
            "conflict_status": _section_bullets(text, "### Conflict Status"),
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
        source_paths = [
            (self._config.repo_root / Path(item).expanduser()).resolve()
            if not Path(item).expanduser().is_absolute()
            else Path(item).expanduser()
            for item in source_refs
        ]
        authority_paths = [
            (self._config.repo_root / Path(item).expanduser()).resolve()
            if not Path(item).expanduser().is_absolute()
            else Path(item).expanduser()
            for item in authority_refs
        ]
        evidence_paths = [
            (self._config.repo_root / Path(item).expanduser()).resolve()
            if not Path(item).expanduser().is_absolute()
            else Path(item).expanduser()
            for item in evidence_refs
        ]
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
            self._classify_truth_ref(sp) in {"global-canonical", "legal-core", "project-map-index"}
            for sp in source_paths
        ):
            errors.append(f"source refs do not include a non-canonical origin: {path}")
        if evidence_paths and not any(self._lower_evidence_ref(ep) for ep in evidence_paths):
            errors.append(f"evidence refs do not include lower-layer support: {path}")
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
# 6. ScopeResolver — scope 解析
# ---------------------------------------------------------------------------

class ScopeResolver:
    """Resolves project scope from cwd and manages scope overrides."""

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

    def determine_project_scope(self, cwd: Path) -> str:
        cfg = self._config
        if not _path_is_under_lexical(cwd, cfg.repo_root):
            return cfg.default_project_scope
        for scope, roots in cfg.scope_match_hints.items():
            for root in roots:
                if _path_is_under_lexical(cwd, root):
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

    def decision_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_decision_refs + self._config.project_decision_refs.get(project_scope, [])
        return _existing_paths(refs)

    def lesson_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.default_lesson_refs + self._config.project_lesson_refs.get(project_scope, [])
        return _existing_paths(refs)

    def docs_refs_for_scope(self, project_scope: str) -> list[str]:
        refs = self._config.project_doc_refs.get(project_scope, [])
        return _existing_paths(refs)
