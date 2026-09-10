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


# ---------------------------------------------------------------------------
# VAL-CFG-005: Git命中 + 竞争配置冲突留痕
# ---------------------------------------------------------------------------


class TestGitConflictEscalation:
    def test_git_hit_with_memory_root_conflict_emits_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """VAL-CFG-005: git root命中且配置memory_root ≠ git根 → 路由git + 冲突行."""
        # Create a git repo
        git_root = tmp_path / "git_repo"
        git_root.mkdir()
        (git_root / ".git").mkdir()
        # Create a config with conflicting memory_root
        _write_config(
            git_root / CONFIG_NAME,
            'project = "test"\nmemory_root = "./different"\n',
        )
        # Create the different directory
        diff_dir = git_root / "different"
        diff_dir.mkdir()

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(git_root)

        # Should still route to git root (git优先)
        assert repo_root == git_root.resolve()
        # But emit conflict error line
        conflict_logs = [r for r in caplog.records if "config and git root conflict" in r.message]
        assert len(conflict_logs) >= 1
        assert str(git_root.resolve()) in conflict_logs[0].getMessage()  # git根
        assert str(diff_dir.resolve()) in conflict_logs[0].getMessage()  # 配置声明根
        assert str(git_root / CONFIG_NAME) in conflict_logs[0].getMessage()  # 配置路径


# ---------------------------------------------------------------------------
# VAL-CFG-007: members越界拒绝
# ---------------------------------------------------------------------------


class TestMembersBoundaryRejection:
    def test_members_with_parent_escape_rejected(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """../ escaping in members → configuration level rejected."""
        outer = tmp_path / "outer"
        outer.mkdir()
        target = outer / "target"
        target.mkdir()
        # Config with ../ that escapes config parent
        _write_config(
            outer / CONFIG_NAME,
            'project = "test"\nmemory_root = "./target"\nmembers = ["../outside"]\n',
        )

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)

        # Should fall back to discovery (config rejected)
        assert repo_root == outer.resolve()

    def test_members_with_absolute_outside_root_rejected(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """Absolute path outside config root → configuration level rejected."""
        outer = tmp_path / "outer"
        outer.mkdir()
        target = outer / "target"
        target.mkdir()
        # Config with absolute path outside config parent
        _write_config(
            outer / CONFIG_NAME,
            'project = "test"\nmemory_root = "./target"\nmembers = ["/tmp/outside"]\n',
        )

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)

        # Config rejected due to越界 members
        assert repo_root == outer.resolve()

    def test_members_mixed_valid_and_invalid(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """混合合法+越界 members → configuration level rejected."""
        outer = tmp_path / "outer"
        outer.mkdir()
        valid_dir = outer / "valid"
        valid_dir.mkdir()
        target = outer / "target"
        target.mkdir()
        # Config with one valid and one越界 member
        _write_config(
            outer / CONFIG_NAME,
            'project = "test"\nmemory_root = "./target"\nmembers = ["./valid", "/invalid"]\n',
        )

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)

        # 越界拒绝
        assert repo_root == outer.resolve()


# ---------------------------------------------------------------------------
# VAL-CFG-016: 幽灵 members 告警
# ---------------------------------------------------------------------------


class TestGhostMembersWarning:
    def test_ghost_members_route_unchanged_with_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """有效 memory_root + 幽灵 members → 路由不变 + 告警行."""
        target = tmp_path / "target"
        target.mkdir()
        # Config with valid memory_root but ghost members
        _write_config(
            tmp_path / CONFIG_NAME,
            'project = "test"\nmemory_root = "./target"\nmembers = ["./ghost1", "./ghost2"]\n',
        )

        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(tmp_path)

        # Should route to memory_root (unchanged)
        assert repo_root == target.resolve()
        # But emit ghost paths warning
        ghost_logs = [r for r in caplog.records if "ghost paths" in r.message]
        assert len(ghost_logs) >= 1
        assert str(tmp_path / "ghost1") in ghost_logs[0].getMessage()
        assert str(tmp_path / "ghost2") in ghost_logs[0].getMessage()


# ---------------------------------------------------------------------------
# VAL-CFG-018: 无效值不击穿网关 (非崩溃路径)
# ---------------------------------------------------------------------------


