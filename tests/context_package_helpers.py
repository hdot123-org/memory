#!/usr/bin/env python3
"""Shared helpers for context package tests.

Extracted from test_memory_hook_core.py and test_core_config_path.py
to eliminate 98% AST duplicate _make_minimal_kwargs blocks (issue #673).
"""


from pathlib import Path
from typing import Any


def _make_minimal_kwargs(
    tmp_path: Path, *, create_project_file: bool = False
) -> dict[str, Any]:
    """Build minimal kwargs for build_context_package_core.

    Args:
        tmp_path: pytest tmp_path fixture.
        create_project_file: When True, also create
            projects/workbot/PROJECT.md on disk.  Tests that need the
            file to exist pass True; tests that create it explicitly
            afterwards leave this as False.
    """
    base = tmp_path / "memory_core"
    base.mkdir(parents=True, exist_ok=True)

    # Create files that the core builder will try to read
    (base / "NOW.md").write_text("# NOW\n\n## Summary\n- test\n", encoding="utf-8")
    (base / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (base / "memory").mkdir(exist_ok=True)
    (base / "memory" / "kb").mkdir(exist_ok=True)
    (base / "memory" / "kb" / "INDEX.md").write_text("# KB Index\n", encoding="utf-8")
    (base / "memory" / "docs").mkdir(exist_ok=True)
    (base / "memory" / "docs" / "INDEX.md").write_text(
        "# Docs Index\n", encoding="utf-8"
    )
    (base / "projects").mkdir(exist_ok=True)
    (base / "projects" / "workbot").mkdir(exist_ok=True)

    if create_project_file:
        # Create project canonical file so it doesn't trigger degraded status
        proj_file = base / "projects" / "workbot" / "PROJECT.md"
        proj_file.write_text("# Project\n", encoding="utf-8")

    return {
        # Group 1: Environment
        "host": "factory",
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
