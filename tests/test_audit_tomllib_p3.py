"""M3 audit robustness tests: tomllib parsing, fingerprint collision, whitelist tightening, backups recursion.

Covers VAL-AUDIT-001 through VAL-AUDIT-017.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.tools._audit_checks import (
    _extract_version_from_toml,
    check_global_residue,
    check_large_or_db_files,
    check_unsigned_files,
    check_version_consistency,
)
from memory_core.tools._audit_project import _normalize_for_compare


# ---------------------------------------------------------------------------
# VAL-AUDIT-001: 四优先级键双引号解析
# ---------------------------------------------------------------------------
class TestValAudit001FourPriorityDoubleQuote:
    @pytest.mark.parametrize(
        "toml_text",
        [
            '[memory]\nmemory_version = "X"',  # (a) memory.lock style
            '[core]\nversion = "X"',  # (b) adapter.toml style
            'memory_version = "X"',  # (c) ownership.toml style (top-level)
            'version = "X"',  # (d) fallback (top-level)
        ],
    )
    def test_four_priority_keys_double_quote(self, toml_text: str) -> None:
        result = _extract_version_from_toml(toml_text.replace("X", CURRENT_MEMORY_VERSION))
        assert result == CURRENT_MEMORY_VERSION


# ---------------------------------------------------------------------------
# VAL-AUDIT-002: 单引号 version 键正确解析
# ---------------------------------------------------------------------------
class TestValAudit002SingleQuote:
    @pytest.mark.parametrize(
        "toml_text",
        [
            "[memory]\nmemory_version = 'X'",
            "[core]\nversion = 'X'",
            "memory_version = 'X'",
            "version = 'X'",
        ],
    )
    def test_single_quote_version(self, toml_text: str) -> None:
        result = _extract_version_from_toml(toml_text.replace("X", CURRENT_MEMORY_VERSION))
        assert result == CURRENT_MEMORY_VERSION


# ---------------------------------------------------------------------------
# VAL-AUDIT-003: 非参与 table 的 version 键不匹配
# ---------------------------------------------------------------------------
class TestValAudit003NonParticipatingTable:
    @pytest.mark.parametrize(
        "toml_text",
        [
            '[dependencies]\nversion = "9.9.9"',
            '[tool.poetry]\nversion = "9.9.9"',
            '[metadata]\nmemory_version = "9.9.9"',
            '[extra.core]\nversion = "9.9.9"',
        ],
    )
    def test_non_participating_table_returns_none(self, toml_text: str) -> None:
        result = _extract_version_from_toml(toml_text)
        assert result is None


# ---------------------------------------------------------------------------
# VAL-AUDIT-004: 优先级序 + 位置无关
# ---------------------------------------------------------------------------
class TestValAudit004PriorityOrder:
    def test_dependencies_before_memory(self) -> None:
        text = f'[dependencies]\nversion = "9.9.9"\n\n[memory]\nmemory_version = "{CURRENT_MEMORY_VERSION}"'
        assert _extract_version_from_toml(text) == CURRENT_MEMORY_VERSION

    def test_dependencies_before_core(self) -> None:
        text = f'[dependencies]\nversion = "9.9.9"\n\n[core]\nversion = "{CURRENT_MEMORY_VERSION}"'
        assert _extract_version_from_toml(text) == CURRENT_MEMORY_VERSION

    def test_dependencies_before_top_level_memory_version(self) -> None:
        text = f'memory_version = "{CURRENT_MEMORY_VERSION}"\n\n[dependencies]\nversion = "9.9.9"'
        assert _extract_version_from_toml(text) == CURRENT_MEMORY_VERSION

    def test_core_version_priority_over_top_level_memory_version(self) -> None:
        # C2 修复：memory_version 必须在 [core] 头之前，否则 tomllib 会将其归入 [core] table
        text = f'memory_version = "{CURRENT_MEMORY_VERSION}"\n\n[core]\nversion = "8.8.8"'
        assert _extract_version_from_toml(text) == "8.8.8"

    def test_memory_version_priority_over_core_version(self) -> None:
        text = f'[memory]\nmemory_version = "7.7.7"\n\n[core]\nversion = "{CURRENT_MEMORY_VERSION}"'
        assert _extract_version_from_toml(text) == "7.7.7"


# ---------------------------------------------------------------------------
# VAL-AUDIT-005: 畸形 TOML 回退不崩溃
# ---------------------------------------------------------------------------
class TestValAudit005MalformedToml:
    @pytest.mark.parametrize(
        "toml_text",
        [
            "[memory\n",  # unclosed table header
            'memory_version = = "0.40.1"',  # double equals
            'memory_version = "0.4[EOF]',  # unterminated string
            "memory_version = \x00",  # NUL character
        ],
    )
    def test_malformed_toml_no_crash(self, toml_text: str) -> None:
        # Should not raise; may return str or None
        result = _extract_version_from_toml(toml_text)
        assert result is None or isinstance(result, str)

    def test_mildly_malformed_still_extracts(self) -> None:
        # Table header malformed but key-value is fine
        text = '[memory\nmemory_version = "0.40.1"\n'
        result = _extract_version_from_toml(text)
        # Fallback regex should still extract
        assert result == "0.40.1"


# ---------------------------------------------------------------------------
# VAL-AUDIT-006: 标准三文件全绿
# ---------------------------------------------------------------------------
class TestValAudit006StandardThreeFiles:
    def test_standard_three_files_no_violations(self, tmp_path: Path) -> None:
        from memory_core.tools._init_templates_core import template_adapter_toml, template_memory_lock
        from memory_core.tools._init_templates_misc import template_ownership_toml

        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)

        lock_content, _ = template_memory_lock("demo")
        adapter_content, _ = template_adapter_toml("demo")
        ownership_content, _ = template_ownership_toml("demo")

        (system_dir / "memory.lock").write_text(lock_content)
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# VAL-AUDIT-007: 缺失文件仍报 critical
# ---------------------------------------------------------------------------
class TestValAudit007MissingFiles:
    def test_all_three_missing(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        violations = check_version_consistency(tmp_path)
        assert len(violations) == 3
        files = {v["file"] for v in violations}
        assert "memory/system/memory.lock" in files
        assert "memory/system/adapter.toml" in files
        assert "memory/system/ownership.toml" in files

    def test_only_memory_lock_missing(self, tmp_path: Path) -> None:
        from memory_core.tools._init_templates_core import template_adapter_toml
        from memory_core.tools._init_templates_misc import template_ownership_toml

        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)
        adapter_content, _ = template_adapter_toml("demo")
        ownership_content, _ = template_ownership_toml("demo")
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        assert len(violations) == 1
        assert violations[0]["file"] == "memory/system/memory.lock"

    def test_single_quote_memory_lock_no_violations(self, tmp_path: Path) -> None:
        from memory_core.tools._init_templates_core import template_adapter_toml
        from memory_core.tools._init_templates_misc import template_ownership_toml

        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)

        # memory.lock with single quotes
        lock_content = f"""[memory]
