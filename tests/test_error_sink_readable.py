#!/usr/bin/env python3
"""Tests for ErrorSinkImpl human-readable output (T1.2)."""
from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.memory_hook_impls import ErrorSinkImpl


def _fixed_iso() -> str:
    return "2026-05-21T12:34:56+08:00"


def test_log_writes_structured_and_readable_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(ErrorSinkImpl.READABLE_DISABLE_ENV, raising=False)
    log = tmp_path / "errors.log"
    sink = ErrorSinkImpl(log, now_iso_fn=_fixed_iso)
    sink.log("comp", "boom", {"host": "codex", "event": "session-start"})

    structured = log.read_text()
    assert "[comp] [error] boom" in structured
    assert '"host": "codex"' in structured

    readable = log.with_name(log.stem + ErrorSinkImpl.READABLE_SUFFIX).read_text()
    assert "[ERROR] component=comp boom" in readable
    assert "host=codex" in readable
    assert "event=session-start" in readable


def test_readable_output_includes_daily_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(ErrorSinkImpl.READABLE_DISABLE_ENV, raising=False)
    log = tmp_path / "errors.log"
    sink = ErrorSinkImpl(log, now_iso_fn=_fixed_iso)
    sink.log("comp", "boom", {"k": "v"})

    daily_dir = log.parent / "errors"
    structured_daily = daily_dir / "2026-05-21.log"
    readable_daily = daily_dir / ("2026-05-21" + ErrorSinkImpl.READABLE_SUFFIX)
    assert structured_daily.exists()
    assert readable_daily.exists()
    assert "k=v" in readable_daily.read_text()


def test_readable_output_can_be_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(ErrorSinkImpl.READABLE_DISABLE_ENV, "1")
    log = tmp_path / "errors.log"
    sink = ErrorSinkImpl(log, now_iso_fn=_fixed_iso)
    sink.log("comp", "boom", {"k": "v"})

    readable_primary = log.with_name(log.stem + ErrorSinkImpl.READABLE_SUFFIX)
    assert log.exists()
    assert not readable_primary.exists()


def test_format_kv_quotes_values_with_whitespace():
    rendered = ErrorSinkImpl._format_kv({"msg": "with space", "code": 42})
    assert 'msg="with space"' in rendered
    assert "code=42" in rendered


def test_format_kv_serializes_nested_structures():
    rendered = ErrorSinkImpl._format_kv({"context": {"a": 1, "b": [1, 2]}})
    assert "context=" in rendered
    # Nested JSON contains whitespace, so the whole value is re-quoted with escapes.
    assert "\\\"a\\\": 1" in rendered or '"a": 1' in rendered


def test_format_kv_handles_empty_dict():
    assert ErrorSinkImpl._format_kv({}) == ""
    assert ErrorSinkImpl._format_kv(None) == ""  # type: ignore[arg-type]


def test_readable_line_format_is_stable():
    line = ErrorSinkImpl._readable_line(
        "2026-05-21T12:34:56+08:00",
        "memory-hook-gateway",
        "artifact write failed",
        {"host": "codex", "event": "session-start"},
    )
    assert line.startswith("[2026-05-21T12:34:56+08:00] [ERROR] component=memory-hook-gateway artifact write failed")
    assert "host=codex" in line
    assert "event=session-start" in line
    assert line.endswith("\n")


def test_log_does_not_raise_on_readable_failure(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(ErrorSinkImpl.READABLE_DISABLE_ENV, raising=False)
    log = tmp_path / "errors.log"
    sink = ErrorSinkImpl(log, now_iso_fn=_fixed_iso)

    original_open = Path.open

    def fail_for_readable(self, *args, **kwargs):
        if self.name.endswith(ErrorSinkImpl.READABLE_SUFFIX):
            raise OSError("simulated")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_for_readable)
    sink.log("comp", "boom", {"k": "v"})  # should not raise
    assert log.exists()
