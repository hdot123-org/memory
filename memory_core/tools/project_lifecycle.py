"""Project lifecycle tracking for global memory hooks.

The lifecycle tracker is deliberately conservative: it records that a project
path is active or missing, but it never deletes memory artifacts.  This keeps
Codex workspace churn separate from memory retention.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug.lower() or "unknown"


def _run_git(cwd: Path, args: list[str]) -> str | None:
    if not cwd.exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _git_root(cwd: Path) -> Path | None:
    value = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    return Path(value).expanduser() if value else None


def _git_remote(cwd: Path) -> str | None:
    return _run_git(cwd, ["remote", "get-url", "origin"])


def _project_name_from_remote(remote: str) -> str:
    cleaned = remote.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    return cleaned.rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def build_project_lifecycle_record(
    *,
    cwd: Path,
    host: str,
    event: str,
    payload: dict[str, Any],
    now_iso_fn: Callable[[], str],
) -> dict[str, Any]:
    """Build a lifecycle record for the hook invocation."""
    expanded_cwd = cwd.expanduser()
    path_exists = expanded_cwd.exists()
    git_root = _git_root(expanded_cwd)
    identity_root = git_root or expanded_cwd
    remote = _git_remote(identity_root) if git_root else None
    identity_source = "git_remote" if remote else "path"
    identity_value = remote or str(identity_root)
    project_hash = hashlib.sha256(identity_value.encode("utf-8")).hexdigest()[:12]
    project_name = _project_name_from_remote(remote) if remote else identity_root.name
    project_id = f"{_safe_slug(project_name)}-{project_hash}"

    return {
        "schema_version": "project-lifecycle-v1",
        "project_id": project_id,
        "project_name": _safe_slug(project_name),
        "status": "active" if path_exists else "missing",
        "host": host,
        "event": event,
        "observed_at": now_iso_fn(),
        "local_path": str(expanded_cwd),
        "path_exists": path_exists,
        "git_root": str(git_root) if git_root else None,
        "git_remote": remote,
        "identity_source": identity_source,
        "identity_value": identity_value,
        "payload_cwd": payload.get("cwd") if isinstance(payload.get("cwd"), str) else None,
        "retention_policy": "preserve-memory-on-missing-path",
    }


def _path_index_path(lifecycle_root: Path) -> Path:
    return lifecycle_root / "path-index.json"


def _load_path_index(lifecycle_root: Path) -> dict[str, Any]:
    path = _path_index_path(lifecycle_root)
    if not path.exists():
        return {"schema_version": "project-lifecycle-path-index-v1", "paths": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": "project-lifecycle-path-index-v1", "paths": {}}
    if not isinstance(loaded, dict):
        return {"schema_version": "project-lifecycle-path-index-v1", "paths": {}}
    paths = loaded.get("paths")
    if not isinstance(paths, dict):
        loaded["paths"] = {}
    loaded.setdefault("schema_version", "project-lifecycle-path-index-v1")
    return loaded


def _write_path_index(lifecycle_root: Path, path_index: dict[str, Any]) -> None:
    path = _path_index_path(lifecycle_root)
    path.write_text(json.dumps(path_index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _path_index_key(cwd: Path) -> str:
    return str(cwd.expanduser())


def _apply_indexed_identity(record: dict[str, Any], path_entry: dict[str, Any] | None) -> None:
    if record.get("status") != "missing" or not isinstance(path_entry, dict):
        return
    for key in ("project_id", "project_name", "git_root", "git_remote", "identity_source", "identity_value"):
        value = path_entry.get(key)
        if value is not None:
            record[key] = value
    if path_entry.get("first_observed_at"):
        record["first_observed_at"] = path_entry["first_observed_at"]


def _update_path_index(path_index: dict[str, Any], record: dict[str, Any]) -> None:
    paths = path_index.setdefault("paths", {})
    if not isinstance(paths, dict):
        paths = {}
        path_index["paths"] = paths
    local_path = record.get("local_path")
    if not isinstance(local_path, str) or not local_path:
        return
    previous = paths.get(local_path)
    first_observed_at = record.get("first_observed_at")
    if isinstance(previous, dict):
        first_observed_at = previous.get("first_observed_at") or first_observed_at
    paths[local_path] = {
        "project_id": record.get("project_id"),
        "project_name": record.get("project_name"),
        "git_root": record.get("git_root"),
        "git_remote": record.get("git_remote"),
        "identity_source": record.get("identity_source"),
        "identity_value": record.get("identity_value"),
        "first_observed_at": first_observed_at,
        "last_observed_at": record.get("observed_at"),
    }


def _cleanup_old_event_files(
    *,
    lifecycle_root: Path,
    project_id: str,
    retention_days: int,
    now_fn: Callable[[], Any] | None = None,
) -> int:
    """Delete event files older than retention_days. Returns count deleted.

    Throttled via .last-cleanup sentinel — returns 0 if cleanup already ran today.
    If retention_days is 0, cleanup is disabled and this returns 0 immediately.
    All exceptions are caught and logged to prevent blocking the hook.
    """
    if retention_days <= 0:
        return 0

    try:
        if now_fn is None:
            now = datetime.now()
        else:
            result = now_fn()
            if isinstance(result, datetime):
                now = result
            else:
                # now_fn returned an ISO string; parse the date portion
                now = datetime.fromisoformat(str(result)[:19])

        today_str = now.strftime("%Y-%m-%d")
        cutoff_date = now.date() - timedelta(days=retention_days)

        project_dir = lifecycle_root / "projects" / project_id
        events_dir = project_dir / "events"
        sentinel_path = project_dir / ".last-cleanup"

        # Throttle: check if cleanup already ran today
        if sentinel_path.exists():
            try:
                last_cleanup_date = sentinel_path.read_text(encoding="utf-8").strip()
                if last_cleanup_date == today_str:
                    return 0
            except OSError:
                pass

        if not events_dir.exists() or not events_dir.is_dir():
            return 0

        deleted_count = 0
        for event_file in events_dir.glob("*.jsonl"):
            # Parse date from filename: {YYYY-MM-DD}.jsonl
            try:
                file_date_str = event_file.stem  # e.g., "2026-08-01"
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d").date()
                if file_date < cutoff_date:
                    event_file.unlink()
                    deleted_count += 1
            except (ValueError, OSError):
                # Skip files that don't match expected pattern or can't be deleted
                continue

        # Write/update the sentinel with today's date
        try:
            sentinel_path.write_text(today_str + "\n", encoding="utf-8")
        except OSError:
            pass

        return deleted_count
    except Exception as exc:
        # Cleanup failures must never block the hook, but log the failure
        warnings.warn(f"lifecycle cleanup failed for project '{project_id}': {exc}", stacklevel=2)
        return 0


def record_project_lifecycle(
    *,
    lifecycle_root: Path,
    cwd: Path,
    host: str,
    event: str,
    payload: dict[str, Any],
    now_iso_fn: Callable[[], str],
) -> dict[str, Any]:
    """Write lifecycle state and append an event line.

    Existing records are updated in place.  No artifact or memory directory is
    removed, even when the project path is missing.
    """
    record = build_project_lifecycle_record(
        cwd=cwd,
        host=host,
        event=event,
        payload=payload,
        now_iso_fn=now_iso_fn,
    )
    projects_dir = lifecycle_root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    path_index = _load_path_index(lifecycle_root)
    path_entry = path_index.get("paths", {}).get(_path_index_key(cwd))
    _apply_indexed_identity(record, path_entry if isinstance(path_entry, dict) else None)

    record_path = projects_dir / f"{record['project_id']}.json"

    if record_path.exists():
        try:
            previous = json.loads(record_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = {}
        if isinstance(previous, dict):
            record["first_observed_at"] = previous.get("first_observed_at") or previous.get("observed_at")
    record.setdefault("first_observed_at", record["observed_at"])
    _update_path_index(path_index, record)

    rendered = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    record_path.write_text(rendered, encoding="utf-8")
    _write_path_index(lifecycle_root, path_index)

    # Per-project daily event file (replaces global events.jsonl)
    event_date = record["observed_at"][:10]  # "2026-08-01" — first 10 chars of ISO timestamp
    project_events_dir = projects_dir / record["project_id"] / "events"
    project_events_dir.mkdir(parents=True, exist_ok=True)
    event_log = project_events_dir / f"{event_date}.jsonl"
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    record["record_path"] = str(record_path)
    record["event_log"] = str(event_log)

    # Opportunistic cleanup of old event files (throttled to once per day)
    try:
        try:
            retention_days = int(os.environ.get("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "30"))
        except ValueError:
            # Non-integer env var value — fall back to default instead of silently disabling cleanup
            retention_days = 30
        _cleanup_old_event_files(
            lifecycle_root=lifecycle_root,
            project_id=record["project_id"],
            retention_days=retention_days,
            now_fn=now_iso_fn,
        )
    except Exception as exc:
        # Cleanup failures must never block the hook, but log the failure
        warnings.warn(f"lifecycle retention cleanup failed: {exc}", stacklevel=2)

    return record


def _compute_path_index(lifecycle_root: Path) -> dict[str, Any]:
    """Compute the path index from projects/*.json without writing.

    Returns a dict with:
        - total_files_scanned: number of projects/*.json files processed
        - active_entries: number of records passing filters
        - skipped_inactive: number of records with status != "active"
        - skipped_missing: number of records with path_exists == False
        - deduplicated: number of duplicate local_path entries removed
        - paths: the computed paths dict
    """
    projects_dir = lifecycle_root / "projects"

    total_files_scanned = 0
    skipped_inactive = 0
    skipped_missing = 0
    deduplicated = 0

    # Collect all active records, dedup by local_path
    paths: dict[str, dict[str, Any]] = {}
    # Track earliest first_observed_at per local_path across all records
    first_observed_map: dict[str, str] = {}

    if projects_dir.exists() and projects_dir.is_dir():
        for project_file in sorted(projects_dir.glob("*.json")):
            total_files_scanned += 1
            try:
                record = json.loads(project_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(record, dict):
                continue

            local_path = record.get("local_path")
            if not isinstance(local_path, str) or not local_path:
                continue

            status = record.get("status")
            if status != "active":
                skipped_inactive += 1
                continue

            path_exists = record.get("path_exists")
            if path_exists is False:
                skipped_missing += 1
                continue

            observed_at = record.get("observed_at", "")
            first_observed_at = record.get("first_observed_at") or observed_at

            # Track earliest first_observed_at for this local_path
            if local_path in first_observed_map:
                if first_observed_at < first_observed_map[local_path]:
                    first_observed_map[local_path] = first_observed_at
            else:
                first_observed_map[local_path] = first_observed_at

            # Dedup: keep record with latest observed_at
            if local_path in paths:
                deduplicated += 1
                existing_observed = paths[local_path].get("last_observed_at", "")
                if observed_at > existing_observed:
                    paths[local_path] = {
                        "project_id": record.get("project_id"),
                        "project_name": record.get("project_name"),
                        "git_root": record.get("git_root"),
                        "git_remote": record.get("git_remote"),
                        "identity_source": record.get("identity_source"),
                        "identity_value": record.get("identity_value"),
                        "last_observed_at": observed_at,
                    }
            else:
                paths[local_path] = {
                    "project_id": record.get("project_id"),
                    "project_name": record.get("project_name"),
                    "git_root": record.get("git_root"),
                    "git_remote": record.get("git_remote"),
                    "identity_source": record.get("identity_source"),
                    "identity_value": record.get("identity_value"),
                    "last_observed_at": observed_at,
                }

    # Attach earliest first_observed_at to each entry
    for local_path, entry in paths.items():
        entry["first_observed_at"] = first_observed_map.get(local_path, entry.get("last_observed_at"))

    active_entries = len(paths)

    return {
        "total_files_scanned": total_files_scanned,
        "active_entries": active_entries,
        "skipped_inactive": skipped_inactive,
        "skipped_missing": skipped_missing,
        "deduplicated": deduplicated,
        "paths": paths,
    }


def rebuild_path_index(lifecycle_root: str | Path) -> dict[str, Any]:
    """Rebuild path-index.json from projects/*.json files.

    Traverses all per-project JSON files, filters inactive/missing records,
    deduplicates by local_path (keeping latest observed_at), and atomically
    writes path-index.json.

    Returns a statistics dict with keys:
        - total_files_scanned: number of projects/*.json files processed
        - active_entries: number of records passing filters
        - skipped_inactive: number of records with status != "active"
        - skipped_missing: number of records with path_exists == False
        - deduplicated: number of duplicate local_path entries removed
        - paths: the rebuilt paths dict
    """
    lifecycle_root = Path(lifecycle_root)

    # Compute the index
    result = _compute_path_index(lifecycle_root)

    # Build path-index.json structure
    path_index = {
        "schema_version": "project-lifecycle-path-index-v1",
        "paths": result["paths"],
    }

    # Atomic write: temp file + os.replace
    index_path = _path_index_path(lifecycle_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory, then atomic rename
    fd, temp_path = tempfile.mkstemp(
        dir=index_path.parent,
        prefix=".path-index-",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(path_index, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(temp_path, index_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    return result


def rebuild_main(argv: list[str] | None = None) -> None:
    """CLI entry point for memory-lifecycle-rebuild."""
    parser = argparse.ArgumentParser(
        prog="memory-lifecycle-rebuild",
        description="Rebuild path-index.json from projects/*.json files",
    )
    parser.add_argument(
        "--lifecycle-root",
        type=str,
        default="~/.memory-core/project-lifecycle",
        help="Path to lifecycle root (default: ~/.memory-core/project-lifecycle)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be rebuilt without writing path-index.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output statistics as JSON",
    )

    args = parser.parse_args(argv)
    lifecycle_root = Path(args.lifecycle_root).expanduser()

    if args.dry_run:
        # Dry run: compute but don't write
        result = _compute_path_index(lifecycle_root)

        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("dry-run: would rebuild path-index.json")
            print(f"  total_files_scanned: {result['total_files_scanned']}")
            print(f"  active_entries: {result['active_entries']}")
            print(f"  skipped_inactive: {result['skipped_inactive']}")
            print(f"  skipped_missing: {result['skipped_missing']}")
            print(f"  deduplicated: {result['deduplicated']}")
            print(f"  paths: {len(result['paths'])} entries")
    else:
        result = rebuild_path_index(lifecycle_root)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("Rebuilt path-index.json:")
            print(f"  total_files_scanned: {result['total_files_scanned']}")
            print(f"  active_entries: {result['active_entries']}")
            print(f"  skipped_inactive: {result['skipped_inactive']}")
            print(f"  skipped_missing: {result['skipped_missing']}")
            print(f"  deduplicated: {result['deduplicated']}")
            print(f"  paths: {len(result['paths'])} entries")

    sys.exit(0)


def migrate_lifecycle_events(lifecycle_root: Path) -> dict[str, Any]:
    """Migrate global events.jsonl to per-project daily files.

    Reads events.jsonl, groups by project_id + date, writes per-project daily files.
    Archives original as events.jsonl.archived (byte-identical).

    Returns stats: {total_read, total_written, per_project: {id: count}, skipped: count, archive_path: str}
    """
    lifecycle_root = Path(lifecycle_root)
    events_jsonl = lifecycle_root / "events.jsonl"

    # Idempotent: if events.jsonl doesn't exist, return zero stats
    if not events_jsonl.exists():
        return {
            "total_read": 0,
            "total_written": 0,
            "per_project": {},
            "skipped": 0,
            "archive_path": None,
        }

    # Read and group events by project_id and date
    grouped_events: dict[str, dict[str, list[str]]] = {}  # {project_id: {date: [lines]}}
    total_read = 0
    skipped = 0

    with events_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            total_read += 1
            line = line.strip()
            if not line:
                skipped += 1  # blank lines count toward skipped for stats reconciliation
                continue

            # Parse JSON
            try:
                event_data = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            # Guard: valid JSON that is not a dict (e.g., '123', '[1,2]') — skip gracefully
            if not isinstance(event_data, dict):
                skipped += 1
                continue

            # Extract required fields
            project_id = event_data.get("project_id")
            observed_at = event_data.get("observed_at")

            if not project_id or not observed_at:
                skipped += 1
                continue

            # Derive date from observed_at (first 10 chars: YYYY-MM-DD)
            event_date = observed_at[:10]

            # Group by project_id and date
            if project_id not in grouped_events:
                grouped_events[project_id] = {}
            if event_date not in grouped_events[project_id]:
                grouped_events[project_id][event_date] = []
            grouped_events[project_id][event_date].append(line)

    # Write per-project daily files
    projects_dir = lifecycle_root / "projects"
    total_written = 0
    per_project_counts: dict[str, int] = {}

    for project_id, date_groups in grouped_events.items():
        project_events_dir = projects_dir / project_id / "events"
        project_events_dir.mkdir(parents=True, exist_ok=True)

        project_total = 0
        for event_date, lines in date_groups.items():
            daily_file = project_events_dir / f"{event_date}.jsonl"

            # Check if file already exists (for idempotency)
            existing_lines: set[str] = set()
            if daily_file.exists():
                with daily_file.open("r", encoding="utf-8") as f:
                    existing_lines = {line.strip() for line in f if line.strip()}

            # Append only new lines
            new_lines = [line for line in lines if line not in existing_lines]
            if new_lines:
                with daily_file.open("a", encoding="utf-8") as f:
                    for line in new_lines:
                        f.write(line + "\n")
                total_written += len(new_lines)
                project_total += len(new_lines)
            else:
                # All lines already exist
                total_written += len(lines)
                project_total += len(lines)

        per_project_counts[project_id] = project_total

    # Archive original events.jsonl (atomic rename)
    archive_path = lifecycle_root / "events.jsonl.archived"
    try:
        os.replace(events_jsonl, archive_path)
    except OSError:
        # If rename fails, try copy + delete as fallback
        import shutil
        shutil.copy2(events_jsonl, archive_path)
        events_jsonl.unlink()

    return {
        "total_read": total_read,
        "total_written": total_written,
        "per_project": per_project_counts,
        "skipped": skipped,
        "archive_path": str(archive_path),
    }


def migrate_main(argv: list[str] | None = None) -> None:
    """CLI entry point for memory-lifecycle-migrate."""
    parser = argparse.ArgumentParser(
        prog="memory-lifecycle-migrate",
        description="Migrate global events.jsonl to per-project daily files",
    )
    parser.add_argument(
        "--lifecycle-root",
        type=str,
        default="~/.memory-core/project-lifecycle",
        help="Path to lifecycle root (default: ~/.memory-core/project-lifecycle)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output statistics as JSON",
    )

    args = parser.parse_args(argv)
    lifecycle_root = Path(args.lifecycle_root).expanduser()

    stats = migrate_lifecycle_events(lifecycle_root)

    if args.json_output:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print("Migration complete:")
        print(f"  total_read: {stats['total_read']}")
        print(f"  total_written: {stats['total_written']}")
        print(f"  skipped: {stats['skipped']}")
        if stats['per_project']:
            print("  per_project:")
            for project_id, count in sorted(stats['per_project'].items()):
                print(f"    {project_id}: {count}")
        if stats['archive_path']:
            print(f"  archive_path: {stats['archive_path']}")
        else:
            print("  archive_path: (no migration needed, events.jsonl not found)")

    sys.exit(0)
