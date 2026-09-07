"""Tests for memory-amend append-only tool (债 7b, R2').

Covers: normal append, --header correction-number inference (#1 → #2),
missing target / missing parent errors, prefix invariant, atomic write,
binary safety, empty-stdin guard.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from memory_core.tools.memory_amend import (
    amend_file,
    build_append_block,
    main,
    next_correction_number,
)


class _FakeStdin:
    """Minimal stdin stub exposing .buffer.read() with raw bytes."""

    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def _run_main(argv: list[str], stdin_data: bytes, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(stdin_data))
    return main(argv)


class TestBuildAppendBlock:
    """Pure-function tests for the append block builder."""

    def test_prefix_invariant_plain_append(self) -> None:
        """旧内容必须是 新内容=旧+块 的逐字节前缀（append-only 不变式）。"""
        old = "# 决策记录\n\n正文".encode()
        block, num = build_append_block(old, "\n补充说明\n".encode(), header_title=None)
        assert num == 0
        new = old + block
        assert new[: len(old)] == old

    def test_header_block_first_correction_is_1(self) -> None:
        """无既有更正段时 --header 生成 #1 头行。"""
        old = "# 决策记录\n".encode()
        block, num = build_append_block(old, "修正内容\n".encode(), header_title="补充结论", today="2026-09-07")
        assert num == 1
        assert block.startswith("> ⚠️ 更正段 #1（2026-09-07，append-only）：补充结论\n\n".encode())

    def test_separator_newline_when_old_has_no_trailing_newline(self) -> None:
        """旧内容无换行收尾时补行边界隔离，且不改写旧字节。"""
        old = b"no trailing newline"
        block, _ = build_append_block(old, b"appended", header_title=None)
        assert (old + block).startswith(old)
        assert block.startswith(b"\n")

    def test_block_always_ends_with_newline(self) -> None:
        block, _ = build_append_block(b"old\n", b"no newline at end", header_title=None)
        assert block.endswith(b"\n")


class TestNextCorrectionNumber:
    def test_no_existing_returns_1(self) -> None:
        assert next_correction_number("# 决策记录\n\n正文") == 1

    def test_inference_from_existing_max(self) -> None:
        text = "# 决策\n> ⚠️ 更正段 #1（2026-09-01，append-only）：A\n\n> ⚠️ 更正段 #2（2026-09-02，append-only）：B\n"
        assert next_correction_number(text) == 3


class TestAmendFile:
    def test_append_preserves_old_bytes(self, tmp_path: Path) -> None:
        target = tmp_path / "decision.md"
        original = "# 决策记录\n\n正文内容\n"
        target.write_text(original, encoding="utf-8")

        appended, num = amend_file(target, "补充\n".encode(), header_title=None)
        assert num == 0
        assert target.read_text(encoding="utf-8").startswith(original)
        assert appended == len("补充\n".encode())

    def test_header_number_inference_1_then_2(self, tmp_path: Path) -> None:
        target = tmp_path / "decision.md"
        target.write_text("# 决策记录\n", encoding="utf-8")

        _, n1 = amend_file(target, "第一次更正\n".encode(), header_title="更正一")
        assert n1 == 1
        _, n2 = amend_file(target, "第二次更正\n".encode(), header_title="更正二")
        assert n2 == 2
        content = target.read_text(encoding="utf-8")
        assert "> ⚠️ 更正段 #1（" in content
        assert "> ⚠️ 更正段 #2（" in content
        # append-only：旧前缀逐字节保留
        assert content.startswith("# 决策记录\n")

    def test_target_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            amend_file(tmp_path / "missing.md", b"x\n", header_title=None)

    def test_parent_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(NotADirectoryError):
            amend_file(tmp_path / "no-such-dir" / "f.md", b"x\n", header_title=None)

    def test_binary_append_is_byte_safe(self, tmp_path: Path) -> None:
        target = tmp_path / "log.md"
        original = b"# log\n"
        target.write_bytes(original)
        raw = b"\xff\xfe non-utf8 bytes \x00\n"
        amend_file(target, raw, header_title=None)
        assert target.read_bytes() == original + raw

    def test_atomic_write_failure_leaves_original_intact(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """os.replace 失败时原文件字节不动，且无 tmp 残留。"""
        target = tmp_path / "decision.md"
        original = "# 决策记录\n".encode()
        target.write_bytes(original)

        def _boom(self_src: object, dst: object) -> None:
            raise OSError("simulated rename failure")

        monkeypatch.setattr(Path, "replace", _boom)
        with pytest.raises(OSError):
            amend_file(target, "追加\n".encode(), header_title=None)
        assert target.read_bytes() == original
        leftovers = [p.name for p in tmp_path.iterdir() if "memory-amend-tmp" in p.name]
        assert leftovers == []

    def test_no_tmp_left_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "decision.md"
        target.write_text("old\n", encoding="utf-8")
        amend_file(target, b"new\n", header_title=None)
        leftovers = [p.name for p in tmp_path.iterdir() if "memory-amend-tmp" in p.name]
        assert leftovers == []


class TestMain:
    def test_cli_plain_append_exit_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "decision.md"
        target.write_text("# 决策\n", encoding="utf-8")
        rc = _run_main(
            [
                str(target),
            ],
            "追加正文\n".encode(),
            monkeypatch,
        )
        assert rc == 0
        err = capsys.readouterr().err
        assert "已追加" in err
        assert "append-only" in err
        assert target.read_text(encoding="utf-8") == "# 决策\n追加正文\n"

    def test_cli_header_reports_correction_number(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "decision.md"
        target.write_text("# 决策\n", encoding="utf-8")
        rc = _run_main([str(target), "--header", "标题一"], "内容\n".encode(), monkeypatch)
        assert rc == 0
        err = capsys.readouterr().err
        assert "更正段 #1" in err
        rc2 = _run_main([str(target), "--header", "标题二"], "内容2\n".encode(), monkeypatch)
        assert rc2 == 0
        assert "更正段 #2" in capsys.readouterr().err

    def test_cli_missing_target_exit_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = _run_main([str(tmp_path / "missing.md")], b"x\n", monkeypatch)
        assert rc == 1
        assert "目标文件不存在" in capsys.readouterr().err

    def test_cli_missing_parent_exit_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = _run_main([str(tmp_path / "nodir" / "x.md")], b"x\n", monkeypatch)
        assert rc == 1
        assert "父目录不存在" in capsys.readouterr().err

    def test_cli_empty_stdin_without_header_is_noop_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "decision.md"
        target.write_text("original\n", encoding="utf-8")
        rc = _run_main([str(target)], b"", monkeypatch)
        assert rc == 1
        assert target.read_text(encoding="utf-8") == "original\n"

    def test_cli_empty_stdin_with_header_still_appends_header(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "decision.md"
        target.write_text("original\n", encoding="utf-8")
        rc = _run_main([str(target), "--header", "仅头行"], b"", monkeypatch)
        assert rc == 0
        content = target.read_text(encoding="utf-8")
        assert content.startswith("original\n")
        assert "更正段 #1" in content
