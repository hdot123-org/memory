"""Tests for the minimal MCP server exposed by memory-core.

These tests exercise the tool implementations directly through ``call_tool``
(and ``list_tools`` for tool filtering) without spinning up the full stdio
transport. Each tool returns a ``list[TextContent]`` whose first element's
``text`` is a JSON-stringified payload, so a small helper parses the payload
for assertions.

All write tests use pytest ``tmp_path`` fixture for isolation. No test writes
to SOURCE_REPO_CWD, HOME, or ~/.memory-core directly.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from memory_core.tools import mcp_server
from memory_core.tools.mcp_server import call_tool, list_tools

# The memory-core source repository itself — used as a realistic read-only
# project root that is guaranteed to exist and contain memory/kb and
# memory/docs trees.  NEVER used as a write target.
SOURCE_REPO_CWD = str(Path(__file__).resolve().parent.parent)


def _invoke(name: str, arguments: dict[str, Any]) -> Any:
    """Call ``call_tool`` synchronously and parse the JSON payload."""
    result = asyncio.run(call_tool(name, arguments))
    assert result, "call_tool returned an empty list"
    return json.loads(result[0].text)


# Prevent any test from writing to the real lifecycle registry.
# load_context internally calls build_context_package_simple which records
# lifecycle events via the gateway. The gateway checks the
# MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE env var before writing.
@pytest.fixture(autouse=True)
def _prevent_lifecycle_writes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure no lifecycle writes occur during tests by redirecting to tmp_path."""
    # Mock record_project_lifecycle so no real lifecycle registry writes happen.
    monkeypatch.setattr(
        "memory_core.tools.mcp_server.record_project_lifecycle",
        lambda **kwargs: {"project_id": "test-project", "status": "active"},
        raising=False,
    )
    # Also mock at the project_lifecycle module level
    from unittest.mock import MagicMock

    monkeypatch.setattr(
        "memory_core.tools.project_lifecycle.record_project_lifecycle",
        MagicMock(return_value={"project_id": "test-project", "status": "active"}),
        raising=False,
    )
    # And in memory_hook_gateway which also calls it
    monkeypatch.setattr(
        "memory_core.tools.memory_hook_gateway.record_project_lifecycle",
        MagicMock(return_value={"project_id": "test-project", "status": "active"}),
        raising=False,
    )


# ---------------------------------------------------------------------------
# Read-only tool tests (no filesystem writes)
# ---------------------------------------------------------------------------

class TestLoadContext:
    def test_load_context(self) -> None:
        payload = _invoke("load_context", {"cwd": SOURCE_REPO_CWD})
        assert payload["status"] in ("ok", "degraded")
        assert payload["status"] != "error"


class TestSearchMemory:
    def test_search_memory(self) -> None:
        payload = _invoke(
            "search_memory", {"query": "hook", "cwd": SOURCE_REPO_CWD}
        )
        assert isinstance(payload, list)
        assert len(payload) >= 1
        first = payload[0]
        assert "file_path" in first
        assert "line_number" in first
        assert "matched_line" in first


class TestResolveDocPath:
    def test_resolve_doc_path_valid(self) -> None:
        payload = _invoke(
            "resolve_doc_path",
            {"category": "lesson", "filename": "test.md", "cwd": SOURCE_REPO_CWD},
        )
        assert "path" in payload
        assert "memory/kb/lessons" in payload["path"]

    def test_resolve_doc_path_invalid_category(self) -> None:
        payload = _invoke(
            "resolve_doc_path",
            {"category": "nonexistent", "filename": "x.md", "cwd": SOURCE_REPO_CWD},
        )
        assert payload["status"] == "error"
        assert "Unknown category" in payload["message"]

    def test_resolve_doc_path_traversal_filename(self) -> None:
        """resolve_doc_path must reject path-traversal filenames."""
        payload = _invoke(
            "resolve_doc_path",
            {
                "category": "note",
                "filename": "../../../etc/passwd",
                "cwd": SOURCE_REPO_CWD,
            },
        )
        assert payload["status"] == "error"
        assert "invalid" in payload["message"].lower() or "traversal" in payload["message"].lower()


