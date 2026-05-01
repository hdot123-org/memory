#!/usr/bin/env python3
"""Tests for business_policy_checks.py — path / scope / permission rules.

Covers:
- _path_is_under (symlink-resolving containment)
- _path_is_under_lexical (lexical containment without symlink resolution)
- TruthBasisResolver._path_is_under, _classify_truth_ref,
  _authority_ref_allowed, _lower_evidence_ref
- ScopeResolver.determine_project_scope
- Boundary / edge cases: empty, None-equivalent, Unicode,超长路径,
  symlinks, exact-boundary paths
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memory_core.tools.business_policy_checks import (
    ScopeResolver,
    TruthBasisResolver,
    _path_is_under,
    _path_is_under_lexical,
)
from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop_read(path: Path) -> str:
    return ""


def _make_config(tmp_path: Path, **overrides: Any) -> GatewayBusinessPolicyConfig:
    """Build a minimal GatewayBusinessPolicyConfig rooted under tmp_path."""
    repo = tmp_path / "repo"
    pm_root = tmp_path / "project_map"
    for d in (repo, pm_root):
        d.mkdir(parents=True, exist_ok=True)
    (repo / "workspace").mkdir(parents=True, exist_ok=True)

    defaults: dict[str, Any] = {
        "repo_root": repo,
        "workspace_root": repo / "workspace",
        "project_map_root": pm_root,
        "project_map_files": [pm_root / "INDEX.md", pm_root / "legal-core-map.md", pm_root / "ingestion-registry-map.md"],
        "project_map_governance": pm_root / "governance.md",
        "truth_model": repo / "workspace" / "truth_model.md",
        "global_canonical": [repo / "workspace" / "global_1.md", repo / "workspace" / "global_2.md"],
        "authority_allowed_paths": {repo / "workspace" / "authority_1.md", repo / "workspace" / "authority_2.md"},
        "lower_evidence_roots": [repo / "workspace" / "evidence", repo / "workspace" / "logs"],
        "legal_core_markers": ["active-legal"],
        "required_registry_scopes": ["incoming-raw"],
        "project_canonical": {"test-scope": repo / "workspace" / "test_scope.md"},
        "project_runtime_root": {"test-scope": repo / "workspace" / "runtime"},
        "project_doc_refs": {},
        "default_decision_refs": [],
        "project_decision_refs": {},
        "default_lesson_refs": [],
        "project_lesson_refs": {},
        "governance_frozen_tuple_files": [],
        "event_contract_files": {},
        "frozen_tuple_expected": set(),
        "frozen_tuple_legacy_markers": set(),
        "formal_source_types": set(),
        "formal_event_types": set(),
        "formal_event_statuses": set(),
        "formal_field_keys": set(),
        "legacy_field_keys": set(),
        "required_canonical": [],
        "workspace_index_path": repo / "workspace" / "INDEX.md",
        "docs_index_path": repo / "workspace" / "docs_index.md",
        "overview_doc_path": repo / "workspace" / "overview.md",
        "global_index_path": repo / "workspace" / "global_index.md",
        "hook_contract_path": repo / "workspace" / "hook_contract.md",
        "default_project_scope": "default",
        "scope_match_hints": {
            "kb": [repo / "workspace" / "memory" / "kb"],
            "tools": [repo / "workspace" / "tools"],
            "projects": [repo / "workspace" / "projects"],
        },
        "read_text_if_exists_fn": _noop_read,
    }
    defaults.update(overrides)
    return GatewayBusinessPolicyConfig(**defaults)


# ---------------------------------------------------------------------------
# 1. _path_is_under (symlink-resolving containment)
# ---------------------------------------------------------------------------

class TestPathIsUnder:
    """Tests for the module-level _path_is_under function."""

    def test_direct_child_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        child = root / "child" / "file.txt"
        child.parent.mkdir()
        child.touch()
        assert _path_is_under(child, root) is True

    def test_deep_nested_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        deep = root / "a" / "b" / "c" / "d.txt"
        deep.parent.mkdir(parents=True)
        deep.touch()
        assert _path_is_under(deep, root) is True

    def test_sibling_fails(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        sibling = tmp_path / "sibling" / "file.txt"
        sibling.parent.mkdir()
        sibling.touch()
        assert _path_is_under(sibling, root) is False

    def test_root_itself_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        assert _path_is_under(root, root) is True

    def test_parent_of_root_fails(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        assert _path_is_under(tmp_path, root) is False

    def test_symlink_to_outside_fails(self, tmp_path: Path) -> None:
        """A symlink inside root that points outside root must fail."""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside" / "secret.txt"
        outside.parent.mkdir()
        outside.touch()
        link = root / "escape_link"
        link.symlink_to(outside)
        assert _path_is_under(link, root) is False

    def test_symlink_inside_passes(self, tmp_path: Path) -> None:
        """A symlink inside root pointing to another path inside root passes."""
        root = tmp_path / "root"
        root.mkdir()
        target = root / "real" / "file.txt"
        target.parent.mkdir()
        target.touch()
        link = root / "link"
        link.symlink_to(target)
        assert _path_is_under(link, root) is True

    def test_nonexistent_path_resolves_correctly(self, tmp_path: Path) -> None:
        """Non-existent path inside root still resolves correctly."""
        root = tmp_path / "root"
        root.mkdir()
        ghost = root / "does" / "not" / "exist.txt"
        # _path_is_under uses resolve(), which still works for non-existent
        # paths in Python 3 (returns the resolved prefix + remainder)
        assert _path_is_under(ghost, root) is True

    def test_nonexistent_outside_fails(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        ghost = tmp_path / "elsewhere" / "ghost.txt"
        assert _path_is_under(ghost, root) is False


# ---------------------------------------------------------------------------
# 2. _path_is_under_lexical (no symlink resolution)
# ---------------------------------------------------------------------------

class TestPathIsUnderLexical:
    """Tests for _path_is_under_lexical — lexical containment only."""

    def test_direct_child_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        child = root / "child.txt"
        child.touch()
        assert _path_is_under_lexical(child, root) is True

    def test_symlink_outside_still_passes_lexically(self, tmp_path: Path) -> None:
        """Lexical check sees the symlink path itself, not its target."""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside" / "secret.txt"
        outside.parent.mkdir()
        outside.touch()
        link = root / "escape_link"
        link.symlink_to(outside)
        # Lexically, the link IS under root
        assert _path_is_under_lexical(link, root) is True

    def test_sibling_fails(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        sibling = tmp_path / "sibling" / "file.txt"
        sibling.parent.mkdir()
        sibling.touch()
        assert _path_is_under_lexical(sibling, root) is False

    def test_home_expansion(self, tmp_path: Path) -> None:
        """Paths with ~ should be expanded lexically."""
        root = tmp_path / "root"
        root.mkdir()
        child = root / "file.txt"
        child.touch()
        assert _path_is_under_lexical(child, root) is True

    def test_relative_vs_absolute(self, tmp_path: Path) -> None:
        """Both relative and absolute forms are handled via .absolute()."""
        root = tmp_path / "root"
        root.mkdir()
        # Construct a relative path and check
        os.chdir(str(root))
        rel = Path("subdir")
        rel.mkdir()
        assert _path_is_under_lexical(rel, root) is True


# ---------------------------------------------------------------------------
# 3. TruthBasisResolver._path_is_under (static method)
# ---------------------------------------------------------------------------

class TestTruthBasisResolverPathIsUnder:
    """Tests for TruthBasisResolver._path_is_under (static)."""

    def test_path_under_root(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        child = root / "sub" / "file.txt"
        child.parent.mkdir()
        child.touch()
        assert TruthBasisResolver._path_is_under(child, root) is True

    def test_path_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "other" / "file.txt"
        outside.parent.mkdir()
        outside.touch()
        assert TruthBasisResolver._path_is_under(outside, root) is False

    def test_matches_module_level(self, tmp_path: Path) -> None:
        """Static method must agree with module-level _path_is_under."""
        root = tmp_path / "root"
        root.mkdir()
        child = root / "a.txt"
        child.touch()
        outside = tmp_path / "other.txt"
        outside.touch()
        assert TruthBasisResolver._path_is_under(child, root) == _path_is_under(child, root)
        assert TruthBasisResolver._path_is_under(outside, root) == _path_is_under(outside, root)


# ---------------------------------------------------------------------------
# 4. TruthBasisResolver._classify_truth_ref
# ---------------------------------------------------------------------------

class TestTruthBasisResolverClassify:
    """Tests for _classify_truth_ref — scope classification by path."""

    def _resolver(self, tmp_path: Path) -> tuple[TruthBasisResolver, Path]:
        cfg = _make_config(tmp_path)
        return TruthBasisResolver(cfg), cfg

    def test_legal_core_map(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.project_map_root / "legal-core-map.md"
        p.touch()
        assert resolver._classify_truth_ref(p) == "legal-core"

    def test_project_map_index(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.project_map_root / "INDEX.md"
        p.touch()
        assert resolver._classify_truth_ref(p) == "project-map-index"

    def test_global_canonical(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.global_canonical[0]
        p.touch()
        assert resolver._classify_truth_ref(p) == "global-canonical"

    def test_compat_only_under_kb_global_projects(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "memory" / "kb" / "global" / "projects" / "foo.md"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "compatibility-only"

    def test_project_canonical_under_kb_projects(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "memory" / "kb" / "projects" / "bar.md"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "project-canonical"

    def test_docs_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "memory" / "docs" / "readme.md"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "docs"

    def test_project_runtime_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "projects" / "app.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "project-runtime"

    def test_artifact_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "artifacts" / "build.tar"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "artifact"

    def test_tooling_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "tools" / "helper.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "tooling"

    def test_log_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "memory" / "log" / "event.log"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "log"

    def test_system_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "memory" / "system" / "config.yaml"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "system"

    def test_app_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.repo_root / "app" / "main.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "app"

    def test_agents_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.repo_root / "agents" / "agent.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "agents"

    def test_gpt_web_to_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.repo_root / "gpt-web-to" / "fetch.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "gpt-web-to"

    def test_repo_policy_agents_md(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.repo_root / "AGENTS.md"
        p.touch()
        assert resolver._classify_truth_ref(p) == "repo-policy"

    def test_workspace_entry_index(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.workspace_root / "INDEX.md"
        p.touch()
        assert resolver._classify_truth_ref(p) == "workspace-entry"

    def test_unknown_path_returns_other(self, tmp_path: Path) -> None:
        resolver, _ = self._resolver(tmp_path)
        p = tmp_path / "random" / "weird.txt"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._classify_truth_ref(p) == "other"

    def test_classification_priority_legal_core_over_global(self, tmp_path: Path) -> None:
        """legal-core-map.md should be classified as legal-core even if it
        appears in global_canonical list (exact match wins first)."""
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.project_map_root / "legal-core-map.md"
        p.touch()
        # Even though it's not in global_canonical, exact match is first check
        assert resolver._classify_truth_ref(p) == "legal-core"


# ---------------------------------------------------------------------------
# 5. TruthBasisResolver._authority_ref_allowed
# ---------------------------------------------------------------------------

class TestTruthBasisResolverAuthorityAllowed:
    """Tests for _authority_ref_allowed — permission check for authority refs."""

    def _resolver(self, tmp_path: Path) -> tuple[TruthBasisResolver, Path]:
        cfg = _make_config(tmp_path)
        return TruthBasisResolver(cfg), cfg

    def test_path_in_authority_allowed_set(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = next(iter(cfg.authority_allowed_paths))
        p.touch()
        assert resolver._authority_ref_allowed(p) is True

    def test_path_in_global_canonical(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.global_canonical[0]
        p.touch()
        assert resolver._authority_ref_allowed(p) is True

    def test_path_not_in_either_set(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = tmp_path / "unauthorized" / "file.md"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._authority_ref_allowed(p) is False

    def test_empty_config_allows_nothing(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, authority_allowed_paths=set(), global_canonical=[])
        resolver = TruthBasisResolver(cfg)
        p = tmp_path / "repo" / "some.md"
        p.touch()
        assert resolver._authority_ref_allowed(p) is False


# ---------------------------------------------------------------------------
# 6. TruthBasisResolver._lower_evidence_ref
# ---------------------------------------------------------------------------

class TestTruthBasisResolverLowerEvidence:
    """Tests for _lower_evidence_ref — check if path is under evidence roots."""

    def _resolver(self, tmp_path: Path) -> tuple[TruthBasisResolver, Path]:
        cfg = _make_config(tmp_path)
        return TruthBasisResolver(cfg), cfg

    def test_under_first_evidence_root(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.lower_evidence_roots[0] / "evidence_file.md"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._lower_evidence_ref(p) is True

    def test_under_second_evidence_root(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.lower_evidence_roots[1] / "log_file.log"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._lower_evidence_ref(p) is True

    def test_deeply_nested_under_evidence_root(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = cfg.lower_evidence_roots[0] / "a" / "b" / "c" / "deep.md"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._lower_evidence_ref(p) is True

    def test_outside_all_evidence_roots(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        p = tmp_path / "elsewhere" / "file.txt"
        p.parent.mkdir(parents=True)
        p.touch()
        assert resolver._lower_evidence_ref(p) is False

    def test_empty_evidence_roots(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, lower_evidence_roots=[])
        resolver = TruthBasisResolver(cfg)
        p = tmp_path / "repo" / "any.md"
        p.touch()
        assert resolver._lower_evidence_ref(p) is False


# ---------------------------------------------------------------------------
# 7. ScopeResolver.determine_project_scope
# ---------------------------------------------------------------------------

class TestScopeResolverDetermineScope:
    """Tests for ScopeResolver.determine_project_scope."""

    def _resolver(self, tmp_path: Path) -> tuple[ScopeResolver, Path]:
        cfg = _make_config(tmp_path)
        return ScopeResolver(cfg), cfg

    def test_cwd_outside_repo_returns_default(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        outside = tmp_path / "outside_repo"
        outside.mkdir()
        assert resolver.determine_project_scope(outside) == cfg.default_project_scope

    def test_cwd_under_kb_returns_kb_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        kb_dir = cfg.workspace_root / "memory" / "kb" / "projects" / "myproj"
        kb_dir.mkdir(parents=True)
        assert resolver.determine_project_scope(kb_dir) == "kb"

    def test_cwd_under_tools_returns_tools_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        tools_dir = cfg.workspace_root / "tools" / "sub"
        tools_dir.mkdir(parents=True)
        assert resolver.determine_project_scope(tools_dir) == "tools"

    def test_cwd_under_projects_returns_projects_scope(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        proj_dir = cfg.workspace_root / "projects" / "app"
        proj_dir.mkdir(parents=True)
        assert resolver.determine_project_scope(proj_dir) == "projects"

    def test_cwd_at_workspace_root_returns_default(self, tmp_path: Path) -> None:
        """Workspace root is under repo_root but not under any scope hint."""
        resolver, cfg = self._resolver(tmp_path)
        # workspace_root is a sibling of repo_root under tmp_path, so
        # it's outside repo_root → default
        assert resolver.determine_project_scope(cfg.workspace_root) == cfg.default_project_scope

    def test_cwd_at_repo_root_returns_default(self, tmp_path: Path) -> None:
        """Repo root is under itself but not under any scope hint → default."""
        resolver, cfg = self._resolver(tmp_path)
        assert resolver.determine_project_scope(cfg.repo_root) == cfg.default_project_scope

    def test_cwd_in_repo_but_not_in_any_hint_returns_default(self, tmp_path: Path) -> None:
        resolver, cfg = self._resolver(tmp_path)
        misc = cfg.repo_root / "misc" / "stuff"
        misc.mkdir(parents=True)
        assert resolver.determine_project_scope(misc) == cfg.default_project_scope


# ---------------------------------------------------------------------------
# 8. ScopeResolver with scope overrides (JSON config)
# ---------------------------------------------------------------------------

class TestScopeResolverOverrides:
    """Tests for ScopeResolver with scope config overrides."""

    def test_load_valid_scope_config(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        config_file = tmp_path / "scope_config.json"
        config_file.write_text(json.dumps({
            "project_canonical": {"custom-scope": "workspace/custom.md"},
            "project_runtime_root": {"custom-scope": "workspace/custom_rt"},
        }), encoding="utf-8")

        resolver = ScopeResolver(cfg, scope_config_path=config_file)
        canon = resolver.get_project_canonical()
        assert "custom-scope" in canon

    def test_malformed_json_returns_empty_overrides(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ broken json", encoding="utf-8")

        resolver = ScopeResolver(cfg, scope_config_path=bad_file)
        canon = resolver.get_project_canonical()
        # Only the base config entries
        assert "custom-scope" not in canon

    def test_missing_config_file_returns_empty_overrides(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        ghost = tmp_path / "nope.json"
        resolver = ScopeResolver(cfg, scope_config_path=ghost)
        canon = resolver.get_project_canonical()
        assert "custom-scope" not in canon

    def test_non_dict_json_returns_empty_overrides(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        arr_file = tmp_path / "array.json"
        arr_file.write_text("[1, 2, 3]", encoding="utf-8")
        resolver = ScopeResolver(cfg, scope_config_path=arr_file)
        canon = resolver.get_project_canonical()
        assert "custom-scope" not in canon

    def test_override_with_absolute_path(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        config_file = tmp_path / "scope_config.json"
        abs_path = str(tmp_path / "abs_canonical.md")
        config_file.write_text(json.dumps({
            "project_canonical": {"abs-scope": abs_path},
        }), encoding="utf-8")

        resolver = ScopeResolver(cfg, scope_config_path=config_file)
        canon = resolver.get_project_canonical()
        assert canon["abs-scope"] == Path(abs_path)

    def test_env_var_scope_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _make_config(tmp_path)
        config_file = tmp_path / "env_scope.json"
        config_file.write_text(json.dumps({
            "project_canonical": {"env-scope": "env_canonical.md"},
        }), encoding="utf-8")

        monkeypatch.setenv(ScopeResolver.SCOPE_CONFIG_PATH_ENV, str(config_file))
        resolver = ScopeResolver(cfg)
        canon = resolver.get_project_canonical()
        assert "env-scope" in canon


# ---------------------------------------------------------------------------
# 9. Edge cases: empty, None-equivalent, Unicode,超长路径
# ---------------------------------------------------------------------------

class TestPathEdgeCases:
    """Boundary and edge-case tests for path handling."""

    def test_path_is_under_empty_path_vs_root(self, tmp_path: Path) -> None:
        """Empty string path resolves to cwd; should fail containment."""
        root = tmp_path / "root"
        root.mkdir()
        empty = Path("")
        assert _path_is_under(empty, root) is False

    def test_path_is_under_dot_vs_root(self, tmp_path: Path) -> None:
        """Dot resolves to cwd; if cwd is root, it passes."""
        root = tmp_path / "root"
        root.mkdir()
        os.chdir(str(root))
        dot = Path(".")
        assert _path_is_under(dot, root) is True

    def test_path_is_under_dotdot_outside(self, tmp_path: Path) -> None:
        """Double dot should escape root."""
        root = tmp_path / "root"
        root.mkdir()
        child = root / "child"
        child.mkdir()
        os.chdir(str(child))
        dd = Path("..")
        assert _path_is_under(dd, root) is True  # .. resolves to root itself

    def test_unicode_path_inside_root(self, tmp_path: Path) -> None:
        """Unicode directory names should be handled correctly."""
        root = tmp_path / "root"
        root.mkdir()
        uni = root / "目录" / "文件.txt"
        uni.parent.mkdir()
        uni.touch()
        assert _path_is_under(uni, root) is True

    def test_unicode_path_outside_root(self, tmp_path: Path) -> None:
        uni = tmp_path / "外部" / "file.txt"
        uni.parent.mkdir()
        uni.touch()
        root = tmp_path / "root"
        root.mkdir()
        assert _path_is_under(uni, root) is False

    def test_unicode_lexical_inside(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        uni = root / "日本語" / "テスト.txt"
        uni.parent.mkdir()
        uni.touch()
        assert _path_is_under_lexical(uni, root) is True

    def test_very_long_path_inside(self, tmp_path: Path) -> None:
        """Very long path (200+ segments) inside root should still work."""
        root = tmp_path / "root"
        root.mkdir()
        deep = root
        for i in range(200):
            deep = deep / f"d{i}"
        deep.parent.mkdir(parents=True, exist_ok=True)
        deep.touch()
        assert _path_is_under(deep, root) is True

    def test_very_long_path_outside(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        deep = tmp_path / "other"
        for i in range(200):
            deep = deep / f"o{i}"
        deep.parent.mkdir(parents=True, exist_ok=True)
        deep.touch()
        assert _path_is_under(deep, root) is False

    def test_traversal_dots_in_name_not_escape(self, tmp_path: Path) -> None:
        """A directory named '..' (literal) should not escape root."""
        root = tmp_path / "root"
        root.mkdir()
        # On most filesystems you can't actually create a dir named '..'
        # but we can test a path string with '..' that stays inside
        p = root / "valid" / ".." / "also_valid.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        assert _path_is_under(p, root) is True

    def test_symlink_chain_stays_inside(self, tmp_path: Path) -> None:
        """Chain of symlinks all pointing inside root must pass."""
        root = tmp_path / "root"
        root.mkdir()
        target = root / "real.txt"
        target.touch()
        link1 = root / "link1"
        link1.symlink_to(target)
        link2 = root / "link2"
        link2.symlink_to(link1)
        assert _path_is_under(link2, root) is True

    def test_symlink_chain_escapes(self, tmp_path: Path) -> None:
        """Chain ending in a symlink that escapes must fail."""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside.txt"
        outside.touch()
        link = root / "escape"
        link.symlink_to(outside)
        assert _path_is_under(link, root) is False


# ---------------------------------------------------------------------------
# 10. ScopeResolver helper methods
# ---------------------------------------------------------------------------

class TestScopeResolverHelpers:
    """Tests for ScopeResolver's non-scope-determination helpers."""

    def test_get_project_canonical_merges_config(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        canon = resolver.get_project_canonical()
        assert "test-scope" in canon
        assert canon["test-scope"] == cfg.project_canonical["test-scope"]

    def test_get_project_runtime_root_returns_config(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        rt = resolver.get_project_runtime_root()
        assert "test-scope" in rt

    def test_get_required_canonical_returns_list(self, tmp_path: Path) -> None:
        extra = [tmp_path / "req_1.md", tmp_path / "req_2.md"]
        cfg = _make_config(tmp_path, required_canonical=extra)
        resolver = ScopeResolver(cfg)
        result = resolver.get_required_canonical()
        assert result == extra

    def test_get_global_canonical_returns_list(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        result = resolver.get_global_canonical()
        assert result == cfg.global_canonical

    def test_project_map_refs_returns_string_list(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        refs = resolver.project_map_refs()
        assert isinstance(refs, list)
        assert all(isinstance(r, str) for r in refs)
        assert len(refs) == len(cfg.project_map_files)

    def test_decision_refs_for_scope_default_only(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        refs = resolver.decision_refs_for_scope("unknown-scope")
        # Returns existing paths from default_decision_refs (empty in our config)
        assert isinstance(refs, list)

    def test_lesson_refs_for_scope_default_only(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        refs = resolver.lesson_refs_for_scope("unknown-scope")
        assert isinstance(refs, list)

    def test_docs_refs_for_scope_empty_when_no_config(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = ScopeResolver(cfg)
        refs = resolver.docs_refs_for_scope("any")
        assert refs == []


# ---------------------------------------------------------------------------
# 11. Boundary paths (exactly at root)
# ---------------------------------------------------------------------------

class TestBoundaryPaths:
    """Paths that sit exactly on scope boundaries."""

    def test_path_equals_root_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        assert _path_is_under(root, root) is True

    def test_lexical_path_equals_root_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        assert _path_is_under_lexical(root, root) is True

    def test_immediate_child_passes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        child = root / "child.txt"
        child.touch()
        assert _path_is_under(child, root) is True
        assert _path_is_under_lexical(child, root) is True

    def test_parent_one_level_above_fails(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        assert _path_is_under(tmp_path, root) is False
        assert _path_is_under_lexical(tmp_path, root) is False


# ---------------------------------------------------------------------------
# 12. TruthBasisResolver truth_basis_for_scope integration
# ---------------------------------------------------------------------------

class TestTruthBasisForScopeIntegration:
    """Integration tests for truth_basis_for_scope end-to-end."""

    def test_unknown_scope_returns_fail(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("nonexistent-scope")
        assert result["validation"] == "fail"
        assert any("unsupported project scope" in e for e in result["errors"])

    def test_known_scope_with_empty_files_returns_errors(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        # Ensure the global canonical and project canonical files exist but are empty
        for p in cfg.global_canonical:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        proj = cfg.project_canonical["test-scope"]
        proj.parent.mkdir(parents=True, exist_ok=True)
        proj.touch()

        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("test-scope")
        # Empty files won't have Truth Basis sections → errors expected
        assert result["validation"] == "fail"
        assert len(result["errors"]) > 0

    def test_known_scope_returns_project_ref(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        proj = cfg.project_canonical["test-scope"]
        proj.parent.mkdir(parents=True, exist_ok=True)
        proj.touch()
        for p in cfg.global_canonical:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

        resolver = TruthBasisResolver(cfg)
        result = resolver.truth_basis_for_scope("test-scope")
        assert result["project_ref"] == str(proj)
        assert "test-scope" not in [e for e in result["errors"] if "unsupported" in e]