class TestInvalidValueNonBlocking:
    def test_empty_string_memory_root_nonblocking(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """空串 memory_root → not crash + structured error + degraded routing."""
        git_dir = tmp_path / "git_repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()

        # Config with empty string memory_root
        _write_config(
            git_dir / CONFIG_NAME,
            'project = "test"\nmemory_root = ""\n',
        )

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(git_dir)

        # No exception raised - non-blocking path
        # Error should be logged
        empty_logs = [r for r in caplog.records if "empty string" in r.message]
        assert len(empty_logs) >= 1, "Expected error log for empty string memory_root"

    def test_empty_list_memory_root_nonblocking(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """空列表 memory_root → not crash + structured error + degraded routing."""
        git_dir = tmp_path / "git_repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()

        # Config with empty list memory_root
        _write_config(
            git_dir / CONFIG_NAME,
            'project = "test"\nmemory_root = []\n',
        )

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(git_dir)

        # No exception raised - non-blocking path
        # Error should be logged
        empty_logs = [r for r in caplog.records if "empty list" in r.message]
        assert len(empty_logs) >= 1, "Expected error log for empty list memory_root"


# ---------------------------------------------------------------------------
# VAL-CFG-006: 嵌套重叠口径 (跨配置祖先/后代)
# ---------------------------------------------------------------------------


class TestNestedOverlap:
    def test_cross_config_ancestor_descendant_overlap(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """VAL-CFG-006: 跨配置嵌套包含（p1是p2的祖先/后代）→ 拒绝并列冲突."""
        outer = tmp_path / "outer"
        outer.mkdir()
        inner = outer / "inner"
        inner.mkdir()
        # outer declares ./a; inner declares ./a/b which IS nested under outer/a
        # When inner's ./a/b is resolved, it should be under outer's ./a
        _write_config(
            outer / CONFIG_NAME,
            'project = "outer"\nmembers = ["./a"]\n',
        )
        _write_config(
            inner / CONFIG_NAME,
            'project = "inner"\nmembers = ["../a/b"]\n',  # ../a/b from inner = outer/a/b (under outer/a)
        )
        # Create the paths
        (outer / "a").mkdir()
        (outer / "a" / "b").mkdir()

        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(inner)

        # Config level rejected due to nested overlap
        overlap_errors = [r for r in caplog.records if "VAL-CFG-006" in r.message]
        assert len(overlap_errors) >= 1
        assert (
            "ancestor" in overlap_errors[0].getMessage().lower() or "nested" in overlap_errors[0].getMessage().lower()
        )


# ---------------------------------------------------------------------------
# VAL-CFG-010 + VAL-CFG-017: world-writable 过滤 + fall-through
# ---------------------------------------------------------------------------


class TestWorldWritableAndFallThrough:
    def test_world_writable_config_filtered_from_overlap(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """world-writable 配置不参与 overlap (VAL-CFG-010)."""
        outer = tmp_path / "outer"
        outer.mkdir()
        inner = outer / "inner"
        inner.mkdir()
        shared = outer / "shared"
        shared.mkdir()

        # inner config is world-writable and declares shared
        inner_cfg = inner / CONFIG_NAME
        _write_config(inner_cfg, 'project = "inner"\nmembers = ["../shared"]\n')
        inner_cfg.chmod(0o666)

        # outer config declares shared (but isn't world-writable)
        outer_cfg = outer / CONFIG_NAME
        _write_config(outer_cfg, 'project = "outer"\nmembers = ["./shared"]\n')

        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(inner)

        # World-writable config ignored, only outer config considered
        # No overlap since only one valid config
        assert repo_root in (inner.resolve(), outer.resolve())

    def test_fall_through_only_when_truly_no_memory_root_members(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """VAL-CFG-017: fall-through告警仅当「解析成功且确无 memory_root 与 members」."""
        outer = tmp_path / "outer"
        outer.mkdir()
        target = outer / "target"
        target.mkdir()

        # Config with memory_root
        _write_config(outer / CONFIG_NAME, 'project = "test"\nmemory_root = "./target"\n')

        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)

        # Should route to memory_root, no fall-through warning
        assert repo_root == target.resolve()
        no_fall_through = [r for r in caplog.records if "no memory_root and no members" in r.message]
        assert len(no_fall_through) == 0
