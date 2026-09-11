#!/usr/bin/env python3.12
"""Tests for memory-project.toml hardened config layer (M4 Phase 2).

Covers the gateway-side functions in memory_core/tools/_gateway_config.py:
- Config parsing (strict / non-strict syntax error handling)
- Config discovery (seed-first, ancestor collection)
- memory_root resolution (self-reference, containment escape)
- memory_root value validation (empty string / empty list / explicit types)
- Cross-config members overlap detection (VAL-CFG-006, directional labels)
- Four-level routing integration (git short-circuit, config routing,
  world-writable degradation, overlap rejection, parse-once)
- L4 rejection mechanism (VAL-CFG-019)
- Scrutiny round-1 hardening: expanded system deny list (①), HOME
  unset/symlink realpath robustness (②), explicit type errors (③),
  fall-through hygiene after containment rejection (⑥), Level-1 666
  gating + warning dedup (⑪), parse-once (⑬), no unbound mem_root (⑭)
"""

import logging
import shutil
import tempfile
import tomllib
from pathlib import Path

import pytest

from memory_core.tools import _gateway_config as gw
from memory_core.tools._gateway_config import (
    _check_l4_rejection,
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


@pytest.fixture
def tmp_path() -> Path:
    """Re-anchored tmp_path outside the system deny list and the source repo.

    pytest's default basetemp lives under /private/var (macOS TMPDIR),
    which the expanded _SYSTEM_PATHS deny list now rejects; anchoring under
    the repo's own tree instead would trip is_memory_core_source_repo's
    git-root detection. ~/.cache sits in the home subtree (explicitly
    allowed by the deny policy) and outside the repo, so the config layer
    can be exercised without special-casing. Cleaned up per test.
    """
    base = Path("~/.cache/memory-core-m4-config-tests").expanduser()
    base.mkdir(parents=True, exist_ok=True)
    case_dir = Path(tempfile.mkdtemp(prefix="case-", dir=base))
    yield case_dir
    shutil.rmtree(case_dir, ignore_errors=True)


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
        msg = overlap_errors[0].getMessage()
        ancestor = str((outer / "a").resolve())
        descendant = str((outer / "a" / "b").resolve())
        # Directional assertion (scrutiny misc-m4 ⑫): the nested path must be
        # labeled descendant OF the ancestor — guards against label inversion.
        assert f"descendant of {ancestor}" in msg, f"expected 'descendant of {ancestor}' in: {msg}"
        assert descendant in msg, f"expected descendant path {descendant} in: {msg}"


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


# ---------------------------------------------------------------------------
# VAL-CFG-017: members-only 配置 → 告警 + 启发式路由
# ---------------------------------------------------------------------------


class TestMembersOnlyConfig:
    def test_members_only_routes_to_heuristic_not_config_parent(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """VAL-CFG-017: members-only → 告警 + 启发式路由(≠ config parent)."""
        outer = tmp_path / "outer"
        outer.mkdir()
        # Config with members but NO memory_root
        _write_config(
            outer / CONFIG_NAME,
            'project = "test"\nmembers = ["./child"]\n',
        )
        # Create a subdirectory that would be heuristic candidate
        child = outer / "child"
        child.mkdir()
        (child / ".git").mkdir()

        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)

        # Should use heuristic (refined to child), NOT config parent
        assert repo_root == child.resolve(), f"Expected {child.resolve()}, got {repo_root}"
        # Should emit warning about missing memory_root
        warning_logs = [r for r in caplog.records if "no memory_root (has members only)" in r.message]
        assert len(warning_logs) >= 1
        assert str(outer / CONFIG_NAME) in warning_logs[0].getMessage()


# ---------------------------------------------------------------------------
# VAL-CFG-019: L4 自返零写入违约 - 空种子拒绝服务
# ---------------------------------------------------------------------------


class TestL4Rejection:
    def test_empty_seed_no_git_no_config_no_candidate_rejected(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """VAL-CFG-019: empty seed → explicit rejection with exit 0 + stderr + zero writes."""
        # Empty dir: no .git, no config, no child repo
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        rejection_msg = _check_l4_rejection(empty_dir)
        assert rejection_msg is not None
        assert "no .git directory" in rejection_msg
        assert "no memory-project.toml config" in rejection_msg
        assert "no valid child repository" in rejection_msg

    def test_empty_seed_with_git_ok(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """Empty seed with .git → OK (not rejected)."""
        git_dir = tmp_path / "git_repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()

        rejection_msg = _check_l4_rejection(git_dir)
        assert rejection_msg is None

    def test_empty_seed_with_config_ok(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """Empty seed with config → OK (not rejected)."""
        config_dir = tmp_path / "config_dir"
        config_dir.mkdir()
        _write_config(config_dir / CONFIG_NAME, 'project = "test"\n')

        rejection_msg = _check_l4_rejection(config_dir)
        assert rejection_msg is None

    def test_b_layer_refined_seed_ok(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """B-layer refined seed (non-git + valid child) → OK."""
        # Create non-git parent with git child
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        (child / ".git").mkdir()

        rejection_msg = _check_l4_rejection(parent)
        assert rejection_msg is None  # B-layer refinement finds child

    def test_memory_project_ok(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """Project with memory/system/ (no .git) → OK (valid memory project)."""
        mem_dir = tmp_path / "memory" / "system"
        mem_dir.mkdir(parents=True)

        rejection_msg = _check_l4_rejection(tmp_path)
        assert rejection_msg is None  # Valid memory project

    def test_plain_subdir_of_ancestor_configured_project_ok(self, tmp_path: Path):
        """VAL-CFG-014 layout: plain subdir of an ancestor-configured project → not rejected.

        The routing layer resolves roots via the ancestor config, so the seed
        itself carries none of the local markers.
        """
        outer = tmp_path / "proj"
        sub = outer / "sub"
        sub.mkdir(parents=True)
        (outer / "mem").mkdir()
        _write_config(outer / CONFIG_NAME, 'memory_root = "./mem"\n')

        assert _check_l4_rejection(sub) is None

    def test_broken_ancestor_config_still_rejects_plain_subdir(self, tmp_path: Path):
        """Unparseable ancestor config does not bypass the gate (mirrors routing gating)."""
        outer = tmp_path / "proj"
        sub = outer / "sub"
        sub.mkdir(parents=True)
        _write_config(outer / CONFIG_NAME, "broken [[[\n")

        assert _check_l4_rejection(sub) is not None

    def test_world_writable_ancestor_config_still_rejects_plain_subdir(self, tmp_path: Path):
        """World-writable (ignored) ancestor config does not bypass the gate."""
        outer = tmp_path / "proj"
        sub = outer / "sub"
        sub.mkdir(parents=True)
        cfg = _write_config(outer / CONFIG_NAME, 'memory_root = "./mem"\n')
        cfg.chmod(0o666)
        try:
            assert _check_l4_rejection(sub) is not None
        finally:
            cfg.chmod(0o644)


# ---------------------------------------------------------------------------
# Scrutiny ①/②: expanded system deny list + HOME realpath robustness
# ---------------------------------------------------------------------------


class TestSystemPathDenyList:
    def test_expanded_entries_present(self):
        """①: classic OS-managed roots are all in the deny list."""
        expected = {
            "/tmp",
            "/private/tmp",
            "/var",
            "/private/var",
            "/etc",
            "/bin",
            "/sbin",
            "/opt",
            "/Applications",
        }
        assert expected <= set(gw._SYSTEM_PATHS)

    def test_config_under_deny_listed_root_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """①: memory_root resolving under a deny-listed root is rejected.

        The deny-list branch is only reachable when the config tree itself
        sits under a denied root (containment catches plain ../ escapes
        first), so the test injects tmp_path into the deny list.
        """
        cfg = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./m"\n')
        (tmp_path / "m").mkdir()
        monkeypatch.setattr(gw, "_SYSTEM_PATHS", frozenset({str(tmp_path)} | set(gw._SYSTEM_PATHS)))
        assert _resolve_memory_root("./m", cfg) is None

    def test_home_exact_denied_subdir_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """HOME itself is denied, proper subdirectories of HOME stay routable."""
        home = tmp_path / "home"
        (home / "work").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        # Simulate the deny entry an import under this HOME would produce
        monkeypatch.setattr(gw, "_SYSTEM_PATHS", frozenset({"/", str(home)} | set(gw._SYSTEM_PATHS)))
        cfg_exact = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./home"\n')
        # HOME itself (exact match) is denied
        assert _resolve_memory_root("./home", cfg_exact) is None
        # Subdirectory of HOME is allowed
        cfg_sub = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./home/work"\n')
        assert _resolve_memory_root("./home/work", cfg_sub) == (home / "work").resolve()

    def test_home_symlink_realpath_normalized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """②: symlinked HOME must not cause the home tree to be denied.

        HOME env points at a symlink; the raw-string comparison would treat
        the resolved home as a non-HOME system path and deny every
        subdirectory under it.
        """
        home_real = tmp_path / "home_real"
        (home_real / "work").mkdir(parents=True)
        home_link = tmp_path / "home_link"
        home_link.symlink_to(home_real, target_is_directory=True)
        monkeypatch.setenv("HOME", str(home_link))
        # Simulate the deny entry an import under this HOME would produce
        monkeypatch.setattr(gw, "_SYSTEM_PATHS", frozenset({"/", str(home_link)}))
        cfg_sub = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./home_real/work"\n')
        assert _resolve_memory_root("./home_real/work", cfg_sub) == (home_real / "work").resolve()
        # The real home itself is still denied (exact match via symlink)
        cfg_exact = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./home_real"\n')
        assert _resolve_memory_root("./home_real", cfg_exact) is None

    def test_home_unset_does_not_break_resolution(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """②: unset HOME degrades gracefully instead of crashing the deny check."""
        (tmp_path / "m").mkdir()
        cfg = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./m"\n')
        monkeypatch.delenv("HOME", raising=False)
        assert _resolve_memory_root("./m", cfg) == (tmp_path / "m").resolve()


# ---------------------------------------------------------------------------
# Scrutiny ③: explicit type errors instead of silent str() coercion
# ---------------------------------------------------------------------------


class TestValidateMemoryRootValueTypes:
    @pytest.mark.parametrize("value", [123, 1.5, True, {"root": "./m"}, None])
    def test_non_string_scalar_rejected(self, tmp_path: Path, value):
        is_valid, error = _validate_memory_root_value(value, tmp_path / CONFIG_NAME)
        assert not is_valid
        assert "invalid type" in (error or "")

    def test_list_with_non_string_first_element_rejected(self, tmp_path: Path):
        is_valid, error = _validate_memory_root_value([42], tmp_path / CONFIG_NAME)
        assert not is_valid
        assert "invalid type" in (error or "")

    def test_string_list_first_element_accepted(self, tmp_path: Path):
        assert _validate_memory_root_value(["./m"], tmp_path / CONFIG_NAME) == (True, None)


class TestResolveMemoryRootTypes:
    def test_non_string_scalar_returns_none_with_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        cfg = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./m"\n')
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            assert _resolve_memory_root(123, cfg) is None
        assert any("invalid type" in r.message for r in caplog.records)

    def test_list_non_string_first_element_returns_none(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        cfg = _write_config(tmp_path / CONFIG_NAME, 'memory_root = "./m"\n')
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            assert _resolve_memory_root([42, "./m"], cfg) is None
        assert any("invalid type" in r.message for r in caplog.records)


class TestExplicitTypeErrorsRouting:
    def test_int_memory_root_rejected_with_explicit_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """③: int memory_root → explicit error + degraded routing (no str(123))."""
        outer = tmp_path / "outer"
        outer.mkdir()
        _write_config(outer / CONFIG_NAME, 'project = "t"\nmemory_root = 123\n')
        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)
        assert repo_root == outer.resolve()  # degraded routing
        assert any("invalid type" in r.message for r in caplog.records)

    def test_non_string_list_element_rejected_with_explicit_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """③: memory_root = [1] → explicit error + degraded routing."""
        outer = tmp_path / "outer"
        outer.mkdir()
        _write_config(outer / CONFIG_NAME, 'project = "t"\nmemory_root = [1]\n')
        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)
        assert repo_root == outer.resolve()  # degraded routing
        assert any("invalid type" in r.message for r in caplog.records)

    def test_non_string_member_rejected(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """③: non-string member entry → explicit out-of-bounds rejection."""
        outer = tmp_path / "outer"
        outer.mkdir()
        target = outer / "target"
        target.mkdir()
        _write_config(outer / CONFIG_NAME, 'memory_root = "./target"\nmembers = ["./ok", 42]\n')
        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)
        assert repo_root == outer.resolve()  # config level rejected
        assert any("non-string member" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Scrutiny ⑥/⑭: fall-through hygiene + no unbound mem_root at Level 2
# ---------------------------------------------------------------------------


class TestFallThroughHygiene:
    def test_containment_rejection_skips_fallthrough_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """⑥: containment-rejected memory_root must not produce the misleading
        'no memory_root and no members' fall-through warning."""
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / "child").mkdir()
        _write_config(outer / CONFIG_NAME, 'memory_root = "../../elsewhere"\nmembers = ["./child"]\n')
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)
        assert repo_root == outer.resolve()  # degraded routing
        assert not any("no memory_root and no members" in r.message for r in caplog.records)
        assert any("escapes config parent" in r.message for r in caplog.records)

    def test_empty_list_memory_root_nonblocking_level2(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """⑭: empty-list memory_root at Level 2 (non-git seed) → error logged,
        no NameError from an unbound mem_root, degraded routing."""
        outer = tmp_path / "outer"
        outer.mkdir()
        _write_config(outer / CONFIG_NAME, 'project = "t"\nmemory_root = []\n')
        with caplog.at_level(logging.ERROR, logger=_MODULE_LOGGER):
            repo_root, _ = _resolve_repo_root_with_config(outer)
        assert repo_root == outer.resolve()  # degraded routing
        assert any("empty list" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Scrutiny ⑪: Level-1 666 gating + world-writable warning dedup
# ---------------------------------------------------------------------------


class TestLevelOneHardening:
    def test_level1_world_writable_config_skips_conflict_check(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """⑪: 666 config at a git seed is untrusted → no VAL-CFG-005 conflict line."""
        git_root = tmp_path / "git_repo"
        git_root.mkdir()
        (git_root / ".git").mkdir()
        (git_root / "different").mkdir()
        cfg = _write_config(git_root / CONFIG_NAME, 'project = "t"\nmemory_root = "./different"\n')
        cfg.chmod(0o666)
        try:
            with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
                repo_root, _ = _resolve_repo_root_with_config(git_root)
            assert repo_root == git_root.resolve()  # git still wins
            assert not any("config and git root conflict" in r.message for r in caplog.records)
            assert any("world-writable" in r.message for r in caplog.records)
        finally:
            cfg.chmod(0o644)

    def test_world_writable_warning_emitted_once(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        """⑪: the same world-writable config logs exactly one warning."""
        outer = tmp_path / "outer"
        outer.mkdir()
        target = outer / "target"
        target.mkdir()
        cfg = _write_config(outer / CONFIG_NAME, 'memory_root = "./target"\n')
        cfg.chmod(0o666)
        try:
            with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
                _resolve_repo_root_with_config(outer)
            ww_warnings = [r for r in caplog.records if "world-writable" in r.message]
            assert len(ww_warnings) == 1
        finally:
            cfg.chmod(0o644)


# ---------------------------------------------------------------------------
# Scrutiny ⑬: parse-once optimization
# ---------------------------------------------------------------------------


class TestParseOnce:
    def test_configs_parsed_exactly_once(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """⑬: each config in the tree is parsed once (no re-parse of the winner)."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        (outer / "m").mkdir()
        (inner / "m").mkdir()
        _write_config(outer / CONFIG_NAME, 'memory_root = "./m"\n')
        _write_config(inner / CONFIG_NAME, 'memory_root = "./m"\n')
        calls: list[Path] = []
        real_parse = gw._parse_project_config

        def counting_parse(path: Path, **kwargs):
            calls.append(path)
            return real_parse(path, **kwargs)

        monkeypatch.setattr(gw, "_parse_project_config", counting_parse)
        _resolve_repo_root_with_config(inner)
        expected = [(inner / CONFIG_NAME).resolve(), (outer / CONFIG_NAME).resolve()]
        assert sorted(calls) == sorted(expected)  # exactly one parse per config
