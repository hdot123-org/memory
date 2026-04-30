#!/usr/bin/env python3
"""M7 P4 edge-case tests for PolicyRegistryImpl policy-pack loading and conflict resolution.

Covers:
- Malformed / missing / empty policy pack files (silent fallback)
- Extra unknown fields in policy packs (ignored gracefully)
- Scope validation (allowed scopes, inheritance as declarative metadata only)
- Conflict resolution strategies (fail-fast, prefer-strict, preserve-and-escalate)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running via pytest from repo root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memory_core.tools.memory_hook_impls import PolicyRegistryImpl

# ---------------------------------------------------------------------------
# TestPolicyPackLoading
# ---------------------------------------------------------------------------


class TestPolicyPackLoading:
    """Edge cases around dynamic policy-pack file loading."""

    def test_malformed_json_silent_fallback(self, tmp_path: Path) -> None:
        """Malformed JSON must not crash; registry falls back to DEFAULT_POLICIES."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ invalid json !!!", encoding="utf-8")

        reg = PolicyRegistryImpl(policy_pack_path=bad_file)

        # Should still have the built-in defaults
        assert reg.get_policy("kb_write_mode") == PolicyRegistryImpl.DEFAULT_POLICIES["kb_write_mode"]
        # Schema version stays at the class default
        assert reg._schema_version == PolicyRegistryImpl.SCHEMA_VERSION

    def test_missing_policy_pack_graceful_degradation(self, tmp_path: Path) -> None:
        """Pointing to a non-existent file must not crash; defaults are used."""
        ghost = tmp_path / "does-not-exist.json"
        assert not ghost.exists()

        reg = PolicyRegistryImpl(policy_pack_path=ghost)

        assert reg.get_policy("kb_write_mode") == PolicyRegistryImpl.DEFAULT_POLICIES["kb_write_mode"]
        assert reg._schema_version == PolicyRegistryImpl.SCHEMA_VERSION

    def test_empty_policy_pack_file(self, tmp_path: Path) -> None:
        """An empty JSON object {} must not crash; defaults are preserved."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}", encoding="utf-8")

        reg = PolicyRegistryImpl(policy_pack_path=empty_file)

        # All defaults intact
        for key, value in PolicyRegistryImpl.DEFAULT_POLICIES.items():
            assert reg.get_policy(key) == value

    def test_policy_pack_extra_fields_ignored(self, tmp_path: Path) -> None:
        """Unknown top-level keys in the JSON must not break loading."""
        pack_file = tmp_path / "extra.json"
        pack_file.write_text(
            json.dumps(
                {
                    "schema_version": "m7-p4-v1",
                    "policies": {"legality_source": "custom-legal"},
                    "conflict_strategies": {"legality_source": "fail-fast"},
                    "unknown_field": "should be ignored",
                    "another_unknown": [1, 2, 3],
                    "nested": {"deep": {"value": True}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        reg = PolicyRegistryImpl(policy_pack_path=pack_file)

        # Known fields applied
        assert reg._schema_version == "m7-p4-v1"
        assert reg.get_policy("legality_source") == "custom-legal"
        # Extra fields did not cause errors (no exception raised)


# ---------------------------------------------------------------------------
# TestScopeValidation
# ---------------------------------------------------------------------------


class TestScopeValidation:
    """Scope validation and inheritance behavior."""

    def test_valid_scope_accepted(self, tmp_path: Path) -> None:
        """A scope present in allowed_scopes must pass validation."""
        reg = PolicyRegistryImpl(
            allowed_scopes={"workbot", "neutral"},
        )

        errors = reg.validate({"project_scope": "workbot"})
        assert errors == []

    def test_scope_inheritance_declarative_only(self, tmp_path: Path) -> None:
        """Child scope should get an 'inherits' key but policies are NOT merged from parent."""
        parent_policies = {
            "legality_source": "parent-legal",
            "kb_write_mode": "parent-write",
        }
        reg = PolicyRegistryImpl(
            allowed_scopes={"parent", "child"},
            scope_inherits={"child": "parent"},
            default_policies=parent_policies,
        )

        pack = reg.get_policy_pack("child")

        # The inherits key must be present (declarative metadata)
        assert pack.get("inherits") == "parent"

        # Policies are NOT merged from parent — they are just the registry's
        # current _policies dict (no parent-scope overlay).
        # In other words, get_policy_pack("child") returns the same policies as
        # get_policy_pack("parent") because there is no actual merge logic.
        parent_pack = reg.get_policy_pack("parent")
        assert pack["policies"] == parent_pack["policies"]


# ---------------------------------------------------------------------------
# TestConflictResolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    """Conflict resolution strategy behavior."""

    def test_fail_fast_strategy_raises(self, tmp_path: Path) -> None:
        """fail-fast strategy must raise ValueError when values conflict."""
        reg = PolicyRegistryImpl()

        with pytest.raises(ValueError, match="conflict on.*strategy=fail-fast"):
            reg.resolve_conflict("legality_source", ["value-a", "value-b"], "fail-fast")

    def test_prefer_strict_strategy(self, tmp_path: Path) -> None:
        """prefer-strict must return the stricter value for known policy keys."""
        reg = PolicyRegistryImpl()

        # For kb_overwrite_allowed, "false" is stricter than "true"
        result = reg.resolve_conflict(
            "kb_overwrite_allowed", ["true", "false"], "prefer-strict"
        )
        assert result == "false"

        # For registration_phase, "declared-not-enforced" is stricter
        result2 = reg.resolve_conflict(
            "registration_phase", ["enforced", "declared-not-enforced"], "prefer-strict"
        )
        assert result2 == "declared-not-enforced"

    def test_preserve_and_escalate_strategy(self, tmp_path: Path) -> None:
        """preserve-and-escalate must preserve the first value (no drop)."""
        reg = PolicyRegistryImpl()

        result = reg.resolve_conflict(
            "registration_commit", ["keep-this", "drop-this"], "preserve-and-escalate"
        )
        assert result == "keep-this"
