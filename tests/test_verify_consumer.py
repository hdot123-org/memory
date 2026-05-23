#!/usr/bin/env python3
"""Tests for verify_consumer CLI (T2.6)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import verify_consumer
from memory_core.tools.index_schema import build_headers, inject_headers


def _make_initialized_target(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    memory = target / "memory" / "system"
    memory.mkdir(parents=True)
    for fname in ["CANONICAL.md", "STATE.md", "PLAN.md", "TASKS.md"]:
        (memory / fname).write_text("# stub\n", encoding="utf-8")
    (memory / "adapter.toml").write_text("schema_version = \"adapter-v1\"\n", encoding="utf-8")
    (memory / "ownership.toml").write_text("schema_version = \"memory-ownership-v1\"\n", encoding="utf-8")
    headers = build_headers("0.4.0")
    (target / "INDEX.md").write_text(inject_headers("# Workspace\n", headers), encoding="utf-8")
    (target / "memory" / "kb").mkdir(parents=True)
    (target / "memory" / "kb" / "INDEX.md").write_text(
        inject_headers("# KB\n", headers), encoding="utf-8"
    )
    (target / "memory" / "docs").mkdir(parents=True)
    (target / "memory" / "docs" / "INDEX.md").write_text(
        inject_headers("# Docs\n", headers), encoding="utf-8"
    )
    return target


def test_verify_passes_for_well_formed_target(tmp_path: Path):
    target = _make_initialized_target(tmp_path)
    report = verify_consumer.verify(target)
    assert report.all_passed, [c for c in report.checks if not c.passed]


def test_verify_fails_when_dot_memory_missing(tmp_path: Path):
    target = tmp_path / "empty"
    target.mkdir()
    report = verify_consumer.verify(target)
    assert not report.all_passed
    failed_names = [c.name for c in report.checks if not c.passed]
    assert "target.has_dot_memory" in failed_names


def test_verify_fails_when_required_file_missing(tmp_path: Path):
    target = _make_initialized_target(tmp_path)
    (target / "memory" / "system" / "STATE.md").unlink()
    report = verify_consumer.verify(target)
    assert not report.all_passed
    failed_names = [c.name for c in report.checks if not c.passed]
    assert any("STATE.md" in n for n in failed_names)


def test_verify_flags_index_without_schema_header(tmp_path: Path):
    target = _make_initialized_target(tmp_path)
    (target / "INDEX.md").write_text("# legacy without headers\n", encoding="utf-8")
    report = verify_consumer.verify(target)
    failed = [c for c in report.checks if not c.passed]
    assert any("has_schema_header" in c.name and "INDEX.md" in c.name for c in failed)


def test_verify_flags_incompatible_schema(tmp_path: Path):
    target = _make_initialized_target(tmp_path)
    bad = build_headers("0.4.0", schema_version="9.0")
    (target / "INDEX.md").write_text(inject_headers("# Workspace\n", bad), encoding="utf-8")
    report = verify_consumer.verify(target)
    failed = [c for c in report.checks if not c.passed]
    assert any("schema_compatible" in c.name and "INDEX.md" in c.name for c in failed)


def test_main_returns_zero_on_pass(tmp_path: Path, capsys):
    target = _make_initialized_target(tmp_path)
    rc = verify_consumer.main(["--path", str(target)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "PASS" in captured.out


def test_main_returns_one_on_failure(tmp_path: Path, capsys):
    target = _make_initialized_target(tmp_path)
    (target / "memory" / "system" / "STATE.md").unlink()
    rc = verify_consumer.main(["--path", str(target)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FAIL" in captured.out


def test_main_returns_two_when_uninitialized(tmp_path: Path, capsys):
    target = tmp_path / "empty"
    target.mkdir()
    rc = verify_consumer.main(["--path", str(target)])
    assert rc == 2


def test_main_json_output(tmp_path: Path, capsys):
    target = _make_initialized_target(tmp_path)
    rc = verify_consumer.main(["--path", str(target), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload: dict[str, Any] = json.loads(captured.out)
    assert payload["all_passed"] is True
    assert payload["expected_schema_version"]
    assert isinstance(payload["checks"], list)


def test_main_nonexistent_path_returns_two(tmp_path: Path, capsys):
    bogus = tmp_path / "does-not-exist"
    rc = verify_consumer.main(["--path", str(bogus)])
    assert rc == 2


# --- Fill quality check tests (warnings, not errors) ---

_CANONICAL_WITH_PLACEHOLDER = """\
# CANONICAL.md

## 项目信息

- **项目名称**：TestProject
- **项目类型**：web/api
- **主语言**：（待填写）
- **创建日期**：2025-01-01

## 工具链

## 变更日志
"""

_CANONICAL_FILLED = """\
# CANONICAL.md

## 项目信息

- **项目名称**：TestProject
- **项目类型**：web/api
- **主语言**：Python
- **创建日期**：2025-01-01

## 工具链

| 名称 | 配置文件 | 类别 |
|------|----------|------|
| pytest | pytest.ini | test |
| ruff | ruff.toml | linter |

