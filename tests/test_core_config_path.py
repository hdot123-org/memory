#!/usr/bin/env python3
"""Tests for build_context_package_from_config and build_context_package_simple.

Covers:
- build_context_package_from_config equivalence with kwargs path
- build_context_package_simple basic behavior
- Equivalence between simple and full API paths
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _noop(*_a: Any, **_k: Any) -> Any:
    """Generic no-op callable for callback fields."""
    return None


def _make_minimal_kwargs(tmp_path: Path) -> dict[str, Any]:
    """Build minimal kwargs for build_context_package_core."""
    base = tmp_path / "memory_core"
    base.mkdir(parents=True, exist_ok=True)

    # Create files that the core builder will try to read
    (base / "NOW.md").write_text("# NOW\n\n## Summary\n- test\n", encoding="utf-8")
    (base / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (base / "memory").mkdir(exist_ok=True)
    (base / "memory" / "kb").mkdir(exist_ok=True)
    (base / "memory" / "kb" / "INDEX.md").write_text("# KB Index\n", encoding="utf-8")
    (base / "memory" / "docs").mkdir(exist_ok=True)
    (base / "memory" / "docs" / "INDEX.md").write_text("# Docs Index\n", encoding="utf-8")
    (base / "projects").mkdir(exist_ok=True)
    (base / "projects" / "workbot").mkdir(exist_ok=True)

    return {
        # Group 1: Environment
        "host": "codex",
        "event": "session-start",
        "payload": {"session_id": "test-123"},
        "cwd": base,
        "project_scope": "workbot",
        "workspace_root": base,
        "repo_root": base,
        # Group 2: Paths
        "required_canonical": [],
        "project_canonical": {"workbot": base / "projects" / "workbot" / "PROJECT.md"},
        "project_runtime_root": {},
        "global_canonical": [],
        "project_map_governance": base / "governance.md",
        "event_log": base / "events.jsonl",
        "hook_contract_path": base / "contract.md",
        # Group 3: Policy
        "legality_source_policy": "map-only",
        "registration_commit_policy": "atomic",
        "registration_commit_phase": "declared-not-enforced",
        "project_map_refs": [],
        "surface_id": "surf-1",
        "workspace_id": "ws-1",
        "governance_blocker_scopes": None,
        "event_contract_blocker_scopes": None,
        "core_evidence_refs": None,
        # Group 4: Callbacks
        "extract_excerpt_fn": lambda p: ["test"] if p.exists() else [],
        "now_iso_fn": lambda: "2025-01-01T00:00:00+08:00",
        "write_targets_fn": lambda: {"fact": "test"},
        "validate_project_map_fn": lambda: [],
        "validate_unique_legal_system_contract_fn": lambda: [],
        "policy_validate_fn": lambda ctx: [],
        "get_policy_pack_fn": lambda s: {"policies": {}},
        "governance_frozen_tuple_errors_fn": lambda: [],
        "event_contract_blocker_errors_fn": lambda: [],
        "git_registration_probe_fn": lambda e, p: {"status": "pending"},
        "truth_basis_for_scope_fn": lambda s: {
            "refs": [],
            "errors": [],
            "validation": "pass",
            "project_ref": "",
            "source_refs": [],
            "authority_refs": [],
            "evidence_refs": [],
            "conflict_status": [],
            "policy": "test",
        },
        "decision_refs_for_scope_fn": lambda s: [],
        "lesson_refs_for_scope_fn": lambda s: [],
        "docs_refs_for_scope_fn": lambda s: [],
    }


# ---------------------------------------------------------------------------
# build_context_package_from_config tests
# ---------------------------------------------------------------------------


class TestBuildFromConfig:
    """Validate build_context_package_from_config behavior."""

    def test_produces_same_result_as_kwargs_path(self, tmp_path: Path) -> None:
        """build_context_package_from_config(config) == build_context_package_core(**kwargs)."""
        from memory_core.tools.memory_hook_config import CoreConfig
        from memory_core.tools.memory_hook_core import (
            build_context_package_core,
            build_context_package_from_config,
        )

        kwargs = _make_minimal_kwargs(tmp_path)
        config = CoreConfig(**kwargs)

        result_from_config = build_context_package_from_config(config)
        result_from_kwargs = build_context_package_core(**kwargs)

        # Exclude generated_at — it may differ by microseconds
        result_from_config.pop("generated_at", None)
        result_from_kwargs.pop("generated_at", None)

        assert result_from_config == result_from_kwargs

    def test_status_ok_when_all_paths_valid(self, tmp_path: Path) -> None:
        """Returns status=ok with valid minimal config."""
        from memory_core.tools.memory_hook_config import CoreConfig
        from memory_core.tools.memory_hook_core import build_context_package_from_config

        kwargs = _make_minimal_kwargs(tmp_path)
        # Create the project canonical file so it exists
        proj_file = kwargs["project_canonical"]["workbot"]
        proj_file.parent.mkdir(parents=True, exist_ok=True)
        proj_file.write_text("# Project\n", encoding="utf-8")

        config = CoreConfig(**kwargs)
        result = build_context_package_from_config(config)

        assert result["status"] == "ok"
        assert result["missing_paths"] == []

    def test_status_degraded_on_missing_canonical(self, tmp_path: Path) -> None:
        """Returns status=degraded when required_canonical paths don't exist."""
        from memory_core.tools.memory_hook_config import CoreConfig
        from memory_core.tools.memory_hook_core import build_context_package_from_config

        kwargs = _make_minimal_kwargs(tmp_path)
        # Add a non-existent required canonical path
        kwargs["required_canonical"] = [tmp_path / "nonexistent" / "file.md"]

        config = CoreConfig(**kwargs)
        result = build_context_package_from_config(config)

        assert result["status"] == "degraded"
        assert len(result["missing_paths"]) > 0

    def test_config_rejects_invalid_host(self, tmp_path: Path) -> None:
        """CoreConfig rejects invalid host in __post_init__."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs["host"] = "bad-host"

        with pytest.raises(ValueError, match="host must be"):
            CoreConfig(**kwargs)

    def test_config_via_from_gateway_kwargs(self, tmp_path: Path) -> None:
        """CoreConfig.from_gateway_kwargs produces equivalent config."""
        from memory_core.tools.memory_hook_config import CoreConfig
        from memory_core.tools.memory_hook_core import (
            build_context_package_core,
            build_context_package_from_config,
        )

        kwargs = _make_minimal_kwargs(tmp_path)
        config = CoreConfig.from_gateway_kwargs(**kwargs)

        result_from_config = build_context_package_from_config(config)
        result_from_kwargs = build_context_package_core(**kwargs)

        result_from_config.pop("generated_at", None)
        result_from_kwargs.pop("generated_at", None)

        assert result_from_config == result_from_kwargs


# ---------------------------------------------------------------------------
# build_context_package_simple tests
# ---------------------------------------------------------------------------


class TestBuildContextPackageSimple:
    """Validate build_context_package_simple simplified API."""

    def test_returns_dict_with_status(self, tmp_path: Path) -> None:
        """Returns a dict with at least 'status' key."""
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        result = build_context_package_simple("codex", "session-start", {})

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ("ok", "degraded")

    def test_works_with_empty_payload(self, tmp_path: Path) -> None:
        """Works with payload=None (defaults to empty dict)."""
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        result_none = build_context_package_simple("codex", "session-start", None)
        result_empty = build_context_package_simple("codex", "session-start", {})

        assert isinstance(result_none, dict)
        assert "status" in result_none
        # Both should produce same status (since payload doesn't affect core logic
        # when cwd falls back to environment/repo root)
        assert result_none["status"] == result_empty["status"]

    def test_rejects_invalid_host(self) -> None:
        """Raises ValueError for invalid host."""
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        with pytest.raises(ValueError):
            build_context_package_simple("invalid-host", "session-start", {})

    def test_accepts_claude_host(self) -> None:
        """Accepts 'claude' as valid host."""
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        result = build_context_package_simple("claude", "session-start", {})
        assert isinstance(result, dict)
        assert result.get("host") == "claude"

    def test_returns_schema_version(self) -> None:
        """Result includes schema_version field."""
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        result = build_context_package_simple("codex", "session-start", {})
        assert result.get("schema_version") == "context-package-v1"

    def test_contains_paths(self) -> None:
        """Result contains paths dict (v1 format)."""
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        result = build_context_package_simple("codex", "session-start", {})
        assert isinstance(result.get("paths"), dict)


# ---------------------------------------------------------------------------
# Equivalence tests
# ---------------------------------------------------------------------------


class TestEquivalence:
    """Validate equivalence between different API entry points."""

    def test_simple_equals_full_api(self) -> None:
        """build_context_package_simple(h, e, p) == convert_to_v1(build_context_package(h, e, p))."""
        from memory_core.tools.memory_hook_gateway import (
            build_context_package,
            build_context_package_simple,
        )
        from memory_core.tools.memory_hook_schema import convert_to_v1

        payload = {"session_id": "eq-test-1"}
        result_simple = build_context_package_simple("codex", "session-start", payload)
        result_full_v1 = convert_to_v1(build_context_package("codex", "session-start", payload))

        # Exclude generated_at — may differ by microseconds
        result_simple.pop("generated_at", None)
        result_full_v1.pop("generated_at", None)

        assert result_simple == result_full_v1

    def test_simple_equals_full_with_empty_payload(self) -> None:
        """Equivalence holds with empty payload via convert_to_v1."""
        from memory_core.tools.memory_hook_gateway import (
            build_context_package,
            build_context_package_simple,
        )
        from memory_core.tools.memory_hook_schema import convert_to_v1

        result_simple = build_context_package_simple("codex", "session-start", None)
        result_full_v1 = convert_to_v1(build_context_package("codex", "session-start", {}))

        result_simple.pop("generated_at", None)
        result_full_v1.pop("generated_at", None)

        assert result_simple == result_full_v1
