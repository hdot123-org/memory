#!/usr/bin/env python3
"""Smoke and main-path tests for workspace.tools.business_policy_checks.

Covers:
- Module importability
- Class instantiation
- Core API callability with minimal/empty inputs
- Failure paths: None / empty / nonexistent paths
- Boundary inputs: oversized strings / special characters
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------


class TestModuleImport:
    """Verify the module can be imported and all public symbols are present."""

    def test_import_module(self):
        import memory_core.tools.business_policy_checks as mpc
        assert mpc is not None

    def test_import_classes(self):
        from memory_core.tools.business_policy_checks import (
            EventContractChecker,
            FrozenTupleChecker,
            LegalContractChecker,
            ProjectMapValidator,
            ScopeResolver,
            TruthBasisResolver,
        )
        assert ProjectMapValidator is not None
        assert LegalContractChecker is not None
        assert FrozenTupleChecker is not None
        assert EventContractChecker is not None
        assert TruthBasisResolver is not None
        assert ScopeResolver is not None

    def test_import_helpers(self):
        from memory_core.tools.business_policy_checks import (
            _existing_paths,
            _json_object_keys,
            _json_string_values,
            _markdown_code_tokens,
            _path_is_under,
            _path_is_under_lexical,
            _section_body,
            _section_bullets,
        )
        assert callable(_path_is_under)
        assert callable(_path_is_under_lexical)
        assert callable(_section_bullets)
        assert callable(_section_body)
        assert callable(_markdown_code_tokens)
        assert callable(_json_string_values)
        assert callable(_json_object_keys)
        assert callable(_existing_paths)


# ---------------------------------------------------------------------------
# Shared fixture: minimal GatewayBusinessPolicyConfig
# ---------------------------------------------------------------------------

def _noop_read_text(path: Path) -> str:
    """Default read_text_if_exists that returns empty string for missing files."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


@pytest.fixture
def config(tmp_path: Path) -> Any:
    """Build a minimal GatewayBusinessPolicyConfig backed by tmp_path."""
    from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig

    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    project_map = repo / "project-map"
    project_map.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    for subdir in [
        "memory", "memory/kb", "memory/kb/global",
        "memory/kb/global/projects", "memory/kb/projects",
        "docs", "projects", "artifacts", "tools",
        "memory/log", "memory/system",
    ]:
        (workspace / subdir).mkdir(exist_ok=True)
    (repo / "app").mkdir(exist_ok=True)
    (repo / "agents").mkdir(exist_ok=True)

    return GatewayBusinessPolicyConfig(
        repo_root=repo,
        workspace_root=workspace,
        project_map_root=project_map,
        project_map_files=[
            project_map / "INDEX.md",
            project_map / "legal-core-map.md",
            project_map / "ingestion-registry-map.md",
        ],
        project_map_governance=project_map / "governance.md",
        truth_model=project_map / "legal-core-map.md",
        global_canonical=[repo / "AGENTS.md"],
        authority_allowed_paths=set(),
        lower_evidence_roots=[workspace / "memory" / "kb" / "projects"],
        legal_core_markers=["active-legal"],
        required_registry_scopes=["incoming-raw"],
        project_canonical={"test-scope": project_map / "legal-core-map.md"},
        project_runtime_root={"test-scope": workspace / "projects"},
        project_doc_refs={},
        default_decision_refs=[],
        project_decision_refs={},
        default_lesson_refs=[],
        project_lesson_refs={},
        governance_frozen_tuple_files=[],
        event_contract_files={},
        frozen_tuple_expected=set(),
        frozen_tuple_legacy_markers=set(),
        formal_source_types=set(),
        formal_event_types=set(),
        formal_event_statuses=set(),
        formal_field_keys=set(),
        legacy_field_keys=set(),
        required_canonical=[],
        workspace_index_path=workspace / "INDEX.md",
        docs_index_path=workspace / "docs" / "INDEX.md",
        overview_doc_path=workspace / "docs" / "overview.md",
        global_index_path=repo / "AGENTS.md",
        hook_contract_path=project_map / "hook-contract.md",
        default_project_scope="test-scope",
        scope_match_hints={},
        read_text_if_exists_fn=_noop_read_text,
        policy_pack_path=None,
    )


# ---------------------------------------------------------------------------
# Test: ProjectMapValidator
# ---------------------------------------------------------------------------