## 变更日志
"""

_CANONICAL_MISMATCHED_LANG = """\
# CANONICAL.md

## 项目信息

- **项目名称**：TestProject
- **项目类型**：web/api
- **主语言**：Go
- **创建日期**：2025-01-01

## 工具链

| 名称 | 配置文件 | 类别 |
|------|----------|------|
| make | Makefile | build |

## 变更日志
"""

_CANONICAL_EMPTY_TOOLCHAIN_TEMPLATE = """\
# CANONICAL.md

## 项目信息

- **项目名称**：TestProject
- **项目类型**：web/api
- **主语言**：Python
- **创建日期**：2025-01-01

## 工具链

{{TOOLCHAIN}}

## 变更日志
"""


def _make_target_with_canonical(tmp_path: Path, canonical_content: str) -> Path:
    """Create a minimal initialized target with specific CANONICAL.md content."""
    target = _make_initialized_target(tmp_path)
    (target / "memory" / "system" / "CANONICAL.md").write_text(canonical_content, encoding="utf-8")
    return target


def test_fill_quality_warning_for_placeholder_language(tmp_path: Path, capsys):
    """When 主语言 still has placeholder, a warning check is emitted (not error)."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_WITH_PLACEHOLDER)
    report = verify_consumer.verify(target)
    # Warnings are recorded as passed=True
    assert report.all_passed, "Fill quality warnings should not cause failure"
    # Should have the warning check
    placeholder_checks = [
        c for c in report.checks
        if c.name == "fill_quality.primary_language_placeholder"
    ]
    assert len(placeholder_checks) == 1
    assert "WARNING" in placeholder_checks[0].detail


def test_fill_quality_no_warning_for_filled_language(tmp_path: Path):
    """When 主语言 is filled, no placeholder warning."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_FILLED)
    report = verify_consumer.verify(target)
    placeholder_checks = [
        c for c in report.checks
        if c.name == "fill_quality.primary_language_placeholder"
    ]
    assert len(placeholder_checks) == 0, "No warning expected when language is filled"


def test_fill_quality_warning_for_placeholder_toolchain(tmp_path: Path):
    """When toolchain table has only placeholder entries, a warning is emitted."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_WITH_PLACEHOLDER)
    report = verify_consumer.verify(target)
    assert report.all_passed
    toolchain_checks = [
        c for c in report.checks
        if c.name == "fill_quality.toolchain_placeholder"
    ]
    assert len(toolchain_checks) == 1
    assert "WARNING" in toolchain_checks[0].detail


