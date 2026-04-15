#!/usr/bin/env python3
"""M6 Batch-3 tests: adapter directory split and rollback drill."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from workspace.tools import memory_hook_gateway as gateway
from workspace.tools import memory_hook_provider_rollback as rollback
from workspace.tools.memory_hook_adapters.workbot_policy import WorkbotGatewayBusinessPolicy


def test_gateway_builds_workbot_policy_adapter():
    policy = gateway._build_gateway_business_policy()
    assert isinstance(policy, WorkbotGatewayBusinessPolicy)


def test_rollback_drill_reports_pass_when_legacy_available(monkeypatch):
    def fake_resolve(provider: str, *, allow_fallback: bool = True):
        if provider == "external-core":
            return "legacy", gateway.build_context_package_core, ["external missing"]
        if provider == "legacy":
            return "legacy", gateway.build_context_package_core, []
        return "legacy", gateway.build_context_package_core, []

    monkeypatch.setattr(rollback.gateway, "_resolve_core_builder", fake_resolve)
    monkeypatch.setenv("MEMORY_HOOK_CORE_PROVIDER", "external-core")

    result = rollback.run_rollback_drill()

    assert result["status"] == "passed"
    assert result["requested_provider"] == "external-core"
    assert result["external_probe_provider"] == "legacy"
    assert result["legacy_probe_provider"] == "legacy"


def test_rollback_drill_reports_failed_when_legacy_unavailable(monkeypatch):
    def fake_resolve(provider: str, *, allow_fallback: bool = True):
        return "external-core", gateway.build_context_package_core, ["legacy unavailable"]

    monkeypatch.setattr(rollback.gateway, "_resolve_core_builder", fake_resolve)

    result = rollback.run_rollback_drill()

    assert result["status"] == "failed"
    assert result["legacy_probe_provider"] == "external-core"


def test_rollback_main_exit_code_tracks_status(monkeypatch):
    monkeypatch.setattr(rollback, "run_rollback_drill", lambda: {"status": "failed"})
    assert rollback.main() == 1