class TestProjectMapValidator:
    def test_instantiation(self, config):
        from memory_core.tools.business_policy_checks import ProjectMapValidator
        v = ProjectMapValidator(config)
        assert v is not None
        assert v._config is config

    def test_validate_project_map_files_missing(self, config):
        from memory_core.tools.business_policy_checks import ProjectMapValidator
        v = ProjectMapValidator(config)
        errors = v.validate_project_map_files()
        assert isinstance(errors, list)
        assert len(errors) > 0

    def test_validate_unique_legal_system_contract_missing(self, config):
        from memory_core.tools.business_policy_checks import ProjectMapValidator
        v = ProjectMapValidator(config)
        errors = v.validate_unique_legal_system_contract()
        assert isinstance(errors, list)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Test: LegalContractChecker
# ---------------------------------------------------------------------------


class TestLegalContractChecker:
    def test_instantiation(self, config):
        from memory_core.tools.business_policy_checks import LegalContractChecker
        c = LegalContractChecker(config)
        assert c is not None

    def test_validate_delegates(self, config):
        from memory_core.tools.business_policy_checks import LegalContractChecker
        c = LegalContractChecker(config)
        errors = c.validate_unique_legal_system_contract()
        assert isinstance(errors, list)


# ---------------------------------------------------------------------------
# Test: FrozenTupleChecker
# ---------------------------------------------------------------------------


class TestFrozenTupleChecker:
    def test_instantiation(self, config):
        from memory_core.tools.business_policy_checks import FrozenTupleChecker
        c = FrozenTupleChecker(config)
        assert c is not None

    def test_governance_empty_files_list(self, config):
        cfg = dataclasses.replace(
            config,
            governance_frozen_tuple_files=[],
            frozen_tuple_expected=set(),
            frozen_tuple_legacy_markers=set(),
        )
        from memory_core.tools.business_policy_checks import FrozenTupleChecker
        c = FrozenTupleChecker(cfg)
        errors = c.governance_frozen_tuple_blocker_errors()
        assert errors == []

    def test_governance_missing_files(self, config):
        cfg = dataclasses.replace(
            config,
            governance_frozen_tuple_files=[config.repo_root / "nonexistent.md"],
        )
        from memory_core.tools.business_policy_checks import FrozenTupleChecker
        c = FrozenTupleChecker(cfg)
        errors = c.governance_frozen_tuple_blocker_errors()
        assert len(errors) > 0
        assert "missing" in errors[0].lower()


# ---------------------------------------------------------------------------
# Test: EventContractChecker
# ---------------------------------------------------------------------------


class TestEventContractChecker:
    def test_instantiation(self, config):
        from memory_core.tools.business_policy_checks import EventContractChecker
        c = EventContractChecker(config)
        assert c is not None

    def test_event_contract_missing_files(self, config):
        from memory_core.tools.business_policy_checks import EventContractChecker
        cfg = dataclasses.replace(
            config,
            event_contract_files={
                "upstream_standard": config.repo_root / "missing1.md",
                "upstream_mapping": config.repo_root / "missing2.md",
            },
        )
        c = EventContractChecker(cfg)
        errors = c.event_contract_blocker_errors()
        assert len(errors) > 0
        assert "missing" in errors[0].lower()

    def test_event_contract_complete_matching(self, config, tmp_path):
        """Create all required files with matching content — zero errors."""
        from memory_core.tools.business_policy_checks import EventContractChecker

        cfg = dataclasses.replace(
            config,
            formal_source_types={"git-commit", "cli-run"},
            formal_event_types={"event.start", "event.end"},
            formal_event_statuses={"ok", "fail"},
            formal_field_keys={"source_type"},
            legacy_field_keys={"old_type"},
        )

        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()

        (doc_dir / "upstream_standard.md").write_text(
            "## 3. 正式输入源\n- `git-commit`\n- `cli-run`\n\n"
            "## 4. 正式事件类型\n- `event.start`\n- `event.end`\n\n"
            "## 6. event_status 标准\n- `ok`\n- `fail`\n",
            encoding="utf-8",
        )
        (doc_dir / "upstream_mapping.md").write_text(
            "## 2. 正式输入源范围\n- `git-commit`\n- `cli-run`\n\n"
            "## 3. 输入源到正式事件的映射主表\n- `event.start`\n- `event.end`\n\n"
            "## 4. 主路由规则\n- `ok`\n\n"
            "## 5. 错误码与原因码\n- `fail`\n",
            encoding="utf-8",
        )
        (doc_dir / "formal_contract.md").write_text(
            "## 3. source_type 正式白名单\n- `git-commit`\n- `cli-run`\n\n"
            "## 4. event_type 正式清单\n- `event.start`\n- `event.end`\n\n"
            "## 6. event_status 正式取值\n- `ok`\n- `fail`\n",
            encoding="utf-8",
        )
        (doc_dir / "upstream_samples.json").write_text(
            '{"source_type": "git-commit", "event_type": "event.start", "event_status": "ok"}\n'
            '{"source_type": "cli-run", "event_type": "event.end", "event_status": "fail"}\n',
            encoding="utf-8",
        )
        (doc_dir / "downstream_samples.json").write_text(
            '{"source_type": "git-commit", "event_type": "event.start", "event_status": "ok"}\n',
            encoding="utf-8",
        )

        cfg = dataclasses.replace(
            cfg,
            event_contract_files={
                "upstream_standard": doc_dir / "upstream_standard.md",
                "upstream_mapping": doc_dir / "upstream_mapping.md",
                "formal_contract": doc_dir / "formal_contract.md",
                "upstream_samples": doc_dir / "upstream_samples.json",
                "downstream_samples": doc_dir / "downstream_samples.json",
            },
        )
        c = EventContractChecker(cfg)
        errors = c.event_contract_blocker_errors()
        assert isinstance(errors, list)
        assert errors == []


