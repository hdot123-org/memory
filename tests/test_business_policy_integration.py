#!/usr/bin/env python3
"""Integration regression tests for business_policy_checks.py.

Covers:
- Complete flow: config load -> policy check -> result return
- Gateway integration: simulated gateway calling policy checks
- Adapter config integration: different adapter configs produce different behaviors
- Multi-policy interaction: multiple strategies active simultaneously
- Regression scenarios: core business flows remain intact after changes
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
from workspace.tools._validation_constants import (
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
    SEC_FORMAL_CONTRACT_EVENTS,
    SEC_FORMAL_CONTRACT_SOURCES,
    SEC_FORMAL_CONTRACT_STATUSES,
    SEC_UPSTREAM_MAPPING_ERRORS,
    SEC_UPSTREAM_MAPPING_ROUTING,
    SEC_UPSTREAM_MAPPING_SOURCES,
    SEC_UPSTREAM_MAPPING_TABLE,
    SEC_UPSTREAM_STANDARD_EVENTS,
    SEC_UPSTREAM_STANDARD_SOURCES,
    SEC_UPSTREAM_STANDARD_STATUSES,
)

# ---------------------------------------------------------------------------
# Fixture helper — build GatewayBusinessPolicyConfig via constructor
# ---------------------------------------------------------------------------

def _default_read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _make_config(tmp_path: Path, **overrides: Any):
    """Build a GatewayBusinessPolicyConfig with temp paths and optional overrides."""
    from workspace.tools.memory_hook_impls import GatewayBusinessPolicyConfig

    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    pm_root = ws / "memory" / "project-map"
    pm_root.mkdir(parents=True, exist_ok=True)

    index_md = pm_root / "INDEX.md"
    core_map = pm_root / "legal-core-map.md"
    registry_map = pm_root / "ingestion-registry-map.md"
    governance = pm_root / "governance.md"
    truth_model = pm_root / "truth-model-canonical.md"
    for f in [index_md, core_map, registry_map, governance, truth_model]:
        f.touch()

    global_canon_dir = ws / "memory" / "kb" / "global"
    global_canon_dir.mkdir(parents=True, exist_ok=True)
    global_canon_0 = global_canon_dir / "global-truth.md"
    global_canon_0.touch()
    global_canonical = [global_canon_0]

    workspace_index = ws / "INDEX.md"
    workspace_index.touch()
    docs_index_dir = ws / "memory" / "docs"
    docs_index_dir.mkdir(parents=True, exist_ok=True)
    docs_index = docs_index_dir / "INDEX.md"
    docs_index.touch()
    overview_doc = docs_index_dir / "overview.md"
    overview_doc.touch()
    global_index = global_canon_dir / "INDEX.md"
    global_index.touch()
    hook_contract_dir = ws / "memory" / "system"
    hook_contract_dir.mkdir(parents=True, exist_ok=True)
    hook_contract = hook_contract_dir / "hook-contract.md"
    hook_contract.touch()

    projects_dir = ws / "memory" / "kb" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, Any] = dict(
        repo_root=root,
        workspace_root=ws,
        project_map_root=pm_root,
        project_map_files=[index_md, core_map, registry_map],
        project_map_governance=governance,
        truth_model=truth_model,
        global_canonical=global_canonical,
        authority_allowed_paths=set(global_canonical),
        lower_evidence_roots=[projects_dir],
        legal_core_markers=["active-legal", "map-only"],
        required_registry_scopes=["incoming-raw", "compatibility-only"],
        project_canonical={},
        project_runtime_root={},
        project_doc_refs={},
        default_decision_refs=[],
        project_decision_refs={},
        default_lesson_refs=[],
        project_lesson_refs={},
        governance_frozen_tuple_files=[],
        event_contract_files={},
        frozen_tuple_expected=set(),
        frozen_tuple_legacy_markers=set(),
        formal_source_types={"lark-im", "cmux-event", "git-hook"},
        formal_event_types={"message.create", "event.dispatch", "commit.push"},
        formal_event_statuses={"processed", "rejected", "pending"},
        formal_field_keys={"source_type", "event_type", "event_status"},
        legacy_field_keys={"old_type", "legacy_status"},
        required_canonical=[],
        workspace_index_path=workspace_index,
        docs_index_path=docs_index,
        overview_doc_path=overview_doc,
        global_index_path=global_index,
        hook_contract_path=hook_contract,
        default_project_scope="global",
        scope_match_hints={},
        read_text_if_exists_fn=_default_read_text,
        policy_pack_path=None,
    )
    kwargs.update(overrides)
    return GatewayBusinessPolicyConfig(**kwargs)


# ---------------------------------------------------------------------------
# 1. Complete flow: config load -> policy check -> result return
# ---------------------------------------------------------------------------

class TestCompleteFlow:
    """Verify end-to-end policy check workflows."""

    def _write_valid_project_map(self, cfg) -> None:
        """Write valid markers to all project map files for a clean pass."""
        cfg.project_map_files[0].write_text(
            f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )

    def test_project_map_validator_returns_empty_errors_for_valid_markers(
        self, tmp_path: Path
    ) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        cfg = _make_config(tmp_path)
        self._write_valid_project_map(cfg)

        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert errors == []

    def test_project_map_validator_detects_missing_markers(
        self, tmp_path: Path
    ) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        cfg = _make_config(tmp_path)
        for f in cfg.project_map_files + [cfg.project_map_governance]:
            f.write_text("nothing relevant here\n", encoding="utf-8")

        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert len(errors) > 0
        assert any("does not declare the unique legal entry" in e for e in errors)

    def test_project_map_validator_detects_transition_refs(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        cfg = _make_config(tmp_path)
        index_md = cfg.project_map_files[0]
        index_md.write_text(
            f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n"
            f"{MKR_GIT_COMMIT_GATE}\nold round-1 reference\n",
            encoding="utf-8",
        )
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )

        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert any("transition round" in e for e in errors)

    def test_truth_basis_resolver_returns_fail_for_unknown_scope(
        self, tmp_path: Path
    ) -> None:
        from workspace.tools.business_policy_checks import TruthBasisResolver

        cfg = _make_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("nonexistent-scope")
        assert result["validation"] == "fail"
        assert result["policy"] == "source-authority-evidence-conflict"
        assert any("unsupported project scope" in e for e in result["errors"])

    def test_scope_resolver_determines_default_scope(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        cfg = _make_config(tmp_path, default_project_scope="global", scope_match_hints={})
        resolver = ScopeResolver(cfg, scope_config_path=None)

        scope = resolver.determine_project_scope(tmp_path / "random" / "dir")
        assert scope == "global"

    def test_scope_resolver_matches_hint(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        tools_root = tmp_path / "repo" / "tools"
        cfg = _make_config(tmp_path, default_project_scope="global", scope_match_hints={"tooling": [tools_root]})
        resolver = ScopeResolver(cfg, scope_config_path=None)

        scope = resolver.determine_project_scope(tmp_path / "repo" / "tools" / "sub")
        assert scope == "tooling"

    def test_scope_resolver_handles_scope_overrides(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        global_md = tmp_path / "global.md"
        global_md.touch()
        override_file = tmp_path / "scope-overrides.json"
        override_file.write_text(
            json.dumps({
                "project_canonical": {"workbot": str(tmp_path / "workspace" / "memory" / "kb" / "global" / "workbot-canonical.md")},
            }),
            encoding="utf-8",
        )
        cfg = _make_config(tmp_path, project_canonical={"global": global_md})
        resolver = ScopeResolver(cfg, scope_config_path=override_file)
        canon = resolver.get_project_canonical()
        assert "workbot" in canon


# ---------------------------------------------------------------------------
# 2. Gateway integration: simulated gateway calling policy checks
# ---------------------------------------------------------------------------

class TestGatewayIntegration:
    """Simulate how memory_hook_gateway invokes business policy checks."""

    def test_gateway_style_project_map_check_flow(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        cfg = _make_config(tmp_path)
        cfg.project_map_files[0].write_text(
            f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )

        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_gateway_style_truth_basis_flow(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import TruthBasisResolver

        project_file = tmp_path / "repo" / "projects" / "alpha" / "truth.md"
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text(
            "## Truth Basis\n\n### Source Refs\n- ./source.md\n\n"
            "### Authority Refs\n- ./auth.md\n\n"
            "### Evidence Refs\n- ./evidence.md\n\n"
            "### Conflict Status\n- resolved\n",
            encoding="utf-8",
        )
        cfg = _make_config(tmp_path, project_canonical={"alpha": project_file})
        cfg = replace(cfg, authority_allowed_paths=cfg.authority_allowed_paths | {project_file})

        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("alpha")
        assert result["policy"] == "source-authority-evidence-conflict"
        assert result["project_ref"] == str(project_file)
        assert "validation" in result

    def test_gateway_style_scope_resolution_flow(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        decision_md = tmp_path / "repo" / "decisions.md"
        decision_md.parent.mkdir(parents=True, exist_ok=True)
        decision_md.touch()
        cfg = _make_config(tmp_path, default_decision_refs=[decision_md])
        resolver = ScopeResolver(cfg, scope_config_path=None)

        scope = resolver.determine_project_scope(tmp_path / "repo")
        refs = resolver.decision_refs_for_scope(scope)
        assert isinstance(refs, list)

    def _make_event_contract_dir(self, tmp_path: Path, name: str, upstream_standard: str, upstream_mapping: str, formal_contract: str, upstream_samples: str, downstream_samples: str) -> dict[str, Path]:
        """Create a directory of event contract files and return the mapping."""
        contract_dir = tmp_path / name
        contract_dir.mkdir()
        files = {}
        for fname, content in [
            ("upstream-standard.md", upstream_standard),
            ("upstream-mapping.md", upstream_mapping),
            ("formal-contract.md", formal_contract),
            ("upstream-samples.json", upstream_samples),
            ("downstream-samples.json", downstream_samples),
        ]:
            p = contract_dir / fname
            p.write_text(content, encoding="utf-8")
            files[fname.replace("-", "_").replace(".md", "").replace(".json", "")] = p
        return {
            "upstream_standard": files["upstream_standard"],
            "upstream_mapping": files["upstream_mapping"],
            "formal_contract": files["formal_contract"],
            "upstream_samples": files["upstream_samples"],
            "downstream_samples": files["downstream_samples"],
        }

    def test_gateway_style_event_contract_check(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import EventContractChecker

        formal_sources = "\n".join([SEC_UPSTREAM_STANDARD_SOURCES, "`lark-im`", "`cmux-event`", "`git-hook`"])
        formal_events = "\n".join([SEC_UPSTREAM_STANDARD_EVENTS, "`message.create`", "`event.dispatch`", "`commit.push`"])
        formal_statuses = "\n".join([SEC_UPSTREAM_STANDARD_STATUSES, "`processed`", "`rejected`", "`pending`"])

        upstream_standard = f"{formal_sources}\n\n{formal_events}\n\n{formal_statuses}\n"
        upstream_mapping = (
            f"{SEC_UPSTREAM_MAPPING_SOURCES}\n`lark-im`\n`cmux-event`\n`git-hook`\n\n"
            f"{SEC_UPSTREAM_MAPPING_TABLE}\n`message.create`\n`event.dispatch`\n`commit.push`\n\n"
            f"{SEC_UPSTREAM_MAPPING_ROUTING}\n`processed`\n`rejected`\n`pending`\n\n"
            f"{SEC_UPSTREAM_MAPPING_ERRORS}\n`processed`\n`rejected`\n"
        )
        formal_contract_text = (
            f"{SEC_FORMAL_CONTRACT_SOURCES}\n`lark-im`\n`cmux-event`\n`git-hook`\n\n"
            f"{SEC_FORMAL_CONTRACT_EVENTS}\n`message.create`\n`event.dispatch`\n`commit.push`\n\n"
            f"{SEC_FORMAL_CONTRACT_STATUSES}\n`processed`\n`rejected`\n`pending`\n"
        )
        upstream_samples = json.dumps([
            {"source_type": "lark-im", "event_type": "message.create", "event_status": "processed"},
            {"source_type": "cmux-event", "event_type": "event.dispatch", "event_status": "pending"},
        ])
        downstream_samples = json.dumps([
            {"source_type": "git-hook", "event_type": "commit.push", "event_status": "rejected"},
        ])

        ec_files = self._make_event_contract_dir(
            tmp_path, "ec-valid", upstream_standard, upstream_mapping,
            formal_contract_text, upstream_samples, downstream_samples,
        )
        cfg = _make_config(tmp_path, event_contract_files=ec_files)

        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert errors == []

    def test_gateway_style_missing_contract_files(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import EventContractChecker

        ec_files = {
            "upstream_standard": tmp_path / "nonexistent.md",
            "upstream_mapping": tmp_path / "also-nonexistent.md",
            "formal_contract": tmp_path / "missing.md",
            "upstream_samples": tmp_path / "no-samples.json",
            "downstream_samples": tmp_path / "no-downstream.json",
        }
        cfg = _make_config(tmp_path, event_contract_files=ec_files)

        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert len(errors) > 0
        assert any("missing event contract files" in e for e in errors)


# ---------------------------------------------------------------------------
# 3. Adapter config integration: different adapter configs produce different behaviors
# ---------------------------------------------------------------------------

class TestAdapterConfigIntegration:
    """Different adapter configurations should produce different policy behaviors."""

    def test_workbot_adapter_config_triggers_project_map_checks(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        cfg = _make_config(tmp_path)
        cfg.project_map_files[0].write_text(
            f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )

        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert errors == []

    def test_neutral_adapter_config_minimal_markers(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        cfg = _make_config(tmp_path)
        for f in cfg.project_map_files + [cfg.project_map_governance]:
            f.write_text(
                f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_CORE_ACTIVE_LEGAL}\n",
                encoding="utf-8",
            )

        validator = ProjectMapValidator(cfg)
        errors = validator.validate_project_map_files()
        assert len(errors) > 0

    def test_adapter_with_custom_scope_match_hints(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        tools_root = tmp_path / "repo" / "tools"
        docs_root = tmp_path / "repo" / "docs"
        docs_root.mkdir(parents=True, exist_ok=True)
        cfg = _make_config(
            tmp_path,
            default_project_scope="global",
            scope_match_hints={"tooling": [tools_root], "docs": [docs_root]},
        )
        resolver = ScopeResolver(cfg, scope_config_path=None)

        assert resolver.determine_project_scope(tools_root / "business_policy_checks.py") == "tooling"
        assert resolver.determine_project_scope(docs_root / "readme.md") == "docs"
        assert resolver.determine_project_scope(tmp_path / "repo" / "unrelated") == "global"

    def test_adapter_scope_override_env_var(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        global_md = tmp_path / "global.md"
        global_md.touch()
        override_file = tmp_path / "env-overrides.json"
        override_file.write_text(
            json.dumps({
                "project_canonical": {"env-scope": "custom-path.md"},
            }),
            encoding="utf-8",
        )
        cfg = _make_config(tmp_path, project_canonical={"global": global_md})

        with patch.dict("os.environ", {"MEMORY_HOOK_SCOPE_CONFIG_PATH": str(override_file)}):
            resolver = ScopeResolver(cfg, scope_config_path=None)
            canon = resolver.get_project_canonical()
            assert "env-scope" in canon


# ---------------------------------------------------------------------------
# 4. Multi-policy interaction: multiple strategies active simultaneously
# ---------------------------------------------------------------------------

class TestMultiPolicyInteraction:
    """Test that multiple checkers can run together and produce combined results."""

    def _write_full_legal_docs(self, cfg) -> None:
        """Write all workspace/doc files with required markers."""
        cfg.workspace_index_path.write_text(
            f"{MKR_WORKSPACE_PROJECT_MAP_REF}\n{MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY}\n"
            f"{MKR_WORKSPACE_GIT_COMMIT_RULE}\n{str(cfg.truth_model)}\n",
            encoding="utf-8",
        )
        cfg.docs_index_path.write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_DOCS_UNABSORBED}\n",
            encoding="utf-8",
        )
        cfg.overview_doc_path.write_text(
            f"{MKR_WORKSPACE_PROJECT_MAP_REF}\n",
            encoding="utf-8",
        )
        cfg.global_index_path.write_text(
            f"{MKR_NON_LEGAL_MATERIAL}\n{MKR_INGESTION_REGISTRY_REF}\n"
            f"{cfg.truth_model.name}\n",
            encoding="utf-8",
        )
        cfg.hook_contract_path.write_text(
            f"{MKR_HOOK_MAP_ONLY_CONTEXT}\n{MKR_HOOK_REGISTRATION_GATE}\n",
            encoding="utf-8",
        )

    def test_project_map_and_legal_contract_combined(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import (
            LegalContractChecker,
            ProjectMapValidator,
        )

        cfg = _make_config(tmp_path)
        cfg.project_map_files[0].write_text(
            f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\nmap-only\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )
        self._write_full_legal_docs(cfg)

        pm_validator = ProjectMapValidator(cfg)
        legal_checker = LegalContractChecker(cfg)

        pm_errors = pm_validator.validate_project_map_files()
        legal_errors = legal_checker.validate_unique_legal_system_contract()

        assert pm_errors == []
        assert legal_errors == []

    def test_frozen_tuple_checker_with_expected_markers(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import FrozenTupleChecker

        gov_file = tmp_path / "governance-frozen.md"
        gov_file.write_text(
            "# Governance\n- frozen-tuple-marker-alpha\n- frozen-tuple-marker-beta\n",
            encoding="utf-8",
        )
        cfg = _make_config(
            tmp_path,
            governance_frozen_tuple_files=[gov_file],
            frozen_tuple_expected={"frozen-tuple-marker-alpha", "frozen-tuple-marker-beta"},
            frozen_tuple_legacy_markers=set(),
        )

        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert errors == []

    def test_frozen_tuple_checker_detects_legacy_markers(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import FrozenTupleChecker

        gov_file = tmp_path / "governance-legacy.md"
        gov_file.write_text(
            "# Governance\n- frozen-tuple-marker-alpha\n- old-legacy-marker\n",
            encoding="utf-8",
        )
        cfg = _make_config(
            tmp_path,
            governance_frozen_tuple_files=[gov_file],
            frozen_tuple_expected={"frozen-tuple-marker-alpha"},
            frozen_tuple_legacy_markers={"old-legacy-marker"},
        )

        checker = FrozenTupleChecker(cfg)
        errors = checker.governance_frozen_tuple_blocker_errors()
        assert len(errors) > 0
        assert any("legacy frozen tuple" in e for e in errors)

    def test_event_contract_checker_detects_mismatch(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import EventContractChecker

        upstream_standard = f"{SEC_UPSTREAM_STANDARD_SOURCES}\n`lark-im`\n`unknown-type`\n"
        upstream_mapping = f"{SEC_UPSTREAM_MAPPING_SOURCES}\n`lark-im`\n`unknown-type`\n"
        formal_contract_text = f"{SEC_FORMAL_CONTRACT_SOURCES}\n`lark-im`\n`unknown-type`\n"

        upstream_samples = json.dumps([{"source_type": "unknown-type", "event_type": "unknown", "event_status": "unknown"}])
        downstream_samples = json.dumps([{"source_type": "unknown-type", "event_type": "unknown", "event_status": "unknown"}])

        contract_dir = tmp_path / "ec-mismatch"
        contract_dir.mkdir()
        (contract_dir / "upstream-standard.md").write_text(upstream_standard, encoding="utf-8")
        (contract_dir / "upstream-mapping.md").write_text(upstream_mapping, encoding="utf-8")
        (contract_dir / "formal-contract.md").write_text(formal_contract_text, encoding="utf-8")
        (contract_dir / "upstream-samples.json").write_text(upstream_samples, encoding="utf-8")
        (contract_dir / "downstream-samples.json").write_text(downstream_samples, encoding="utf-8")

        ec_files = {
            "upstream_standard": contract_dir / "upstream-standard.md",
            "upstream_mapping": contract_dir / "upstream-mapping.md",
            "formal_contract": contract_dir / "formal-contract.md",
            "upstream_samples": contract_dir / "upstream-samples.json",
            "downstream_samples": contract_dir / "downstream-samples.json",
        }
        cfg = _make_config(tmp_path, event_contract_files=ec_files)

        checker = EventContractChecker(cfg)
        errors = checker.event_contract_blocker_errors()
        assert len(errors) > 0

    def test_combined_all_checkers_pass(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import (
            EventContractChecker,
            FrozenTupleChecker,
            ProjectMapValidator,
        )

        cfg = _make_config(tmp_path)

        # -- Project map --
        cfg.project_map_files[0].write_text(
            f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )

        # -- Frozen tuple --
        gov_file = tmp_path / "governance-combined.md"
        gov_file.write_text("# Governance\n- expected-marker-x\n", encoding="utf-8")
        cfg = replace(
            cfg,
            governance_frozen_tuple_files=[gov_file],
            frozen_tuple_expected={"expected-marker-x"},
            frozen_tuple_legacy_markers=set(),
        )

        # -- Event contracts --
        formal_sources = "\n".join([SEC_UPSTREAM_STANDARD_SOURCES, "`lark-im`", "`cmux-event`", "`git-hook`"])
        formal_events = "\n".join([SEC_UPSTREAM_STANDARD_EVENTS, "`message.create`", "`event.dispatch`", "`commit.push`"])
        formal_statuses = "\n".join([SEC_UPSTREAM_STANDARD_STATUSES, "`processed`", "`rejected`", "`pending`"])
        upstream_standard = f"{formal_sources}\n\n{formal_events}\n\n{formal_statuses}\n"

        upstream_mapping = (
            f"{SEC_UPSTREAM_MAPPING_SOURCES}\n`lark-im`\n`cmux-event`\n`git-hook`\n\n"
            f"{SEC_UPSTREAM_MAPPING_TABLE}\n`message.create`\n`event.dispatch`\n`commit.push`\n\n"
            f"{SEC_UPSTREAM_MAPPING_ROUTING}\n`processed`\n`rejected`\n`pending`\n\n"
            f"{SEC_UPSTREAM_MAPPING_ERRORS}\n`processed`\n`rejected`\n"
        )
        formal_contract_text = (
            f"{SEC_FORMAL_CONTRACT_SOURCES}\n`lark-im`\n`cmux-event`\n`git-hook`\n\n"
            f"{SEC_FORMAL_CONTRACT_EVENTS}\n`message.create`\n`event.dispatch`\n`commit.push`\n\n"
            f"{SEC_FORMAL_CONTRACT_STATUSES}\n`processed`\n`rejected`\n`pending`\n"
        )
        upstream_samples = json.dumps([
            {"source_type": "lark-im", "event_type": "message.create", "event_status": "processed"},
        ])
        downstream_samples = json.dumps([
            {"source_type": "git-hook", "event_type": "commit.push", "event_status": "rejected"},
        ])

        contract_dir = tmp_path / "ec-combined"
        contract_dir.mkdir()
        (contract_dir / "upstream-standard.md").write_text(upstream_standard, encoding="utf-8")
        (contract_dir / "upstream-mapping.md").write_text(upstream_mapping, encoding="utf-8")
        (contract_dir / "formal-contract.md").write_text(formal_contract_text, encoding="utf-8")
        (contract_dir / "upstream-samples.json").write_text(upstream_samples, encoding="utf-8")
        (contract_dir / "downstream-samples.json").write_text(downstream_samples, encoding="utf-8")

        ec_files = {
            "upstream_standard": contract_dir / "upstream-standard.md",
            "upstream_mapping": contract_dir / "upstream-mapping.md",
            "formal_contract": contract_dir / "formal-contract.md",
            "upstream_samples": contract_dir / "upstream-samples.json",
            "downstream_samples": contract_dir / "downstream-samples.json",
        }
        cfg = replace(cfg, event_contract_files=ec_files)

        all_errors: list[str] = []
        all_errors.extend(ProjectMapValidator(cfg).validate_project_map_files())
        all_errors.extend(FrozenTupleChecker(cfg).governance_frozen_tuple_blocker_errors())
        all_errors.extend(EventContractChecker(cfg).event_contract_blocker_errors())

        assert all_errors == [], f"Unexpected errors: {all_errors}"


# ---------------------------------------------------------------------------
# 5. Regression scenarios: core business flows remain intact
# ---------------------------------------------------------------------------

class TestRegressionScenarios:
    """Ensure core business flows do not break after changes."""

    def test_read_text_if_exists_fn_is_used(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ProjectMapValidator

        call_log: list[Path] = []

        def logged_read(p: Path) -> str:
            call_log.append(p)
            return f"{MKR_UNIQUE_LEGAL_ENTRY}\n{MKR_ACTIVE_LEGAL_MAP_ONLY}\n{MKR_GIT_COMMIT_GATE}\n"

        cfg = _make_config(tmp_path, read_text_if_exists_fn=logged_read)
        cfg.project_map_files[1].write_text(
            f"{MKR_CORE_ACTIVE_LEGAL}\n{MKR_CORE_MAP_ONLY}\n",
            encoding="utf-8",
        )
        cfg.project_map_files[2].write_text(
            f"{MKR_INCOMING_RAW}\n{MKR_COMPATIBILITY_ONLY}\n"
            f"{MKR_ABSORBED_STATUS}\n{MKR_RETIRED_STATUS}\n"
            f"{MKR_REGISTRY_GIT_COMMIT_GATE}\n",
            encoding="utf-8",
        )
        cfg.project_map_governance.write_text(
            f"{MKR_UNWASHED_NOT_LEGAL}\n{MKR_GOVERNANCE_MAP_GRANTS_LEGALITY}\n"
            f"{MKR_ATOMIC_REGISTRATION_GIT_COMMIT}\n",
            encoding="utf-8",
        )

        validator = ProjectMapValidator(cfg)
        validator.validate_project_map_files()
        assert len(call_log) == 4

    def test_truth_basis_ref_classification(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import TruthBasisResolver

        cfg = _make_config(tmp_path)
        resolver = TruthBasisResolver(cfg)

        assert resolver._classify_truth_ref(cfg.project_map_root / "legal-core-map.md") == "legal-core"
        assert resolver._classify_truth_ref(cfg.project_map_root / "INDEX.md") == "project-map-index"
        assert resolver._classify_truth_ref(cfg.repo_root / "AGENTS.md") == "repo-policy"
        assert resolver._classify_truth_ref(cfg.workspace_root / "INDEX.md") == "workspace-entry"

    def test_scope_resolver_handles_outside_repo(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        cfg = _make_config(tmp_path, default_project_scope="fallback")
        resolver = ScopeResolver(cfg, scope_config_path=None)

        scope = resolver.determine_project_scope(Path("/tmp"))
        assert scope == "fallback"

    def test_scope_resolver_loads_invalid_json_gracefully(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        bad_file = tmp_path / "bad-scope.json"
        bad_file.write_text("not json at all {{{", encoding="utf-8")

        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg, scope_config_path=bad_file)
        canon = resolver.get_project_canonical()
        assert canon == {}

    def test_scope_resolver_handles_non_dict_json(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        bad_file = tmp_path / "array-scope.json"
        bad_file.write_text('["not", "a", "dict"]', encoding="utf-8")

        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg, scope_config_path=bad_file)
        canon = resolver.get_project_canonical()
        assert canon == {}

    def test_path_is_under_helper(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _path_is_under

        root = tmp_path / "root"
        child = root / "sub" / "file.md"
        sibling = tmp_path / "sibling" / "file.md"

        child.parent.mkdir(parents=True, exist_ok=True)
        child.touch()
        sibling.parent.mkdir(parents=True, exist_ok=True)
        sibling.touch()

        assert _path_is_under(child, root) is True
        assert _path_is_under(sibling, root) is False

    def test_path_is_under_lexical_helper(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _path_is_under_lexical

        root = tmp_path / "lex-root"
        child = root / "a" / "b"
        outside = tmp_path / "lex-outside"

        assert _path_is_under_lexical(child, root) is True
        assert _path_is_under_lexical(outside, root) is False

    def test_section_bullets_extracts_list_items(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _section_bullets

        text = (
            "## Some Heading\n"
            "- item one\n"
            "- `item two`\n"
            "- item three\n"
            "## Next Heading\n"
            "- should not appear\n"
        )
        bullets = _section_bullets(text, "## Some Heading")
        assert bullets == ["item one", "item two", "item three"]

    def test_section_body_extracts_text_between_headings(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _section_body

        text = (
            "## Target Heading\n"
            "line one\n"
            "line two\n"
            "## Next Heading\n"
            "should not be included\n"
        )
        body = _section_body(text, "## Target Heading")
        assert "line one" in body
        assert "line two" in body
        assert "should not be included" not in body

    def test_markdown_code_tokens_extracts_backtick_values(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _markdown_code_tokens

        text = "Use `lark-im` and `cmux-event` for testing."
        tokens = _markdown_code_tokens(text)
        assert tokens == {"lark-im", "cmux-event"}

    def test_json_string_values_extracts_values_by_key(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _json_string_values

        text = json.dumps([
            {"source_type": "lark-im", "event_type": "msg"},
            {"source_type": "git-hook", "event_type": "push"},
        ])
        values = _json_string_values(text, "source_type")
        assert values == {"lark-im", "git-hook"}

    def test_existing_paths_filters_nonexistent(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import _existing_paths

        existing = tmp_path / "exists.md"
        existing.touch()
        missing = tmp_path / "does-not-exist.md"

        result = _existing_paths([existing, missing])
        assert result == [str(existing)]

    def test_truth_basis_for_scope_returns_global_refs(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import TruthBasisResolver

        extra = tmp_path / "repo" / "extra-global.md"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.touch()
        alpha_md = tmp_path / "alpha.md"
        alpha_md.touch()

        cfg = _make_config(tmp_path)
        cfg = replace(
            cfg,
            global_canonical=cfg.global_canonical + [extra],
            project_canonical={"alpha": alpha_md},
        )

        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("alpha")
        assert "refs" in result
        assert len(result["refs"]) >= 2

    def test_scope_resolver_project_runtime_root_merge(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        runtime_global = tmp_path / "runtime-global"
        runtime_global.mkdir(parents=True, exist_ok=True)
        override_file = tmp_path / "rt-overrides.json"
        override_file.write_text(
            json.dumps({
                "project_runtime_root": {"workbot": str(tmp_path / "workspace" / "runtime-workbot")},
            }),
            encoding="utf-8",
        )
        cfg = _make_config(tmp_path, project_runtime_root={"global": runtime_global})
        resolver = ScopeResolver(cfg, scope_config_path=override_file)
        runtime = resolver.get_project_runtime_root()
        assert "workbot" in runtime

    def test_scope_resolver_get_required_canonical(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        req = [tmp_path / "a.md", tmp_path / "b.md"]
        req[0].touch()
        req[1].touch()
        cfg = _make_config(tmp_path, required_canonical=req)

        resolver = ScopeResolver(cfg, scope_config_path=None)
        result = resolver.get_required_canonical()
        assert result == req

    def test_scope_resolver_get_global_canonical(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg, scope_config_path=None)
        result = resolver.get_global_canonical()
        assert len(result) > 0

    def test_scope_resolver_project_map_refs(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg, scope_config_path=None)
        refs = resolver.project_map_refs()
        assert len(refs) == 3

    def test_scope_resolver_refs_for_scope_combine_defaults_and_project(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        default_ref = tmp_path / "default-ref.md"
        default_ref.touch()
        project_ref = tmp_path / "project-ref.md"
        project_ref.touch()
        cfg = _make_config(
            tmp_path,
            default_decision_refs=[default_ref],
            project_decision_refs={"alpha": [project_ref]},
        )

        resolver = ScopeResolver(cfg, scope_config_path=None)
        refs = resolver.decision_refs_for_scope("alpha")
        assert str(default_ref) in refs
        assert str(project_ref) in refs

    def test_scope_resolver_lesson_refs_for_scope(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        default_ref = tmp_path / "default-lesson.md"
        default_ref.touch()
        project_ref = tmp_path / "project-lesson.md"
        project_ref.touch()
        cfg = _make_config(
            tmp_path,
            default_lesson_refs=[default_ref],
            project_lesson_refs={"beta": [project_ref]},
        )

        resolver = ScopeResolver(cfg, scope_config_path=None)
        refs = resolver.lesson_refs_for_scope("beta")
        assert str(default_ref) in refs
        assert str(project_ref) in refs

    def test_scope_resolver_docs_refs_for_scope(self, tmp_path: Path) -> None:
        from workspace.tools.business_policy_checks import ScopeResolver

        doc_ref = tmp_path / "project-doc.md"
        doc_ref.touch()
        cfg = _make_config(tmp_path, project_doc_refs={"gamma": [doc_ref]})

        resolver = ScopeResolver(cfg, scope_config_path=None)
        refs = resolver.docs_refs_for_scope("gamma")
        assert str(doc_ref) in refs
