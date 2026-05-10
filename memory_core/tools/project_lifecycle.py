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

    rendered = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    record_path.write_text(rendered, encoding="utf-8")
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    record["record_path"] = str(record_path)
    record["event_log"] = str(event_log)
    return record
