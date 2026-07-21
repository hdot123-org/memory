#!/usr/bin/env python3
"""Tests for workspace/tools/cmux_hook_state.py.

Covers:
- Path helper functions
- Hook state file I/O (load, write, reset)
- Event recording with counters
- Lock file creation
- Edge cases: missing files, corrupt JSON, bad payload, concurrent writes
"""


import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "memory_core" / "tools"))
from cmux_hook_state import (
    HookStateError,
    default_hook_state_path,
    load_hook_state,
    load_hook_state_strict,
    record_hook_event,
    reset_hook_state,
    runtime_state_dir,
    write_hook_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EVENT_KWARGS: dict[str, Any] = {
    "event_name": "session-start",
    "workspace_ref": "ws-1",
    "surface_ref": "codex-main",
    "payload": {"session_id": "s-1", "cwd": "/tmp"},
}


def _fake_project_dir(tmp_path: Path) -> Path:
    """Return a subdir that acts as a project root."""
    return tmp_path / "project"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


class TestPathHelpers:
    def test_runtime_state_dir_returns_artifacts_cmux_runtime(self, tmp_path: Path) -> None:
        project = _fake_project_dir(tmp_path)
        result = runtime_state_dir(project)
        assert result == project / "memory" / "artifacts" / "cmux-runtime"

    def test_default_hook_state_path_returns_path(self, tmp_path: Path) -> None:
        project = _fake_project_dir(tmp_path)
        result = default_hook_state_path(project)
        assert isinstance(result, Path)
        assert result.name == "hook-state.json"


# ---------------------------------------------------------------------------
# load_hook_state
# ---------------------------------------------------------------------------


class TestLoadHookState:
    def test_load_hook_state_handles_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        result = load_hook_state(path)
        assert isinstance(result, dict)
        assert result == {
            "runtime": "cmux",
            "updated_at": "",
            "surfaces": {},
        }

    def test_load_hook_state_handles_corrupt_json(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("not json {{{", encoding="utf-8")
        result = load_hook_state(path)
        assert isinstance(result, dict)
        assert "surfaces" in result

    def test_load_hook_state_handles_non_dict_root(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        result = load_hook_state(path)
        assert isinstance(result, dict)
        assert result["surfaces"] == {}

    def test_load_hook_state_reads_valid_state(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        payload = {
            "runtime": "cmux",
            "updated_at": "2026-01-01T00:00:00",
            "surfaces": {"codex-main": {"last_event": "test"}},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = load_hook_state(path)
        assert result["runtime"] == "cmux"
        assert result["surfaces"]["codex-main"]["last_event"] == "test"


# ---------------------------------------------------------------------------
# load_hook_state_strict
# ---------------------------------------------------------------------------


class TestLoadHookStateStrict:
    def test_strict_raises_on_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        with pytest.raises(HookStateError, match="missing"):
            load_hook_state_strict(path)

    def test_strict_raises_on_corrupt_json(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("{{{broken", encoding="utf-8")
        with pytest.raises(HookStateError, match="unreadable"):
            load_hook_state_strict(path)


# ---------------------------------------------------------------------------
# write_hook_state
# ---------------------------------------------------------------------------


class TestWriteHookState:
    def test_write_hook_state_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        payload = {"runtime": "cmux", "updated_at": "now", "surfaces": {}}
        write_hook_state(path, payload)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["runtime"] == "cmux"

    def test_write_hook_state_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "state.json"
        payload = {"runtime": "cmux", "updated_at": "now", "surfaces": {}}
        write_hook_state(path, payload)
        assert path.exists()

    def test_write_hook_state_rejects_non_serializable(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        payload = {"bad": object()}
        with pytest.raises(TypeError):
            write_hook_state(path, payload)

    def test_write_hook_state_idempotent_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        payload = {
            "runtime": "cmux",
            "updated_at": "t1",
            "surfaces": {"s1": {"last_event": "ping"}},
        }
        write_hook_state(path, payload)
        result = load_hook_state(path)
        assert result["surfaces"]["s1"]["last_event"] == "ping"


# ---------------------------------------------------------------------------
# reset_hook_state
# ---------------------------------------------------------------------------


class TestResetHookState:
    def test_reset_creates_fresh_state(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        returned = reset_hook_state(path)
        assert returned == path
        state = load_hook_state(path)
        assert state["updated_at"] == ""
        assert state["surfaces"] == {}


# ---------------------------------------------------------------------------
# record_hook_event
# ---------------------------------------------------------------------------


class TestRecordHookEvent:
    def test_record_hook_event_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        result = record_hook_event(path, **EVENT_KWARGS)
        assert path.exists()
        assert isinstance(result, dict)
        assert result["last_event"] == "session-start"

    def test_record_hook_event_increments_counter(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        record_hook_event(path, **EVENT_KWARGS)
        record_hook_event(
            path,
            event_name="session-start",
            workspace_ref="ws-1",
            surface_ref="codex-main",
            payload={"session_id": "s-2", "cwd": "/tmp"},
        )
        state = load_hook_state(path)
        assert state["surfaces"]["codex-main"]["session_start_count"] == 2

    def test_record_hook_event_tracks_different_event_types(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state.json"
        record_hook_event(path, **EVENT_KWARGS)
        record_hook_event(
            path,
            event_name="prompt-submit",
            workspace_ref="ws-1",
            surface_ref="codex-main",
            payload={"session_id": "s-2", "cwd": "/tmp"},
        )
        record_hook_event(
            path,
            event_name="stop",
            workspace_ref="ws-1",
            surface_ref="codex-main",
            payload={"session_id": "s-2", "cwd": "/tmp"},
        )
        state = load_hook_state(path)
        surface = state["surfaces"]["codex-main"]
        assert surface["session_start_count"] == 1
        assert surface["prompt_submit_count"] == 1
        assert surface["stop_count"] == 1
        assert surface["last_event"] == "stop"

    def test_record_hook_event_handles_missing_dir(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "missing" / "state.json"
        result = record_hook_event(path, **EVENT_KWARGS)
        assert path.exists()
        assert isinstance(result, dict)

    def test_record_hook_event_multiple_surfaces(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        record_hook_event(
            path,
            event_name="session-start",
            workspace_ref="ws-1",
            surface_ref="codex-main",
            payload={"session_id": "s-1", "cwd": "/tmp"},
        )
        record_hook_event(
            path,
            event_name="session-start",
            workspace_ref="ws-2",
            surface_ref="pm-bot",
            payload={"session_id": "s-2", "cwd": "/tmp"},
        )
        state = load_hook_state(path)
        assert "codex-main" in state["surfaces"]
        assert "pm-bot" in state["surfaces"]

    def test_record_hook_event_sets_timestamp(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        record_hook_event(path, **EVENT_KWARGS)
        state = load_hook_state(path)
        assert state["updated_at"] != ""
        assert state["surfaces"]["codex-main"]["last_event_at"] != ""


# ---------------------------------------------------------------------------
# Lock file behavior
# ---------------------------------------------------------------------------


class TestLockFile:
    def test_lock_file_created_alongside_state(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        write_hook_state(path, {"runtime": "cmux", "updated_at": "", "surfaces": {}})
        lock_path = path.with_name("state.json.lock")
        assert lock_path.exists()


# ---------------------------------------------------------------------------
# Concurrent writes
# ---------------------------------------------------------------------------


class TestConcurrentWrites:
    def test_concurrent_writes_no_data_loss(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        # Seed initial state
        write_hook_state(
            path, {"runtime": "cmux", "updated_at": "", "surfaces": {}}
        )
        errors: list[Exception] = []

        def writer(n: int) -> None:
            try:
                for i in range(10):
                    record_hook_event(
                        path,
                        event_name="prompt-submit",
                        workspace_ref=f"ws-{n}",
                        surface_ref=f"surface-{n}",
                        payload={"session_id": f"s-{n}-{i}", "cwd": "/tmp"},
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent write errors: {errors}"
        state = load_hook_state(path)
        # Each thread recorded 10 events on its own surface
        for n in range(3):
            surface = state["surfaces"].get(f"surface-{n}")
            assert surface is not None, f"surface-{n} missing from state"
            assert surface["prompt_submit_count"] == 10
