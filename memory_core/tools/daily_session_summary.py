#!/usr/bin/env python3
"""Daily session summary tool — reads event logs and generates a report.

Usage:
    python daily_session_summary.py --date 2026-05-11
    python daily_session_summary.py --date 2026-05-11 --project /Users/busiji/tool
    python daily_session_summary.py --date 2026-05-11 --json
    python daily_session_summary.py --today
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

def _find_event_log(project_root: Path, target_date: str) -> Path | None:
    """Locate the date-partitioned event log."""
    candidates = [
        project_root / "artifacts" / "memory-hook" / "events" / f"{target_date}.jsonl",
        project_root / "artifacts" / "memory-hook" / "events.jsonl",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _find_context_snapshots(project_root: Path, target_date: str) -> list[Path]:
    """Locate all snapshot files for the target date."""
    daily_dir = project_root / "artifacts" / "memory-hook" / "contexts" / target_date
    if not daily_dir.exists():
        return []
    return sorted(daily_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _load_events(log_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _filter_by_date(events: list[dict[str, Any]], target_date: str) -> list[dict[str, Any]]:
    """Filter events to only those matching the target date."""
    filtered: list[dict[str, Any]] = []
    for evt in events:
        ts = evt.get("generated_at", "")
        if ts.startswith(target_date):
            filtered.append(evt)
        # Also check artifact_refs for date
        refs = evt.get("artifact_refs", {})
        snap = refs.get("snapshot", "")
        if snap and target_date in snap and evt not in filtered:
            filtered.append(evt)
    return filtered


def _filter_by_project(events: list[dict[str, Any]], project_path: str) -> list[dict[str, Any]]:
    """Filter events to only those for a specific project root."""
    if not project_path:
        return events
    return [e for e in events if e.get("repo_root") == project_path or e.get("cwd") == project_path]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

class SessionStats:
    def __init__(self) -> None:
        self.sessions: list[str] = []
        self.prompts: list[str] = []
        self.stops: list[str] = []
        self.projects: dict[str, int] = {}
        self.status_ok = 0
        self.status_degraded = 0
        self.errors: list[dict[str, Any]] = []
        self.timeline: list[dict[str, str]] = []

    def add_event(self, evt: dict[str, Any]) -> None:
        event_type = evt.get("event", "unknown")
        ts = evt.get("generated_at", evt.get("artifact_refs", {}).get("snapshot", ""))
        status = evt.get("status", "unknown")
        cwd = evt.get("cwd", "unknown")

        # Timeline
        self.timeline.append({
            "time": ts[:19] if len(ts) >= 19 else ts,
            "event": event_type,
            "status": status,
            "project": str(cwd),
        })

        # Count by type
        if event_type == "session-start":
            self.sessions.append(ts)
        elif event_type == "prompt-submit":
            self.prompts.append(ts)
        elif event_type == "stop":
            self.stops.append(ts)

        # Project distribution
        proj = str(cwd)
        self.projects[proj] = self.projects.get(proj, 0) + 1

        # Status
        if status == "ok":
            self.status_ok += 1
        else:
            self.status_degraded += 1

        # Errors
        validation_errors = evt.get("validation_errors", [])
        if validation_errors:
            self.errors.append({
                "time": ts[:19] if len(ts) >= 19 else ts,
                "event": event_type,
                "project": proj,
                "errors": validation_errors,
            })


def _load_errors(project_root: Path, target_date: str) -> list[str]:
    """Load daily error log lines."""
    error_path = project_root / "memory" / "system" / "errors" / f"{target_date}.log"
    if not error_path.exists():
        error_path = project_root / "memory" / "system" / "errors.log"
        if not error_path.exists():
            return []
    lines = []
    for line in error_path.read_text(encoding="utf-8").splitlines():
        if target_date in line:
            lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_report(stats: SessionStats, target_date: str, errors_log: list[str]) -> None:
    print("=" * 60)
    print(f"Daily Session Summary — {target_date}")
    print("=" * 60)

    print("\n**Session Activity**")
    print(f"  Sessions started:   {len(stats.sessions)}")
    print(f"  Prompts submitted:  {len(stats.prompts)}")
    print(f"  Sessions stopped:   {len(stats.stops)}")

    print("\n**Health**")
    print(f"  OK:       {stats.status_ok}")
    print(f"  Degraded: {stats.status_degraded}")

    if stats.projects:
        print("\n**Projects (by event count)**")
        for proj, count in sorted(stats.projects.items(), key=lambda x: -x[1]):
            short = proj.split("/")[-1] if proj != "unknown" else "unknown"
            print(f"  {short}: {count}")

    if stats.errors:
        print(f"\n**Validation Errors ({len(stats.errors)} occurrences)**")
        for err in stats.errors:
            print(f"  [{err['time']}] {err['event']} — {err['project'].split('/')[-1]}")
            for e in err["errors"]:
                print(f"    • {e}")

    if errors_log:
        print(f"\n**System Errors ({len(errors_log)} lines)**")
        for line in errors_log[:10]:
            # Truncate long lines
            display = line[:120] + "..." if len(line) > 120 else line
            print(f"  {display}")
        if len(errors_log) > 10:
            print(f"  ... and {len(errors_log) - 10} more lines")

    if stats.timeline:
        print("\n**Timeline**")
        for entry in stats.timeline:
            status_marker = "✓" if entry["status"] == "ok" else "!"
            print(f"  {entry['time']} [{entry['event']}] {status_marker} {entry['project'].split('/')[-1]}")

    print("\n" + "=" * 60)


def _json_report(stats: SessionStats, target_date: str, errors_log: list[str]) -> dict[str, Any]:
    return {
        "date": target_date,
        "sessions": len(stats.sessions),
        "prompts": len(stats.prompts),
        "stops": len(stats.stops),
        "status_ok": stats.status_ok,
        "status_degraded": stats.status_degraded,
        "projects": stats.projects,
        "validation_errors": stats.errors,
        "system_error_count": len(errors_log),
        "timeline": stats.timeline,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily session summary from memory event logs.")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--today", action="store_true", help="Use today's date")
    parser.add_argument("--project", type=str, help="Project root path to filter by")
    parser.add_argument("--all-projects", action="store_true", help="Scan all known projects")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    if args.today:
        target_date = date.today().isoformat()
    elif args.date:
        target_date = args.date
    else:
        print("Error: specify --date YYYY-MM-DD or --today", file=sys.stderr)
        return 1

    # Determine projects to scan
    projects: list[Path] = []
    if args.project:
        projects.append(Path(args.project).expanduser().resolve())
    elif args.all_projects:
        # Scan known project lifecycle index
        lifecycle_index = Path.home() / ".memory-core" / "project-lifecycle" / "path-index.json"
        if lifecycle_index.exists():
            try:
                idx = json.loads(lifecycle_index.read_text())
                projects = [Path(p).resolve() for p in idx.get("paths", [])]
            except (json.JSONDecodeError, OSError):
                pass
        # Fallback: scan common project roots
        if not projects:
            for base in [Path.home()]:
                for p in base.iterdir():
                    if p.is_dir() and (p / "memory" / "system").exists():
                        projects.append(p)
    else:
        # Default: use current directory's project root
        cwd = Path.cwd()
        # Walk up to find memory/system or .git
        current = cwd.resolve()
        while current != current.parent:
            if (current / "memory" / "system").exists():
                projects.append(current)
                break
            if (current / ".git").is_dir():
                projects.append(current)
                break
            current = current.parent
        if not projects:
            projects.append(cwd)

    if not projects:
        print("No projects found to scan.", file=sys.stderr)
        return 1

    all_stats = SessionStats()
    all_errors: list[str] = []

    for proj in projects:
        # Read event log
        log_path = _find_event_log(proj, target_date)
        if log_path is None:
            continue

        events = _load_events(log_path)
        if not events:
            # Try legacy combined log (unpartitioned events.jsonl)
            legacy_log = proj / "artifacts" / "memory-hook" / "events.jsonl"
            if legacy_log.exists():
                legacy_events = _load_events(legacy_log)
                events = _filter_by_date(legacy_events, target_date)

        events = _filter_by_project(events, str(proj))

        for evt in events:
            all_stats.add_event(evt)

        # Load error log
        all_errors.extend(_load_errors(proj, target_date))

    if args.json:
        report = _json_report(all_stats, target_date, all_errors)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(all_stats, target_date, all_errors)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
