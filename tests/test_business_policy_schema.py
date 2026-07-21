#!/usr/bin/env python3
"""Tests for business_policy_checks.py schema parsing and validation.

Covers:
- GatewayBusinessPolicyConfig schema: field types, required/optional, defaults
- ProjectMapValidator: validate_project_map_files, validate_unique_legal_system_contract
- FrozenTupleChecker: governance_frozen_tuple_blocker_errors
- EventContractChecker: event_contract_blocker_errors
- TruthBasisResolver: truth_basis_for_scope, classify helpers
- ScopeResolver: determine_project_scope, scope overrides, ref lookups
"""

import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Repo-root setup
# ---------------------------------------------------------------------------
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools._validation_constants import (
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
from memory_core.tools.business_policy_checks import (
    EventContractChecker,
    FrozenTupleChecker,
    ProjectMapValidator,
    ScopeResolver,
    TruthBasisResolver,
    _existing_paths,
    _json_object_keys,
    _json_string_values,
    _markdown_code_tokens,
    _path_is_under,
    _path_is_under_lexical,
    _section_body,
    _section_bullets,
)
from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig

# ---------------------------------------------------------------------------
# Fixtures — minimal config builder
# ---------------------------------------------------------------------------

def _noop_read(path: Path) -> str:
    return ""


def _file_reader(path: Path) -> str:
    """Read file content if it exists, else empty string."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _ensure_dir(p: Path) -> Path:
    """Create directory (and parents) if it doesn't exist, return p."""
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_minimal_config(tmp_path: Path, **overrides: Any) -> GatewayBusinessPolicyConfig:
    """Build a GatewayBusinessPolicyConfig with all required fields using sensible defaults."""
    repo = _ensure_dir(tmp_path / "repo")
    workspace = _ensure_dir(tmp_path / "workspace")
    pm_root = _ensure_dir(tmp_path / "project-map")

    defaults: dict[str, Any] = {
        "repo_root": repo,
        "workspace_root": workspace,
        "project_map_root": pm_root,
        "project_map_files": [pm_root / "INDEX.md", pm_root / "legal-core-map.md", pm_root / "ingestion-registry-map.md"],
        "project_map_governance": pm_root / "governance.md",
        "truth_model": workspace / "truth.md",
        "global_canonical": [workspace / "global.md"],
        "authority_allowed_paths": {workspace / "global.md"},
        "lower_evidence_roots": [workspace / "memory" / "kb" / "projects"],
        "legal_core_markers": ["active-legal"],
        "required_registry_scopes": ["incoming-raw", "compatibility-only"],
        "project_canonical": {},
        "project_runtime_root": {},
        "project_doc_refs": {},
        "default_decision_refs": [],
        "project_decision_refs": {},
        "default_lesson_refs": [],
        "project_lesson_refs": {},
        "governance_frozen_tuple_files": [],
        "event_contract_files": {},
        "frozen_tuple_expected": set(),
        "frozen_tuple_legacy_markers": set(),
        "formal_source_types": set(),
        "formal_event_types": set(),
        "formal_event_statuses": set(),
        "formal_field_keys": set(),
        "legacy_field_keys": set(),
        "required_canonical": [],
        "workspace_index_path": workspace / "INDEX.md",
        "docs_index_path": workspace / "docs" / "INDEX.md",
        "overview_doc_path": workspace / "overview.md",
        "global_index_path": workspace / "global-index.md",
        "hook_contract_path": pm_root / "hook-contract.md",
        "default_project_scope": "memory-core",
        "scope_match_hints": {},
        "read_text_if_exists_fn": _noop_read,
        "policy_pack_path": None,
    }
    defaults.update(overrides)
    return GatewayBusinessPolicyConfig(**defaults)


@pytest.fixture
def minimal_config(tmp_path: Path) -> GatewayBusinessPolicyConfig:
    return make_minimal_config(tmp_path)


@pytest.fixture
def valid_config_with_files(tmp_path: Path) -> GatewayBusinessPolicyConfig:
    """Config where all referenced files exist with valid content.

    workspace is placed inside repo so truth_model.resolve().relative_to(repo.resolve()) works.
    Uses a real file reader so validators see actual file content.
    """
    repo = _ensure_dir(tmp_path / "repo")
    workspace = _ensure_dir(repo / "workspace")
    pm_root = _ensure_dir(repo / "project-map")
    docs_dir = _ensure_dir(workspace / "docs")
    kb_projects = _ensure_dir(workspace / "memory" / "kb" / "projects")

    # project-map files with valid markers
    index_text = f"# Project Map Index\n{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n"
    (pm_root / "INDEX.md").write_text(index_text)

    core_text = f"# Legal Core Map\n{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n"
    (pm_root / "legal-core-map.md").write_text(core_text)

    registry_text = f"# Ingestion Registry\n{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n{MKR_REGISTRY_GIT_COMMIT_GATE}\n"
    (pm_root / "ingestion-registry-map.md").write_text(registry_text)

    governance_text = f"# Governance\n{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n"
    (pm_root / "governance.md").write_text(governance_text)

    # workspace / docs / overview / global index
    truth_model = workspace / "truth.md"
    truth_model.write_text("# Truth Model\n")

    workspace_index = workspace / "INDEX.md"
    workspace_index.write_text(
        f"project-map/INDEX.md\n{MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_WORKSPACE_GIT_COMMIT_RULE}\n"
        f"{(truth_model.resolve().relative_to(repo.resolve()).as_posix())}\n"
    )

    docs_index = docs_dir / "INDEX.md"
    docs_index.write_text(f"{MKR_INCOMING_RAW}\n{MKR_DOCS_UNABSORBED}\n")

    overview_doc = workspace / "overview.md"
    overview_doc.write_text(f"{MKR_WORKSPACE_PROJECT_MAP_REF}\n")

    global_index = workspace / "global-index.md"
    global_index.write_text(f"{MKR_NON_LEGAL_MATERIAL}\n{MKR_INGESTION_REGISTRY_REF}\n{truth_model.name}\n")

    hook_contract = pm_root / "hook-contract.md"
    hook_contract.write_text(f"{MKR_HOOK_MAP_ONLY_CONTEXT}\n{MKR_HOOK_REGISTRATION_GATE}\n")

    return make_minimal_config(
        tmp_path,
        repo_root=repo,
        workspace_root=workspace,
        project_map_root=pm_root,
        project_map_files=[pm_root / "INDEX.md", pm_root / "legal-core-map.md", pm_root / "ingestion-registry-map.md"],
        project_map_governance=pm_root / "governance.md",
        truth_model=truth_model,
        global_canonical=[workspace / "global.md"],
        authority_allowed_paths={workspace / "global.md"},
        lower_evidence_roots=[kb_projects],
        legal_core_markers=["active-legal"],
        required_registry_scopes=["incoming-raw", "compatibility-only"],
        project_canonical={"memory-core": workspace / "memory-core.md"},
        workspace_index_path=workspace_index,
        docs_index_path=docs_index,
        overview_doc_path=overview_doc,
        global_index_path=global_index,
        hook_contract_path=hook_contract,
        read_text_if_exists_fn=_file_reader,
    )


# ---------------------------------------------------------------------------
# 1. GatewayBusinessPolicyConfig schema tests
# ---------------------------------------------------------------------------

class TestGatewayBusinessPolicyConfigSchema:
    """Schema-level tests for the config dataclass."""

    def test_all_required_fields_present(self):
        """All 37 fields must be defined on the dataclass."""
        field_names = {f.name for f in fields(GatewayBusinessPolicyConfig)}
        expected = {
            "repo_root", "workspace_root", "project_map_root",
            "project_map_files", "project_map_governance", "truth_model",
            "global_canonical", "authority_allowed_paths", "lower_evidence_roots",
            "legal_core_markers", "required_registry_scopes",
            "project_canonical", "project_runtime_root",
            "project_doc_refs", "default_decision_refs", "project_decision_refs",
            "default_lesson_refs", "project_lesson_refs",
            "governance_frozen_tuple_files", "event_contract_files",
            "frozen_tuple_expected", "frozen_tuple_legacy_markers",
            "formal_source_types", "formal_event_types", "formal_event_statuses",
            "formal_field_keys", "legacy_field_keys",
            "required_canonical",
            "workspace_index_path", "docs_index_path",
            "overview_doc_path", "global_index_path", "hook_contract_path",
            "default_project_scope", "scope_match_hints",
            "read_text_if_exists_fn", "policy_pack_path",
        }
        assert field_names == expected

    def test_config_instantiation_with_all_fields(self, minimal_config):
        """Config must be instantiable when all required fields are provided."""
        assert isinstance(minimal_config, GatewayBusinessPolicyConfig)

    def test_policy_pack_path_is_optional(self, minimal_config):
        """policy_pack_path should default to None when not provided."""
        assert minimal_config.policy_pack_path is None

    def test_policy_pack_path_accepts_path(self, tmp_path):
        """policy_pack_path should accept a Path value."""
        cfg = make_minimal_config(tmp_path, policy_pack_path=tmp_path / "policies.json")
        assert cfg.policy_pack_path == tmp_path / "policies.json"

    def test_path_fields_must_be_path_instances(self, tmp_path):
        """Path fields should store Path objects."""
        cfg = make_minimal_config(tmp_path)
        assert isinstance(cfg.repo_root, Path)
        assert isinstance(cfg.workspace_root, Path)
        assert isinstance(cfg.project_map_root, Path)

    def test_list_fields_default_to_empty_list(self, minimal_config):
        """List fields should accept empty lists."""
        assert isinstance(minimal_config.project_map_files, list)
        assert isinstance(minimal_config.global_canonical, list)
        assert isinstance(minimal_config.required_canonical, list)

    def test_set_fields_accept_set_instances(self, minimal_config):
        """Set fields should accept set instances."""
        assert isinstance(minimal_config.authority_allowed_paths, set)
        assert isinstance(minimal_config.frozen_tuple_expected, set)

    def test_dict_fields_accept_dict_instances(self, minimal_config):
        """Dict fields should accept dict instances."""
        assert isinstance(minimal_config.project_canonical, dict)
        assert isinstance(minimal_config.scope_match_hints, dict)

    def test_read_text_fn_must_be_callable(self, minimal_config):
        """read_text_if_exists_fn must be a callable."""
        assert callable(minimal_config.read_text_if_exists_fn)

    def test_read_text_fn_is_used(self, tmp_path):
        """The read_text_if_exists_fn should be invoked by validator helpers."""
        call_log: list[Path] = []

        def tracking_read(path: Path) -> str:
            call_log.append(path)
            return "content"

        cfg = make_minimal_config(tmp_path, read_text_if_exists_fn=tracking_read)
        validator = ProjectMapValidator(cfg)
        validator.validate_project_map_files()
        assert len(call_log) > 0

    def test_default_project_scope_is_string(self, minimal_config):
        """default_project_scope must be a string."""
        assert isinstance(minimal_config.default_project_scope, str)
        assert minimal_config.default_project_scope == "memory-core"

    def test_config_field_count(self):
        """Config should have exactly 37 fields."""
        assert len(list(fields(GatewayBusinessPolicyConfig))) == 37


# ---------------------------------------------------------------------------
# 2. Helper function tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Tests for the shared helper functions."""

    def test_path_is_under_true(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        child = root / "child" / "file.txt"
        child.parent.mkdir(parents=True)
        child.touch()
        assert _path_is_under(child, root) is True

    def test_path_is_under_false(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        other = tmp_path / "other" / "file.txt"
        other.parent.mkdir(parents=True)
        other.touch()
        assert _path_is_under(other, root) is False

    def test_path_is_under_lexical_true(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        child = root / "sub"
        child.mkdir()
        assert _path_is_under_lexical(child, root) is True

    def test_path_is_under_lexical_false(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        assert _path_is_under_lexical(other, root) is False

    def test_section_bullets_finds_bullets(self):
        text = "## Section A\n- item one\n- `item two`\n## Section B\n- item three\n"
        bullets = _section_bullets(text, "## Section A")
        assert bullets == ["item one", "item two"]

    def test_section_bullets_empty_section(self):
        text = "## Section A\n## Section B\n- item\n"
        bullets = _section_bullets(text, "## Section A")
        assert bullets == []

    def test_section_bullets_no_heading(self):
        text = "- orphan bullet\n"
        bullets = _section_bullets(text, "## Missing")
        assert bullets == []

    def test_section_body_returns_text(self):
        text = "## Heading\nsome body text\nmore text\n## Next Heading\n"
        body = _section_body(text, "## Heading")
        assert "some body text" in body
        assert "more text" in body

    def test_section_body_empty_on_missing_heading(self):
        assert _section_body("no headings here", "## Missing") == ""

    def test_section_body_stops_at_next_heading(self):
        text = "## A\nbody A\n## B\nbody B\n"
        body = _section_body(text, "## A")
        assert "body A" in body
        assert "body B" not in body

    def test_markdown_code_tokens(self):
        text = "use `foo` and `bar` in `baz`"
        tokens = _markdown_code_tokens(text)
        assert tokens == {"foo", "bar", "baz"}

    def test_markdown_code_tokens_empty(self):
        assert _markdown_code_tokens("no backticks") == set()

    def test_json_string_values(self):
        text = '{"source_type": "lark", "event_type": "msg"}'
        vals = _json_string_values(text, "source_type")
        assert vals == {"lark"}

    def test_json_string_values_multiple(self):
        text = '{"source_type": "a"}\n{"source_type": "b"}'
        vals = _json_string_values(text, "source_type")
        assert vals == {"a", "b"}

    def test_json_object_keys(self):
        text = '{"key1": "v1", "key2": "v2"}'
        keys = _json_object_keys(text)
        assert keys == {"key1", "key2"}

    def test_existing_paths_filters_missing(self, tmp_path):
        existing = tmp_path / "exists.txt"
        existing.touch()
        missing = tmp_path / "nope.txt"
        result = _existing_paths([existing, missing])
        assert result == [str(existing)]

    def test_existing_paths_all_missing(self, tmp_path):
        result = _existing_paths([tmp_path / "a.txt", tmp_path / "b.txt"])
        assert result == []


# ---------------------------------------------------------------------------
# 3. ProjectMapValidator tests
# ---------------------------------------------------------------------------

class TestProjectMapValidator:
    """Tests for ProjectMapValidator schema parsing and validation."""

    def test_validate_project_map_files_no_errors_with_valid_content(self, valid_config_with_files):
        """Valid project-map files should produce zero errors."""
        validator = ProjectMapValidator(valid_config_with_files)
        errors = validator.validate_project_map_files()
        assert errors == []

    def test_validate_project_map_files_missing_markers(self, tmp_path):
        """Files missing required markers should produce errors."""
        pm_root = _ensure_dir(tmp_path / "project-map")
        (pm_root / "INDEX.md").write_text("no markers here")
        (pm_root / "legal-core-map.md").write_text("no markers")
        (pm_root / "ingestion-registry-map.md").write_text("empty")
        (pm_root / "governance.md").write_text("empty")

        cfg = make_minimal_config(tmp_path, project_map_root=pm_root, read_text_if_exists_fn=_file_reader)
        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert len(errors) > 0
        error_text = " ".join(errors)
        assert "unique legal entry" in error_text
        assert "active-legal map-only" in error_text

    def test_validate_project_map_files_round_references_flagged(self, tmp_path):
        """Files still referencing transition round/wave files should be flagged."""
        pm_root = _ensure_dir(tmp_path / "project-map")
        index_text = f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\nround-1 files\n"
        (pm_root / "INDEX.md").write_text(index_text)
        (pm_root / "legal-core-map.md").write_text(f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\nwaves/old\n")
        (pm_root / "ingestion-registry-map.md").write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n{MKR_REGISTRY_GIT_COMMIT_GATE}\n"
        )
        (pm_root / "governance.md").write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n"
        )

        cfg = make_minimal_config(tmp_path, project_map_root=pm_root, read_text_if_exists_fn=_file_reader)
        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        error_text = " ".join(errors)
        assert "round" in error_text or "wave" in error_text

    def test_validate_unique_legal_system_contract_valid(self, valid_config_with_files):
        """Valid legal system contract files should produce zero errors."""
        validator = ProjectMapValidator(valid_config_with_files)
        errors = validator.validate_unique_legal_system_contract()
        assert errors == []

    def test_validate_unique_legal_system_contract_missing_refs(self, tmp_path):
        """Missing marker references should be flagged."""
        workspace = _ensure_dir(tmp_path / "workspace")
        pm_root = _ensure_dir(tmp_path / "project-map")

        ws_index = workspace / "INDEX.md"
        ws_index.write_text("")  # empty — all markers missing
        docs_index = _ensure_dir(workspace / "docs") / "INDEX.md"
        docs_index.write_text("")
        overview = workspace / "overview.md"
        overview.write_text("")
        global_index = workspace / "global-index.md"
        global_index.write_text("")
        truth_model = workspace / "truth.md"
        truth_model.write_text("")
        hook_contract = pm_root / "hook-contract.md"
        hook_contract.write_text("")
        core_map = pm_root / "legal-core-map.md"
        core_map.write_text("")
        registry = pm_root / "ingestion-registry-map.md"
        registry.write_text("")

        cfg = make_minimal_config(
            tmp_path,
            workspace_root=workspace,
            project_map_root=pm_root,
            project_map_files=[pm_root / "INDEX.md", core_map, registry],
            truth_model=truth_model,
            workspace_index_path=ws_index,
            docs_index_path=docs_index,
            overview_doc_path=overview,
            global_index_path=global_index,
            hook_contract_path=hook_contract,
            project_canonical={"mem": workspace / "mem.md"},
            read_text_if_exists_fn=_file_reader,
        )
        validator = ProjectMapValidator(cfg)
        errors = validator.validate_unique_legal_system_contract()
        assert len(errors) > 0
        error_text = " ".join(errors)
        assert "project-map entry" in error_text


# ---------------------------------------------------------------------------
# 5. FrozenTupleChecker tests
# ---------------------------------------------------------------------------

class TestFrozenTupleChecker:
    """Tests for FrozenTupleChecker schema validation."""

    def test_no_errors_when_no_files(self, minimal_config):
        """Empty governance_frozen_tuple_files should return no errors."""
        checker = FrozenTupleChecker(minimal_config)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert errors == []

    def test_missing_files_return_error(self, tmp_path):
        """Non-existent governance files should return a missing-files error."""
        cfg = make_minimal_config(tmp_path, governance_frozen_tuple_files=[tmp_path / "nope.md"])
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) == 1
        assert "missing governance files" in errors[0]

    def test_expected_markers_missing(self, tmp_path):
        """Files missing expected markers should be flagged."""
        gov_file = tmp_path / "gov.md"
        gov_file.write_text("some content without markers")
        cfg = make_minimal_config(
            tmp_path,
            governance_frozen_tuple_files=[gov_file],
            frozen_tuple_expected={"EXPECTED_MARKER_1", "EXPECTED_MARKER_2"},
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) >= 1
        assert "missing expected tuple markers" in errors[0]

    def test_expected_markers_present_no_error(self, tmp_path):
        """Files with all expected markers should produce no errors."""
        gov_file = tmp_path / "gov.md"
        gov_file.write_text("EXPECTED_MARKER_A and EXPECTED_MARKER_B here")
        cfg = make_minimal_config(
            tmp_path,
            governance_frozen_tuple_files=[gov_file],
            frozen_tuple_expected={"EXPECTED_MARKER_A", "EXPECTED_MARKER_B"},
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert errors == []

    def test_legacy_markers_flagged(self, tmp_path):
        """Presence of legacy markers should be reported."""
        gov_file = tmp_path / "gov.md"
        gov_file.write_text("EXPECTED_OK\nLEGACY_MARKER_OLD\n")
        cfg = make_minimal_config(
            tmp_path,
            governance_frozen_tuple_files=[gov_file],
            frozen_tuple_expected={"EXPECTED_OK"},
            frozen_tuple_legacy_markers={"LEGACY_MARKER_OLD"},
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) >= 1
        assert "legacy" in errors[-1].lower()

    def test_multiple_governance_files_combined(self, tmp_path):
        """Multiple governance files should have their text combined for checks."""
        f1 = tmp_path / "gov1.md"
        f1.write_text("MARKER_A\n")
        f2 = tmp_path / "gov2.md"
        f2.write_text("MARKER_B\n")
        cfg = make_minimal_config(
            tmp_path,
            governance_frozen_tuple_files=[f1, f2],
            frozen_tuple_expected={"MARKER_A", "MARKER_B"},
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert errors == []


# ---------------------------------------------------------------------------
# 6. EventContractChecker tests
# ---------------------------------------------------------------------------

class TestEventContractChecker:
    """Tests for EventContractChecker schema validation."""

    def test_no_errors_when_no_files(self, minimal_config):
        """Empty event_contract_files should return no errors (defensive check)."""
        checker = EventContractChecker(minimal_config)
        errors = checker.event_contract_blocker_errors()
        assert errors == []

    def test_missing_files_return_error(self, tmp_path):
        """Non-existent event contract files should return a missing-files error."""
        cfg = make_minimal_config(
            tmp_path,
            event_contract_files={
                "upstream_standard": tmp_path / "us.md",
                "upstream_mapping": tmp_path / "um.md",
                "formal_contract": tmp_path / "fc.md",
                "upstream_samples": tmp_path / "us.json",
                "downstream_samples": tmp_path / "ds.json",
            },
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert len(errors) == 1
        assert "missing event contract files" in errors[0]

    def test_formal_sets_mismatch_flagged(self, tmp_path):
        """Mismatched formal source types in contract docs should be flagged."""
        us = tmp_path / "us.md"
        us.write_text("## 3. 正式输入源\n`wrong_type`\n")
        um = tmp_path / "um.md"
        um.write_text("## 2. 正式输入源范围\n`wrong_type`\n## 3. 输入源到正式事件的映射主表\n`wrong_evt`\n## 4. 主路由规则\n## 5. 错误码与原因码\n")
        fc = tmp_path / "fc.md"
        fc.write_text("## 3. source_type 正式白名单\n`wrong_type`\n## 4. event_type 正式清单\n## 6. event_status 正式取值\n")
        us_json = tmp_path / "us.json"
        us_json.write_text('{"source_type": "valid"}')
        ds_json = tmp_path / "ds.json"
        ds_json.write_text('{"source_type": "valid"}')

        cfg = make_minimal_config(
            tmp_path,
            event_contract_files={
                "upstream_standard": us,
                "upstream_mapping": um,
                "formal_contract": fc,
                "upstream_samples": us_json,
                "downstream_samples": ds_json,
            },
            formal_source_types={"correct_type"},
            formal_event_types={"correct_evt"},
            formal_event_statuses={"ok"},
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert len(errors) > 0

    def test_valid_event_contracts_no_errors(self, tmp_path):
        """Well-formed event contract files with matching formal sets should be clean."""
        us = tmp_path / "us.md"
        us.write_text(
            "## 3. 正式输入源\n`lark`\n`api`\n"
            "## 4. 正式事件类型\n`msg.received`\n`task.updated`\n"
            "## 6. event_status 标准\n`success`\n`error`\n"
        )
        um = tmp_path / "um.md"
        um.write_text(
            "## 2. 正式输入源范围\n`lark`\n`api`\n"
            "## 3. 输入源到正式事件的映射主表\n`msg.received`\n`task.updated`\n"
            "## 4. 主路由规则\n`success`\n`error`\n"
            "## 5. 错误码与原因码\n"
        )
        fc = tmp_path / "fc.md"
        fc.write_text(
            "## 3. source_type 正式白名单\n`lark`\n`api`\n"
            "## 4. event_type 正式清单\n`msg.received`\n`task.updated`\n"
            "## 6. event_status 正式取值\n`success`\n`error`\n"
        )
        us_json = tmp_path / "us.json"
        us_json.write_text(
            '{"source_type": "lark", "event_type": "msg.received", "event_status": "success", "formal_field": "val"}'
        )
        ds_json = tmp_path / "ds.json"
        ds_json.write_text(
            '{"source_type": "api", "event_type": "task.updated", "event_status": "error", "formal_field": "val"}'
        )

        cfg = make_minimal_config(
            tmp_path,
            event_contract_files={
                "upstream_standard": us,
                "upstream_mapping": um,
                "formal_contract": fc,
                "upstream_samples": us_json,
                "downstream_samples": ds_json,
            },
            formal_source_types={"lark", "api"},
            formal_event_types={"msg.received", "task.updated"},
            formal_event_statuses={"success", "error"},
            formal_field_keys={"formal_field"},
            legacy_field_keys={"old_field"},
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert errors == []

    def test_sample_unknown_source_types_flagged(self, tmp_path):
        """Sample JSON with out-of-contract source_type should be flagged."""
        us = tmp_path / "us.md"
        us.write_text("## 3. 正式输入源\n`valid`\n## 4. 正式事件类型\n`evt`\n## 6. event_status 标准\n`ok`\n")
        um = tmp_path / "um.md"
        um.write_text("## 2. 正式输入源范围\n`valid`\n## 3. 输入源到正式事件的映射主表\n`evt`\n## 4. 主路由规则\n`ok`\n## 5. 错误码与原因码\n")
        fc = tmp_path / "fc.md"
        fc.write_text("## 3. source_type 正式白名单\n`valid`\n## 4. event_type 正式清单\n`evt`\n## 6. event_status 正式取值\n`ok`\n")
        us_json = tmp_path / "us.json"
        us_json.write_text('{"source_type": "unknown_type"}')
        ds_json = tmp_path / "ds.json"
        ds_json.write_text('{"source_type": "valid"}')

        cfg = make_minimal_config(
            tmp_path,
            event_contract_files={
                "upstream_standard": us,
                "upstream_mapping": um,
                "formal_contract": fc,
                "upstream_samples": us_json,
                "downstream_samples": ds_json,
            },
            formal_source_types={"valid"},
            formal_event_types={"evt"},
            formal_event_statuses={"ok"},
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert any("out-of-contract source_type" in e for e in errors)

    def test_sample_legacy_fields_flagged(self, tmp_path):
        """Sample JSON with legacy field keys should be flagged."""
        us = tmp_path / "us.md"
        us.write_text("## 3. 正式输入源\n`v`\n## 4. 正式事件类型\n`e`\n## 6. event_status 标准\n`s`\n")
        um = tmp_path / "um.md"
        um.write_text("## 2. 正式输入源范围\n`v`\n## 3. 输入源到正式事件的映射主表\n`e`\n## 4. 主路由规则\n`s`\n## 5. 错误码与原因码\n")
        fc = tmp_path / "fc.md"
        fc.write_text("## 3. source_type 正式白名单\n`v`\n## 4. event_type 正式清单\n`e`\n## 6. event_status 正式取值\n`s`\n")
        us_json = tmp_path / "us.json"
        us_json.write_text('{"source_type": "v", "event_type": "e", "event_status": "s", "old_field": "x"}')
        ds_json = tmp_path / "ds.json"
        ds_json.write_text('{"source_type": "v", "event_type": "e", "event_status": "s"}')

        cfg = make_minimal_config(
            tmp_path,
            event_contract_files={
                "upstream_standard": us,
                "upstream_mapping": um,
                "formal_contract": fc,
                "upstream_samples": us_json,
                "downstream_samples": ds_json,
            },
            formal_source_types={"v"},
            formal_event_types={"e"},
            formal_event_statuses={"s"},
            formal_field_keys=set(),
            legacy_field_keys={"old_field"},
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert any("legacy field" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# 7. TruthBasisResolver tests
# ---------------------------------------------------------------------------

class TestTruthBasisResolver:
    """Tests for TruthBasisResolver truth-basis parsing and validation."""

    def test_unsupported_scope_returns_fail(self, minimal_config):
        """Unsupported project scope should return validation=fail."""
        resolver = TruthBasisResolver(minimal_config)
        result = resolver.truth_basis_for_scope("nonexistent_scope")
        assert result["validation"] == "fail"
        assert "unsupported project scope" in " ".join(result["errors"])
        assert result["conflict_status"] == ["unresolved"]

    def test_truth_basis_for_scope_with_project(self, tmp_path):
        """Valid project scope with truth-basis sections should parse correctly."""
        repo = _ensure_dir(tmp_path / "repo")
        workspace = _ensure_dir(repo / "workspace")
        pm_root = _ensure_dir(repo / "project-map")
        kb_projects = _ensure_dir(workspace / "memory" / "kb" / "projects")

        global_md = workspace / "global.md"
        global_md.write_text(
            "### Truth Basis\n"
            "### Source Refs\n- project-map/INDEX.md\n"
            "### Authority Refs\n- global.md\n"
            "### Evidence Refs\n- memory/kb/projects/sample.md\n"
            "### Conflict Status\n- resolved\n"
        )
        project_md = workspace / "project-a.md"
        project_md.write_text(
            "### Truth Basis\n"
            "### Source Refs\n- project-map/legal-core-map.md\n"
            "### Authority Refs\n- global.md\n"
            "### Evidence Refs\n- memory/kb/projects/p.md\n"
            "### Conflict Status\n- resolved\n"
        )

        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            workspace_root=workspace,
            project_map_root=pm_root,
            global_canonical=[global_md],
            authority_allowed_paths={global_md},
            lower_evidence_roots=[kb_projects],
            project_canonical={"project-a": project_md},
        )
        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("project-a")
        assert result["validation"] in ("pass", "fail")
        assert result["policy"] == "source-authority-evidence-conflict"
        assert result["project_ref"] == str(project_md)

    def test_classify_truth_ref_legal_core(self, tmp_path):
        """legal-core-map.md should be classified as 'legal-core'."""
        pm_root = _ensure_dir(tmp_path / "project-map")
        cfg = make_minimal_config(tmp_path, project_map_root=pm_root)
        resolver = TruthBasisResolver(cfg)
        assert resolver._classify_truth_ref(pm_root / "legal-core-map.md") == "legal-core"

    def test_classify_truth_ref_project_map_index(self, tmp_path):
        """INDEX.md in project_map_root should be classified as 'project-map-index'."""
        pm_root = _ensure_dir(tmp_path / "project-map")
        cfg = make_minimal_config(tmp_path, project_map_root=pm_root)
        resolver = TruthBasisResolver(cfg)
        assert resolver._classify_truth_ref(pm_root / "INDEX.md") == "project-map-index"

    def test_truth_basis_missing_file(self, tmp_path):
        """Non-existent project canonical should still return a result structure."""
        workspace = _ensure_dir(tmp_path / "workspace")
        missing_md = workspace / "missing.md"
        cfg = make_minimal_config(
            tmp_path,
            workspace_root=workspace,
            project_canonical={"ghost": missing_md},
        )
        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("ghost")
        assert "errors" in result
        assert "validation" in result

    def test_truth_basis_sections_parsed(self, tmp_path):
        """Truth-basis sections should be correctly parsed from markdown."""
        f = tmp_path / "doc.md"
        content = (
            "### Truth Basis\n"
            "### Source Refs\n- path/a.md\n- path/b.md\n"
            "### Authority Refs\n- path/c.md\n"
            "### Evidence Refs\n- path/d.md\n"
            "### Conflict Status\n- resolved\n"
            "### Other Section\n- ignored\n"
        )
        f.write_text(content)
        cfg = make_minimal_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        sections = resolver._truth_basis_sections_for(f, content)
        assert sections["source_refs"] == ["path/a.md", "path/b.md"]
        assert sections["authority_refs"] == ["path/c.md"]
        assert sections["evidence_refs"] == ["path/d.md"]
        assert sections["conflict_status"] == ["resolved"]

    def test_truth_basis_errors_missing_sections(self, tmp_path):
        """File without truth basis sections should report errors."""
        f = tmp_path / "empty.md"
        content = "# Just a heading\nno truth basis here\n"
        f.write_text(content)
        cfg = make_minimal_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        errors = resolver._truth_basis_errors_for(f, content)
        assert len(errors) >= 1
        assert "truth basis section missing" in errors[0]

    def test_truth_basis_errors_unresolved_conflict(self, tmp_path):
        """Unresolved conflict status should be flagged."""
        f = tmp_path / "doc.md"
        content = (
            "### Truth Basis\n"
            "### Source Refs\n- a.md\n"
            "### Authority Refs\n- b.md\n"
            "### Evidence Refs\n- c.md\n"
            "### Conflict Status\n- pending\n"
        )
        f.write_text(content)
        cfg = make_minimal_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        errors = resolver._truth_basis_errors_for(f, content)
        assert any("unresolved" in e for e in errors)

    def test_truth_basis_errors_source_evidence_overlap(self, tmp_path):
        """Identical source and evidence refs should be flagged."""
        f = tmp_path / "doc.md"
        content = (
            "### Truth Basis\n"
            "### Source Refs\n- same.md\n"
            "### Authority Refs\n- other.md\n"
            "### Evidence Refs\n- same.md\n"
            "### Conflict Status\n- resolved\n"
        )
        f.write_text(content)
        cfg = make_minimal_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        errors = resolver._truth_basis_errors_for(f, content)
        assert any("must not be identical" in e for e in errors)

    def test_truth_basis_errors_source_authority_overlap(self, tmp_path):
        """Source refs overlapping authority refs should be flagged."""
        f = tmp_path / "doc.md"
        content = (
            "### Truth Basis\n"
            "### Source Refs\n- shared.md\n"
            "### Authority Refs\n- shared.md\n"
            "### Evidence Refs\n- diff.md\n"
            "### Conflict Status\n- resolved\n"
        )
        f.write_text(content)
        cfg = make_minimal_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        errors = resolver._truth_basis_errors_for(f, content)
        assert any("overlap authority" in e for e in errors)

    def test_truth_basis_errors_authority_evidence_overlap(self, tmp_path):
        """Authority refs overlapping evidence refs should be flagged."""
        f = tmp_path / "doc.md"
        content = (
            "### Truth Basis\n"
            "### Source Refs\n- a.md\n"
            "### Authority Refs\n- shared.md\n"
            "### Evidence Refs\n- shared.md\n"
            "### Conflict Status\n- resolved\n"
        )
        f.write_text(content)
        cfg = make_minimal_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        errors = resolver._truth_basis_errors_for(f, content)
        assert any("authority refs overlap evidence" in e for e in errors)


# ---------------------------------------------------------------------------
# 8. ScopeResolver tests
# ---------------------------------------------------------------------------

class TestScopeResolver:
    """Tests for ScopeResolver scope resolution and overrides."""

    def test_determine_scope_default_when_no_hints(self, minimal_config):
        """Without scope_match_hints, should return default_project_scope."""
        resolver = ScopeResolver(minimal_config)
        result = resolver.determine_project_scope(minimal_config.repo_root / "anywhere")
        assert result == minimal_config.default_project_scope

    def test_determine_scope_matches_hints(self, tmp_path):
        """cwd under a hint root should return that scope.

        Note: hints paths must be under repo_root for _path_is_under_lexical to match,
        since determine_project_scope first checks cwd is under repo_root.
        """
        repo = _ensure_dir(tmp_path / "repo")
        tools_dir = _ensure_dir(repo / "tools")

        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            scope_match_hints={"tools-scope": [tools_dir]},
            default_project_scope="default",
        )
        resolver = ScopeResolver(cfg)
        result = resolver.determine_project_scope(tools_dir / "sub")
        assert result == "tools-scope"

    def test_determine_scope_outside_repo(self, tmp_path):
        """cwd outside repo_root should return default scope."""
        outside = _ensure_dir(tmp_path / "outside")
        cfg = make_minimal_config(tmp_path, default_project_scope="fallback")
        resolver = ScopeResolver(cfg)
        result = resolver.determine_project_scope(outside)
        assert result == "fallback"

    def test_get_project_canonical_merges_config(self, tmp_path):
        """Should return the config's project_canonical dict."""
        repo = _ensure_dir(tmp_path / "repo")
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            project_canonical={"a": repo / "a.md"},
        )
        resolver = ScopeResolver(cfg)
        result = resolver.get_project_canonical()
        assert "a" in result

    def test_get_project_canonical_with_overrides(self, tmp_path):
        """Scope config overrides should merge into project_canonical."""
        workspace = _ensure_dir(tmp_path / "workspace")
        scope_cfg = tmp_path / "scope.json"
        scope_cfg.write_text(json.dumps({
            "project_canonical": {"override-scope": "relative/path.md"},
        }))
        cfg = make_minimal_config(
            tmp_path,
            workspace_root=workspace,
            project_canonical={"existing": workspace / "existing.md"},
        )
        resolver = ScopeResolver(cfg, scope_config_path=scope_cfg)
        result = resolver.get_project_canonical()
        assert "existing" in result
        assert "override-scope" in result

    def test_get_project_runtime_root(self, tmp_path):
        """Should return the config's project_runtime_root dict."""
        repo = _ensure_dir(tmp_path / "repo")
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            project_runtime_root={"scope1": repo / "runtime1"},
        )
        resolver = ScopeResolver(cfg)
        result = resolver.get_project_runtime_root()
        assert "scope1" in result

    def test_get_project_runtime_root_with_overrides(self, tmp_path):
        """Scope config overrides should merge into project_runtime_root."""
        workspace = _ensure_dir(tmp_path / "workspace")
        scope_cfg = tmp_path / "scope.json"
        scope_cfg.write_text(json.dumps({
            "project_runtime_root": {"scope1": "new_runtime"},
        }))
        cfg = make_minimal_config(
            tmp_path,
            workspace_root=workspace,
            project_runtime_root={"scope1": workspace / "old"},
        )
        resolver = ScopeResolver(cfg, scope_config_path=scope_cfg)
        result = resolver.get_project_runtime_root()
        assert "scope1" in result

    def test_get_required_canonical(self, tmp_path):
        """Should return the config's required_canonical list."""
        repo = _ensure_dir(tmp_path / "repo")
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            required_canonical=[repo / "req.md"],
        )
        resolver = ScopeResolver(cfg)
        result = resolver.get_required_canonical()
        assert len(result) == 1

    def test_get_global_canonical(self, tmp_path):
        """Should return the config's global_canonical list."""
        workspace = _ensure_dir(tmp_path / "workspace")
        cfg = make_minimal_config(
            tmp_path,
            workspace_root=workspace,
            global_canonical=[workspace / "g.md"],
        )
        resolver = ScopeResolver(cfg)
        result = resolver.get_global_canonical()
        assert len(result) == 1

    def test_project_map_refs(self, minimal_config):
        """Should return string versions of project_map_files."""
        resolver = ScopeResolver(minimal_config)
        refs = resolver.project_map_refs()
        assert isinstance(refs, list)
        assert all(isinstance(r, str) for r in refs)

    def test_decision_refs_for_scope_default(self, tmp_path):
        """Should return default_decision_refs when no project-specific refs exist."""
        repo = _ensure_dir(tmp_path / "repo")
        default_ref = repo / "default_dec.md"
        default_ref.touch()
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            default_decision_refs=[default_ref],
        )
        resolver = ScopeResolver(cfg)
        refs = resolver.decision_refs_for_scope("unknown")
        assert len(refs) == 1

    def test_decision_refs_for_scope_project_specific(self, tmp_path):
        """Project-specific decision refs should be appended to defaults."""
        repo = _ensure_dir(tmp_path / "repo")
        default_ref = repo / "default_dec.md"
        default_ref.touch()
        project_ref = repo / "project_dec.md"
        project_ref.touch()

        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            default_decision_refs=[default_ref],
            project_decision_refs={"my-scope": [project_ref]},
        )
        resolver = ScopeResolver(cfg)
        refs = resolver.decision_refs_for_scope("my-scope")
        assert len(refs) == 2

    def test_lesson_refs_for_scope_default(self, tmp_path):
        """Default lesson refs should be returned when no project-specific refs exist."""
        repo = _ensure_dir(tmp_path / "repo")
        lesson = repo / "lesson.md"
        lesson.touch()
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            default_lesson_refs=[lesson],
        )
        resolver = ScopeResolver(cfg)
        refs = resolver.lesson_refs_for_scope("any")
        assert len(refs) == 1

    def test_lesson_refs_for_scope_project_specific(self, tmp_path):
        """Project-specific lesson refs should be appended."""
        repo = _ensure_dir(tmp_path / "repo")
        default_ref = repo / "default_lesson.md"
        default_ref.touch()
        project_ref = repo / "project_lesson.md"
        project_ref.touch()

        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            default_lesson_refs=[default_ref],
            project_lesson_refs={"scope-x": [project_ref]},
        )
        resolver = ScopeResolver(cfg)
        refs = resolver.lesson_refs_for_scope("scope-x")
        assert len(refs) == 2

    def test_docs_refs_for_scope(self, tmp_path):
        """Project doc refs should be returned for matching scope."""
        repo = _ensure_dir(tmp_path / "repo")
        doc = repo / "doc.md"
        doc.touch()
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            project_doc_refs={"scope-y": [doc]},
        )
        resolver = ScopeResolver(cfg)
        refs = resolver.docs_refs_for_scope("scope-y")
        assert len(refs) == 1

    def test_docs_refs_for_scope_missing(self, minimal_config):
        """Empty list for unknown scope."""
        resolver = ScopeResolver(minimal_config)
        refs = resolver.docs_refs_for_scope("unknown")
        assert refs == []

    def test_scope_config_invalid_json_returns_empty(self, tmp_path):
        """Invalid JSON in scope config should yield empty overrides."""
        scope_cfg = tmp_path / "bad.json"
        scope_cfg.write_text("not json {{{")
        cfg = make_minimal_config(tmp_path)
        resolver = ScopeResolver(cfg, scope_config_path=scope_cfg)
        assert resolver._scope_overrides == {}

    def test_scope_config_not_dict_returns_empty(self, tmp_path):
        """JSON array in scope config should yield empty overrides."""
        scope_cfg = tmp_path / "arr.json"
        scope_cfg.write_text("[1, 2, 3]")
        cfg = make_minimal_config(tmp_path)
        resolver = ScopeResolver(cfg, scope_config_path=scope_cfg)
        assert resolver._scope_overrides == {}

    def test_scope_config_env_variable(self, tmp_path, monkeypatch):
        """ScopeResolver should read SCOPE_CONFIG_PATH_ENV from environment."""
        scope_cfg = tmp_path / "env_scope.json"
        scope_cfg.write_text(json.dumps({"project_canonical": {"env-scope": "env.md"}}))
        monkeypatch.setenv(ScopeResolver.SCOPE_CONFIG_PATH_ENV, str(scope_cfg))
        cfg = make_minimal_config(tmp_path)
        resolver = ScopeResolver(cfg)
        assert "env-scope" in resolver.get_project_canonical()

    def test_resolve_override_path_absolute(self, minimal_config):
        """Absolute override paths should be returned as-is."""
        resolver = ScopeResolver(minimal_config)
        result = resolver._resolve_override_path("/abs/path.md")
        assert result == Path("/abs/path.md")

    def test_resolve_override_path_relative(self, tmp_path):
        """Relative override paths should be resolved against repo_root."""
        repo = _ensure_dir(tmp_path / "repo")
        cfg = make_minimal_config(tmp_path, repo_root=repo)
        resolver = ScopeResolver(cfg)
        result = resolver._resolve_override_path("relative/path.md")
        assert repo in result.parents


# ---------------------------------------------------------------------------
# 9. Integration — multiple valid config variants
# ---------------------------------------------------------------------------

class TestValidConfigVariants:
    """Tests that multiple valid config shapes are accepted."""

    def test_minimal_config_is_valid(self, minimal_config):
        """A bare-minimal config should be instantiable and usable."""
        assert minimal_config.repo_root is not None
        assert isinstance(minimal_config.project_map_files, list)

    def test_config_with_full_event_contract(self, tmp_path):
        """Config with all event contract fields set should be valid."""
        for name in ("us.md", "um.md", "fc.md", "us.json", "ds.json"):
            f = tmp_path / name
            f.write_text("")
        cfg = make_minimal_config(
            tmp_path,
            event_contract_files={
                "upstream_standard": tmp_path / "us.md",
                "upstream_mapping": tmp_path / "um.md",
                "formal_contract": tmp_path / "fc.md",
                "upstream_samples": tmp_path / "us.json",
                "downstream_samples": tmp_path / "ds.json",
            },
        )
        assert len(cfg.event_contract_files) == 5

    def test_config_with_full_governance(self, tmp_path):
        """Config with governance files and markers should be valid."""
        gov = tmp_path / "gov.md"
        gov.write_text("")
        cfg = make_minimal_config(
            tmp_path,
            governance_frozen_tuple_files=[gov],
            frozen_tuple_expected={"MKR_1", "MKR_2"},
            frozen_tuple_legacy_markers={"LEGACY_1"},
        )
        assert len(cfg.governance_frozen_tuple_files) == 1

    def test_config_with_project_mappings(self, tmp_path):
        """Config with project canonical and runtime mappings should be valid."""
        cfg = make_minimal_config(
            tmp_path,
            project_canonical={"proj-a": tmp_path / "a.md", "proj-b": tmp_path / "b.md"},
            project_runtime_root={"proj-a": tmp_path / "run-a", "proj-b": tmp_path / "run-b"},
        )
        assert len(cfg.project_canonical) == 2
        assert len(cfg.project_runtime_root) == 2

    def test_config_with_scope_match_hints(self, tmp_path):
        """Config with scope match hints should be valid."""
        tools = _ensure_dir(tmp_path / "tools")
        agents = _ensure_dir(tmp_path / "agents")
        cfg = make_minimal_config(
            tmp_path,
            scope_match_hints={
                "tools-scope": [tools],
                "agents-scope": [agents],
            },
        )
        assert len(cfg.scope_match_hints) == 2


# ---------------------------------------------------------------------------
# 10. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge-case tests for schema validation."""

    def test_empty_read_text_returns_empty_string(self, minimal_config):
        """The default _noop_read returns empty string."""
        result = minimal_config.read_text_if_exists_fn(Path("/nonexistent"))
        assert result == ""

    def test_validator_with_empty_read_fn_produces_errors(self, minimal_config):
        """Validators should produce errors when files return empty text."""
        validator = ProjectMapValidator(minimal_config)
        errors = validator.validate_project_map_files()
        assert len(errors) > 0

    def test_scope_resolver_no_config_path(self, minimal_config):
        """Without a scope config path, overrides should be empty."""
        resolver = ScopeResolver(minimal_config)
        assert resolver._scope_overrides == {}

    def test_truth_basis_resolver_get_project_canonical(self, tmp_path):
        """TruthBasisResolver.get_project_canonical should delegate to config."""
        repo = _ensure_dir(tmp_path / "repo")
        cfg = make_minimal_config(
            tmp_path,
            repo_root=repo,
            project_canonical={"test": repo / "test.md"},
        )
        resolver = TruthBasisResolver(cfg)
        result = resolver.get_project_canonical()
        assert "test" in result

    def test_config_mutable_defaults_not_shared(self, tmp_path):
        """Creating two configs from same tmp_path should not share mutable defaults."""
        c1 = make_minimal_config(tmp_path)
        repo2 = _ensure_dir(tmp_path / "repo2")
        workspace2 = _ensure_dir(tmp_path / "workspace2")
        pm2 = _ensure_dir(tmp_path / "pm2")
        c2 = make_minimal_config(tmp_path, repo_root=repo2, workspace_root=workspace2, project_map_root=pm2)
        c1.project_map_files.append(tmp_path / "extra.md")
        assert len(c1.project_map_files) != len(c2.project_map_files)
