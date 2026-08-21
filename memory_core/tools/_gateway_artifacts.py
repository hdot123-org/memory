#!/usr/bin/env python3.12
"""Gateway 工件层：artifact 写入与错误日志。

依赖层级：依赖 _gateway_config。
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ._gateway_config import (
    CONTEXT_ROOT,
    ERROR_LOG,
    EVENT_LOG,
    _get_artifact_sink,
    _get_error_sink,
    _logger,
    now_iso,
)


def _ensure_artifact_dirs() -> None:
    try:
        _get_artifact_sink().ensure_dirs()
    except RuntimeError:
        CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)


def append_error_log(component: str, message: str, context: dict[str, Any]) -> None:
    """Append error to error log with fallback to direct file write."""
    try:
        sink = _get_error_sink()
        sink.log(component, message, context)
    except RuntimeError:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        timestamp = now_iso()
        day = timestamp[:10]
        daily_error_log = ERROR_LOG.parent / "errors" / f"{day}.log"
        daily_error_log.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(context, ensure_ascii=False, sort_keys=True)
        line = f"[{timestamp}] [{component}] [error] {message} | context={rendered}\n"
        with daily_error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)
        with ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line)


def write_artifacts(package: dict[str, Any]) -> dict[str, str]:
    """Write context package artifacts with fallback to direct file write."""
    from ._gateway_policy import _write_artifacts_via_sink
    try:
        return _write_artifacts_via_sink(package)
    except RuntimeError:
        _ensure_artifact_dirs()
        now = datetime.now()
        day = now.date().isoformat()
        timestamp = now.strftime("%Y%m%dT%H%M%S%f")
        daily_context_root = CONTEXT_ROOT / day
        daily_context_root.mkdir(parents=True, exist_ok=True)
        snapshot_path = daily_context_root / f"{timestamp}-{package['host']}-{package['event']}.json"
        suffix = 1
        while snapshot_path.exists():
            snapshot_path = daily_context_root / f"{timestamp}-{suffix:02d}-{package['host']}-{package['event']}.json"
            suffix += 1
        latest_path = CONTEXT_ROOT / f"latest-{package['host']}-{package['event']}.json"
        daily_latest_path = daily_context_root / f"latest-{package['host']}-{package['event']}.json"
        daily_event_log = EVENT_LOG.parent / "events" / f"{day}.jsonl"
        package["artifact_refs"] = {
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "daily_latest": str(daily_latest_path),
            "event_log": str(daily_event_log),
            "legacy_event_log": str(EVENT_LOG),
        }
        rendered = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        snapshot_path.write_text(rendered, encoding="utf-8")
        latest_path.write_text(rendered, encoding="utf-8")
        daily_latest_path.write_text(rendered, encoding="utf-8")
        event_line = json.dumps(package, ensure_ascii=False) + "\n"
        daily_event_log.parent.mkdir(parents=True, exist_ok=True)
        with daily_event_log.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        return {"snapshot": str(snapshot_path), "latest": str(latest_path), "event_log": str(daily_event_log)}


def _build_readonly_source_repo_package(cwd: Path, host: str, event: str) -> dict[str, Any]:
    """M3: Build a readonly context-package for the memory-core source repo.

    Instead of short-circuiting with empty JSON, return a proper context-package
    that declares the repo is in read-only mode with no allowed writes.
    """
    # Get ownership domains/resources for rules
    from ..ownership import DEFAULT_OWNERSHIP_DOMAINS

    ownership_domains = [
        {
            "name": d.name,
            "path": d.path,
            "level": d.level.name.lower(),
            "recursive": d.recursive,
            "description": d.description,
        }
        for d in DEFAULT_OWNERSHIP_DOMAINS
    ]
    protected_paths = [
        "memory/docs/**",
        "memory/kb/**",
        "memory/system/**",
        "memory/project-map/**",
        "AGENTS.md",
    ]

    # Source-repo-specific domains (not in DEFAULT_OWNERSHIP_DOMAINS)
    ownership_domains.extend([
        {
            "name": "source_repo_docs",
            "path": "docs",
            "level": "critical",
            "recursive": True,
            "description": "Source repo documentation domain (source-repo-readonly only)",
        },
        {
            "name": "source_repo_factory",
            "path": ".factory",
            "level": "critical",
            "recursive": True,
            "description": "Source repo Factory config domain (source-repo-readonly only)",
        },
    ])
    return {
        "package_kind": "source-repo-rules",
        "mode": "read-only",
        "allowed_writes": {},
        "rules": {
            "description": "memory-core source repository - all writes blocked",
            "ownership_domains": ownership_domains,
            "protected_paths": protected_paths,
            "note": "This is the memory-core source repository. Hooks run in readonly mode to prevent self-pollution.",
        },
        "project_root": str(cwd),
        "cwd": str(cwd),
        "host": host,
        "event": event,
        "status": "ok",
    }


def _update_state_dynamic_fields(project_root: Path, scope: str) -> None:
    """Update dynamic fields in STATE.md during session-start.

    Updates the '当前工作区' section to reflect the current git branch and
    latest commit. Only modifies dynamic fields; never overwrites static
    fields (主语言/工具链/etc.) filled by init.

    Writes to memory/kb/projects/{scope}/STATE.md.

    Non-blocking: gracefully handles missing git, missing STATE.md, or
    any errors by silently skipping.
    """
    state_path = project_root / "memory" / "kb" / "projects" / scope / "STATE.md"
    if not state_path.exists():
        return

    try:
        # Gather git info — fail gracefully if not a git repo
        branch_proc = subprocess.run(
            ["git", "-C", str(project_root), "branch", "--show-current"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if branch_proc.returncode != 0:
            return
        branch = branch_proc.stdout.strip()
        if not branch:
            return

        commit_proc = subprocess.run(
            ["git", "-C", str(project_root), "log", "-1", "--format=%h %s"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        commit_info = commit_proc.stdout.strip() if commit_proc.returncode == 0 else ""

        content = state_path.read_text(encoding="utf-8")

        # Build the replacement text
        workspace_line = f"当前分支: {branch}"
        if commit_info:
            workspace_line += f" | 最近提交: {commit_info}"

        # Pattern 1: placeholder (未填写) — init has not filled yet
        new_content = re.sub(
            r'(## 当前工作区\n\n)（待填写[^\n]*）',
            rf'\g<1>{workspace_line}',
            content,
        )

        # Pattern 2: already filled — idempotent refresh
        # Matches lines after "## 当前工作区\n\n" that start with "当前分支:"
        new_content = re.sub(
            r'(## 当前工作区\n\n)当前分支: [^\n]+',
            rf'\g<1>{workspace_line}',
            new_content,
        )

        if new_content != content:
            state_path.write_text(new_content, encoding="utf-8")
    except (subprocess.TimeoutExpired, OSError):
        pass  # Non-blocking


def _launch_async_health_check(cwd: Path) -> None:
    """Launch a background process to perform deep memory health validation.

    This prevents heavy validation (reading many files, git commands,
    and running the full context package build) from blocking the hook startup.

    Results are written to: memory/system/health-report.json

    On launch failure, writes a structured failure record to health-report.json
    with launch_status=failed for observability.
    """
    import sys
    report_path = cwd / "memory" / "system" / "health-report.json"
    try:
        health_script = str((Path(__file__).parent / "memory_health_report.py").resolve())

        # Output path for the report
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Launch detached subprocess (cwd is critical for discovery)
        # Child process writes to report_path directly.
        subprocess.Popen(
            [sys.executable, health_script, "--target", str(cwd)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent
            cwd=str(cwd),            # Set working directory
        )

        _logger.info("Launched async health check for %s", cwd)
    except Exception as e:
        _logger.debug("Failed to launch async health check: %s", e)
        # P2 observability: Write structured failure record for async health check launch failure
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            failure_report = {
                "status": "error",
                "launch_status": "failed",
                "last_launch_error": str(e),
                "checked_at": now_iso(),
                "missing_paths": [],
                "validation_errors": [],
            }
            report_path.write_text(json.dumps(failure_report, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as write_err:
            # Fallback: use append_error_log if writing health report fails
            append_error_log(
                "memory-hook-gateway",
                "failed to launch async health check and write health report",
                {
                    "cwd": str(cwd),
                    "launch_error": str(e),
                    "write_error": str(write_err),
                },
            )


def _inject_health_alert(cwd: Path, package: dict[str, Any]) -> None:
    """Inject health alert from previous session if degraded."""
    prev_health_report = cwd / "memory" / "system" / "health-report.json"
    if not prev_health_report.exists():
        return
    try:
        report_text = prev_health_report.read_text()
        report_data = json.loads(report_text)
        if report_data.get("status") == "degraded":
            package.setdefault("system_context", {})
            package["system_context"]["previous_health_alert"] = {
                "status": "degraded",
                "errors": report_data.get("validation_errors", [])[:5],
                "note": "Detected from previous session startup health check",
            }
            append_error_log("health-check", "Project health degraded (from previous check)", report_data)
    except Exception as e:
        _logger.debug("Failed to read previous health report: %s", e)
