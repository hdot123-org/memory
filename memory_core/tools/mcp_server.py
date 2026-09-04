"""Minimal MCP (Model Context Protocol) server for memory-core.

This module exposes memory-core's context-loading and search capabilities to
MCP-compatible IDEs (ZCode, Claude Desktop, etc.) over a stdio transport.

Tools provided
--------------
1. ``load_context`` — Loads the full project context package for a given
   working directory. Equivalent to running the ``session-start`` hook and
   returning the resulting context package (status, system_context,
   project_context, allowed_reads, allowed_writes, validation_errors, etc.).

2. ``search_memory`` — Performs a case-insensitive keyword search across the
   project's knowledge base (``memory/kb/``) and docs (``memory/docs/``)
   Markdown files and returns matching lines with file paths and line numbers.

3. ``resolve_doc_path`` — Resolves the correct write target path for a
   document category using the DOC_CATEGORIES routing table.

4. ``save_memory`` — Writes memory content to the resolved path for a
   document category, creating parent directories as needed.

5. ``validate_write`` — Non-blocking pre-write validation against ownership
   and document-routing rules.

6. ``record_event`` — Records a project lifecycle event to the global
   lifecycle registry.

7. ``get_health`` — Reads the project health report.

8. ``list_projects`` — Lists all known projects from the lifecycle registry.

9. ``get_daily_summary`` — Reads the daily session log for a given date.

The server uses the MCP Python SDK's low-level ``Server`` API and never crashes
the process on tool errors — failures are returned as JSON error payloads.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_core.tools._guard_classify import classify_tool_use
from memory_core.tools.doc_router import DOC_CATEGORIES
from memory_core.tools.memory_hook_gateway import build_context_package_simple
from memory_core.tools.project_lifecycle import record_project_lifecycle

# Source-repo detection import is guarded so the server still loads even if the
# ownership module is unavailable; the check is skipped when the import fails.
try:
    from memory_core.ownership import is_memory_core_source_repo
except ImportError:  # pragma: no cover - ownership is a core module
    is_memory_core_source_repo = None  # type: ignore[assignment]

# Maximum number of search results returned by search_memory.
_MAX_SEARCH_RESULTS = 50

# Optional allow-list for tool filtering. ``None`` exposes all tools; a set
# restricts both ``list_tools`` and ``call_tool`` to the named tools only.
# Populated by ``main_sync`` from the ``--tools`` CLI flag.
_ALLOWED_TOOLS: set[str] | None = None

# The host tag passed to build_context_package_simple. Currently set to "factory"
# for backward compatibility; the underlying context-building logic is
# platform-agnostic so it works correctly for any MCP client (including ZCode).
# Future: could be made configurable or auto-detected from environment.
_HOST = "factory"

app = Server("memory-core")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _load_context(cwd: str) -> dict[str, Any]:
    """Build and return the context package for ``cwd``.

    Delegates to :func:`build_context_package_simple` with the ``session-start``
    event. Returns the full context package dict on success or an error dict on
    failure.
    """
    try:
        package = build_context_package_simple(
            _HOST,
            "session-start",
            {"cwd": cwd},
        )
        return package
    except Exception as exc:  # noqa: BLE001 — never crash the server
        return {"status": "error", "message": str(exc)}


def _search_memory(query: str, cwd: str) -> list[dict[str, Any]]:
    """Search project KB/docs and global KB Markdown files for ``query``.

    Performs a case-insensitive substring search across all ``.md`` files in:
    1. Project layer: ``<cwd>/memory/kb/`` and ``<cwd>/memory/docs/``
    2. Global layer: ``~/.memory/global-kb/`` (read-only cross-project fallback)

    Returns up to :data:`_MAX_SEARCH_RESULTS` matches, each with file_path,
    relative_path, line_number, matched_line, context_type, and source
    (``"project"`` or ``"global"``).
    """
    from memory_core.tools.global_kb_init import get_global_kb_root

    results: list[dict[str, Any]] = []
    query_lower = query.lower()

    global_kb_root = str(get_global_kb_root())

    search_roots = [
        (str(Path(cwd) / "memory" / "kb"), "kb", cwd, "project"),
        (str(Path(cwd) / "memory" / "docs"), "docs", cwd, "project"),
        (global_kb_root, "global", global_kb_root, "global"),
    ]

    for root_dir, context_type, base_for_rel, source in search_roots:
        if not Path(root_dir).is_dir():
            # Skip missing directories gracefully.
            continue
        for dirpath, _dirnames, filenames in os.walk(root_dir):
            for filename in filenames:
                if not filename.endswith(".md"):
                    continue
                file_path = str(Path(dirpath) / filename)
                relative_path = os.path.relpath(file_path, base_for_rel)
                try:
                    with Path(file_path).open(encoding="utf-8", errors="replace") as fh:
                        for line_number, line in enumerate(fh, start=1):
                            if query_lower in line.lower():
                                results.append(
                                    {
                                        "file_path": file_path,
                                        "relative_path": relative_path,
                                        "line_number": line_number,
                                        "matched_line": line.rstrip("\n"),
                                        "context_type": context_type,
                                        "source": source,
                                    }
                                )
                                if len(results) >= _MAX_SEARCH_RESULTS:
                                    return results
                except OSError:
                    # Skip files that cannot be read (permissions, etc.).
                    continue
    return results


# ---------------------------------------------------------------------------
# Tool implementations (tools 3-9)
# ---------------------------------------------------------------------------
def _validate_filename(filename: str) -> dict[str, Any] | None:
    """Return error dict if filename is invalid, None if valid.

    Rejects filenames containing path separators, traversal sequences,
    leading dots, or absolute paths to prevent path traversal attacks.
    """
    if "/" in filename or "\\" in filename or filename.startswith(".") or Path(filename).is_absolute():
        return {
            "status": "error",
            "message": ("Invalid filename: must not contain path separators or traversal sequences"),
        }
    return None


def _resolve_doc_path(category: str, filename: str, cwd: str) -> dict[str, Any]:
    """Resolve the write target path for a document category.

    Uses :data:`DOC_CATEGORIES` (the single source of truth for document
    routing) joined with ``cwd`` to produce an absolute path inside the
    consuming project. Surfaces an explicit error for unknown labels so MCP
    clients can self-correct.
    """
    categories = list(DOC_CATEGORIES.keys())
    if category not in DOC_CATEGORIES:
        return {
            "status": "error",
            "message": (f"Unknown category: '{category}'. Valid categories: {categories}"),
            "categories": categories,
        }
    # Validate filename to prevent path traversal attacks
    filename_error = _validate_filename(filename)
    if filename_error:
        return filename_error
    rel_dir = DOC_CATEGORIES[category]
    full_path = Path(cwd) / rel_dir / filename
    return {
        "path": str(full_path.absolute()),
        "category": category,
        "filename": filename,
        "categories": categories,
    }


def _save_memory(category: str, filename: str, content: str, cwd: str) -> dict[str, Any]:
    """Write memory content to the resolved path for ``category``.

    Creates parent directories as needed. Refuses to write when ``cwd`` resolves
    to the user's HOME directory (anti-pollution guard).
    """
    real_cwd = Path(cwd).expanduser().resolve()
    home = Path("~").expanduser().resolve()
    if real_cwd == home:
        return {
            "status": "error",
            "message": "Cannot write to HOME directory",
        }
    # Refuse to write into the memory-core source repository itself (read-only).
    # Without this guard an MCP client could bypass hook protection and pollute
    # the protocol library by passing cwd pointing at this source repo.
    if is_memory_core_source_repo is not None and is_memory_core_source_repo(Path(cwd)):
        return {
            "status": "error",
            "message": "Cannot write to memory-core source repository (read-only)",
        }
    categories = list(DOC_CATEGORIES.keys())
    if category not in DOC_CATEGORIES:
        return {
            "status": "error",
            "message": (f"Unknown category: '{category}'. Valid categories: {categories}"),
            "categories": categories,
        }
    # Validate filename to prevent path traversal attacks
    filename_error = _validate_filename(filename)
    if filename_error:
        return filename_error
    rel_dir = DOC_CATEGORIES[category]
    full_path = Path(cwd) / rel_dir / filename
    # Final safety net: verify the resolved path stays within the target dir.
    expected_root = (Path(cwd) / rel_dir).resolve()
    if full_path.resolve().is_relative_to(expected_root) is False:
        return {
            "status": "error",
            "message": "Invalid filename: path traversal detected",
        }
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        return {"status": "error", "message": f"Failed to write file: {exc}"}
    return {
        "path": str(full_path.absolute()),
        "bytes_written": len(content),
    }


def _validate_write(path: str, tool_name: str, cwd: str) -> dict[str, Any]:
    """Non-blocking pre-write validation via the guard classifier.

    Returns the decision, severity, scenario, and human-readable reason. Does
    not block the write — callers (MCP clients) decide how to act on the
    result.
    """
    result = classify_tool_use(
        {"tool_name": tool_name, "tool_input": {"file_path": path}},
        Path(cwd),
    )
    return {
        "matched": result.matched,
        "severity": result.severity,
        "message": result.message,
        "decision": result.detail.get("decision"),
        "scenario": result.detail.get("scenario"),
        "detail": result.detail,
    }


def _record_event(event: str, cwd: str, host: str) -> dict[str, Any]:
    """Record a project lifecycle event (session-start, prompt-submit, stop).

    Writes to the global lifecycle registry under
    ``~/.memory-core/project-lifecycle``.
    """
    lifecycle_root = Path("~/.memory-core/project-lifecycle").expanduser()
    record = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=Path(cwd),
        host=host,
        event=event,
        payload={"cwd": cwd},
        now_iso_fn=datetime.now().isoformat,
    )
    return {
        "status": "recorded",
        "event": event,
        "cwd": cwd,
        "project_id": record.get("project_id"),
    }


def _get_health(cwd: str) -> dict[str, Any]:
    """Read the project health report from ``memory/system/health-report.json``."""
    path = Path(cwd) / "memory" / "system" / "health-report.json"
    if not path.is_file():
        return {
            "status": "no_health_report",
            "message": ("Health report not found. Run memory-init or wait for the next session-start hook."),
        }
    try:
        with path.open(encoding="utf-8") as fh:
            loaded: dict[str, Any] = json.load(fh)
        return loaded
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "status": "error",
            "message": f"Failed to read health report: {exc}",
            "path": str(path),
        }


def _list_projects() -> list[dict[str, Any]]:
    """List all known projects from the global lifecycle registry."""
    lifecycle_root = Path("~/.memory-core/project-lifecycle").expanduser()
    index_path = lifecycle_root / "path-index.json"
    projects_dir = lifecycle_root / "projects"
    if not index_path.is_file():
        return []
    try:
        with index_path.open(encoding="utf-8") as fh:
            index = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    paths = index.get("paths", {}) if isinstance(index, dict) else {}

    projects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in paths.values():
        if not isinstance(entry, dict):
            continue
        project_id = entry.get("project_id")
        if not project_id or project_id in seen:
            continue
        # Prefer the richer per-project record file when available.
        record = entry
        project_file = projects_dir / f"{project_id}.json"
        if project_file.is_file():
            try:
                with project_file.open(encoding="utf-8") as fh:
                    loaded = json.load(fh)
                    if isinstance(loaded, dict):
                        record = loaded
            except (json.JSONDecodeError, OSError):
                # Fall back to the index entry on read failure.
                record = entry
        seen.add(project_id)
        projects.append(
            {
                "project_id": project_id,
                "project_name": record.get("project_name") or entry.get("project_name"),
                "status": record.get("status") or entry.get("status"),
                "local_path": record.get("local_path") or entry.get("local_path"),
                "last_observed_at": record.get("last_observed_at")
                or record.get("observed_at")
                or entry.get("last_observed_at"),
                "git_remote": record.get("git_remote") or entry.get("git_remote"),
            }
        )
    return projects


def _get_daily_summary(date: str, cwd: str) -> dict[str, Any]:
    """Read the session log for ``date`` (YYYY-MM-DD) from ``memory/log/``."""
    # Validate date format to prevent path traversal via malformed dates
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return {
            "status": "error",
            "message": f"Invalid date format: '{date}'. Expected YYYY-MM-DD.",
        }
    path = Path(cwd) / "memory" / "log" / f"{date}-sessions.md"
    if not path.is_file():
        return {
            "date": date,
            "found": False,
            "message": "No session log for this date",
        }
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        return {
            "date": date,
            "found": False,
            "message": f"Failed to read session log: {exc}",
        }
    return {"date": date, "content": content, "found": True}


# ---------------------------------------------------------------------------
# MCP server wiring
# ---------------------------------------------------------------------------
@app.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    """Declare the nine tools exposed by this server.

    When :data:`_ALLOWED_TOOLS` is set (via the ``--tools`` CLI flag), only the
    named tools are returned. When it is ``None`` all nine tools are exposed.
    """
    all_tools = [
        Tool(
            name="load_context",
            description=(
                "Load the full project context package for a working directory. "
                "Returns status, system_context, project_context, allowed_reads, "
                "allowed_writes, and validation_errors. Replaces the session-start "
                "hook for MCP clients."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root. Defaults to the server's current working directory."
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="search_memory",
            description=(
                "Search across the project knowledge base (memory/kb/), docs "
                "(memory/docs/), and global knowledge base (~/.memory/global-kb/) "
                "Markdown files by keyword. Returns matching lines with file paths "
                "and line numbers. Case-insensitive. Results include a 'source' "
                "field ('project' or 'global') to distinguish origin."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword or phrase to search for.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root to search in. "
                            "Defaults to the server's current working directory."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="resolve_doc_path",
            description=(
                "Resolve the correct write target path for a document category "
                "using the DOC_CATEGORIES routing table. Returns the absolute "
                "path and the list of available categories. Use before writing "
                "memory artifacts so files land in the right directory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": (
                            "Document category label. One of the DOC_CATEGORIES "
                            "keys (e.g. decision, lesson, runbook, plan, "
                            "bug-report, note, draft, rfc, audit, refactor-log)."
                        ),
                    },
                    "filename": {
                        "type": "string",
                        "description": "Target file name (e.g. 'D-001.md').",
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root. Defaults to the server's current working directory."
                        ),
                    },
                },
                "required": ["category", "filename"],
            },
        ),
        Tool(
            name="save_memory",
            description=(
                "Write memory content to the path resolved for a document "
                "category. Creates parent directories as needed. Refuses to "
                "write to the HOME directory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": ("Document category label (one of DOC_CATEGORIES keys)."),
                    },
                    "filename": {
                        "type": "string",
                        "description": "Target file name (e.g. 'L-001.md').",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root. Defaults to the server's current working directory."
                        ),
                    },
                },
                "required": ["category", "filename", "content"],
            },
        ),
        Tool(
            name="validate_write",
            description=(
                "Non-blocking pre-write validation. Classifies a prospective file "
                "write against ownership and document-routing rules and returns a "
                "decision (allow/block) with a human-readable reason. Does not "
                "block the write — callers decide how to act."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute file path being written.",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": (
                            "Originating tool name (Write, Edit, MultiEdit, "
                            "NotebookEdit, Execute, Task). Defaults to 'Write'."
                        ),
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root used for ownership "
                            "classification. Defaults to the server's current "
                            "working directory."
                        ),
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="record_event",
            description=(
                "Record a project lifecycle event (e.g. session-start, "
                "prompt-submit, stop) to the global lifecycle registry. "
                "Replaces hook event recording in pull-mode MCP deployments."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": ("Lifecycle event name (e.g. session-start, prompt-submit, stop)."),
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "host": {
                        "type": "string",
                        "description": ("Host tag identifying the calling platform. Defaults to 'mcp'."),
                    },
                },
                "required": ["event", "cwd"],
            },
        ),
        Tool(
            name="get_health",
            description=(
                "Read the project health report from "
                "memory/system/health-report.json. Returns the full report dict, "
                "or a 'no_health_report' status when the file is absent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root. Defaults to the server's current working directory."
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="list_projects",
            description=(
                "List all known projects from the global lifecycle registry "
                "(~/.memory-core/project-lifecycle). Returns project_id, "
                "project_name, status, local_path, last_observed_at, and "
                "git_remote for each project."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_daily_summary",
            description=(
                "Read the daily session log (memory/log/{date}-sessions.md) for a "
                "given date. Returns the file content or a 'not found' status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": ("Date in YYYY-MM-DD format. Defaults to today."),
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Absolute path to the project root. Defaults to the server's current working directory."
                        ),
                    },
                },
                "required": [],
            },
        ),
    ]
    if _ALLOWED_TOOLS is None:
        return all_tools
    return [t for t in all_tools if t.name in _ALLOWED_TOOLS]


# ---------------------------------------------------------------------------
# Table-driven tool dispatch handlers
# ---------------------------------------------------------------------------
def _handle_load_context(arguments: dict[str, Any]) -> Any:
    """Handle the load_context tool call."""
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _load_context(cwd)


def _handle_search_memory(arguments: dict[str, Any]) -> Any:
    """Handle the search_memory tool call."""
    query = arguments.get("query")
    if not query or not isinstance(query, str):
        return {"status": "error", "message": "'query' is required and must be a non-empty string"}
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _search_memory(query, cwd)


def _handle_resolve_doc_path(arguments: dict[str, Any]) -> Any:
    """Handle the resolve_doc_path tool call."""
    category = arguments.get("category")
    filename = arguments.get("filename")
    if not category or not isinstance(category, str):
        return {"status": "error", "message": "'category' is required"}
    if not filename or not isinstance(filename, str):
        return {"status": "error", "message": "'filename' is required"}
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _resolve_doc_path(category, filename, cwd)


def _handle_save_memory(arguments: dict[str, Any]) -> Any:
    """Handle the save_memory tool call."""
    category = arguments.get("category")
    filename = arguments.get("filename")
    content = arguments.get("content")
    if not category or not isinstance(category, str):
        return {"status": "error", "message": "'category' is required"}
    if not filename or not isinstance(filename, str):
        return {"status": "error", "message": "'filename' is required"}
    if content is None or not isinstance(content, str):
        return {"status": "error", "message": "'content' is required"}
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _save_memory(category, filename, content, cwd)


def _handle_validate_write(arguments: dict[str, Any]) -> Any:
    """Handle the validate_write tool call."""
    path = arguments.get("path")
    if not path or not isinstance(path, str):
        return {"status": "error", "message": "'path' is required"}
    tool_name = arguments.get("tool_name") or "Write"
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _validate_write(path, tool_name, cwd)


def _handle_record_event(arguments: dict[str, Any]) -> Any:
    """Handle the record_event tool call."""
    event = arguments.get("event")
    cwd = arguments.get("cwd")
    if not event or not isinstance(event, str):
        return {"status": "error", "message": "'event' is required"}
    if not cwd or not isinstance(cwd, str):
        return {"status": "error", "message": "'cwd' is required"}
    host = arguments.get("host") or "mcp"
    try:
        return _record_event(event, cwd, host)
    except Exception as exc:  # noqa: BLE001 — never crash the server
        return {"status": "error", "message": str(exc), "event": event, "cwd": cwd}


def _handle_get_health(arguments: dict[str, Any]) -> Any:
    """Handle the get_health tool call."""
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _get_health(cwd)


def _handle_list_projects(arguments: dict[str, Any]) -> Any:
    """Handle the list_projects tool call."""
    return _list_projects()


def _handle_get_daily_summary(arguments: dict[str, Any]) -> Any:
    """Handle the get_daily_summary tool call."""
    date = arguments.get("date") or datetime.now().strftime("%Y-%m-%d")
    cwd = arguments.get("cwd") or str(Path.cwd())
    return _get_daily_summary(date, cwd)


# Dispatch table mapping tool names to their handler functions.
_TOOL_HANDLERS: dict[str, Any] = {
    "load_context": _handle_load_context,
    "search_memory": _handle_search_memory,
    "resolve_doc_path": _handle_resolve_doc_path,
    "save_memory": _handle_save_memory,
    "validate_write": _handle_validate_write,
    "record_event": _handle_record_event,
    "get_health": _handle_get_health,
    "list_projects": _handle_list_projects,
    "get_daily_summary": _handle_get_daily_summary,
}


@app.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch an incoming tool call to the correct implementation.

    Always returns a list containing a single :class:`TextContent` whose text is
    a JSON-stringified payload. Tool errors are returned as JSON error objects
    rather than raising.
    """
    try:
        if _ALLOWED_TOOLS is not None and name not in _ALLOWED_TOOLS:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "error",
                            "message": (f"Tool '{name}' is not available on this server"),
                        }
                    ),
                )
            ]

        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"status": "error", "message": f"Unknown tool: {name}"}),
                )
            ]

        result = handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as exc:  # noqa: BLE001 — never crash the server
        return [
            TextContent(
                type="text",
                text=json.dumps({"status": "error", "message": str(exc)}),
            )
        ]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
async def main() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main_sync() -> None:
    """Synchronous CLI entry point wrapping :func:`main`.

    Supports an optional ``--tools`` flag whose value is a comma-separated list
    of tool names. When provided, only the named tools are exposed via
    ``list_tools`` and callable via ``call_tool``. Example::

        memory-mcp-server --tools search_memory,get_health
    """
    import sys

    tools_arg = None
    if "--tools" in sys.argv:
        idx = sys.argv.index("--tools")
        if idx + 1 >= len(sys.argv):
            print(
                "Error: --tools requires a value (comma-separated tool names)",
                file=sys.stderr,
            )
            sys.exit(1)
        tools_arg = sys.argv[idx + 1].split(",")

    global _ALLOWED_TOOLS
    if tools_arg:
        _ALLOWED_TOOLS = set(t.strip() for t in tools_arg)

    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
