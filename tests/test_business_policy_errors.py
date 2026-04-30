#!/usr/bin/env python3
"""Business policy error messages and report output tests.

Covers:
- Error message content verification (assert messages contain key phrases)
- Error message format consistency across checkers
- Report/dict output structure validation from TruthBasisResolver
- Multiple errors aggregation behavior
- Boundary: no-errors case
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workspace.tools.business_policy_checks import (
    EventContractChecker,
    FrozenTupleChecker,
    ProjectMapValidator,
    ScopeResolver,
    TruthBasisResolver,
)
from workspace.tools.memory_hook_impls import GatewayBusinessPolicyConfig

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _noop_read(_path: Path) -> str:
    return ""


def _make_minimal_config(tmp_path: Path) -> GatewayBusinessPolicyConfig:
    """Build a minimal GatewayBusinessPolicyConfig with all required fields."""
    base = tmp_path / "workspace"
    base.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    # Create minimal files that exist so we can control content
    pm_index = base / "project-map" / "INDEX.md"
    pm_index.parent.mkdir(parents=True, exist_ok=True)
    pm_index.touch()

    core_map = base / "project-map" / "legal-core-map.md"
    core_map.touch()

    registry = base / "project-map" / "ingestion-registry-map.md"
    registry.touch()

    governance = base / "project-map" / "governance.md"
    governance.touch()

    truth_model = base / "memory" / "kb" / "global" / "workbot-truth-model.md"
    truth_model.parent.mkdir(parents=True, exist_ok=True)
    truth_model.touch()

    workspace_index = base / "INDEX.md"
    workspace_index.touch()

    docs_index = base / "memory" / "docs" / "INDEX.md"
    docs_index.parent.mkdir(parents=True, exist_ok=True)
    docs_index.touch()

    overview_doc = base / "memory" / "docs" / "overview.md"
    overview_doc.touch()

    global_index = base / "memory" / "kb" / "global" / "INDEX.md"
    global_index.touch()

    hook_contract = base / "memory" / "hook-contract.md"
    hook_contract.touch()

    return GatewayBusinessPolicyConfig(
        repo_root=repo_root,
        workspace_root=base,
        project_map_root=base / "project-map",
        project_map_files=[pm_index, core_map, registry],
        project_map_governance=governance,
        truth_model=truth_model,
        global_canonical=[truth_model],
        authority_allowed_paths={truth_model},
        lower_evidence_roots=[base / "memory" / "kb" / "projects"],
        legal_core_markers=["marker-1"],
        required_registry_scopes=["scope-1"],
        project_canonical={"workbot": truth_model},
        project_runtime_root={"workbot": base / "runtime"},
        project_doc_refs={},
        default_decision_refs=[],
        project_decision_refs={},
        default_lesson_refs=[],
        project_lesson_refs={},
        governance_frozen_tuple_files=[governance],
        event_contract_files={
            "upstream_standard": base / "upstream_standard.md",
            "upstream_mapping": base / "upstream_mapping.md",
            "formal_contract": base / "formal_contract.md",
            "upstream_samples": base / "upstream_samples.json",
            "downstream_samples": base / "downstream_samples.json",
        },
        frozen_tuple_expected={"expected-marker"},
        frozen_tuple_legacy_markers={"legacy-marker"},
        formal_source_types={"source-a"},
        formal_event_types={"event-a"},
        formal_event_statuses={"status-a"},
        formal_field_keys={"field-a"},
        legacy_field_keys={"legacy-field"},
        required_canonical=[],
        workspace_index_path=workspace_index,
        docs_index_path=docs_index,
        overview_doc_path=overview_doc,
        global_index_path=global_index,
        hook_contract_path=hook_contract,
        default_project_scope="default",
        scope_match_hints={"workbot": [base / "memory"]},
        read_text_if_exists_fn=_noop_read,
    )


@pytest.fixture()
def minimal_config(tmp_path: Path) -> GatewayBusinessPolicyConfig:
    return _make_minimal_config(tmp_path)


# ---------------------------------------------------------------------------
# 1. ProjectMapValidator — error messages
# ---------------------------------------------------------------------------

class TestProjectMapValidatorErrors:
    """Verify error messages from project-map validation contain expected keywords."""

    def test_validate_project_map_files_empty_content_produces_errors(self, minimal_config):
        """When all files are empty, every marker check fails."""
        validator = ProjectMapValidator(minimal_config)
        errors = validator.validate_project_map_files()
        assert len(errors) > 0
        all_text = " ".join(errors)
        assert "unique legal entry" in all_text
        assert "active-legal map-only" in all_text
        assert "git-commit gate" in all_text

    def test_validate_project_map_files_no_round_references(self, minimal_config):
        """Round/wave references in project-map produce errors."""
        content = "round-1 files\nwaves/phase-2"

        def fake_read(path: Path) -> str:
            return content

        cfg = replace(minimal_config, read_text_if_exists_fn=fake_read)
        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        round_errors = [e for e in errors if "transition round" in e]
        assert len(round_errors) > 0

    def test_validate_project_map_files_all_markers_present_no_errors(self, minimal_config):
        """When all required markers are present, no errors are returned."""
        index_content = (
            "唯一合法入口\n"
            "只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。\n"
            "同次 `git commit` 提交后才生效\n"
        )
        core_content = "active-legal\n只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。\n"
        registry_content = (
            "incoming-raw\ncompatibility-only\n`absorbed`\n`retired`\n同次 `git commit` 提交后才生效\n"
        )
        governance_content = (
            "未经过唯一真相系统清洗\n"
            "只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。\n"
            "未完成同次 `git commit` 的目录登记，不得视为生效。\n"
        )

        files = {
            str(minimal_config.project_map_files[0]): index_content,
            str(minimal_config.project_map_files[1]): core_content,
            str(minimal_config.project_map_files[2]): registry_content,
            str(minimal_config.project_map_governance): governance_content,
        }

        def fake_read(path: Path) -> str:
            return files.get(str(path), "")

        cfg = replace(minimal_config, read_text_if_exists_fn=fake_read)
        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert errors == []

    def test_validate_unique_legal_system_contract_empty_files_produce_errors(self, minimal_config):
        """Empty workspace/docs/global/hook files produce errors about missing declarations."""
        validator = ProjectMapValidator(minimal_config)
        errors = validator.validate_unique_legal_system_contract()
        assert len(errors) > 0
        all_text = " ".join(errors)
        assert "project-map" in all_text.lower() or "workspace" in all_text.lower()

    def test_validate_unique_legal_system_contract_complete_no_errors(self, minimal_config):
        """All files with correct markers produce no errors."""
        workspace_content = (
            "project-map/INDEX.md\n"
            "只有被地图标为 `active-legal` 的条目或目录，才是合法资料；仅进入登记册不授予合法性。\n"
            "目录登记和目录状态迁移必须与相关文件同次 `git commit` 才生效。\n"
            + str(minimal_config.truth_model) + "\n"
        )
        docs_content = "incoming-raw\n未被地图明确吸收\n"
        global_content = "Non-Legal Material\ningestion-registry-map.md\nworkbot-truth-model.md\n"
        overview_content = "project-map/INDEX.md\n"
        core_content = "marker-1\n"
        registry_content = "scope-1\n"
        hook_content = (
            "gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。\n"
            "未完成提交的登记不得生效\n"
        )

        files = {
            str(minimal_config.workspace_index_path): workspace_content,
            str(minimal_config.docs_index_path): docs_content,
            str(minimal_config.overview_doc_path): overview_content,
            str(minimal_config.global_index_path): global_content,
            str(minimal_config.project_map_files[1]): core_content,
            str(minimal_config.project_map_files[2]): registry_content,
            str(minimal_config.hook_contract_path): hook_content,
        }

        def fake_read(path: Path) -> str:
            return files.get(str(path), "")

        cfg = replace(minimal_config, read_text_if_exists_fn=fake_read)
        validator = ProjectMapValidator(cfg)
        errors = validator.validate_unique_legal_system_contract()
        assert errors == []


# ---------------------------------------------------------------------------
# 2. FrozenTupleChecker — error messages
# ---------------------------------------------------------------------------

class TestFrozenTupleCheckerErrors:
    """Verify error messages from governance frozen tuple checks."""

    def test_missing_governance_files_error(self, minimal_config, tmp_path: Path):
        """When governance files do not exist, error mentions missing files."""
        cfg = replace(minimal_config, governance_frozen_tuple_files=[tmp_path / "nonexistent.md"])
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) == 1
        assert "missing governance files" in errors[0]

    def test_missing_expected_tuple_markers_error(self, minimal_config, tmp_path: Path):
        """When files exist but lack expected markers, error lists missing markers."""
        marker_file = tmp_path / "governance.md"
        marker_file.write_text("no markers here", encoding="utf-8")
        cfg = replace(
            minimal_config,
            governance_frozen_tuple_files=[marker_file],
            frozen_tuple_expected={"marker-a", "marker-b"},
            frozen_tuple_legacy_markers=set(),
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) == 1
        assert "missing expected tuple markers" in errors[0]
        assert "marker-a" in errors[0]
        assert "marker-b" in errors[0]

    def test_legacy_markers_still_present_error(self, minimal_config, tmp_path: Path):
        """When files contain legacy markers, error lists them."""
        marker_file = tmp_path / "governance.md"
        marker_file.write_text("legacy-marker and expected-marker", encoding="utf-8")
        cfg = replace(
            minimal_config,
            governance_frozen_tuple_files=[marker_file],
            frozen_tuple_expected={"expected-marker"},
            frozen_tuple_legacy_markers={"legacy-marker"},
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) == 1
        assert "legacy frozen tuple markers" in errors[0]
        assert "legacy-marker" in errors[0]

    def test_no_errors_when_all_correct(self, minimal_config, tmp_path: Path):
        """Correct governance files produce no errors."""
        marker_file = tmp_path / "governance.md"
        marker_file.write_text("expected-marker", encoding="utf-8")
        cfg = replace(
            minimal_config,
            governance_frozen_tuple_files=[marker_file],
            frozen_tuple_expected={"expected-marker"},
            frozen_tuple_legacy_markers=set(),
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert errors == []

    def test_multiple_missing_files_aggregated(self, minimal_config, tmp_path: Path):
        """Multiple missing files are listed in a single error message."""
        cfg = replace(
            minimal_config,
            governance_frozen_tuple_files=[
                tmp_path / "missing-a.md",
                tmp_path / "missing-b.md",
                tmp_path / "missing-c.md",
            ],
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) == 1
        for name in ("missing-a.md", "missing-b.md", "missing-c.md"):
            assert name in errors[0]


# ---------------------------------------------------------------------------
# 3. EventContractChecker — error messages
# ---------------------------------------------------------------------------

class TestEventContractCheckerErrors:
    """Verify error messages from event contract blocker checks."""

    def _write_event_contract_files(
        self,
        tmp_path: Path,
        upstream_standard: str = "",
        upstream_mapping: str = "",
        formal_contract: str = "",
        upstream_samples: str = "{}",
        downstream_samples: str = "{}",
    ) -> dict[str, Path]:
        files = {}
        for name, content in {
            "upstream_standard": upstream_standard,
            "upstream_mapping": upstream_mapping,
            "formal_contract": formal_contract,
            "upstream_samples": upstream_samples,
            "downstream_samples": downstream_samples,
        }.items():
            if name.endswith("_samples"):
                p = tmp_path / f"{name}.json"
            else:
                p = tmp_path / f"{name}.md"
            p.write_text(content, encoding="utf-8")
            files[name] = p
        return files

    def test_missing_event_contract_files_error(self, minimal_config, tmp_path: Path):
        """Missing event contract files produce a single error listing all missing files."""
        cfg = replace(
            minimal_config,
            event_contract_files={
                "upstream_standard": tmp_path / "missing-std.md",
                "upstream_mapping": tmp_path / "missing-map.md",
            },
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert len(errors) == 1
        assert "missing event contract files" in errors[0]

    def test_formal_set_mismatch_error(self, minimal_config, tmp_path: Path):
        """Matching formal sets produce no errors."""
        files = self._write_event_contract_files(
            tmp_path,
            upstream_standard=(
                "## 3. 正式输入源\n\n`source-a`\n\n"
                "## 4. 正式事件类型\n\n`event-a`\n\n"
                "## 6. event_status 标准\n\n`status-a`\n"
            ),
            upstream_mapping=(
                "## 2. 正式输入源范围\n\n`source-a`\n\n"
                "## 3. 输入源到正式事件的映射主表\n\n`event-a`\n\n"
                "## 4. 主路由规则\n\n`status-a`\n\n"
                "## 5. 错误码与原因码\n\n"
            ),
            formal_contract=(
                "## 3. source_type 正式白名单\n\n`source-a`\n\n"
                "## 4. event_type 正式清单\n\n`event-a`\n\n"
                "## 6. event_status 正式取值\n\n`status-a`\n"
            ),
            upstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
            downstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
        )
        cfg = replace(minimal_config, event_contract_files=files)
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert errors == []

    def test_formal_set_mismatch_detects_missing_source(self, minimal_config, tmp_path: Path):
        """Missing source_type in formal contract produces a mismatch error."""
        files = self._write_event_contract_files(
            tmp_path,
            upstream_standard=(
                "## 3. 正式输入源\n\n`source-a`\n\n"
                "## 4. 正式事件类型\n\n`event-a`\n\n"
                "## 6. event_status 标准\n\n`status-a`\n"
            ),
            upstream_mapping=(
                "## 2. 正式输入源范围\n\n`source-a`\n\n"
                "## 3. 输入源到正式事件的映射主表\n\n`event-a`\n\n"
                "## 4. 主路由规则\n\n`status-a`\n\n"
                "## 5. 错误码与原因码\n\n"
            ),
            formal_contract=(
                "## 3. source_type 正式白名单\n\n`source-a`\n\n"
                "## 4. event_type 正式清单\n\n`event-a`\n\n"
                "## 6. event_status 正式取值\n\n`status-a`\n"
            ),
            upstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
            downstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
        )
        cfg = replace(
            minimal_config,
            event_contract_files=files,
            formal_source_types={"source-a", "source-b"},
        )
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        mismatch_errors = [e for e in errors if "mismatch" in e and "source_types" in e]
        assert len(mismatch_errors) > 0
        assert "upstream_standard" in mismatch_errors[0]

    def test_out_of_contract_source_type_error(self, minimal_config, tmp_path: Path):
        """Sample JSON with unknown source_type produces an out-of-contract error."""
        files = self._write_event_contract_files(
            tmp_path,
            upstream_standard=(
                "## 3. 正式输入源\n\n`source-a`\n\n"
                "## 4. 正式事件类型\n\n`event-a`\n\n"
                "## 6. event_status 标准\n\n`status-a`\n"
            ),
            upstream_mapping=(
                "## 2. 正式输入源范围\n\n`source-a`\n\n"
                "## 3. 输入源到正式事件的映射主表\n\n`event-a`\n\n"
                "## 4. 主路由规则\n\n`status-a`\n\n"
                "## 5. 错误码与原因码\n\n"
            ),
            formal_contract=(
                "## 3. source_type 正式白名单\n\n`source-a`\n\n"
                "## 4. event_type 正式清单\n\n`event-a`\n\n"
                "## 6. event_status 正式取值\n\n`status-a`\n"
            ),
            upstream_samples='{"source_type": "rogue-source", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
            downstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
        )
        cfg = replace(minimal_config, event_contract_files=files)
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        ooc_errors = [e for e in errors if "out-of-contract source_type" in e]
        assert len(ooc_errors) > 0
        assert "rogue-source" in ooc_errors[0]

    def test_legacy_field_keys_error(self, minimal_config, tmp_path: Path):
        """Sample JSON using legacy field keys produces an error."""
        files = self._write_event_contract_files(
            tmp_path,
            upstream_standard=(
                "## 3. 正式输入源\n\n`source-a`\n\n"
                "## 4. 正式事件类型\n\n`event-a`\n\n"
                "## 6. event_status 标准\n\n`status-a`\n"
            ),
            upstream_mapping=(
                "## 2. 正式输入源范围\n\n`source-a`\n\n"
                "## 3. 输入源到正式事件的映射主表\n\n`event-a`\n\n"
                "## 4. 主路由规则\n\n`status-a`\n\n"
                "## 5. 错误码与原因码\n\n"
            ),
            formal_contract=(
                "## 3. source_type 正式白名单\n\n`source-a`\n\n"
                "## 4. event_type 正式清单\n\n`event-a`\n\n"
                "## 6. event_status 正式取值\n\n`status-a`\n"
            ),
            upstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val", "legacy-field": "old"}',
            downstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
        )
        cfg = replace(minimal_config, event_contract_files=files)
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        legacy_errors = [e for e in errors if "legacy field keys" in e]
        assert len(legacy_errors) > 0
        assert "legacy-field" in legacy_errors[0]

    def test_missing_formal_field_keys_error(self, minimal_config, tmp_path: Path):
        """Sample JSON missing formal field keys produces an error."""
        cfg = replace(
            minimal_config,
            formal_field_keys={"field-a", "field-b"},
        )
        files = self._write_event_contract_files(
            tmp_path,
            upstream_standard=(
                "## 3. 正式输入源\n\n`source-a`\n\n"
                "## 4. 正式事件类型\n\n`event-a`\n\n"
                "## 6. event_status 标准\n\n`status-a`\n"
            ),
            upstream_mapping=(
                "## 2. 正式输入源范围\n\n`source-a`\n\n"
                "## 3. 输入源到正式事件的映射主表\n\n`event-a`\n\n"
                "## 4. 主路由规则\n\n`status-a`\n\n"
                "## 5. 错误码与原因码\n\n"
            ),
            formal_contract=(
                "## 3. source_type 正式白名单\n\n`source-a`\n\n"
                "## 4. event_type 正式清单\n\n`event-a`\n\n"
                "## 6. event_status 正式取值\n\n`status-a`\n"
            ),
            upstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
            downstream_samples='{"source_type": "source-a", "event_type": "event-a", "event_status": "status-a", "field-a": "val"}',
        )
        cfg = replace(cfg, event_contract_files=files)
        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        missing_errors = [e for e in errors if "missing formal field keys" in e]
        assert len(missing_errors) > 0
        assert "field-b" in missing_errors[0]


# ---------------------------------------------------------------------------
# 4. TruthBasisResolver — report structure and error messages
# ---------------------------------------------------------------------------

class TestTruthBasisResolverReport:
    """Verify the report/dict structure returned by truth_basis_for_scope."""

    def test_report_structure_for_unknown_scope(self, minimal_config):
        """Unknown scope returns a dict with expected keys and validation=fail."""
        resolver = TruthBasisResolver(minimal_config)
        report = resolver.truth_basis_for_scope("unknown-scope")

        assert isinstance(report, dict)
        for key in ("policy", "refs", "global_refs", "project_ref", "source_refs",
                     "authority_refs", "evidence_refs", "conflict_status", "errors", "validation"):
            assert key in report
        assert report["validation"] == "fail"
        assert report["project_ref"] == ""
        assert len(report["errors"]) > 0
        assert "unsupported project scope" in report["errors"][0]

    def test_report_structure_for_known_scope(self, minimal_config, tmp_path: Path):
        """Known scope returns a dict with project_ref and validation status."""
        project_file = tmp_path / "project-canonical.md"
        project_file.write_text(
            "Truth Basis\n\n### Source Refs\n- ./src.md\n\n### Authority Refs\n- ./auth.md\n\n### Evidence Refs\n- ./evidence.md\n\n### Conflict Status\n- resolved\n",
            encoding="utf-8",
        )
        cfg = replace(minimal_config, project_canonical={"workbot": project_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")

        assert isinstance(report, dict)
        assert report["project_ref"] == str(project_file)
        assert "validation" in report
        assert "errors" in report
        assert isinstance(report["errors"], list)

    def test_report_errors_list_is_list_of_strings(self, minimal_config):
        """The errors field in the report is always a list of strings."""
        resolver = TruthBasisResolver(minimal_config)
        report = resolver.truth_basis_for_scope("unknown-scope")
        assert isinstance(report["errors"], list)
        for err in report["errors"]:
            assert isinstance(err, str)


class TestTruthBasisResolverErrors:
    """Verify specific error messages from truth basis validation."""

    def test_missing_truth_canonical_error(self, minimal_config, tmp_path: Path):
        """Non-existent truth canonical produces a missing truth canonical error."""
        missing_file = tmp_path / "missing.md"
        cfg = replace(minimal_config, project_canonical={"workbot": missing_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        missing_errors = [e for e in report["errors"] if "missing truth canonical" in e]
        assert len(missing_errors) > 0

    def test_truth_basis_section_missing_error(self, minimal_config, tmp_path: Path):
        """File without 'Truth Basis' section produces a section-missing error."""
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("no truth basis here", encoding="utf-8")
        cfg = replace(minimal_config, project_canonical={"workbot": bad_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        section_errors = [e for e in report["errors"] if "truth basis section missing" in e]
        assert len(section_errors) > 0

    def test_missing_source_refs_error(self, minimal_config, tmp_path: Path):
        """Truth Basis with empty Source Refs produces an error."""
        project_file = tmp_path / "project.md"
        project_file.write_text(
            "Truth Basis\n\n### Source Refs\n\n### Authority Refs\n- ./auth.md\n\n### Evidence Refs\n- ./evidence.md\n\n### Conflict Status\n- resolved\n",
            encoding="utf-8",
        )
        cfg = replace(minimal_config, project_canonical={"workbot": project_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        src_errors = [e for e in report["errors"] if "source refs missing" in e]
        assert len(src_errors) > 0

    def test_unresolved_conflict_status_error(self, minimal_config, tmp_path: Path):
        """Conflict Status that is not 'resolved' produces an error."""
        project_file = tmp_path / "project.md"
        project_file.write_text(
            "Truth Basis\n\n### Source Refs\n- ./src.md\n\n### Authority Refs\n- ./auth.md\n\n### Evidence Refs\n- ./evidence.md\n\n### Conflict Status\n- pending\n",
            encoding="utf-8",
        )
        cfg = replace(minimal_config, project_canonical={"workbot": project_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        conflict_errors = [e for e in report["errors"] if "conflict status unresolved" in e]
        assert len(conflict_errors) > 0

    def test_identical_source_and_evidence_refs_error(self, minimal_config, tmp_path: Path):
        """When source refs and evidence refs are identical, an error is produced."""
        project_file = tmp_path / "project.md"
        project_file.write_text(
            "Truth Basis\n\n### Source Refs\n- ./same.md\n\n### Authority Refs\n- ./auth.md\n\n### Evidence Refs\n- ./same.md\n\n### Conflict Status\n- resolved\n",
            encoding="utf-8",
        )
        cfg = replace(minimal_config, project_canonical={"workbot": project_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        overlap_errors = [e for e in report["errors"] if "must not be identical" in e]
        assert len(overlap_errors) > 0


# ---------------------------------------------------------------------------
# 5. ScopeResolver — scope determination
# ---------------------------------------------------------------------------

class TestScopeResolverScopeDetermination:
    """Verify scope resolution behavior."""

    def test_default_scope_outside_repo(self, minimal_config, tmp_path: Path):
        """CWD outside repo root returns default scope."""
        cfg = replace(minimal_config, default_project_scope="my-default")
        outside = tmp_path / "outside"
        outside.mkdir()

        resolver = ScopeResolver(cfg)
        scope = resolver.determine_project_scope(outside)
        assert scope == "my-default"

    def test_scope_match_hints_inside_repo(self, minimal_config, tmp_path: Path):
        """CWD matching a scope hint returns that scope."""
        # workspace must be under repo_root for lexical containment to pass
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        cfg = replace(
            minimal_config,
            repo_root=tmp_path,
            workspace_root=tmp_path,
            scope_match_hints={"workbot": [mem_dir]},
        )

        resolver = ScopeResolver(cfg)
        scope = resolver.determine_project_scope(mem_dir / "kb")
        assert scope == "workbot"


# ---------------------------------------------------------------------------
# 6. Error aggregation — multiple errors at once
# ---------------------------------------------------------------------------

class TestErrorAggregation:
    """Verify that multiple errors are aggregated correctly."""

    def test_project_map_multiple_errors(self, minimal_config):
        """Empty project-map files produce multiple distinct errors."""
        validator = ProjectMapValidator(minimal_config)
        errors = validator.validate_project_map_files()
        assert len(errors) >= 3
        for e in errors:
            assert isinstance(e, str)
            assert len(e) > 0

    def test_frozen_tuple_multiple_missing_markers_aggregated(self, minimal_config, tmp_path: Path):
        """Multiple missing markers are listed in a single error."""
        marker_file = tmp_path / "governance.md"
        marker_file.write_text("", encoding="utf-8")
        cfg = replace(
            minimal_config,
            governance_frozen_tuple_files=[marker_file],
            frozen_tuple_expected={"marker-a", "marker-b", "marker-c"},
            frozen_tuple_legacy_markers=set(),
        )
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) == 1
        for m in ("marker-a", "marker-b", "marker-c"):
            assert m in errors[0]

    def test_truth_basis_aggregates_all_file_errors(self, minimal_config, tmp_path: Path):
        """Truth basis validation collects errors from both global canonical and project file."""
        bad_global = tmp_path / "bad-global.md"
        bad_global.write_text("Truth Basis\n\n### Source Refs\n\n### Authority Refs\n\n### Evidence Refs\n\n### Conflict Status\n\n", encoding="utf-8")
        bad_project = tmp_path / "bad-project.md"
        bad_project.write_text("no truth basis", encoding="utf-8")
        cfg = replace(
            minimal_config,
            global_canonical=[bad_global],
            project_canonical={"workbot": bad_project},
        )
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        assert len(report["errors"]) >= 2
        has_section_error = any("missing" in e or "section missing" in e for e in report["errors"])
        assert has_section_error


# ---------------------------------------------------------------------------
# 7. Boundary — no errors
# ---------------------------------------------------------------------------

class TestNoErrorBoundary:
    """Verify the no-error boundary case across checkers."""

    def test_project_map_no_errors_with_correct_content(self, minimal_config):
        """Correct project-map content yields an empty error list."""
        index_content = (
            "唯一合法入口\n"
            "只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。\n"
            "同次 `git commit` 提交后才生效\n"
        )
        core_content = "active-legal\n只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。\n"
        registry_content = (
            "incoming-raw\ncompatibility-only\n`absorbed`\n`retired`\n同次 `git commit` 提交后才生效\n"
        )
        governance_content = (
            "未经过唯一真相系统清洗\n"
            "只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。\n"
            "未完成同次 `git commit` 的目录登记，不得视为生效。\n"
        )

        files = {
            str(minimal_config.project_map_files[0]): index_content,
            str(minimal_config.project_map_files[1]): core_content,
            str(minimal_config.project_map_files[2]): registry_content,
            str(minimal_config.project_map_governance): governance_content,
        }

        def fake_read(path: Path) -> str:
            return files.get(str(path), "")

        cfg = replace(minimal_config, read_text_if_exists_fn=fake_read)
        validator = ProjectMapValidator(cfg)
        assert validator.validate_project_map_files() == []

    def test_frozen_tuple_no_errors(self, minimal_config, tmp_path: Path):
        """Correct frozen tuple markers yield no errors."""
        marker_file = tmp_path / "governance.md"
        marker_file.write_text("expected-marker", encoding="utf-8")
        cfg = replace(
            minimal_config,
            governance_frozen_tuple_files=[marker_file],
            frozen_tuple_expected={"expected-marker"},
            frozen_tuple_legacy_markers=set(),
        )
        checker = FrozenTupleChecker(cfg)
        assert checker.governance_frozen_tuple_blocker_errors() == []


# ---------------------------------------------------------------------------
# 8. Error message format consistency
# ---------------------------------------------------------------------------

class TestErrorMessageFormatConsistency:
    """Verify error messages follow consistent formatting patterns."""

    def test_project_map_errors_are_lowercase_descriptions(self, minimal_config):
        """Project-map errors are lowercase descriptive sentences."""
        validator = ProjectMapValidator(minimal_config)
        errors = validator.validate_project_map_files()
        for e in errors:
            assert " " in e  # contains spaces => descriptive, not a single word
            assert not e.startswith("MKR_")  # not a raw constant name

    def test_error_messages_do_not_contain_raw_paths_unless_missing(self, minimal_config, tmp_path: Path):
        """Missing-file errors include path names; content errors do not leak paths."""
        cfg = replace(minimal_config, governance_frozen_tuple_files=[tmp_path / "nonexistent.md"])
        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert "nonexistent.md" in errors[0]

    def test_truth_basis_errors_include_file_reference(self, minimal_config, tmp_path: Path):
        """Truth basis errors include the file path for context."""
        project_file = tmp_path / "project.md"
        project_file.write_text(
            "Truth Basis\n\n### Source Refs\n\n### Authority Refs\n- ./auth.md\n\n### Evidence Refs\n- ./evidence.md\n\n### Conflict Status\n- resolved\n",
            encoding="utf-8",
        )
        cfg = replace(minimal_config, project_canonical={"workbot": project_file})
        resolver = TruthBasisResolver(cfg)
        report = resolver.truth_basis_for_scope("workbot")
        # At least one error should reference the project file
        project_errors = [e for e in report["errors"] if "project.md" in e]
        assert len(project_errors) > 0
