#!/usr/bin/env python3
"""Tests for memory_hook_metrics (T1.1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import memory_hook_metrics as metrics


def _sample_package(status: str = "ok") -> dict:
    return {
        "status": status,
        "validation_errors": ["a", "b"] if status != "ok" else [],
        "missing_paths": ["p"] if status != "ok" else [],
        "package_kind": "context-package-v1",
        "system_context": {"core_provider": "legacy"},
    }


def test_collect_metrics_extracts_core_fields():
    record = metrics.collect_metrics("codex", "session-start", _sample_package("ok"))
    assert record["host"] == "codex"
    assert record["event"] == "session-start"
    assert record["status"] == "ok"
    assert record["validation_error_count"] == 0
    assert record["missing_paths_count"] == 0
    assert record["degraded"] is False
    assert record["core_provider"] == "legacy"
    assert record["context_package_size_bytes"] > 0
    assert "timestamp" in record


def test_collect_metrics_marks_degraded():
    record = metrics.collect_metrics("claude", "stop", _sample_package("degraded"))
    assert record["status"] == "degraded"
    assert record["degraded"] is True
    assert record["validation_error_count"] == 2
    assert record["missing_paths_count"] == 1


def test_collect_metrics_handles_non_dict_package():
    record = metrics.collect_metrics("factory", "session-start", None)  # type: ignore[arg-type]
    assert record["status"] == "unknown"
    assert record["validation_error_count"] == 0
    assert record["missing_paths_count"] == 0
    assert record["context_package_size_bytes"] >= 0


def test_emit_metrics_writes_jsonl(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(metrics.ENV_DISABLE, raising=False)
    monkeypatch.delenv(metrics.ENV_METRICS_PATH, raising=False)
    artifact_root = tmp_path / "memory" / "artifacts"
    result = metrics.emit_metrics(artifact_root, "codex", "session-start", _sample_package())
    assert result is not None
    assert result == artifact_root / metrics.METRICS_FILENAME
    assert result.exists()
    line = result.read_text().strip()
    assert line, "metrics file should not be empty"
    record = json.loads(line)
    assert record["host"] == "codex"
    assert record["event"] == "session-start"


def test_emit_metrics_appends_multiple_records(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(metrics.ENV_DISABLE, raising=False)
    monkeypatch.delenv(metrics.ENV_METRICS_PATH, raising=False)
    artifact_root = tmp_path / "memory" / "artifacts"
    metrics.emit_metrics(artifact_root, "codex", "session-start", _sample_package())
    metrics.emit_metrics(artifact_root, "claude", "prompt-submit", _sample_package("degraded"))
    path = artifact_root / metrics.METRICS_FILENAME
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    rec1 = json.loads(lines[0])
    rec2 = json.loads(lines[1])
    assert rec1["host"] == "codex"
    assert rec2["host"] == "claude"
    assert rec2["status"] == "degraded"


def test_emit_metrics_disabled_returns_none(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(metrics.ENV_DISABLE, "1")
    artifact_root = tmp_path / "memory" / "artifacts"
    result = metrics.emit_metrics(artifact_root, "codex", "session-start", _sample_package())
    assert result is None
    assert not (artifact_root / metrics.METRICS_FILENAME).exists()


def test_emit_metrics_respects_path_override(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(metrics.ENV_DISABLE, raising=False)
    override = tmp_path / "custom" / "metrics-stream.jsonl"
    monkeypatch.setenv(metrics.ENV_METRICS_PATH, str(override))
    artifact_root = tmp_path / "memory" / "artifacts"
    result = metrics.emit_metrics(artifact_root, "codex", "session-start", _sample_package())
    assert result == override
    assert override.exists()
    assert not (artifact_root / metrics.METRICS_FILENAME).exists()


def test_write_metrics_failure_is_non_blocking(tmp_path: Path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("file-not-dir")
    # metrics_path under a file path will fail mkdir; emit_metrics should swallow it.
    monkeypatch.setenv(metrics.ENV_METRICS_PATH, str(blocked / "metrics.jsonl"))
    monkeypatch.delenv(metrics.ENV_DISABLE, raising=False)
    result = metrics.emit_metrics(tmp_path, "codex", "session-start", _sample_package())
    assert result is None


def test_is_metrics_disabled_only_for_exact_one(monkeypatch):
    monkeypatch.delenv(metrics.ENV_DISABLE, raising=False)
    assert metrics.is_metrics_disabled() is False
    monkeypatch.setenv(metrics.ENV_DISABLE, "0")
    assert metrics.is_metrics_disabled() is False
    monkeypatch.setenv(metrics.ENV_DISABLE, "1")
    assert metrics.is_metrics_disabled() is True
