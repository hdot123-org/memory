#!/usr/bin/env python3
"""Tests for VAL-TEL-001/002/003: missing canonical files severity fix.

Verifies:
- VAL-TEL-001: Missing canonical files (truth-model.md, memory-system.md,
  memory-routing.md) no longer trigger degraded status.
- VAL-TEL-002: Missing canonical files appear in warnings, not errors.
- VAL-TEL-003: Real errors still produce degraded status.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MEMORY_HOOK_ADAPTER", "default")


def _make_minimal_kwargs(tmp_path: Path) -> dict[str, Any]:
    """Build minimal kwargs for build_context_package_core."""
    base = tmp_path / "memory_core"
    base.mkdir(parents=True, exist_ok=True)

    (base / "NOW.md").write_text("# NOW\n\n## Summary\n- test\n", encoding="utf-8")
    (base / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (base / "memory").mkdir(exist_ok=True)
    (base / "memory" / "kb").mkdir(exist_ok=True)
    (base / "memory" / "kb" / "INDEX.md").write_text("# KB Index\n", encoding="utf-8")
    (base / "memory" / "docs").mkdir(exist_ok=True)
    (base / "memory" / "docs" / "INDEX.md").write_text("# Docs Index\n", encoding="utf-8")
    (base / "projects").mkdir(exist_ok=True)
    (base / "projects" / "workbot").mkdir(exist_ok=True)

    # Create project canonical file so it doesn't trigger degraded status
    proj_file = base / "projects" / "workbot" / "PROJECT.md"
    proj_file.write_text("# Project\n", encoding="utf-8")

    return {
        "host": "factory",
        "event": "session-start",
        "payload": {"session_id": "test-123"},
        "cwd": base,
        "project_scope": "workbot",
        "workspace_root": base,
        "repo_root": base,
        "required_canonical": [],
        "project_canonical": {"workbot": base / "projects" / "workbot" / "PROJECT.md"},
        "project_runtime_root": {},
        "global_canonical": [],
        "project_map_governance": base / "governance.md",
        "event_log": base / "events.jsonl",
        "hook_contract_path": base / "contract.md",
        "legality_source_policy": "map-only",
        "registration_commit_policy": "atomic",
        "registration_commit_phase": "declared-not-enforced",
        "project_map_refs": [],
        "surface_id": "surf-1",
        "workspace_id": "ws-1",
        "governance_blocker_scopes": None,
        "event_contract_blocker_scopes": None,
        "core_evidence_refs": None,
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


class TestMissingCanonicalFilesSeverityFix:
    """VAL-TEL-001/002/003: canonical files missing should be warnings, not errors."""

    def test_missing_canonical_files_status_ok(self, tmp_path: Path) -> None:
        """VAL-TEL-001: When only canonical files are missing, status should be ok."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path)
        # Create the project file so it doesn't trigger degraded
        proj_file = kwargs["project_canonical"]["workbot"]
        proj_file.parent.mkdir(parents=True, exist_ok=True)
        proj_file.write_text("# Project\n", encoding="utf-8")

        # Add the three canonical files that are typically missing in consumer projects
        canonical_dir = tmp_path / "memory_core" / "memory" / "kb" / "global"
        kwargs["required_canonical"] = [
            canonical_dir / "truth-model.md",
            canonical_dir / "memory-system.md",
            canonical_dir / "memory-routing.md",
        ]

        result = build_context_package_core(**kwargs)

        assert result["status"] == "ok", (
            f"Expected status 'ok' when only canonical files are missing, "
            f"got '{result['status']}'"
        )

    def test_missing_canonical_files_in_warnings(self, tmp_path: Path) -> None:
        """VAL-TEL-002: Missing canonical files appear in warnings, not in error lists."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path)
        canonical_dir = tmp_path / "memory_core" / "memory" / "kb" / "global"
        kwargs["required_canonical"] = [
            canonical_dir / "truth-model.md",
            canonical_dir / "memory-system.md",
        ]

        result = build_context_package_core(**kwargs)

        # Missing canonical files should be in warnings
        assert "warnings" in result, "Result should contain a 'warnings' field"
        assert len(result["warnings"]) > 0, "Warnings should contain missing canonical file entries"

        # Missing canonical files should NOT be in missing_paths (which feeds degraded)
        for path_str in result.get("missing_paths", []):
            assert "truth-model.md" not in path_str, (
                "truth-model.md should not be in missing_paths"
            )
            assert "memory-system.md" not in path_str, (
                "memory-system.md should not be in missing_paths"
            )

        # validation_errors should not contain canonical-file-missing entries
        for err in result.get("validation_errors", []):
            assert "truth-model.md" not in err
            assert "memory-system.md" not in err

    def test_real_errors_still_degraded(self, tmp_path: Path) -> None:
        """VAL-TEL-003: Real errors still produce degraded status."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path)
        # Inject a real error via project_map validation
        kwargs["validate_project_map_fn"] = lambda: ["project map validation failed"]

        result = build_context_package_core(**kwargs)

        assert result["status"] == "degraded", (
            f"Expected status 'degraded' when real errors exist, "
            f"got '{result['status']}'"
        )

    def test_non_canonical_missing_still_degraded(self, tmp_path: Path) -> None:
        """Non-canonical missing paths should still trigger degraded status."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path)
        # Add a non-canonical missing file
        kwargs["required_canonical"] = [tmp_path / "some" / "other" / "file.md"]

        result = build_context_package_core(**kwargs)

        assert result["status"] == "degraded", (
            f"Expected status 'degraded' when non-canonical file is missing, "
            f"got '{result['status']}'"
        )