def test_fill_quality_no_warning_for_filled_toolchain(tmp_path: Path):
    """When toolchain has real entries, no placeholder warning."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_FILLED)
    report = verify_consumer.verify(target)
    toolchain_checks = [
        c for c in report.checks
        if c.name == "fill_quality.toolchain_placeholder"
    ]
    assert len(toolchain_checks) == 0, "No warning expected when toolchain is filled"


def test_fill_consistency_warning_for_mismatched_language(tmp_path: Path):
    """When declared language mismatches actual project language, warning emitted."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_MISMATCHED_LANG)
    # Create a Python project (pyproject.toml)
    (target / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    report = verify_consumer.verify(target)
    # Warnings don't cause failure
    assert report.all_passed, "Consistency warnings should not cause failure"
    mismatch_checks = [
        c for c in report.checks
        if c.name == "fill_consistency.language_mismatch"
    ]
    assert len(mismatch_checks) == 1
    assert "WARNING" in mismatch_checks[0].detail
    assert "Go" in mismatch_checks[0].detail  # declared
    assert "Python" in mismatch_checks[0].detail  # actual


def test_fill_consistency_no_warning_for_matching_language(tmp_path: Path):
    """When declared language matches actual, no warning."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_FILLED)
    # Create a Python project
    (target / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    report = verify_consumer.verify(target)
    mismatch_checks = [
        c for c in report.checks
        if c.name == "fill_consistency.language_mismatch"
    ]
    assert len(mismatch_checks) == 0, "No warning expected when languages match"


def test_fill_quality_still_returns_zero_with_warnings(tmp_path: Path, capsys):
    """Verify that fill quality warnings do not cause non-zero exit code."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_WITH_PLACEHOLDER)
    rc = verify_consumer.main(["--path", str(target)])
    captured = capsys.readouterr()
    assert rc == 0, "Warnings should not change exit code"
    assert "PASS" in captured.out


def test_fill_consistency_json_output_includes_warnings(tmp_path: Path, capsys):
    """JSON output should include fill quality warning checks."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_WITH_PLACEHOLDER)
    rc = verify_consumer.main(["--path", str(target), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload: dict[str, Any] = json.loads(captured.out)
    check_names = [c["name"] for c in payload["checks"]]
    assert "fill_quality.primary_language_placeholder" in check_names


def test_fill_quality_warning_for_empty_toolchain_template(tmp_path: Path):
    """When toolchain section only has {{TOOLCHAIN}} template var, warning emitted."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_EMPTY_TOOLCHAIN_TEMPLATE)
    report = verify_consumer.verify(target)
    assert report.all_passed
    toolchain_checks = [
        c for c in report.checks
        if c.name == "fill_quality.toolchain_placeholder"
    ]
    assert len(toolchain_checks) == 1
    assert "WARNING" in toolchain_checks[0].detail


# --- Table format tests ---

_CANONICAL_TABLE_PLACEHOLDER = """\
# CANONICAL.md

## 项目信息

| 字段 | 值 |
|------|-----|
| 项目名称 | TestProject |
| 项目类型 | （待填写） |
| 主语言 | （待填写） |
| 创建日期 | 2025-01-01 |

## 编码规范

（待填写：项目编码标准描述，如缩进、编码风格等）

## 架构约束

（待填写：架构层面的约束条件，如设计模式、分层要求等）

## 命名约定

（待填写：变量、函数、文件命名规则）

## 工具链

| 工具 | 版本/说明 |
|------|----------|
| （待填写） | （待填写） |

## 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2025-01-01 | 1.0.0 | 初始规范建立 |
"""

_CANONICAL_TABLE_FILLED = """\
# CANONICAL.md

## 项目信息

| 字段 | 值 |
|------|-----|
| 项目名称 | TestProject |
| 项目类型 | web/api |
| 主语言 | Python |
| 创建日期 | 2025-01-01 |

## 编码规范

PEP 8 风格指南，使用 4 空格缩进。

## 架构约束

分层架构，Controller-Service-Repository 模式。

## 命名约定

使用 snake_case 命名函数和变量。

## 工具链

| 工具 | 版本/说明 |
|------|----------|
| pytest | 7.4.0 |
| ruff | 0.1.6 |

## 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2025-01-01 | 1.0.0 | 初始规范建立 |
"""

_CANONICAL_TABLE_MISMATCHED_LANG = """\
# CANONICAL.md

## 项目信息

| 字段 | 值 |
|------|-----|
| 项目名称 | TestProject |
| 项目类型 | web/api |
| 主语言 | Go |
| 创建日期 | 2025-01-01 |

## 工具链

| 工具 | 版本/说明 |
|------|----------|
| go | 1.21 |

## 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2025-01-01 | 1.0.0 | 初始规范建立 |
"""


def test_fill_quality_table_format_placeholder_language(tmp_path: Path):
    """When 主语言 uses table format with placeholder, warning is emitted."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_TABLE_PLACEHOLDER)
    report = verify_consumer.verify(target)
    assert report.all_passed, "Fill quality warnings should not cause failure"
    placeholder_checks = [
        c for c in report.checks
        if c.name == "fill_quality.primary_language_placeholder"
    ]
    assert len(placeholder_checks) == 1
    assert "WARNING" in placeholder_checks[0].detail


def test_fill_quality_table_format_filled_language(tmp_path: Path):
    """When 主语言 uses table format and is filled, no warning."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_TABLE_FILLED)
    report = verify_consumer.verify(target)
    placeholder_checks = [
        c for c in report.checks
        if c.name == "fill_quality.primary_language_placeholder"
    ]
    assert len(placeholder_checks) == 0, "No warning expected when language is filled"


def test_fill_quality_table_format_toolchain_placeholder(tmp_path: Path):
    """When toolchain uses table format with placeholder rows, warning emitted."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_TABLE_PLACEHOLDER)
    report = verify_consumer.verify(target)
    assert report.all_passed
    toolchain_checks = [
        c for c in report.checks
        if c.name == "fill_quality.toolchain_placeholder"
    ]
    assert len(toolchain_checks) == 1
    assert "WARNING" in toolchain_checks[0].detail


def test_fill_quality_table_format_filled_toolchain(tmp_path: Path):
    """When toolchain table has real entries, no warning."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_TABLE_FILLED)
    report = verify_consumer.verify(target)
    toolchain_checks = [
        c for c in report.checks
        if c.name == "fill_quality.toolchain_placeholder"
    ]
    assert len(toolchain_checks) == 0, "No warning expected when toolchain is filled"


def test_fill_consistency_table_format_language_mismatch(tmp_path: Path):
    """When table-format declared language mismatches actual, warning emitted."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_TABLE_MISMATCHED_LANG)
    (target / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    report = verify_consumer.verify(target)
    assert report.all_passed, "Consistency warnings should not cause failure"
    mismatch_checks = [
        c for c in report.checks
        if c.name == "fill_consistency.language_mismatch"
    ]
    assert len(mismatch_checks) == 1
    assert "Go" in mismatch_checks[0].detail
    assert "Python" in mismatch_checks[0].detail


def test_fill_consistency_table_format_language_match(tmp_path: Path):
    """When table-format declared language matches actual, no warning."""
    target = _make_target_with_canonical(tmp_path, _CANONICAL_TABLE_FILLED)
    (target / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    report = verify_consumer.verify(target)
    mismatch_checks = [
        c for c in report.checks
        if c.name == "fill_consistency.language_mismatch"
    ]
    assert len(mismatch_checks) == 0, "No warning expected when languages match"
