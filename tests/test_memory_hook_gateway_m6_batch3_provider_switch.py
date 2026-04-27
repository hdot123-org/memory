#!/usr/bin/env python3
"""M6 Batch-3 tests: legacy/external-core switch and shadow-run."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from workspace.tools import memory_hook_gateway as gateway


def test_resolve_core_builder_defaults_to_legacy():
    provider, builder, errors = gateway._resolve_core_builder("legacy")
    assert provider == "legacy"
    assert callable(builder)
    assert errors == []


def test_resolve_core_builder_fallbacks_to_legacy_when_external_load_fails(monkeypatch):
    monkeypatch.setattr(
        gateway,
        "_load_external_core_builder",
        lambda: (_ for _ in ()).throw(RuntimeError("external unavailable")),
    )

    provider, builder, errors = gateway._resolve_core_builder("external-core")
    assert provider == "legacy"
    assert builder is gateway.build_context_package_core
    assert any("fallback to legacy" in err for err in errors)


def test_build_context_package_records_provider_and_shadow_run(monkeypatch):
    class FakeBusinessPolicy:
        def project_map_refs(self):
            return []

        def get_required_canonical(self):
            return []

        def get_project_canonical(self):
            return {"workbot": gateway.WORKSPACE_ROOT / "memory" / "kb" / "projects" / "workbot.md"}

        def get_project_runtime_root(self):
            return {"workbot": gateway.WORKSPACE_ROOT / "projects"}

        def get_global_canonical(self):
            return []

    monkeypatch.setattr(gateway, "_get_gateway_business_policy", lambda: FakeBusinessPolicy())
    monkeypatch.setattr(gateway, "_discover_cwd", lambda payload: gateway.WORKSPACE_ROOT)
    monkeypatch.setattr(gateway, "determine_project_scope", lambda cwd: "workbot")
    monkeypatch.setenv("MEMORY_HOOK_CORE_PROVIDER", "legacy")
    monkeypatch.setenv("MEMORY_HOOK_SHADOW_RUN", "1")

    call_count = [0]

    def fake_from_config(config):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"status": "ok", "validation_errors": [], "system_context": {}}
        return {"status": "degraded", "validation_errors": ["shadow"], "system_context": {}}

    monkeypatch.setattr(gateway, "build_context_package_from_config", fake_from_config)

    package = gateway.build_context_package("codex", "session-start", {})

    assert package["system_context"]["core_provider"] == "legacy"
    assert package["system_context"]["core_provider_requested"] == "legacy"
    shadow = package["system_context"]["shadow_run"]
    assert shadow["provider"] == "external-core"
    assert shadow["ok"] is True
    assert shadow["status"] == "degraded"
    assert shadow["validation_error_count"] == 1