# ---------------------------------------------------------------------------
# save_memory guard tests (no actual writes)
# ---------------------------------------------------------------------------

class TestSaveMemoryGuards:
    def test_save_memory_home_guard(self) -> None:
        home = os.path.expanduser("~")
        payload = _invoke(
            "save_memory",
            {
                "category": "note",
                "filename": "should-not-write.md",
                "content": "data",
                "cwd": home,
            },
        )
        assert payload["status"] == "error"
        assert "HOME" in payload["message"]

    def test_save_memory_source_repo_guard(self) -> None:
        payload = _invoke(
            "save_memory",
            {
                "category": "note",
                "filename": "should-not-write.md",
                "content": "data",
                "cwd": SOURCE_REPO_CWD,
            },
        )
        assert payload["status"] == "error"
        msg = payload["message"].lower()
        assert "source repo" in msg or "read-only" in msg

    def test_save_memory_path_traversal(self) -> None:
        payload = _invoke(
            "save_memory",
            {
                "category": "note",
                "filename": "../../../etc/crontab",
                "content": "data",
                "cwd": "/tmp",
            },
        )
        assert payload["status"] == "error"
        assert (
            "traversal" in payload["message"].lower()
            or "invalid" in payload["message"].lower()
        )

    def test_save_memory_absolute_path(self) -> None:
        payload = _invoke(
            "save_memory",
            {
                "category": "note",
                "filename": "/etc/passwd",
                "content": "data",
                "cwd": "/tmp",
            },
        )
        assert payload["status"] == "error"


# ---------------------------------------------------------------------------
# save_memory positive write test (tmp_path isolated)
# ---------------------------------------------------------------------------

class TestSaveMemorySuccess:
    def test_save_memory_writes_file(self, tmp_path: Path) -> None:
        """save_memory should create the file and report bytes_written."""
        content = "# Test\nHello from MCP"
        payload = _invoke(
            "save_memory",
            {
                "category": "note",
                "filename": "test-write.md",
                "content": content,
                "cwd": str(tmp_path),
            },
        )
        # Successful save_memory returns {"path": ..., "bytes_written": ...}
        assert "path" in payload
        assert payload.get("bytes_written", 0) > 0
        written_path = tmp_path / "memory" / "docs" / "notes" / "test-write.md"
        assert written_path.exists()
        assert written_path.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# validate_write (read-only)
# ---------------------------------------------------------------------------

class TestValidateWrite:
    def test_validate_write(self) -> None:
        payload = _invoke(
            "validate_write",
            {
                "path": os.path.join(SOURCE_REPO_CWD, "memory", "kb", "x.md"),
                "tool_name": "Write",
                "cwd": SOURCE_REPO_CWD,
            },
        )
        assert "decision" in payload


# ---------------------------------------------------------------------------
# record_event tests (lifecycle writes mocked)
# ---------------------------------------------------------------------------

class TestRecordEvent:
    def test_record_event_success(self, tmp_path: Path) -> None:
        """record_event must NOT write to real ~/.memory-core."""
        fake_record = {
            "project_id": "test-project",
            "project_name": "test",
            "status": "active",
        }
        with patch(
            "memory_core.tools.mcp_server.record_project_lifecycle",
            return_value=fake_record,
        ) as mock_fn:
            payload = _invoke(
                "record_event",
                {"event": "session-start", "cwd": str(tmp_path)},
            )
        assert payload["status"] == "recorded"
        assert payload["event"] == "session-start"
        mock_fn.assert_called_once()

    def test_record_event_missing_cwd(self) -> None:
        payload = _invoke("record_event", {"event": "stop"})
        assert payload["status"] == "error"


# ---------------------------------------------------------------------------
# get_health tests
# ---------------------------------------------------------------------------

