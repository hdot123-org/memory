"""Tests for cmux_hook_state module."""

import json
from pathlib import Path

import pytest

from memory_core.tools.cmux_hook_state import (
    HookStateError,
    _base_payload,
    _default_surface_state,
    default_hook_state_path,
    load_hook_state,
    load_hook_state_strict,
    record_hook_event,
    reset_hook_state,
    runtime_state_dir,
    write_hook_state,
)


class TestRuntimeStateDir:
    def test_returns_correct_path(self, tmp_path):
        result = runtime_state_dir(tmp_path)
        assert result == tmp_path / "memory" / "artifacts" / "cmux-runtime"

    def test_expands_user(self):
        result = runtime_state_dir(Path("~/test"))
        assert "~" not in str(result)


class TestDefaultHookStatePath:
    def test_returns_runtime_dir_child(self, tmp_path):
        result = default_hook_state_path(tmp_path)
        assert result.name == "hook-state.json"
        assert "cmux-runtime" in str(result)


class TestBasePayload:
    def test_structure(self):
        payload = _base_payload()
        assert payload["runtime"] == "cmux"
        assert payload["updated_at"] == ""
        assert payload["surfaces"] == {}


class TestLoadHookState:
    def test_nonexistent_returns_base(self, tmp_path):
        path = tmp_path / "state.json"
        result = load_hook_state(path)
        assert result["runtime"] == "cmux"
        assert result["surfaces"] == {}

    def test_valid_file(self, tmp_path):
        path = tmp_path / "state.json"
        data = {"runtime": "cmux", "surfaces": {"s1": {"count": 1}}}
        path.write_text(json.dumps(data))
        result = load_hook_state(path)
        assert result["surfaces"]["s1"]["count"] == 1

    def test_invalid_json_returns_base(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not json")
        result = load_hook_state(path)
        assert result["runtime"] == "cmux"

    def test_non_dict_returns_base(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("[1, 2, 3]")
        result = load_hook_state(path)
        assert result["runtime"] == "cmux"

    def test_surfaces_not_dict_fixed(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text('{"surfaces": "not-a-dict"}')
        result = load_hook_state(path)
        assert result["surfaces"] == {}


class TestLoadHookStateStrict:
    def test_nonexistent_raises(self, tmp_path):
        with pytest.raises(HookStateError, match="missing"):
            load_hook_state_strict(tmp_path / "missing.json")

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("bad")
        with pytest.raises(HookStateError, match="unreadable"):
            load_hook_state_strict(path)

    def test_non_dict_raises(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("[1]")
        with pytest.raises(HookStateError, match="not an object"):
            load_hook_state_strict(path)

    def test_surfaces_not_dict_raises(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text('{"surfaces": "x"}')
        with pytest.raises(HookStateError, match="surfaces"):
            load_hook_state_strict(path)


class TestWriteHookState:
    def test_writes_valid_json(self, tmp_path):
        path = tmp_path / "state.json"
        payload = {"runtime": "cmux", "surfaces": {"s1": {"count": 1}}}
        write_hook_state(path, payload)
        loaded = json.loads(path.read_text())
        assert loaded["surfaces"]["s1"]["count"] == 1

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "state.json"
        write_hook_state(path, _base_payload())
        assert path.exists()

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "state.json"
        write_hook_state(path, {"runtime": "old", "surfaces": {"s": {"x": 1}}})
        write_hook_state(path, {"runtime": "new", "surfaces": {}})
        loaded = json.loads(path.read_text())
        assert loaded["runtime"] == "new"


class TestResetHookState:
    def test_resets_to_base(self, tmp_path):
        path = tmp_path / "state.json"
        write_hook_state(path, {"runtime": "old", "surfaces": {"s": {"x": 1}}})
        result = reset_hook_state(path)
        loaded = json.loads(result.read_text())
        assert loaded["surfaces"] == {}


class TestRecordHookEvent:
    def test_session_start_increments(self, tmp_path):
        path = tmp_path / "state.json"
        reset_hook_state(path)
        record_hook_event(
            path,
            event_name="session-start",
            workspace_ref="ws1",
            surface_ref="surf1",
            payload={"session_id": "s123", "cwd": "/tmp"},
        )
        state = load_hook_state(path)
        assert state["surfaces"]["surf1"]["session_start_count"] == 1

    def test_multiple_events(self, tmp_path):
        path = tmp_path / "state.json"
        reset_hook_state(path)
        for _ in range(3):
            record_hook_event(
                path,
                event_name="prompt-submit",
                workspace_ref="ws1",
                surface_ref="surf1",
                payload={},
            )
        state = load_hook_state(path)
        assert state["surfaces"]["surf1"]["prompt_submit_count"] == 3

    def test_stop_event(self, tmp_path):
        path = tmp_path / "state.json"
        reset_hook_state(path)
        record_hook_event(
            path,
            event_name="stop",
            workspace_ref="ws1",
            surface_ref="surf1",
            payload={},
        )
        state = load_hook_state(path)
        assert state["surfaces"]["surf1"]["stop_count"] == 1

    def test_notification_event(self, tmp_path):
        path = tmp_path / "state.json"
        reset_hook_state(path)
        record_hook_event(
            path,
            event_name="notification",
            workspace_ref="ws1",
            surface_ref="surf1",
            payload={},
        )
        state = load_hook_state(path)
        assert state["surfaces"]["surf1"]["notification_count"] == 1

    def test_unknown_event_still_records_last_event(self, tmp_path):
        path = tmp_path / "state.json"
        reset_hook_state(path)
        record_hook_event(
            path,
            event_name="custom-event",
            workspace_ref="ws1",
            surface_ref="surf1",
            payload={},
        )
        state = load_hook_state(path)
        assert state["surfaces"]["surf1"]["last_event"] == "custom-event"

    def test_returns_surface_state(self, tmp_path):
        path = tmp_path / "state.json"
        reset_hook_state(path)
        result = record_hook_event(
            path,
            event_name="session-start",
            workspace_ref="ws1",
            surface_ref="surf1",
            payload={},
        )
        assert result["surface_ref"] == "surf1"


class TestDefaultSurfaceState:
    def test_structure(self):
        state = _default_surface_state("ws1", "surf1")
        assert state["workspace_ref"] == "ws1"
        assert state["surface_ref"] == "surf1"
        assert state["session_start_count"] == 0
        assert state["prompt_submit_count"] == 0
        assert state["stop_count"] == 0
        assert state["notification_count"] == 0
        assert state["last_event"] == ""
