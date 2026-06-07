from __future__ import annotations

from pathlib import Path

from memory_core.tools import memory_hook_gateway as gw


def test_original_cwd_preferred_when_enabled(monkeypatch, tmp_path: Path) -> None:
    original = tmp_path / "external-project"
    original.mkdir()

    monkeypatch.setenv("MEMORY_HOOK_ORIGINAL_CWD", str(original))
    monkeypatch.setenv("MEMORY_HOOK_PREFER_EXTERNAL_CWD", "1")

    assert gw._discover_cwd({"cwd": str(gw.REPO_ROOT)}) == original


def test_project_lifecycle_disabled_by_default(monkeypatch, tmp_path: Path) -> None:
    lifecycle_root = tmp_path / "lifecycle"

    monkeypatch.delenv("MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE", raising=False)
    monkeypatch.setattr(gw, "PROJECT_LIFECYCLE_ROOT", lifecycle_root)

    record = gw._record_project_lifecycle_event(
        host="factory",
        event="session-start",
        payload={"cwd": str(tmp_path)},
        cwd=tmp_path,
    )

    assert record is None
    assert not lifecycle_root.exists()


def test_build_context_package_includes_lifecycle_when_enabled(monkeypatch, tmp_path: Path) -> None:
    lifecycle_root = tmp_path / "lifecycle"

    monkeypatch.setenv("MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE", "1")
    monkeypatch.setenv("MEMORY_HOOK_ORIGINAL_CWD", str(tmp_path))
    monkeypatch.setenv("MEMORY_HOOK_PREFER_EXTERNAL_CWD", "1")
    monkeypatch.setattr(gw, "PROJECT_LIFECYCLE_ROOT", lifecycle_root)

    package = gw.build_context_package("factory", "session-start", {"cwd": str(tmp_path)})

    lifecycle = package["system_context"].get("project_lifecycle")
    assert lifecycle is not None
    assert lifecycle["status"] == "active"
    assert lifecycle["local_path"] == str(tmp_path)
    assert Path(lifecycle["record_path"]).is_file()


def test_global_state_root_does_not_redirect_project_artifact_or_error_paths(monkeypatch, tmp_path: Path) -> None:
    global_state_root = tmp_path / "global-state"
    workspace_root = tmp_path / "project"

    monkeypatch.setenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", str(global_state_root))
    monkeypatch.delenv("MEMORY_HOOK_STORAGE_ROOT", raising=False)

    assert gw._configured_artifact_root(workspace_root) == workspace_root / "memory" / "artifacts" / "memory-hook"
    assert gw._configured_error_log(workspace_root) == workspace_root / "memory" / "system" / "errors.log"
    assert gw._configured_project_lifecycle_root(workspace_root) == global_state_root / "project-lifecycle"


def test_global_state_root_preserves_project_memory_write_targets(monkeypatch, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project_memory = project / "memory"
    project_memory.mkdir(parents=True)
    global_state_root = tmp_path / "global-state"

    monkeypatch.setenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", str(global_state_root))
    monkeypatch.setattr(gw, "WORKSPACE_ROOT", project)
    monkeypatch.setattr(gw, "ARTIFACT_ROOT", project / "memory" / "artifacts" / "memory-hook")
    monkeypatch.setattr(gw, "ERROR_LOG", project_memory / "system" / "errors.log")
    monkeypatch.setattr(gw, "PROJECT_LIFECYCLE_ROOT", global_state_root / "project-lifecycle")
    monkeypatch.setattr(gw, "_default_write_policy", None)

    targets = gw.write_targets()

    assert targets["artifacts"] == str(project / "memory" / "artifacts")
    assert targets["system_error"] == str(project_memory / "system" / "errors.log")
    assert targets["hook_lifecycle"] == str(global_state_root / "project-lifecycle")
    assert Path(targets["artifacts"]).is_relative_to(project)
    assert Path(targets["system_error"]).is_relative_to(project_memory)

def test_artifact_and_error_logs_are_date_partitioned(monkeypatch, tmp_path: Path) -> None:
    import json
    from datetime import datetime as real_datetime

    from memory_core.tools.memory_hook_impls import ArtifactWriter, ErrorSinkImpl

    class FixedDatetime:
        @staticmethod
        def now():
            return real_datetime(2026, 5, 11, 9, 8, 7, 123456)

    project = tmp_path / "project"
    context_root = project / "memory" / "artifacts" / "memory-hook" / "contexts"
    error_log = project / "memory" / "system" / "errors.log"
    writer = ArtifactWriter(context_root=context_root, error_log=error_log, datetime_module=FixedDatetime)
    package = {"schema_version": "wb-hook-v2"}

    assert writer.write("factory", "session-start", package) is True

    snapshot = context_root / "2026-05-11" / "20260511T090807123456-factory-session-start.json"
    daily_latest = context_root / "2026-05-11" / "latest-factory-session-start.json"
    latest = context_root / "latest-factory-session-start.json"
    daily_events = project / "memory" / "artifacts" / "memory-hook" / "events" / "2026-05-11.jsonl"
    legacy_events = project / "memory" / "artifacts" / "memory-hook" / "events.jsonl"

    assert snapshot.is_file()
    assert daily_latest.is_file()
    assert latest.is_file()
    assert daily_events.is_file()
    assert legacy_events.is_file()
    refs = json.loads(snapshot.read_text(encoding="utf-8"))["artifact_refs"]
    assert refs["snapshot"] == str(snapshot)
    assert refs["daily_latest"] == str(daily_latest)
    assert refs["event_log"] == str(daily_events)
    assert refs["legacy_event_log"] == str(legacy_events)

    sink = ErrorSinkImpl(error_log, now_iso_fn=lambda: "2026-05-11T09:08:07+08:00")
    sink.log("component", "boom", {"x": 1})

    daily_errors = project / "memory" / "system" / "errors" / "2026-05-11.log"
    assert daily_errors.is_file()
    assert error_log.is_file()
    assert "boom" in daily_errors.read_text(encoding="utf-8")
    assert "boom" in error_log.read_text(encoding="utf-8")
