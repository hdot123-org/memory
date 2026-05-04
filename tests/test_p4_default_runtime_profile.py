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
        "PROJECT_MAP_FILES",
        "PROJECT_MAP_GOVERNANCE",
        "HOOK_CONTRACT_PATH",
        "GLOBAL_RULE_PATH",
        "MEMORY_SYSTEM_PATH",
        "POLICY_PACK_PATH",
        "GATEWAY_POLICY_CLASS",
        "LEGALITY_SOURCE_POLICY",
        "REGISTRATION_COMMIT_POLICY",
        "REGISTRATION_COMMIT_PHASE",
        "REGISTRATION_GIT_SCOPE",
        "LEGAL_CORE_MARKERS",
        "REQUIRED_REGISTRY_SCOPES",
        "REQUIRED_CANONICAL",
        "PROJECT_CANONICAL",
        "PROJECT_RUNTIME_ROOT",
        "PROJECT_DOC_REFS",
        "GLOBAL_CANONICAL",
        "AUTHORITY_ALLOWED_PATHS",
        "LOWER_EVIDENCE_ROOTS",
        "DEFAULT_DECISION_REFS",
        "PROJECT_DECISION_REFS",
        "GOVERNANCE_FROZEN_TUPLE_FILES",
        "EVENT_CONTRACT_FILES",
        "FROZEN_TUPLE_EXPECTED",
        "FROZEN_TUPLE_LEGACY_MARKERS",
        "FORMAL_SOURCE_TYPES",
        "FORMAL_EVENT_TYPES",
        "FORMAL_EVENT_STATUSES",
        "FORMAL_FIELD_KEYS",
        "LEGACY_FIELD_KEYS",
        "DEFAULT_LESSON_REFS",
        "PROJECT_LESSON_REFS",
        "GOVERNANCE_BLOCKER_SCOPES",
        "EVENT_CONTRACT_BLOCKER_SCOPES",
        "DEFAULT_PROJECT_SCOPE",
        "ROUTE_PROJECT_RUNTIME_SCOPE",
        "SCOPE_MATCH_HINTS",
        "CORE_EVIDENCE_REFS",
        "POLICY_ALLOWED_SCOPES",
        "CLAUDE_HOOK_STATE_FILE",
        "POLICY_SCOPE_INHERITS",
        "ARTIFACT_COMPACTION",
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

    def test_returns_required_keys(self, tmp_path: Path) -> None:
        self._make_adapter_toml(tmp_path)
        profile = build_default_runtime_profile(tmp_path)
        assert set(profile.keys()) == self.REQUIRED_KEYS

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
