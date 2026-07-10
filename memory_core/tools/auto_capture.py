#!/usr/bin/env python3
"""Auto-capture module for session-end knowledge base candidates.

Scans project memory/kb/lessons/ and decisions/ for today's changes
and copies them to ~/.memory/global-kb/pending/ with source metadata.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

# C 层错误日志导入
try:
    from memory_core.tools.error_logger import write_error_log
except ImportError:
    write_error_log = None  # type: ignore[misc,assignment]


def capture_candidates(
    project_root: Path,
    global_kb_root: Path,
) -> list[dict[str, Any]]:
    """
    扫描项目 memory/kb/lessons/ 和 decisions/ 当日变更文件,复制到 pending/。

    Auto-capture mechanism for session-end: scans project knowledge base for
    files modified today and copies them to ~/.memory/global-kb/pending/ with
    source metadata for later promotion.

    Args:
        project_root: Project root directory
        global_kb_root: Global KB root directory (typically ~/.memory/global-kb)

    Returns:
        List of candidate dictionaries with source_file, source_project, captured_at

    Implementation:
        - Scans lessons/ and decisions/ for files modified today
        - Copies to pending/ with metadata frontmatter
        - Filename includes project name to avoid conflicts
        - Only writes to pending/, never to formal categories (zero noise)
    """
    candidates: list[dict[str, Any]] = []
    today = datetime.now().date()
    captured_at = datetime.now().isoformat()

    # Directories to scan
    scan_dirs = [
        project_root / "memory" / "kb" / "lessons",
        project_root / "memory" / "kb" / "decisions",
    ]

    # Ensure pending/ exists
    pending_dir = global_kb_root / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        # Scan for files modified today
        for file_path in scan_dir.iterdir():
            if not file_path.is_file():
                continue

            # Check modification time
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime.date() != today:
                    continue
            except (OSError, ValueError):
                continue

            # This file was modified today, capture it
            try:
                # Read original content
                content = file_path.read_text(encoding="utf-8")

                # Generate pending filename with project name to avoid conflicts
                project_name = project_root.name
                category = file_path.parent.name  # "lessons" or "decisions"
                pending_filename = f"{project_name}_{category}_{file_path.name}"
                pending_path = pending_dir / pending_filename

                # Build metadata frontmatter
                metadata_lines = [
                    "---",
                    f"source_project: {project_root}",
                    f"source_file: {file_path.relative_to(project_root)}",
                    f"captured_at: {captured_at}",
                    "---",
                    "",
                ]

                # Write to pending/ with metadata
                with pending_path.open("w", encoding="utf-8") as f:
                    f.write("\n".join(metadata_lines))
                    f.write(content)

                # Record candidate
                candidates.append({
                    "source_file": str(file_path.relative_to(project_root)),
                    "source_project": str(project_root),
                    "captured_at": captured_at,
                    "pending_path": str(pending_path),
                })

            except (OSError, IOError) as e:
                # Capture failed, log but don't block
                if write_error_log is not None:
                    write_error_log(
                        str(project_root),
                        "auto_capture_failed",
                        {
                            "source_file": str(file_path),
                            "error": str(e),
                        },
                        f"Failed to capture candidate: {file_path}",
                    )

    return candidates
