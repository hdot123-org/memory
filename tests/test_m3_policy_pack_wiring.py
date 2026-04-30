#!/usr/bin/env python3
"""M3 policy-pack wiring tests.

Tests cover three areas:
1. Policy-pack injection into PolicyRegistryImpl (the class that owns
   policy loading, SCHEMA_VERSION, DEFAULT_POLICIES, get_policy())
2. Adapter-level policy resolution (workbot vs neutral)
3. Consistency between JSON policy pack and adapter/runtime values

NOTE: GatewayBusinessPolicyConfig currently has a dataclass field-ordering
bug (policy_pack_path with default precedes read_text_if_exists_fn without
default). These tests are written against the intended final shape — they
will pass once Worker 1 fixes the field ordering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running via pytest from repo root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_json(tmp_path: Path) -> Path:
    """Create a temporary JSON policy pack file and return its path."""
    pack = {
        "schema_version": "m3-policy-pack-v1",
        "scope": "test-scope",
        "policies": {
            "legality_source": "test-legal-only",
            "registration_commit": "test-required",
            "kb_write_mode": "test-write-through",
        },
        "conflict_strategies": {
            "legality_source": "fail-fast",
            "default": "preserve-and-escalate",
        },
    }
    dest = tmp_path / "test-policy-pack.json"
    dest.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


@pytest.fixture()
def empty_dir(tmp_path: Path) -> Path:
    """Return an empty temporary directory."""
    return tmp_path


# ---------------------------------------------------------------------------
# TestPolicyPackInjection
# ---------------------------------------------------------------------------

class TestPolicyPackInjection:
    """Verify that PolicyRegistryImpl accepts and resolves policy_pack_path
    through the injection chain: explicit arg > env var > default path >
    graceful degradation.

    PolicyRegistryImpl is the class that owns SCHEMA_VERSION,
    DEFAULT_POLICIES, DEFAULT_POLICY_PACK_PATH, and get_policy().
    """

    def test_config_accepts_policy_pack_path(
        self, temp_json: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PolicyRegistryImpl should accept policy_pack_path as a
        constructor keyword argument and load policies from that file."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        registry = PolicyRegistryImpl(
            allowed_scopes={"test-scope"},
            scope_inherits={},
            policy_pack_path=temp_json,
        )

        # The injected pack overrides "legality_source" from default
        assert registry.get_policy("legality_source") == "test-legal-only"
        assert registry.get_policy("registration_commit") == "test-required"
        assert registry.get_policy("kb_write_mode") == "test-write-through"

    def test_injected_policy_pack_overrides_default(
        self, temp_json: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When policy_pack_path is explicitly set, it must take priority
        over both the env var and the default path."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        # Point env var at a different file — it should be ignored
        env_pack = temp_json.parent / "env-policy-pack.json"
        env_pack.write_text(
            json.dumps({
                "schema_version": "m3-policy-pack-v1",
                "policies": {"legality_source": "env-override"},
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("MEMORY_HOOK_POLICY_PACK_PATH", str(env_pack))

        registry = PolicyRegistryImpl(
            allowed_scopes={"test-scope"},
            scope_inherits={},
            policy_pack_path=temp_json,  # explicit — should win
        )

        # Explicit path wins — env override must NOT appear
        assert registry.get_policy("legality_source") == "test-legal-only"

    def test_env_var_policy_pack_fallback(
        self, empty_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When config has no explicit policy_pack_path, the env var
        MEMORY_HOOK_POLICY_PACK_PATH should be used as fallback."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        env_pack = empty_dir / "env-fallback.json"
        env_pack.write_text(
            json.dumps({
                "schema_version": "m3-policy-pack-v1",
                "policies": {"kb_write_mode": "env-write-through"},
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("MEMORY_HOOK_POLICY_PACK_PATH", str(env_pack))

        registry = PolicyRegistryImpl(
            allowed_scopes={"test-scope"},
            scope_inherits={},
            # No policy_pack_path — env var should be used
        )

        assert registry.get_policy("kb_write_mode") == "env-write-through"

    def test_graceful_degradation_when_no_pack(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no policy_pack_path is set, no env var exists, and no
        default file is present, the registry should still work with
        DEFAULT_POLICIES only (no crash)."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        # Clear env var
        monkeypatch.delenv("MEMORY_HOOK_POLICY_PACK_PATH", raising=False)

        # Patch DEFAULT_POLICY_PACK_PATH to a nonexistent path
        fake_default = REPO_ROOT / "__nonexistent_policy_pack__.json"
        with patch.object(
            PolicyRegistryImpl,
            "DEFAULT_POLICY_PACK_PATH",
            fake_default,
        ):
            registry = PolicyRegistryImpl(
                allowed_scopes={"test-scope"},
                scope_inherits={},
            )

        # Should still have DEFAULT_POLICIES
        assert registry.get_policy("registration_phase") == "declared-not-enforced"
        assert registry.get_policy("truth_basis_policy") == "source-authority-evidence-conflict"
        # Non-existent key returns None
        assert registry.get_policy("nonexistent_key") is None


# ---------------------------------------------------------------------------
# TestAdapterPolicyResolution
# ---------------------------------------------------------------------------

class TestAdapterPolicyResolution:
    """Verify that the workbot adapter resolves the correct consumer-specific
    policies from the runtime profile and policy pack, while the neutral
    adapter stays generic."""

    # Workbot runtime profile constants (mirrored from workbot_runtime_profile)
    WORKBOT_LEGALITY_SOURCE = "active-legal-map-only"
    WORKBOT_REGISTRATION_COMMIT = "required-after-absorption-complete"

    def test_workbot_adapter_has_legality_source(self) -> None:
        """The workbot runtime profile must declare legality_source as
        'active-legal-map-only'."""
        from workspace.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile,
        )

        profile = build_workbot_runtime_profile(REPO_ROOT, REPO_ROOT / "workspace")
        assert profile["LEGALITY_SOURCE_POLICY"] == self.WORKBOT_LEGALITY_SOURCE

    def test_workbot_adapter_has_registration_commit(self) -> None:
        """The workbot runtime profile must declare registration_commit as
        'required-after-absorption-complete'."""
        from workspace.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile,
        )

        profile = build_workbot_runtime_profile(REPO_ROOT, REPO_ROOT / "workspace")
        assert profile["REGISTRATION_COMMIT_POLICY"] == self.WORKBOT_REGISTRATION_COMMIT

    def test_neutral_adapter_has_no_consumer_policies(self) -> None:
        """The neutral (host-agnostic) DEFAULT_POLICIES must not contain
        consumer-specific policy values. Consumer keys like
        legality_source and registration_commit should only come from
        adapter-specific policy packs, not from the base defaults."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        # DEFAULT_POLICIES should not contain workbot-specific values
        defaults = PolicyRegistryImpl.DEFAULT_POLICIES
        # These are the consumer-specific keys that should NOT appear in defaults
        consumer_keys = {"legality_source", "registration_commit"}
        for key in consumer_keys:
            assert key not in defaults, (
                f"consumer-specific key '{key}' should not be in DEFAULT_POLICIES"
            )

    def test_adapter_policies_merge_with_base(self, temp_json: Path) -> None:
        """Adapter-specific policies from the JSON pack should merge on top
        of DEFAULT_POLICIES — base keys not overridden by the pack should
        still be present."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        registry = PolicyRegistryImpl(
            allowed_scopes={"test-scope"},
            scope_inherits={},
            policy_pack_path=temp_json,
        )

        # Pack overrides
        assert registry.get_policy("legality_source") == "test-legal-only"
        # Base defaults preserved (not overridden by pack)
        assert registry.get_policy("registration_phase") == "declared-not-enforced"
        assert registry.get_policy("truth_basis_policy") == "source-authority-evidence-conflict"


# ---------------------------------------------------------------------------
# TestPolicyPackConsistency
# ---------------------------------------------------------------------------

class TestPolicyPackConsistency:
    """Verify that the JSON policy pack on disk is consistent with the
    workbot adapter's runtime profile values and has the expected schema."""

    POLICY_PACK_FILE = REPO_ROOT / "workspace" / "memory" / "kb" / "global" / "workbot-policy-pack.json"

    def test_json_policy_pack_matches_adapter_values(self) -> None:
        """The JSON policy pack's policies must match the workbot runtime
        profile's LEGALITY_SOURCE_POLICY and REGISTRATION_COMMIT_POLICY."""
        from workspace.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile,
        )

        if not self.POLICY_PACK_FILE.exists():
            pytest.skip("workbot-policy-pack.json not present")

        pack = json.loads(self.POLICY_PACK_FILE.read_text(encoding="utf-8"))
        profile = build_workbot_runtime_profile(REPO_ROOT, REPO_ROOT / "workspace")

        policies = pack.get("policies", {})
        assert policies.get("legality_source") == profile["LEGALITY_SOURCE_POLICY"]
        assert policies.get("registration_commit") == profile["REGISTRATION_COMMIT_POLICY"]

    def test_schema_version_matches(self) -> None:
        """The schema_version in the JSON policy pack must match the
        PolicyRegistryImpl.SCHEMA_VERSION constant."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        if not self.POLICY_PACK_FILE.exists():
            pytest.skip("workbot-policy-pack.json not present")

        pack = json.loads(self.POLICY_PACK_FILE.read_text(encoding="utf-8"))
        expected_version = PolicyRegistryImpl.SCHEMA_VERSION

        assert pack.get("schema_version") == expected_version, (
            f"JSON schema_version={pack.get('schema_version')!r} "
            f"does not match SCHEMA_VERSION={expected_version!r}"
        )