class TestGetHealth:
    def test_get_health_no_report(self, tmp_path: Path) -> None:
        payload = _invoke("get_health", {"cwd": str(tmp_path)})
        assert payload["status"] == "no_health_report"

    def test_get_health_positive(self, tmp_path: Path) -> None:
        """Create a temp health-report.json and verify reading."""
        health_dir = tmp_path / "memory" / "system"
        health_dir.mkdir(parents=True)
        report = {
            "status": "ok",
            "checks": {"hooks": "pass", "context": "pass"},
            "score": 100,
        }
        (health_dir / "health-report.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        payload = _invoke("get_health", {"cwd": str(tmp_path)})
        assert payload["status"] == "ok"
        assert payload["score"] == 100
        assert "checks" in payload


# ---------------------------------------------------------------------------
# list_projects (read-only)
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_list_projects(self) -> None:
        payload = _invoke("list_projects", {})
        assert isinstance(payload, list)


# ---------------------------------------------------------------------------
# get_daily_summary tests
# ---------------------------------------------------------------------------

class TestGetDailySummary:
    def test_get_daily_summary_not_found(self, tmp_path: Path) -> None:
        payload = _invoke(
            "get_daily_summary",
            {"date": "2020-01-01", "cwd": str(tmp_path)},
        )
        assert payload["found"] is False

    def test_get_daily_summary_positive(self, tmp_path: Path) -> None:
        """Create a temp session log and verify reading."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        log_content = "# 2025-06-15 Sessions\n\n- session 1\n- session 2\n"
        (log_dir / "2025-06-15-sessions.md").write_text(
            log_content, encoding="utf-8"
        )
        payload = _invoke(
            "get_daily_summary",
            {"date": "2025-06-15", "cwd": str(tmp_path)},
        )
        assert payload["found"] is True
        assert payload["date"] == "2025-06-15"
        assert "session 1" in payload["content"]

    def test_get_daily_summary_invalid_date(self) -> None:
        """Non-YYYY-MM-DD date must be rejected."""
        payload = _invoke(
            "get_daily_summary",
            {"date": "../../etc/hostname", "cwd": "/tmp"},
        )
        assert payload["status"] == "error"
        assert "invalid" in payload["message"].lower() or "date" in payload["message"].lower()


# ---------------------------------------------------------------------------
# Tool filtering and unknown tool tests
# ---------------------------------------------------------------------------

class TestToolFiltering:
    def test_tool_filtering_list(self) -> None:
        """list_tools respects _ALLOWED_TOOLS."""
        original = mcp_server._ALLOWED_TOOLS
        mcp_server._ALLOWED_TOOLS = {"search_memory"}
        try:
            tools = asyncio.run(list_tools())
            assert len(tools) == 1
            assert tools[0].name == "search_memory"
        finally:
            mcp_server._ALLOWED_TOOLS = original

    def test_call_tool_filter_rejection(self) -> None:
        """call_tool returns error when tool is excluded by _ALLOWED_TOOLS."""
        original = mcp_server._ALLOWED_TOOLS
        mcp_server._ALLOWED_TOOLS = {"search_memory"}
        try:
            payload = _invoke(
                "load_context",
                {"cwd": SOURCE_REPO_CWD},
            )
            assert payload["status"] == "error"
            assert "not available" in payload["message"]
        finally:
            mcp_server._ALLOWED_TOOLS = original


class TestUnknownTool:
    def test_unknown_tool(self) -> None:
        payload = _invoke("nonexistent_tool", {})
        assert payload["status"] == "error"
        assert "unknown" in payload["message"].lower() or "Unknown" in payload["message"]


# ---------------------------------------------------------------------------
# main_sync --tools CLI argument parsing
# ---------------------------------------------------------------------------

class TestMainSyncCLI:
    def test_tools_no_value_fails(self) -> None:
        """--tools with no following argument must exit non-zero."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.mcp_server",
                "--tools",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode != 0
        assert "--tools" in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
