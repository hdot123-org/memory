#!/opt/homebrew/bin/python3
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class HookStateError(RuntimeError):
    pass


def _hook_state_lock_path(path: Path) -> Path:
    path = path.expanduser().resolve()
    return path.with_name(f"{path.name}.lock")


@contextmanager
def _exclusive_hook_state_lock(path: Path):
    lock_path = _hook_state_lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def runtime_state_dir(project_dir: Path) -> Path:
    project_dir = project_dir.expanduser().resolve()
    return project_dir / "artifacts" / "cmux-runtime"


def default_hook_state_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "hook-state.json"


def default_assignment_file_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "cmux-assignment.json"


def default_pm_bot_watch_assignment_file_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "pm-bot-watch.json"


def default_codex_main_task_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "codex-main-task.json"


def default_project_overview_json_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "project-task-overview.json"


def default_project_overview_text_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "project-task-overview.txt"


def default_assignment_watcher_pid_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "watch_cmux_assignments.pid"


def default_assignment_watcher_log_path(project_dir: Path) -> Path:
    return runtime_state_dir(project_dir) / "watch_cmux_assignments.log"


def _base_payload() -> dict[str, object]:
    return {
        "runtime": "cmux",
        "updated_at": "",
        "surfaces": {},
    }


def reset_hook_state(path: Path) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_hook_state(path, _base_payload())
    return path


def load_hook_state(path: Path) -> dict[str, object]:
    path = path.expanduser().resolve()
    if not path.exists():
        return _base_payload()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _base_payload()
    if not isinstance(payload, dict):
        return _base_payload()
    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, dict):
        payload["surfaces"] = {}
    return payload


def load_hook_state_strict(path: Path) -> dict[str, object]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise HookStateError(f"hook state file missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HookStateError(f"hook state file unreadable: {path} -> {exc}") from exc
    if not isinstance(payload, dict):
        raise HookStateError(f"hook state payload is not an object: {path}")
    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, dict):
        raise HookStateError(f"hook state surfaces block is invalid: {path}")
    return payload


def _write_hook_state_unlocked(path: Path, payload: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            fd = -1  # Ownership transferred to os.fdopen context manager
            Path(tmp_name).replace(path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    except OSError as exc:
        raise HookStateError(
            f"failed to write hook state to {path}: {exc} "
            f"(payload keys: {list(payload.keys())})"
        ) from exc
    try:
        load_hook_state_strict(path)
    except HookStateError as exc:
        raise HookStateError(
            f"hook state verification failed after write to {path}: {exc} "
            f"(payload keys: {list(payload.keys())})"
        ) from exc


def write_hook_state(path: Path, payload: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    with _exclusive_hook_state_lock(path):
        _write_hook_state_unlocked(path, payload)


def get_surface_hook_state(path: Path, surface_ref: str) -> dict[str, object]:
    payload = load_hook_state(path)
    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, dict):
        return {}
    surface_state = surfaces.get(surface_ref)
    if not isinstance(surface_state, dict):
        return {}
    return surface_state


def _default_surface_state(workspace_ref: str, surface_ref: str) -> dict[str, object]:
    """Return a fresh surface-state dict with default counters."""
    return {
        "workspace_ref": workspace_ref,
        "surface_ref": surface_ref,
        "session_start_count": 0,
        "prompt_submit_count": 0,
        "stop_count": 0,
        "notification_count": 0,
        "last_event": "",
        "last_event_at": "",
        "last_session_id": "",
        "last_cwd": "",
    }


def record_hook_event(
    path: Path,
    *,
    event_name: str,
    workspace_ref: str,
    surface_ref: str,
    payload: dict[str, object],
) -> dict[str, object]:
    path = path.expanduser().resolve()
    with _exclusive_hook_state_lock(path):
        state = load_hook_state(path)
        surfaces = state.setdefault("surfaces", {})
        if not isinstance(surfaces, dict):
            surfaces = {}
            state["surfaces"] = surfaces

        surface_state = surfaces.get(surface_ref)
        if not isinstance(surface_state, dict):
            surface_state = _default_surface_state(workspace_ref, surface_ref)
            surfaces[surface_ref] = surface_state

        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        surface_state["workspace_ref"] = workspace_ref
        surface_state["surface_ref"] = surface_ref
        surface_state["last_event"] = event_name
        surface_state["last_event_at"] = now
        surface_state["last_session_id"] = str(payload.get("session_id") or "")
        surface_state["last_cwd"] = str(payload.get("cwd") or "")

        if event_name == "session-start":
            surface_state["session_start_count"] = int(surface_state.get("session_start_count") or 0) + 1
        elif event_name == "prompt-submit":
            surface_state["prompt_submit_count"] = int(surface_state.get("prompt_submit_count") or 0) + 1
        elif event_name == "stop":
            surface_state["stop_count"] = int(surface_state.get("stop_count") or 0) + 1
        elif event_name == "notification":
            surface_state["notification_count"] = int(surface_state.get("notification_count") or 0) + 1

        state["updated_at"] = now
        _write_hook_state_unlocked(path, state)
        return surface_state
