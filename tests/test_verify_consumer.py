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
    memory = target / ".memory"
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
    (target / ".memory" / "STATE.md").unlink()
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
    (target / ".memory" / "STATE.md").unlink()
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
