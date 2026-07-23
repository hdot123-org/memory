"""Tests for _scope_resolver_base.ScopeResolverBase."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory_core.tools._scope_resolver_base import ScopeResolverBase


@pytest.fixture
def mock_config():
    """Build a minimal GatewayBusinessPolicyConfig mock."""
    cfg = MagicMock()
    cfg.repo_root = Path("/fake/repo")
    cfg.default_project_scope = "default"
    cfg.scope_match_hints = {"alpha": [Path("/fake/repo/alpha")]}
    cfg.project_canonical = {"default": Path("/fake/repo/memory/kb/projects")}
    cfg.project_runtime_root = {"default": Path("/fake/repo/projects")}
    cfg.required_canonical = [Path("/fake/repo/memory/kb/projects/default.md")]
    cfg.global_canonical = [Path("/fake/repo/memory/kb/global")]
    cfg.project_map_files = [Path("/fake/repo/project-map/INDEX.md")]
    return cfg


class TestScopeResolverBase:
    def test_init_no_config_path(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        assert resolver._scope_overrides == {}

    def test_determine_project_scope_outside_repo(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        scope = resolver.determine_project_scope(Path("/elsewhere"))
        assert scope == "default"

    def test_determine_project_scope_inside_repo(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        scope = resolver.determine_project_scope(Path("/fake/repo/alpha/sub"))
        assert scope == "alpha"

    def test_determine_project_scope_inside_no_match(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        scope = resolver.determine_project_scope(Path("/fake/repo/beta"))
        assert scope == "default"

    def test_get_project_canonical_no_overrides(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        result = resolver.get_project_canonical()
        assert "default" in result

    def test_get_project_runtime_root_no_overrides(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        result = resolver.get_project_runtime_root()
        assert "default" in result

    def test_get_required_canonical(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        result = resolver.get_required_canonical()
        assert len(result) == 1

    def test_get_global_canonical(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        result = resolver.get_global_canonical()
        assert len(result) == 1

    def test_project_map_refs(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        refs = resolver.project_map_refs()
        assert any("INDEX.md" in r for r in refs)

    def test_load_scope_overrides_from_file(self, mock_config, tmp_path):
        overrides_file = tmp_path / "overrides.json"
        overrides_file.write_text(
            '{"project_canonical": {"custom": "/custom/path"}}'
        )
        resolver = ScopeResolverBase(mock_config, scope_config_path=overrides_file)
        result = resolver.get_project_canonical()
        assert "custom" in result
        assert result["custom"] == Path("/custom/path")

    def test_load_scope_overrides_invalid_json(self, mock_config, tmp_path):
        overrides_file = tmp_path / "bad.json"
        overrides_file.write_text("not json")
        resolver = ScopeResolverBase(mock_config, scope_config_path=overrides_file)
        assert resolver._scope_overrides == {}

    def test_load_scope_overrides_nonexistent(self, mock_config, tmp_path):
        overrides_file = tmp_path / "nonexistent.json"
        resolver = ScopeResolverBase(mock_config, scope_config_path=overrides_file)
        assert resolver._scope_overrides == {}

    def test_resolve_override_path_relative(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        result = resolver._resolve_override_path("relative/path")
        assert result == (mock_config.repo_root / "relative" / "path").resolve()

    def test_resolve_override_path_absolute(self, mock_config):
        resolver = ScopeResolverBase(mock_config)
        result = resolver._resolve_override_path("/abs/path")
        assert result == Path("/abs/path")

    def test_load_scope_overrides_env_var(self, mock_config, tmp_path, monkeypatch):
        overrides_file = tmp_path / "env_overrides.json"
        overrides_file.write_text(
            '{"project_runtime_root": {"env_scope": "/env/root"}}'
        )
        monkeypatch.setenv(
            ScopeResolverBase.SCOPE_CONFIG_PATH_ENV, str(overrides_file)
        )
        resolver = ScopeResolverBase(mock_config)
        result = resolver.get_project_runtime_root()
        assert "env_scope" in result
