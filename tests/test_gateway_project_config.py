#!/usr/bin/env python3.12
"""Tests for memory-project.toml hardened config layer (M4 Phase 2).

Covers the gateway-side functions in memory_core/tools/_gateway_config.py:
- Config parsing (strict / non-strict syntax error handling)
- Config discovery (seed-first, ancestor collection)
- memory_root resolution (self-reference, containment escape)
- memory_root value validation (empty string / empty list)
- Cross-config members overlap detection (VAL-CFG-006)
- Four-level routing integration (git short-circuit, config routing,
  world-writable degradation, overlap rejection)
"""

import logging
import tomllib
from pathlib import Path

import pytest

from memory_core.tools._gateway_config import (
    _check_members_overlap,
    _find_all_project_configs,
    _find_project_config_path,
    _parse_project_config,
    _resolve_memory_root,
    _resolve_repo_root_with_config,
    _validate_memory_root_value,
)

CONFIG_NAME = "memory-project.toml"
_MODULE_LOGGER = "memory_core.tools._gateway_config"


def _write_config(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParseProjectConfig:
    def test_parse_valid_config(self, tmp_path: Path):
        cfg = _write_config(
            tmp_path / CONFIG_NAME,
            'project = "demo"\nmemory_root = "./m"\nmembers = ["./a", "./b"]\n',
        )
        parsed = _parse_project_config(cfg)
        assert parsed == {"project": "demo", "memory_root": "./m", "members": ["./a", "./b"]}

    def test_syntax_error_strict_raises(self, tmp_path: Path):
        cfg = _write_config(tmp_path / CONFIG_NAME, "not valid toml [[[\n")
        with pytest.raises(tomllib.TOMLDecodeError):
            _parse_project_config(cfg, strict=True)

    def test_syntax_error_non_strict_returns_none(self, tmp_path: Path):
        cfg = _write_config(tmp_path / CONFIG_NAME, "not valid toml [[[\n")
        assert _parse_project_config(cfg) is None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestConfigDiscovery:
    def test_seed_first_wins_over_ancestor(self, tmp_path: Path):
        inner = _write_config(tmp_path / "inner" / CONFIG_NAME, 'project = "inner"\n')
        outer = _write_config(tmp_path / CONFIG_NAME, 'project = "outer"\n')
        assert _find_project_config_path(tmp_path / "inner") == inner.resolve()
        assert outer.exists()  # ancestor config exists but loses to nearest

    def test_collect_all_ancestors_nearest_first(self, tmp_path: Path):
        inner = _write_config(tmp_path / "inner" / CONFIG_NAME, 'project = "inner"\n')
        outer = _write_config(tmp_path / CONFIG_NAME, 'project = "outer"\n')
        assert _find_all_project_configs(tmp_path / "inner") == [inner.resolve(), outer.resolve()]

    def test_no_config_returns_empty(self, tmp_path: Path):
        assert _find_all_project_configs(tmp_path) == []
        assert _find_project_config_path(tmp_path) is None


# ---------------------------------------------------------------------------
# memory_root resolution and value validation
# ---------------------------------------------------------------------------


class TestResolveMemoryRoot:
    def test_self_reference_resolves_to_config_parent(self, tmp_path: Path):
        cfg = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./"\n')
        assert _resolve_memory_root("./", cfg) == tmp_path.resolve()

    def test_parent_escape_rejected(self, tmp_path: Path):
        cfg = _write_config(tmp_path / "inner" / CONFIG_NAME, 'memory_root = "../../elsewhere"\n')
        assert _resolve_memory_root("../../elsewhere", cfg) is None


class TestValidateMemoryRootValue:
    def test_valid_string(self, tmp_path: Path):
        cfg = tmp_path / CONFIG_NAME
        assert _validate_memory_root_value("./m", cfg) == (True, None)

    def test_empty_string_rejected(self, tmp_path: Path):
        cfg = tmp_path / CONFIG_NAME
        is_valid, error = _validate_memory_root_value("", cfg)
        assert not is_valid
        assert "empty string" in (error or "")

    def test_empty_list_rejected(self, tmp_path: Path):
        cfg = tmp_path / CONFIG_NAME
        is_valid, error = _validate_memory_root_value([], cfg)
        assert not is_valid
        assert "empty list" in (error or "")


# ---------------------------------------------------------------------------
# Members overlap (VAL-CFG-006)
# ---------------------------------------------------------------------------


class TestMembersOverlap:
    def test_overlap_across_configs_detected(self, tmp_path: Path):
        inner_cfg = (tmp_path / "inner" / CONFIG_NAME).resolve()
        outer_cfg = (tmp_path / CONFIG_NAME).resolve()
        shared = (tmp_path / "shared").resolve()
        overlaps = _check_members_overlap(
            [
                (inner_cfg, {"members": ["../shared"]}),
                (outer_cfg, {"members": ["./shared"]}),
            ]
        )
        assert overlaps is not None
        assert len(overlaps) == 1
        assert str(shared) in overlaps[0]
        assert str(inner_cfg) in overlaps[0] and str(outer_cfg) in overlaps[0]

    def test_disjoint_members_no_overlap(self, tmp_path: Path):
        inner_cfg = (tmp_path / "inner" / CONFIG_NAME).resolve()
        outer_cfg = (tmp_path / CONFIG_NAME).resolve()
        assert (
            _check_members_overlap(
                [
                    (inner_cfg, {"members": ["./a"]}),
                    (outer_cfg, {"members": ["./b"]}),
                ]
            )
            is None
        )


# ---------------------------------------------------------------------------
# Four-level routing integration
# ---------------------------------------------------------------------------


class TestResolveRepoRootWithConfig:
    def test_git_seed_short_circuits_level_one(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        assert _resolve_repo_root_with_config(tmp_path) == (tmp_path, tmp_path)

    def test_config_memory_root_routes_level_two(self, tmp_path: Path):
        target = tmp_path / "target"
        target.mkdir()
        _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./target"\n')
        assert _resolve_repo_root_with_config(tmp_path) == (target.resolve(), target.resolve())

    def test_world_writable_config_degrades_with_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        target = tmp_path / "target"
        target.mkdir()
        cfg = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./target"\n')
        cfg.chmod(0o666)
        try:
            with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
                repo_root, _ = _resolve_repo_root_with_config(tmp_path)
            assert repo_root != target.resolve()
            assert any("world-writable" in r.message for r in caplog.records)
        finally:
            cfg.chmod(0o644)

    def test_overlapping_members_reject_config_level(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """VAL-CFG-006: two configs declaring the same member → config level rejected with list."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        (outer / "shared").mkdir()
        target = inner / "t1"
        target.mkdir()
        # inner declares ../shared; outer declares ./shared → same resolved path
        _write_config(inner / CONFIG_NAME, 'memory_root = "./t1"\nmembers = ["../shared"]\n')
        _write_config(outer / CONFIG_NAME, 'members = ["./shared"]\n')
        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(inner)
        # Config level rejected: must NOT route to the config-declared memory_root
        assert repo_root != target.resolve()
        overlap_errors = [r for r in caplog.records if "VAL-CFG-006" in r.message]
        assert overlap_errors, f"expected VAL-CFG-006 overlap error in logs: {caplog.records}"
        assert "shared" in overlap_errors[0].getMessage()
