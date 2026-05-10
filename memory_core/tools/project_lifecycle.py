"""Project lifecycle tracking for global memory hooks.

The lifecycle tracker is deliberately conservative: it records that a project
path is active or missing, but it never deletes memory artifacts.  This keeps
Codex workspace churn separate from memory retention.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
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
    event_log = lifecycle_root / "events.jsonl"

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
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    record["record_path"] = str(record_path)
    record["event_log"] = str(event_log)
    return record
