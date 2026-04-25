#!/usr/bin/env python3
"""M7 baseline gates for independent memory repository."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from workspace.tools.memory_hook_gateway import build_context_package
from workspace.tools.memory_hook_impls import PolicyRegistryImpl


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def test_runtime_smoke_status_ok() -> None:
    package = build_context_package("codex", "session-start", {})
    assert package.get("status") == "ok"
    assert package.get("validation_errors") == []


def test_no_legacy_workbot_absolute_paths_in_workspace() -> None:
    legacy_root = "/Users/busiji/workbot"
    offenders: list[str] = []
    for path in (repo_root / "workspace").rglob("*"):
        if not path.is_file():
            continue
        text = _read_text(path)
        if legacy_root in text:
            offenders.append(str(path))
    assert offenders == []


def test_project_map_contract_markers_present() -> None:
    project_map_index = _read_text(repo_root / "workspace" / "project-map" / "INDEX.md")
    legal_core_map = _read_text(repo_root / "workspace" / "project-map" / "legal-core-map.md")
    ingestion_registry = _read_text(repo_root / "workspace" / "project-map" / "ingestion-registry-map.md")
    governance = _read_text(
        repo_root / "workspace" / "memory" / "kb" / "global" / "workbot-project-map-governance.md"
    )

    assert "唯一合法入口" in project_map_index
    assert "active-legal" in legal_core_map
    assert "incoming-raw" in ingestion_registry
    assert "`absorbed`" in ingestion_registry and "`retired`" in ingestion_registry
    assert "未经过唯一真相系统清洗" in governance


def test_policy_registry_default_layer_is_not_workbot_bound() -> None:
    registry = PolicyRegistryImpl(policy_pack_path=repo_root / "workspace" / "memory" / "kb" / "global" / "__missing__.json")
    package = registry.get_policy_pack("generic-scope")

    assert package["scope"] == "generic-scope"
    assert "inherits" not in package
    assert package["policies"].get("legality_source") is None
    assert package["policies"].get("registration_commit") is None
