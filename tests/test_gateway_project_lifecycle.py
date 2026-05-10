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
        host="codex",
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

    package = gw.build_context_package("codex", "session-start", {"cwd": str(tmp_path)})

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

    assert gw._configured_artifact_root(workspace_root) == workspace_root / "artifacts" / "memory-hook"
    assert gw._configured_error_log(workspace_root) == workspace_root / "memory" / "system" / "errors.log"
    assert gw._configured_project_lifecycle_root(workspace_root) == global_state_root / "project-lifecycle"


def test_global_state_root_preserves_project_memory_write_targets(monkeypatch, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project_memory = project / "memory"
    project_memory.mkdir(parents=True)
    global_state_root = tmp_path / "global-state"

    monkeypatch.setenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", str(global_state_root))
    monkeypatch.setattr(gw, "WORKSPACE_ROOT", project)
    monkeypatch.setattr(gw, "ARTIFACT_ROOT", project / "artifacts" / "memory-hook")
    monkeypatch.setattr(gw, "ERROR_LOG", project_memory / "system" / "errors.log")
    monkeypatch.setattr(gw, "PROJECT_LIFECYCLE_ROOT", global_state_root / "project-lifecycle")
    monkeypatch.setattr(gw, "_default_write_policy", None)

    targets = gw.write_targets()

    assert targets["artifacts"] == str(project / "artifacts")
    assert targets["system_error"] == str(project_memory / "system" / "errors.log")
    assert targets["hook_lifecycle"] == str(global_state_root / "project-lifecycle")
    assert Path(targets["artifacts"]).is_relative_to(project)
    assert Path(targets["system_error"]).is_relative_to(project_memory)
