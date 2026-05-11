"""Tests for adapter.toml structured migration transforms.

Covers:
- Same-version identity transform preserves all fields
- Known version pairs: all original fields retained + necessary fields added
- Unknown version pairs: raises ValueError with consistent error message
"""
from __future__ import annotations

import pytest

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.tools.adapter_toml_schema import (
    _MIGRATION_TRANSFORMS,
    _apply_migration_transforms,
    _noop_transform,
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdapterTomlStructured:
    """Structured migration transform tests."""

    def test_noop_transform_identity_preserves_fields(self) -> None:
        """Same-version identity transform does not lose any fields."""
        data = {
            "core": {
                "version": CURRENT_MEMORY_VERSION,
                "adapter": "default",
            },
            "policy": {
                "legality_source_policy": "map-only",
                "registration_commit_policy": "same-commit",
                "registration_commit_phase": "post",
            },
            "routing": {
                "project_name": "test-project",
                "project_scope": "full",
                "host": "codex",
                "canonical_files": ["CANONICAL.md", "PLAN.md"],
                "artifact_root": "/tmp/artifacts",
            },
        }
        result = _apply_migration_transforms(data, CURRENT_MEMORY_VERSION, CURRENT_MEMORY_VERSION)
        assert result == data, "Identity transform should return data unchanged"

    def test_noop_transform_is_registered(self) -> None:
        """The noop transform must be registered in _MIGRATION_TRANSFORMS."""
        key = (CURRENT_MEMORY_VERSION, CURRENT_MEMORY_VERSION)
        assert key in _MIGRATION_TRANSFORMS
        assert _MIGRATION_TRANSFORMS[key] is _noop_transform

    def test_known_version_v010_to_current_preserves_legacy_fields(self) -> None:
        """0.1.0 -> CURRENT transform preserves all legacy adapter fields."""
        legacy_data = {
            "adapter": {
                "version": "0.1.0",
                "adapter": "workbot",
                "project_name": "my-project",
                "project_scope": "wide",
                "host": "claude",
                "canonical_files": ["PLAN.md"],
                "artifact_root": "/artifacts",
                "legality_source_policy": "strict",
                "registration_commit_policy": "pre",
                "registration_commit_phase": "early",
            }
        }
        result = _apply_migration_transforms(legacy_data, "0.1.0", CURRENT_MEMORY_VERSION)
        # Should produce canonical layout with core/policy/routing
        assert "core" in result
        assert "routing" in result
        assert "policy" in result

        # Routing fields preserved
        assert result["routing"]["project_name"] == "my-project"
        assert result["routing"]["project_scope"] == "wide"
        assert result["routing"]["host"] == "claude"
        assert result["routing"]["canonical_files"] == ["PLAN.md"]
        assert result["routing"]["artifact_root"] == "/artifacts"

        # Policy fields preserved
        assert result["policy"]["legality_source_policy"] == "strict"
        assert result["policy"]["registration_commit_policy"] == "pre"
        assert result["policy"]["registration_commit_phase"] == "early"

        # Version updated
        assert result["core"]["version"] == CURRENT_MEMORY_VERSION
        assert result["core"]["adapter"] == "workbot"

    def test_known_version_canonical_layout_already(self) -> None:
        """When already in canonical layout, transform just updates version."""
        canonical_data = {
            "core": {
                "version": "0.1.0",
                "adapter": "default",
            },
            "policy": {
                "legality_source_policy": "map-only",
            },
            "routing": {
                "project_name": "proj",
                "project_scope": "full",
                "host": "factory",
            },
        }
        result = _apply_migration_transforms(canonical_data, "0.1.0", CURRENT_MEMORY_VERSION)
        assert result["core"]["version"] == CURRENT_MEMORY_VERSION
        assert result["routing"]["project_name"] == "proj"
        assert result["routing"]["project_scope"] == "full"
        assert result["routing"]["host"] == "factory"
        assert result["policy"]["legality_source_policy"] == "map-only"

    def test_unknown_version_raises_valueerror(self) -> None:
        """Unknown version pair raises ValueError with descriptive message."""
        data = {"adapter": {"version": "9.9.9"}}
        with pytest.raises(ValueError) as excinfo:
            _apply_migration_transforms(data, "9.9.9", "10.0.0")

        message = str(excinfo.value)
        assert "No migration transform registered" in message
        assert "9.9.9" in message
        assert "10.0.0" in message

    def test_unknown_version_partial_match_raises(self) -> None:
        """Partial version match (one side known) still raises ValueError."""
        data = {"adapter": {"version": "0.1.0"}}
        with pytest.raises(ValueError) as excinfo:
            _apply_migration_transforms(data, "0.1.0", "9.9.9")

        message = str(excinfo.value)
        assert "No migration transform registered" in message

    def test_transform_registry_not_empty(self) -> None:
        """The transform registry must have at least one entry."""
        assert len(_MIGRATION_TRANSFORMS) >= 2  # noop + at least one real migration