project = "demo"
memory_version = '{CURRENT_MEMORY_VERSION}'
"""
        adapter_content, _ = template_adapter_toml("demo")
        ownership_content, _ = template_ownership_toml("demo")

        (system_dir / "memory.lock").write_text(lock_content)
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# VAL-AUDIT-008: 版本不一致判定回归
# ---------------------------------------------------------------------------
class TestValAudit008VersionMismatch:
    def test_adapter_mismatch(self, tmp_path: Path) -> None:
        from memory_core.tools._init_templates_core import template_memory_lock
        from memory_core.tools._init_templates_misc import template_ownership_toml

        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)

        lock_content, _ = template_memory_lock("demo")
        ownership_content, _ = template_ownership_toml("demo")

        # adapter.toml with wrong version
        adapter_content = '[core]\nversion = "0.0.1"\n'

        (system_dir / "memory.lock").write_text(lock_content)
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        # Should have: adapter mismatch + unique>1 summary
        assert len(violations) == 2
        files = {v["file"] for v in violations}
        assert "memory/system/adapter.toml" in files
        assert "memory/system/" in files

    def test_all_same_old_version(self, tmp_path: Path) -> None:
        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)

        lock_content = '[memory]\nmemory_version = "0.39.0"\n'
        adapter_content = '[core]\nversion = "0.39.0"\n'
        ownership_content = 'memory_version = "0.39.0"\n'

        (system_dir / "memory.lock").write_text(lock_content)
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        # Three "not matching expected" violations, no unique>1 summary
        assert len(violations) == 3

    def test_all_three_different(self, tmp_path: Path) -> None:
        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)

        lock_content = '[memory]\nmemory_version = "0.38.0"\n'
        adapter_content = '[core]\nversion = "0.39.0"\n'
        ownership_content = 'memory_version = "0.40.0"\n'

        (system_dir / "memory.lock").write_text(lock_content)
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        # Three "not matching expected" + one unique>1 summary
        assert len(violations) == 4


# ---------------------------------------------------------------------------
# VAL-AUDIT-009: 指纹碰撞修复 — 共享模板头不再误报
# ---------------------------------------------------------------------------
class TestValAudit009FingerprintCollision:
    def test_shared_header_different_body_no_residue(self, tmp_path: Path) -> None:
        # Global KB doc: 400 A's + unique tail
        global_text = "A" * 400 + "HEADER-UNIQUE-TAIL-G1"
        global_fp = _normalize_for_compare(global_text)

        # Project doc: 400 A's + different body
        project_text = "A" * 400 + "DIFFERENT-BODY-PROJECT"

        lessons_dir = tmp_path / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "lesson.md").write_text(project_text)

        global_fingerprints = {global_fp: "operations/global-doc.md"}
        violations = check_global_residue(tmp_path, global_fingerprints)
        assert violations == []


# ---------------------------------------------------------------------------
# VAL-AUDIT-010: 真残留仍报
# ---------------------------------------------------------------------------
class TestValAudit010RealResidueDetected:
    def test_identical_content_detected(self, tmp_path: Path) -> None:
        identical_text = "# Some content\n\nThis is the same content."
        global_fp = _normalize_for_compare(identical_text)

        lessons_dir = tmp_path / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "lesson.md").write_text(identical_text)

        global_fingerprints = {global_fp: "operations/global-doc.md"}
        violations = check_global_residue(tmp_path, global_fingerprints)
        assert len(violations) == 1
        assert violations[0]["type"] == "residue"
        assert violations[0]["severity"] == "warning"

    # C3：补充 frontmatter-differs 变体（契约要求两变体参数化）
    def test_identical_content_different_frontmatter_detected(self, tmp_path: Path) -> None:
        """即使 frontmatter 不同，正文相同仍应检出为残留"""
        # 全局 KB 文档无 frontmatter
        global_text = "# Main content\n\nThis is the body."
        global_fp = _normalize_for_compare(global_text)

        # 项目文档有 frontmatter 但正文相同
        project_text_with_frontmatter = """---
