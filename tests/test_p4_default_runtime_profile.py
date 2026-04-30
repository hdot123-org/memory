"""Tests for default_runtime_profile (P4b)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from memory_core.tools.memory_hook_adapters.default_runtime_profile import (
    build_default_runtime_profile,
)

# ── build_default_runtime_profile ──────────────────────────────────


class TestBuildDefaultRuntimeProfile:
    """Generic profile construction from .memory/adapter.toml."""

    REQUIRED_KEYS = {
        "PROJECT_MAP_ROOT",
        "TRUTH_MODEL",
        "REQUIRED_CANONICAL",
        "PROJECT_CANONICAL",
        "GLOBAL_CANONICAL",
        "LEGALITY_SOURCE_POLICY",
        "REGISTRATION_COMMIT_POLICY",
        "REGISTRATION_COMMIT_PHASE",
        "GATEWAY_POLICY_CLASS",
        "ARTIFACT_COMPACTION",
        "DEFAULT_PROJECT_SCOPE",
        "POLICY_ALLOWED_SCOPES",
        "POLICY_SCOPE_INHERITS",
        "GOVERNANCE_BLOCKER_SCOPES",
        "EVENT_CONTRACT_BLOCKER_SCOPES",
    }

    def _make_adapter_toml(self, project: Path, scope: str = "myproject") -> None:
        """Write a minimal canonical adapter.toml."""
        mem = project / ".memory"
        mem.mkdir(parents=True, exist_ok=True)
        toml = textwrap.dedent(f"""\
            [core]
            version = "0.1.0"
            adapter = "default"

            [policy]
            legality_source_policy = "map-only"
            registration_commit_policy = "same-commit"
            registration_commit_phase = "post"

            [routing]
            project_name = "{scope}"
            project_scope = "{scope}"
            host = "codex"
        """)
        (mem / "adapter.toml").write_text(toml)

    def test_returns_exactly_15_keys(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        assert set(profile.keys()) == self.REQUIRED_KEYS
        assert len(profile) == 15

    def test_scope_from_adapter_toml(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path, scope="backend-service")
        profile = build_default_runtime_profile(tmp_path)
        assert profile["DEFAULT_PROJECT_SCOPE"] == "backend-service"
        assert "backend-service" in profile["POLICY_ALLOWED_SCOPES"]

    def test_paths_relative_to_project_root(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path, scope="testproj")
        profile = build_default_runtime_profile(tmp_path)

        assert profile["PROJECT_MAP_ROOT"] == tmp_path / ".memory" / "kb" / "projects"
        assert profile["TRUTH_MODEL"] == tmp_path / ".memory" / "kb" / "global" / "truth-model.md"

    def test_policy_values_from_toml(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        assert profile["LEGALITY_SOURCE_POLICY"] == "map-only"
        assert profile["REGISTRATION_COMMIT_POLICY"] == "same-commit"
        assert profile["REGISTRATION_COMMIT_PHASE"] == "post"

    def test_gateway_policy_class_is_neutral(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        cls = profile["GATEWAY_POLICY_CLASS"]
        assert cls is not None
        assert cls.__name__ == "NeutralGatewayBusinessPolicy"

    def test_empty_scopes_and_inherits(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        assert profile["POLICY_SCOPE_INHERITS"] == {}
        assert profile["GOVERNANCE_BLOCKER_SCOPES"] == set()
        assert profile["EVENT_CONTRACT_BLOCKER_SCOPES"] == set()

    def test_artifact_compaction_all_true(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        compaction = profile["ARTIFACT_COMPACTION"]
        assert isinstance(compaction, dict)
        assert all(v is True for v in compaction.values())

    def test_missing_adapter_toml_uses_defaults(self, tmp_path: Path) -> None:
        """When adapter.toml is absent, profile still builds with defaults."""
        (tmp_path / ".memory").mkdir(parents=True, exist_ok=True)
        profile = build_default_runtime_profile(tmp_path)
        assert set(profile.keys()) == self.REQUIRED_KEYS
        assert profile["DEFAULT_PROJECT_SCOPE"] == "default"

    def test_no_host_specific_literals(self, tmp_path: Path) -> None:
        """Profile dict values must not reference host-specific projects."""
        import re
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        forbidden = re.compile(r"workbot|AEdu", re.IGNORECASE)
        for key, val in profile.items():
            if isinstance(val, str):
                assert not forbidden.search(val), f"{key} contains forbidden literal"
            elif isinstance(val, (list, set, frozenset)):
                for item in val:
                    if isinstance(item, str):
                        assert not forbidden.search(item), f"{key} contains forbidden literal"
            elif isinstance(val, dict):
                for k, v in val.items():
                    for piece in (k, v):
                        if isinstance(piece, str):
                            assert not forbidden.search(piece), f"{key} contains forbidden literal"

    def test_project_canonical_in_scope(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path, scope="webapp")
        profile = build_default_runtime_profile(tmp_path)
        assert "webapp" in profile["PROJECT_CANONICAL"]
