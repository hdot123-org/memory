#!/usr/bin/env python3
"""M5 tests: adapter slimming + core-owned package assembly."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from workspace.tools import memory_hook_gateway as gateway
from workspace.tools.memory_hook_core import build_context_package_core


def _base_core_kwargs(tmp_path: Path) -> dict[str, Any]:
    project_file = tmp_path / "workbot.md"
    project_file.write_text("# workbot\n", encoding="utf-8")
    hook_contract = tmp_path / "hook-contract.md"
    hook_contract.write_text("# hook\n", encoding="utf-8")

    return {
        "host": "codex",
        "event": "stop",
        "payload": {},
        "cwd": tmp_path,
        "project_scope": "workbot",
        "workspace_root": tmp_path,
        "repo_root": tmp_path,
        "required_canonical": [],
        "project_canonical": {"workbot": project_file},
        "project_runtime_root": {"workbot": tmp_path / "projects"},
        "global_canonical": [],
        "project_map_governance": tmp_path / "governance.md",
        "event_log": tmp_path / "events.jsonl",
        "legality_source_policy": "active-legal-map-only",
        "registration_commit_policy": "required-after-absorption-complete",
        "registration_commit_phase": "declared-not-enforced",
        "project_map_refs": [],
        "extract_excerpt_fn": lambda _: [],
        "now_iso_fn": lambda: "2026-01-01T00:00:00+08:00",
        "write_targets_fn": lambda: {"fact": "fact", "system_error": "err", "invalid_memory": "invalid"},
        "validate_project_map_fn": lambda: [],
        "validate_unique_legal_system_contract_fn": lambda: [],
        "policy_validate_fn": lambda _: [],
        "get_policy_pack_fn": lambda _: {"policies": {"registration_phase": "declared-not-enforced"}},
        "governance_frozen_tuple_errors_fn": lambda: [],
        "event_contract_blocker_errors_fn": lambda: [],
        "git_registration_probe_fn": lambda event, payload: {
            "status": "committed-coupled",
            "gate_event": "stop",
            "probe_ok": True,
        },
        "truth_basis_for_scope_fn": lambda _: {
            "policy": "source-authority-evidence-conflict",
            "refs": [str(project_file)],
            "global_refs": [],
            "project_ref": str(project_file),
            "source_refs": [],
            "authority_refs": [],
            "evidence_refs": [],
            "conflict_status": ["resolved"],
            "errors": [],
            "validation": "pass",
        },
        "decision_refs_for_scope_fn": lambda _: [],
        "lesson_refs_for_scope_fn": lambda _: [],
        "docs_refs_for_scope_fn": lambda _: [],
        "hook_contract_path": hook_contract,
        "surface_id": "surface-x",
        "workspace_id": "workspace-y",
    }


class TestM5GatewayAssemblyOnly:
    def test_build_context_package_is_core_assembly_call(self, monkeypatch):
        captured_config: list[Any] = []
        sentinel = {"status": "ok", "schema_version": "wb-hook-v2", "marker": "from-core"}

        monkeypatch.setattr(gateway, "_discover_cwd", lambda payload: gateway.WORKSPACE_ROOT)
        monkeypatch.setattr(gateway, "determine_project_scope", lambda cwd: "workbot")

        def fake_from_config(config):
            captured_config.append(config)
            return sentinel

        monkeypatch.setattr(gateway, "build_context_package_from_config", fake_from_config)

        result = gateway.build_context_package("codex", "session-start", {"task_ref": "T1"})

        assert result is sentinel
        assert len(captured_config) == 1
        cfg = captured_config[0]
        assert cfg.host == "codex"
        assert cfg.event == "session-start"
        assert cfg.project_scope == "workbot"
        assert cfg.validate_project_map_fn is gateway.validate_project_map_files
        assert cfg.truth_basis_for_scope_fn is gateway.truth_basis_for_scope
        assert cfg.write_targets_fn is gateway.write_targets


class TestM5CoreStatusMatrix:
    def test_core_returns_ok_when_all_validations_pass(self, tmp_path: Path):
        package = build_context_package_core(**_base_core_kwargs(tmp_path))

        assert package["status"] == "ok"
        assert package["validation_errors"] == []
        assert package["task_context"]["surface_id"] == "surface-x"
        assert package["task_context"]["workspace_id"] == "workspace-y"
        assert package["system_context"]["registration_commit_enforcement_result"] == "not-enforced"

    def test_core_degrades_when_registration_enforcement_fails(self, tmp_path: Path):
        kwargs = _base_core_kwargs(tmp_path)
        kwargs["get_policy_pack_fn"] = lambda _: {"policies": {"registration_phase": "enforced"}}
        kwargs["git_registration_probe_fn"] = lambda event, payload: {
            "status": "pending-commit",
            "gate_event": "stop",
            "probe_ok": True,
        }

        package = build_context_package_core(**kwargs)

        assert package["status"] == "degraded"
        assert package["system_context"]["registration_commit_enforced"] is True
        assert package["system_context"]["registration_commit_enforcement_result"] == "failed"
        assert any("registration commit enforcement failed" in err for err in package["validation_errors"])

    def test_core_degrades_with_policy_pack_resolution_failure_without_crash(self, tmp_path: Path):
        kwargs = _base_core_kwargs(tmp_path)

        def _raise_policy_pack(_: str) -> dict[str, Any]:
            raise RuntimeError("policy backend unavailable")

        kwargs["get_policy_pack_fn"] = _raise_policy_pack

        package = build_context_package_core(**kwargs)

        assert package["status"] == "degraded"
        assert any("policy-pack resolution failed" in err for err in package["validation_errors"])
        assert package["system_context"]["registration_commit_enforcement_result"] == "not-enforced"

    def test_core_degrades_when_required_canonical_missing(self, tmp_path: Path):
        kwargs = _base_core_kwargs(tmp_path)
        missing_path = tmp_path / "missing-required.md"
        kwargs["required_canonical"] = [missing_path]

        package = build_context_package_core(**kwargs)

        assert package["status"] == "degraded"
        assert str(missing_path) in package["missing_paths"]

    def test_core_evidence_refs_are_injected_and_not_hardcoded(self, tmp_path: Path):
        kwargs = _base_core_kwargs(tmp_path)
        kwargs["core_evidence_refs"] = ["/tmp/evidence-A", "/tmp/evidence-B"]

        package = build_context_package_core(**kwargs)

        assert "/tmp/evidence-A" in package["evidence_refs"]
        assert "/tmp/evidence-B" in package["evidence_refs"]
        assert all("workbot-memory-system.md" not in ref for ref in package["evidence_refs"])