title: Project Lesson
date: 2026-08-25
---
# Main content

This is the body."""

        lessons_dir = tmp_path / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "lesson.md").write_text(project_text_with_frontmatter)

        global_fingerprints = {global_fp: "operations/global-doc.md"}
        violations = check_global_residue(tmp_path, global_fingerprints)
        assert len(violations) == 1
        assert violations[0]["type"] == "residue"


# ---------------------------------------------------------------------------
# VAL-AUDIT-011: 顶层 README/INDEX 豁免保持
# ---------------------------------------------------------------------------
class TestValAudit011TopLevelWhitelist:
    def test_top_level_readme_index_exempt(self, tmp_path: Path) -> None:
        kb_dir = tmp_path / "memory" / "kb"
        kb_dir.mkdir(parents=True)
        (kb_dir / "README.md").write_text("# README")
        (kb_dir / "INDEX.md").write_text("# INDEX")

        violations = check_unsigned_files(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# VAL-AUDIT-012: 深层同名不再豁免
# ---------------------------------------------------------------------------
class TestValAudit012DeepSameNameNotExempt:
    def test_deep_readme_index_not_exempt(self, tmp_path: Path) -> None:
        lessons_dir = tmp_path / "memory" / "kb" / "lessons"
        decisions_dir = tmp_path / "memory" / "kb" / "decisions"
        lessons_dir.mkdir(parents=True)
        decisions_dir.mkdir(parents=True)

        (lessons_dir / "README.md").write_text("# Deep README")
        (decisions_dir / "INDEX.md").write_text("# Deep INDEX")

        violations = check_unsigned_files(tmp_path)
        assert len(violations) == 2
        files = {v["file"] for v in violations}
        assert "memory/kb/lessons/README.md" in files
        assert "memory/kb/decisions/INDEX.md" in files


# ---------------------------------------------------------------------------
# VAL-AUDIT-013: backups 递归检测 — memory/docs/backups/
# ---------------------------------------------------------------------------
class TestValAudit013BackupsRecursive:
    def test_memory_docs_backups_detected(self, tmp_path: Path) -> None:
        backups_dir = tmp_path / "memory" / "docs" / "backups"
        backups_dir.mkdir(parents=True)
        (backups_dir / "dump.sql.bak").write_text("x")

        violations = check_large_or_db_files(tmp_path)
        # Should have directory-level violation
        dir_violations = [v for v in violations if v["file"] == "memory/docs/backups"]
        assert len(dir_violations) == 1
        assert dir_violations[0]["severity"] == "critical"
        assert "backups" in dir_violations[0]["detail"]

    def test_nested_unenumerated_backups(self, tmp_path: Path) -> None:
        backups_dir = tmp_path / "memory" / "kb" / "lessons" / "backups"
        backups_dir.mkdir(parents=True)
        (backups_dir / "x.bak").write_text("x")

        violations = check_large_or_db_files(tmp_path)
        dir_violations = [v for v in violations if "backups" in v["file"]]
        assert len(dir_violations) >= 1


# ---------------------------------------------------------------------------
# VAL-AUDIT-014: backups 无回归 — 根与 kb
# ---------------------------------------------------------------------------
class TestValAudit014BackupsNoRegression:
    def test_root_backups(self, tmp_path: Path) -> None:
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        (backups_dir / "f.bak").write_text("x")

        violations = check_large_or_db_files(tmp_path)
        dir_violations = [v for v in violations if v["file"] == "backups"]
        assert len(dir_violations) == 1

    def test_kb_backups(self, tmp_path: Path) -> None:
        backups_dir = tmp_path / "memory" / "kb" / "backups"
        backups_dir.mkdir(parents=True)
        (backups_dir / "f.bak").write_text("x")

        violations = check_large_or_db_files(tmp_path)
        dir_violations = [v for v in violations if v["file"] == "memory/kb/backups"]
        assert len(dir_violations) == 1

    def test_empty_backups_no_violation(self, tmp_path: Path) -> None:
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        violations = check_large_or_db_files(tmp_path)
        dir_violations = [v for v in violations if "backups" in v["file"]]
        assert len(dir_violations) == 0

    # C4：补充两处 backups 并存恰 2 条（去重）用例
    def test_two_backups_dirs_exactly_two_violations(self, tmp_path: Path) -> None:
        """两处 backups 目录并存时，应报恰 2 条违规（去重后）"""
        # 根目录 backups
        root_backups = tmp_path / "backups"
        root_backups.mkdir()
        (root_backups / "dump1.sql").write_text("x")

        # memory/kb/backups
        kb_backups = tmp_path / "memory" / "kb" / "backups"
        kb_backups.mkdir(parents=True)
        (kb_backups / "dump2.sql").write_text("y")

        violations = check_large_or_db_files(tmp_path)
        dir_violations = [v for v in violations if "backups" in v["file"]]
        assert len(dir_violations) == 2
        files = {v["file"] for v in dir_violations}
        assert "backups" in files
        assert "memory/kb/backups" in files


# ---------------------------------------------------------------------------
# VAL-AUDIT-015: 仓库根实测输出不变
# ---------------------------------------------------------------------------
class TestValAudit015RepoRootBaseline:
    def test_empty_system_dir_baseline(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        violations = check_version_consistency(tmp_path)
        assert len(violations) == 3
        files = {v["file"] for v in violations}
        assert "memory/system/memory.lock" in files
        assert "memory/system/adapter.toml" in files
        assert "memory/system/ownership.toml" in files
        for v in violations:
            assert "缺失或无法解析版本号" in v["detail"]


# ---------------------------------------------------------------------------
# VAL-AUDIT-016: init 产物单引号重写变体
# ---------------------------------------------------------------------------
class TestValAudit016InitSingleQuoteRewrite:
    def test_single_quote_rewrite_no_violations(self, tmp_path: Path) -> None:
        from memory_core.tools._init_templates_core import template_adapter_toml, template_memory_lock
        from memory_core.tools._init_templates_misc import template_ownership_toml

        system_dir = tmp_path / "memory" / "system"
        system_dir.mkdir(parents=True)

        lock_content, _ = template_memory_lock("demo")
        adapter_content, _ = template_adapter_toml("demo")
        ownership_content, _ = template_ownership_toml("demo")

        # Rewrite double quotes to single quotes for version fields
        import re

        lock_content = re.sub(r'memory_version = "([^"]+)"', r"memory_version = '\1'", lock_content)
        adapter_content = re.sub(r'version = "([^"]+)"', r"version = '\1'", adapter_content)
        ownership_content = re.sub(r'memory_version = "([^"]+)"', r"memory_version = '\1'", ownership_content)

        (system_dir / "memory.lock").write_text(lock_content)
        (system_dir / "adapter.toml").write_text(adapter_content)
        (system_dir / "ownership.toml").write_text(ownership_content)

        violations = check_version_consistency(tmp_path)
        assert violations == []
