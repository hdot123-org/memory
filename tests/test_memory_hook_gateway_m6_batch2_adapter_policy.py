#!/usr/bin/env python3
"""M6 Batch-2 tests: gateway business policy adapter and scope-config injection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from workspace.tools import memory_hook_gateway as gateway
from workspace.tools.memory_hook_impls import GatewayBusinessPolicyConfig, GatewayBusinessPolicyImpl


def _policy_config() -> GatewayBusinessPolicyConfig:
    return GatewayBusinessPolicyConfig(
        repo_root=gateway.REPO_ROOT,
        workspace_root=gateway.WORKSPACE_ROOT,
        project_map_root=gateway.PROJECT_MAP_ROOT,
        project_map_files=gateway.PROJECT_MAP_FILES,
        project_map_governance=gateway.PROJECT_MAP_GOVERNANCE,
        truth_model=gateway.TRUTH_MODEL,
        global_canonical=gateway.GLOBAL_CANONICAL,
        authority_allowed_paths=gateway.AUTHORITY_ALLOWED_PATHS,
        lower_evidence_roots=gateway.LOWER_EVIDENCE_ROOTS,
        legal_core_markers=gateway.LEGAL_CORE_MARKERS,
        required_registry_scopes=gateway.REQUIRED_REGISTRY_SCOPES,
        project_canonical=gateway.PROJECT_CANONICAL,
        project_runtime_root=gateway.PROJECT_RUNTIME_ROOT,
        project_doc_refs=gateway.PROJECT_DOC_REFS,
        default_decision_refs=gateway.DEFAULT_DECISION_REFS,
        project_decision_refs=gateway.PROJECT_DECISION_REFS,
        default_lesson_refs=gateway.DEFAULT_LESSON_REFS,
        project_lesson_refs=gateway.PROJECT_LESSON_REFS,
        governance_frozen_tuple_files=gateway.GOVERNANCE_FROZEN_TUPLE_FILES,
        event_contract_files=gateway.EVENT_CONTRACT_FILES,
        frozen_tuple_expected=gateway.FROZEN_TUPLE_EXPECTED,
        frozen_tuple_legacy_markers=gateway.FROZEN_TUPLE_LEGACY_MARKERS,
        formal_source_types=gateway.FORMAL_SOURCE_TYPES,
        formal_event_types=gateway.FORMAL_EVENT_TYPES,
        formal_event_statuses=gateway.FORMAL_EVENT_STATUSES,
        formal_field_keys=gateway.FORMAL_FIELD_KEYS,
        legacy_field_keys=gateway.LEGACY_FIELD_KEYS,
        required_canonical=gateway.REQUIRED_CANONICAL,
        workspace_index_path=gateway.WORKSPACE_ROOT / "INDEX.md",
        docs_index_path=gateway.WORKSPACE_ROOT / "memory" / "docs" / "INDEX.md",
        overview_doc_path=gateway.WORKSPACE_ROOT / "memory" / "docs" / "记忆系统全景文档.md",
        global_index_path=gateway.WORKSPACE_ROOT / "memory" / "kb" / "global" / "INDEX.md",
        hook_contract_path=gateway.HOOK_CONTRACT_PATH,
        default_project_scope=gateway.DEFAULT_PROJECT_SCOPE,
        scope_match_hints=gateway.SCOPE_MATCH_HINTS,
        read_text_if_exists_fn=gateway.read_text_if_exists,
    )


def test_gateway_wrappers_delegate_to_business_policy(monkeypatch):
    class FakePolicy:
        def determine_project_scope(self, cwd: Path) -> str:
            return "fake-scope"

        def get_project_canonical(self) -> dict[str, Path]:
            return {"workbot": Path("/tmp/fake-workbot.md")}

        def get_project_runtime_root(self) -> dict[str, Path]:
            return {"workbot": Path("/tmp/fake-runtime")}

        def get_required_canonical(self) -> list[Path]:
            return []

        def get_global_canonical(self) -> list[Path]:
            return []

        def project_map_refs(self) -> list[str]:
            return ["pm-index", "pm-core"]

        def validate_project_map_files(self) -> list[str]:
            return ["pm-error"]

        def validate_unique_legal_system_contract(self) -> list[str]:
            return ["legal-error"]

        def governance_frozen_tuple_blocker_errors(self) -> list[str]:
            return ["governance-error"]

        def event_contract_blocker_errors(self) -> list[str]:
            return ["event-error"]

        def decision_refs_for_scope(self, project_scope: str) -> list[str]:
            return [f"decision:{project_scope}"]

        def lesson_refs_for_scope(self, project_scope: str) -> list[str]:
            return [f"lesson:{project_scope}"]

        def docs_refs_for_scope(self, project_scope: str) -> list[str]:
            return [f"docs:{project_scope}"]

        def truth_basis_for_scope(self, project_scope: str) -> dict[str, object]:
            return {"policy": "x", "validation": "pass", "scope": project_scope}

    monkeypatch.setattr(gateway, "_get_gateway_business_policy", lambda: FakePolicy())

    assert gateway.determine_project_scope(Path("/any")) == "fake-scope"
    assert gateway.project_map_refs() == ["pm-index", "pm-core"]
    assert gateway.validate_project_map_files() == ["pm-error"]
    assert gateway.validate_unique_legal_system_contract() == ["legal-error"]
    assert gateway.governance_frozen_tuple_blocker_errors() == ["governance-error"]
    assert gateway.event_contract_blocker_errors() == ["event-error"]
    assert gateway.decision_refs_for_scope("workbot") == ["decision:workbot"]
    assert gateway.lesson_refs_for_scope("workbot") == ["lesson:workbot"]
    assert gateway.docs_refs_for_scope("workbot") == ["docs:workbot"]
    assert gateway.truth_basis_for_scope("workbot")["scope"] == "workbot"


def test_business_policy_supports_scope_config_override(tmp_path: Path):
    canonical_override = tmp_path / "canonical" / "workbot.md"
    runtime_override = tmp_path / "runtime" / "workbot"
    scope_config_path = tmp_path / "scope-config.json"
    scope_config_path.write_text(
        json.dumps(
            {
                "project_canonical": {"workbot": str(canonical_override)},
                "project_runtime_root": {"workbot": str(runtime_override)},
            }
        ),
        encoding="utf-8",
    )

    policy = GatewayBusinessPolicyImpl(config=_policy_config(), scope_config_path=scope_config_path)

    canonical = policy.get_project_canonical()
    runtime_root = policy.get_project_runtime_root()

    assert canonical["workbot"] == canonical_override
    assert runtime_root["workbot"] == runtime_override


def test_build_context_package_passes_scope_overrides_to_core(monkeypatch, tmp_path: Path):
    canonical_override = tmp_path / "canonical" / "workbot.md"
    runtime_override = tmp_path / "runtime" / "workbot"
    scope_config_path = tmp_path / "scope-config.json"
    scope_config_path.write_text(
        json.dumps(
            {
                "project_canonical": {"workbot": str(canonical_override)},
                "project_runtime_root": {"workbot": str(runtime_override)},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MEMORY_HOOK_SCOPE_CONFIG_PATH", str(scope_config_path))
    monkeypatch.setattr(gateway, "discover_cwd", lambda payload: gateway.WORKSPACE_ROOT)
    monkeypatch.setattr(gateway, "determine_project_scope", lambda cwd: "workbot")

    captured_config: list[object] = []

    def fake_from_config(config):
        captured_config.append(config)
        return {"status": "ok", "schema_version": "wb-hook-v2"}

    monkeypatch.setattr(gateway, "build_context_package_from_config", fake_from_config)

    package = gateway.build_context_package("codex", "session-start", {})

    assert package["status"] == "ok"
    assert len(captured_config) == 1
    cfg = captured_config[0]
    assert cfg.project_canonical["workbot"] == canonical_override
    assert cfg.project_runtime_root["workbot"] == runtime_override
