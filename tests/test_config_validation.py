#!/usr/bin/env python3
"""Tests for CoreConfig __post_init__ validation logic.

Covers validation that is NOT already tested in test_refactoring.py:
- Path type validation for remaining path fields
- Callable type validation for all 13 callback fields
- String non-empty validation for str fields
- Collection type validation for dict/list fields
- Valid construction sanity check
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_minimal_kwargs(tmp_path: Path) -> dict[str, Any]:
    """Build a minimal but complete kwargs dict for CoreConfig."""
    base = tmp_path / "memory_core"
    base.mkdir(parents=True, exist_ok=True)

    def _noop(*_a, **_k):
        return None

    return {
        # Group 1: Environment
        "host": "codex",
        "event": "session-start",
        "payload": {"session_id": "abc"},
        "cwd": base,
        "project_scope": "workbot",
        "workspace_root": base,
        "repo_root": base,
        # Group 2: Paths
        "required_canonical": [],
        "project_canonical": {},
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
        # Group 4: Callbacks
        "extract_excerpt_fn": _noop,
        "now_iso_fn": _noop,
        "write_targets_fn": _noop,
        "validate_project_map_fn": _noop,
        "validate_unique_legal_system_contract_fn": _noop,
        "policy_validate_fn": _noop,
        "get_policy_pack_fn": _noop,
        "governance_frozen_tuple_errors_fn": _noop,
        "event_contract_blocker_errors_fn": _noop,
        "git_registration_probe_fn": _noop,
        "truth_basis_for_scope_fn": _noop,
        "decision_refs_for_scope_fn": _noop,
        "lesson_refs_for_scope_fn": _noop,
        "docs_refs_for_scope_fn": _noop,
    }


# ---------------------------------------------------------------------------
# Path type validation
# ---------------------------------------------------------------------------


class TestPathTypeValidation:
    """Path fields must be Path instances; otherwise TypeError.

    Note: test_refactoring.py already covers workspace_root and repo_root.
    The only remaining Path field with __post_init__ validation is hook_contract_path.
    """

    def test_hook_contract_path_rejects_string(self, tmp_path):
        """Non-Path value for hook_contract_path raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs["hook_contract_path"] = "/not/a/path"

        with pytest.raises(TypeError, match="hook_contract_path must be a Path"):
            CoreConfig(**kwargs)

    def test_hook_contract_path_rejects_none(self, tmp_path):
        """None for hook_contract_path raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs["hook_contract_path"] = None

        with pytest.raises(TypeError, match="hook_contract_path must be a Path"):
            CoreConfig(**kwargs)


# ---------------------------------------------------------------------------
# Callable type validation
# ---------------------------------------------------------------------------

_CALLBACK_FIELD_NAMES = (
    "extract_excerpt_fn",
    "now_iso_fn",
    "write_targets_fn",
    "validate_project_map_fn",
    "validate_unique_legal_system_contract_fn",
    "policy_validate_fn",
    "get_policy_pack_fn",
    "governance_frozen_tuple_errors_fn",
    "event_contract_blocker_errors_fn",
    "git_registration_probe_fn",
    "truth_basis_for_scope_fn",
    "decision_refs_for_scope_fn",
    "lesson_refs_for_scope_fn",
    "docs_refs_for_scope_fn",
)


class TestCallableTypeValidation:
    """Callback fields must be callable; otherwise TypeError."""

    @pytest.mark.parametrize("field_name", _CALLBACK_FIELD_NAMES)
    def test_callback_field_rejects_string(self, tmp_path, field_name):
        """Non-callable string for a callback field raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs[field_name] = "not_a_callable"

        with pytest.raises(TypeError, match=f"{field_name} must be callable"):
            CoreConfig(**kwargs)

    @pytest.mark.parametrize("field_name", _CALLBACK_FIELD_NAMES)
    def test_callback_field_rejects_none(self, tmp_path, field_name):
        """None for a callback field raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs[field_name] = None

        with pytest.raises(TypeError, match=f"{field_name} must be callable"):
            CoreConfig(**kwargs)

    @pytest.mark.parametrize("field_name", _CALLBACK_FIELD_NAMES)
    def test_callback_field_rejects_int(self, tmp_path, field_name):
        """Non-callable int for a callback field raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs[field_name] = 42

        with pytest.raises(TypeError, match=f"{field_name} must be callable"):
            CoreConfig(**kwargs)


# ---------------------------------------------------------------------------
# String non-empty validation
# ---------------------------------------------------------------------------


class TestStringValidation:
    """String fields must be non-empty where required; otherwise ValueError."""

    @pytest.mark.parametrize(
        "field_name",
        ["project_scope", "legality_source_policy",
         "registration_commit_policy", "registration_commit_phase"],
    )
    def test_string_field_rejects_empty(self, tmp_path, field_name):
        """Empty string for a required non-empty string field raises ValueError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs[field_name] = ""

        with pytest.raises(ValueError, match=f"{field_name} must be"):
            CoreConfig(**kwargs)

    def test_host_rejects_empty(self, tmp_path):
        """Empty host raises ValueError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs["host"] = ""

        with pytest.raises(ValueError):
            CoreConfig(**kwargs)


# ---------------------------------------------------------------------------
# Collection type validation
# ---------------------------------------------------------------------------


class TestCollectionTypeValidation:
    """Collection fields must be the expected type; otherwise TypeError."""

    @pytest.mark.parametrize(
        "field_name,bad_value",
        [
            ("required_canonical", "not_a_list"),
            ("required_canonical", ()),
            ("global_canonical", {}),
            ("global_canonical", "not_a_list"),
            ("project_map_refs", "not_a_list"),
            ("project_map_refs", {}),
        ],
    )
    def test_list_field_rejects_non_list(self, tmp_path, field_name, bad_value):
        """Non-list value for a list field raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs[field_name] = bad_value

        with pytest.raises(TypeError, match=f"{field_name} must be a list"):
            CoreConfig(**kwargs)

    @pytest.mark.parametrize(
        "field_name,bad_value",
        [
            ("project_canonical", []),
            ("project_canonical", "not_a_dict"),
            ("project_runtime_root", []),
            ("project_runtime_root", "not_a_dict"),
        ],
    )
    def test_dict_field_rejects_non_dict(self, tmp_path, field_name, bad_value):
        """Non-dict value for a dict field raises TypeError."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs[field_name] = bad_value

        with pytest.raises(TypeError, match=f"{field_name} must be a dict"):
            CoreConfig(**kwargs)


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------


class TestValidConstruction:
    """Valid parameters should construct CoreConfig successfully."""

    def test_valid_params_construct(self, tmp_path):
        """CoreConfig constructs without error when all fields are valid."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        cfg = CoreConfig(**kwargs)

        assert cfg.host == "codex"
        assert cfg.event == "session-start"
        assert isinstance(cfg.cwd, Path)

    def test_valid_params_with_optional_fields(self, tmp_path):
        """CoreConfig accepts optional fields with valid values."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_kwargs(tmp_path)
        kwargs["governance_blocker_scopes"] = ["scope-1"]
        kwargs["event_contract_blocker_scopes"] = ["scope-2"]
        kwargs["core_evidence_refs"] = ["ref-1"]

        cfg = CoreConfig(**kwargs)

        assert cfg.governance_blocker_scopes == ["scope-1"]
        assert cfg.event_contract_blocker_scopes == ["scope-2"]
        assert cfg.core_evidence_refs == ["ref-1"]
