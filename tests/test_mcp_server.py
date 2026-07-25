"""Tests for the minimal MCP server exposed by memory-core.

These tests exercise the tool implementations directly through ``call_tool``
(and ``list_tools`` for tool filtering) without spinning up the full stdio
transport. Each tool returns a ``list[TextContent]`` whose first element's
``text`` is a JSON-stringified payload, so a small helper parses the payload
for assertions.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

from memory_core.tools import mcp_server
from memory_core.tools.mcp_server import call_tool, list_tools

# The memory-core source repository itself — used as a realistic project root
# that is guaranteed to exist and contain memory/kb and memory/docs trees.
SOURCE_REPO_CWD = str(Path(__file__).resolve().parent.parent)


def _invoke(name: str, arguments: dict) -> dict:
    """Call ``call_tool`` synchronously and parse the JSON payload."""
    result = asyncio.run(call_tool(name, arguments))
    assert result, "call_tool returned an empty list"
    return json.loads(result[0].text)


class TestLoadContext:
    def test_load_context(self) -> None:
        payload = _invoke("load_context", {"cwd": SOURCE_REPO_CWD})
        assert payload["status"] in ("ok", "degraded")
        assert payload["status"] != "error"


class TestSearchMemory:
    def test_search_memory(self) -> None:
        payload = _invoke("search_memory", {"query": "hook", "cwd": SOURCE_REPO_CWD})
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

    def test_resolve_doc_path_invalid(self) -> None:
        payload = _invoke(
            "resolve_doc_path",
            {"category": "nonexistent", "filename": "x.md", "cwd": SOURCE_REPO_CWD},
        )
        assert payload["status"] == "error"
        assert "Unknown category" in payload["message"]


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
        assert "traversal" in payload["message"].lower() or "invalid" in payload["message"].lower()

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


class TestRecordEvent:
    def test_record_event_success(self) -> None:
        payload = _invoke(
            "record_event",
            {"event": "session-start", "cwd": SOURCE_REPO_CWD},
        )
        assert payload["status"] == "recorded"
        assert payload["event"] == "session-start"

    def test_record_event_missing_cwd(self) -> None:
        payload = _invoke("record_event", {"event": "stop"})
        assert payload["status"] == "error"


class TestGetHealth:
    def test_get_health_no_report(self) -> None:
        # Use /tmp as cwd — no health report there
        payload = _invoke("get_health", {"cwd": "/tmp"})
        assert payload["status"] in ("no_health_report", "error", "degraded", "ok")


class TestListProjects:
    def test_list_projects(self) -> None:
        payload = _invoke("list_projects", {})
        assert isinstance(payload, list)


class TestGetDailySummary:
    def test_get_daily_summary_not_found(self) -> None:
        payload = _invoke(
            "get_daily_summary",
            {"date": "2020-01-01", "cwd": SOURCE_REPO_CWD},
        )
        assert payload["found"] is False


class TestToolFiltering:
    def test_tool_filtering(self) -> None:
        original = mcp_server._ALLOWED_TOOLS
        mcp_server._ALLOWED_TOOLS = {"search_memory"}
        try:
            tools = asyncio.run(list_tools())
            assert len(tools) == 1
            assert tools[0].name == "search_memory"
        finally:
            mcp_server._ALLOWED_TOOLS = original


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