# ---------------------------------------------------------------------------
# Test: TruthBasisResolver
# ---------------------------------------------------------------------------


class TestTruthBasisResolver:
    def test_instantiation(self, config):
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        r = TruthBasisResolver(config)
        assert r is not None

    def test_get_project_canonical(self, config):
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        r = TruthBasisResolver(config)
        result = r.get_project_canonical()
        assert isinstance(result, dict)
        assert "test-scope" in result

    def test_truth_basis_unknown_scope(self, config):
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        r = TruthBasisResolver(config)
        result = r.truth_basis_for_scope("nonexistent-scope")
        assert isinstance(result, dict)
        assert result["validation"] == "fail"
        assert len(result["errors"]) > 0

    def test_path_classification(self, config):
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        r = TruthBasisResolver(config)
        for path in [
            config.repo_root / "AGENTS.md",
            config.workspace_root / "INDEX.md",
            config.workspace_root / "tools" / "foo.py",
        ]:
            category = r._classify_truth_ref(path)
            assert isinstance(category, str)
            assert len(category) > 0


# ---------------------------------------------------------------------------
# Test: ScopeResolver
# ---------------------------------------------------------------------------


class TestScopeResolver:
    def test_instantiation(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        assert r is not None

    def test_instantiation_with_override_path(self, config, tmp_path):
        override = tmp_path / "scope.json"
        override.write_text("{}", encoding="utf-8")
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config, scope_config_path=override)
        assert r is not None

    def test_determine_project_scope_default(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        scope = r.determine_project_scope(config.repo_root / "unknown-dir")
        assert scope == config.default_project_scope

    def test_determine_project_scope_outside_repo(self, config, tmp_path):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        scope = r.determine_project_scope(tmp_path / "outside-repo")
        assert scope == config.default_project_scope

    def test_get_project_canonical(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        result = r.get_project_canonical()
        assert isinstance(result, dict)

    def test_get_project_runtime_root(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        result = r.get_project_runtime_root()
        assert isinstance(result, dict)

    def test_get_required_canonical(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        result = r.get_required_canonical()
        assert isinstance(result, list)

    def test_get_global_canonical(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        result = r.get_global_canonical()
        assert isinstance(result, list)

    def test_project_map_refs(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        refs = r.project_map_refs()
        assert isinstance(refs, list)

    def test_refs_for_scope(self, config):
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config)
        assert isinstance(r.decision_refs_for_scope("test-scope"), list)
        assert isinstance(r.lesson_refs_for_scope("test-scope"), list)
        assert isinstance(r.docs_refs_for_scope("test-scope"), list)

    def test_scope_override_valid_json(self, config, tmp_path):
        override = tmp_path / "scope.json"
        override.write_text(json.dumps({
            "project_canonical": {"custom-scope": "custom.md"},
            "project_runtime_root": {"custom-scope": "runtime/"},
        }), encoding="utf-8")
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config, scope_config_path=override)
        canonical = r.get_project_canonical()
        assert "custom-scope" in canonical
        runtime = r.get_project_runtime_root()
        assert "custom-scope" in runtime

    def test_scope_override_invalid_json(self, config, tmp_path):
        override = tmp_path / "scope.json"
        override.write_text("not json", encoding="utf-8")
        from memory_core.tools.business_policy_checks import ScopeResolver
        r = ScopeResolver(config, scope_config_path=override)
        assert r._scope_overrides == {}

    def test_scope_override_env_var(self, config, tmp_path):
        from memory_core.tools.business_policy_checks import ScopeResolver
        override = tmp_path / "scope.json"
        override.write_text("{}", encoding="utf-8")
        old = os.environ.get(ScopeResolver.SCOPE_CONFIG_PATH_ENV)
        try:
            os.environ[ScopeResolver.SCOPE_CONFIG_PATH_ENV] = str(override)
            r = ScopeResolver(config)
            assert r._scope_config_path == override
        finally:
            if old is None:
                os.environ.pop(ScopeResolver.SCOPE_CONFIG_PATH_ENV, None)
            else:
                os.environ[ScopeResolver.SCOPE_CONFIG_PATH_ENV] = old


# ---------------------------------------------------------------------------
# Test: Helper functions
# ---------------------------------------------------------------------------


class TestHelperPathIsUnder:
    def test_path_under_root(self, tmp_path):
        from memory_core.tools.business_policy_checks import _path_is_under
        root = tmp_path / "root"
        root.mkdir()
        child = root / "child" / "file.txt"
        child.parent.mkdir(parents=True)
        child.touch()
        assert _path_is_under(child, root) is True

    def test_path_not_under_root(self, tmp_path):
        from memory_core.tools.business_policy_checks import _path_is_under
        root = tmp_path / "root"
        other = tmp_path / "other"
        root.mkdir()
        other.mkdir()
        file_in_other = other / "file.txt"
        file_in_other.touch()
        assert _path_is_under(file_in_other, root) is False

    def test_lexical_path_under(self, tmp_path):
        from memory_core.tools.business_policy_checks import _path_is_under_lexical
        root = tmp_path / "root"
        root.mkdir()
        child = root / "sub"
        child.mkdir()
        assert _path_is_under_lexical(child, root) is True

    def test_lexical_path_not_under(self, tmp_path):
        from memory_core.tools.business_policy_checks import _path_is_under_lexical
        root = tmp_path / "root"
        other = tmp_path / "other"
        root.mkdir()
        other.mkdir()
        assert _path_is_under_lexical(other, root) is False


class TestHelperSectionParsing:
    def test_section_bullets_basic(self):
        from memory_core.tools.business_policy_checks import _section_bullets
        text = "Some intro\n## My Section\n- item1\n- item2\n## Next\n"
        result = _section_bullets(text, "## My Section")
        assert result == ["item1", "item2"]

    def test_section_bullets_empty(self):
        from memory_core.tools.business_policy_checks import _section_bullets
        result = _section_bullets("no heading here", "## Missing")
        assert result == []

    def test_section_body_basic(self):
        from memory_core.tools.business_policy_checks import _section_body
        text = "intro\n## My Section\nbody line 1\nbody line 2\n## Next\n"
        result = _section_body(text, "## My Section")
        assert "body line 1" in result
        assert "body line 2" in result

    def test_section_body_missing_heading(self):
        from memory_core.tools.business_policy_checks import _section_body
        result = _section_body("no heading", "## Missing")
        assert result == ""


class TestHelperJsonParsing:
    def test_markdown_code_tokens(self):
        from memory_core.tools.business_policy_checks import _markdown_code_tokens
        result = _markdown_code_tokens("use `foo` and `bar`")
        assert result == {"foo", "bar"}

    def test_markdown_code_tokens_empty(self):
        from memory_core.tools.business_policy_checks import _markdown_code_tokens
        assert _markdown_code_tokens("") == set()

    def test_json_string_values(self):
        from memory_core.tools.business_policy_checks import _json_string_values
        text = '{"key": "val1"} {"key": "val2"}'
        result = _json_string_values(text, "key")
        assert result == {"val1", "val2"}

    def test_json_object_keys(self):
        from memory_core.tools.business_policy_checks import _json_object_keys
        text = '{"a": 1, "b": 2}'
        result = _json_object_keys(text)
        assert result == {"a", "b"}


class TestHelperExistingPaths:
    def test_existing_paths_filters(self, tmp_path):
        from memory_core.tools.business_policy_checks import _existing_paths
        existing = tmp_path / "exists.txt"
        existing.touch()
        missing = tmp_path / "missing.txt"
        result = _existing_paths([existing, missing])
        assert result == [str(existing)]

    def test_existing_paths_empty_list(self):
        from memory_core.tools.business_policy_checks import _existing_paths
        assert _existing_paths([]) == []


# ---------------------------------------------------------------------------
# Failure / boundary paths
# ---------------------------------------------------------------------------


class TestFailurePaths:
    """Tests that exercise empty / nonexistent inputs."""

    def test_section_bullets_empty_text(self):
        from memory_core.tools.business_policy_checks import _section_bullets
        result = _section_bullets("", "## H")
        assert result == []

    def test_section_body_empty_text(self):
        from memory_core.tools.business_policy_checks import _section_body
        result = _section_body("", "## H")
        assert result == ""

    def test_markdown_code_tokens_special_chars(self):
        from memory_core.tools.business_policy_checks import _markdown_code_tokens
        text = "`hello world!@#$%^&*()`"
        result = _markdown_code_tokens(text)
        assert "hello world!@#$%^&*()" in result

    def test_json_string_values_special_chars(self):
        from memory_core.tools.business_policy_checks import _json_string_values
        text = '{"k": "v@#$$%"}'
        result = _json_string_values(text, "k")
        assert "v@#$$%" in result

    def test_project_map_validator_empty_config_paths(self, config):
        from memory_core.tools.business_policy_checks import ProjectMapValidator
        v = ProjectMapValidator(config)
        errors = v.validate_project_map_files()
        assert isinstance(errors, list)

    def test_frozen_tuple_checker_empty_markers(self, config):
        cfg = dataclasses.replace(
            config,
            governance_frozen_tuple_files=[],
            frozen_tuple_expected=set(),
            frozen_tuple_legacy_markers=set(),
        )
        from memory_core.tools.business_policy_checks import FrozenTupleChecker
        c = FrozenTupleChecker(cfg)
        assert c.governance_frozen_tuple_blocker_errors() == []


class TestBoundaryInputs:
    """Tests with oversized or unusual inputs."""

    def test_section_bullets_very_long_text(self):
        from memory_core.tools.business_policy_checks import _section_bullets
        long_text = "x" * 100_000 + "\n## H\n- item\n"
        result = _section_bullets(long_text, "## H")
        assert result == ["item"]

    def test_markdown_code_tokens_very_long_text(self):
        from memory_core.tools.business_policy_checks import _markdown_code_tokens
        long_text = " ".join(f"`tok{i}`" for i in range(1000))
        result = _markdown_code_tokens(long_text)
        assert len(result) == 1000

    def test_path_is_under_very_deep_path(self, tmp_path):
        from memory_core.tools.business_policy_checks import _path_is_under
        root = tmp_path / "root"
        deep = root
        for _ in range(50):
            deep = deep / "d"
        deep.mkdir(parents=True)
        assert _path_is_under(deep, root) is True

    def test_event_contract_checker_empty_sets(self, config, tmp_path):
        """EventContractChecker with empty formal sets and minimal files."""
        from memory_core.tools.business_policy_checks import EventContractChecker
        doc_dir = tmp_path / "evt"
        doc_dir.mkdir()
        # Create minimal files so the checker runs; empty sets mean everything matches
        for name in ["upstream_standard", "upstream_mapping", "formal_contract"]:
            (doc_dir / f"{name}.md").write_text("", encoding="utf-8")
        for name in ["upstream_samples", "downstream_samples"]:
            (doc_dir / f"{name}.json").write_text("", encoding="utf-8")
        cfg = dataclasses.replace(
            config,
            formal_source_types=set(),
            formal_event_types=set(),
            formal_event_statuses=set(),
            formal_field_keys=set(),
            legacy_field_keys=set(),
            event_contract_files={
                "upstream_standard": doc_dir / "upstream_standard.md",
                "upstream_mapping": doc_dir / "upstream_mapping.md",
                "formal_contract": doc_dir / "formal_contract.md",
                "upstream_samples": doc_dir / "upstream_samples.json",
                "downstream_samples": doc_dir / "downstream_samples.json",
            },
        )
        c = EventContractChecker(cfg)
        errors = c.event_contract_blocker_errors()
        assert isinstance(errors, list)

    def test_truth_basis_resolver_no_files_on_disk(self, config):
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        r = TruthBasisResolver(config)
        result = r.truth_basis_for_scope("test-scope")
        assert isinstance(result, dict)
        assert "errors" in result
        assert isinstance(result["errors"], list)
