from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

from memory_core.tools.codex_global_hooks import install_codex_hooks, merge_codex_hooks
from memory_core.tools.project_lifecycle import record_project_lifecycle


def test_merge_replaces_existing_memory_hooks_and_preserves_unrelated(tmp_path: Path) -> None:
    wrapper = tmp_path / ".codex" / "bin" / "memory-hook"
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": "custom-session-start", "timeout": 3},
                        {
                            "type": "command",
                            "command": "python3 /Users/busiji/workbot/workspace/tools/memory_hook_gateway.py --host codex --event session-start",
                            "timeout": 10,
                        },
                    ]
                }
            ],
            "OtherEvent": [{"hooks": [{"type": "command", "command": "keep-me"}]}],
        }
    }

    merged = merge_codex_hooks(
        existing,
        {
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": f"{wrapper} --host codex --event session-start"}]}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": f"{wrapper} --host codex --event prompt-submit"}]}],
                "Stop": [{"hooks": [{"type": "command", "command": f"{wrapper} --host codex --event stop"}]}],
            }
        },
    )

    session_commands = [h["command"] for g in merged["hooks"]["SessionStart"] for h in g["hooks"]]
    assert "custom-session-start" in session_commands
    assert all("workbot/workspace/tools/memory_hook_gateway.py" not in cmd for cmd in session_commands)
    assert f"{wrapper} --host codex --event session-start" in session_commands
    assert merged["hooks"]["OtherEvent"] == existing["hooks"]["OtherEvent"]


def _fake_memory_commands(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    command_dir = tmp_path / "bin"
    command_dir.mkdir()
    gateway = command_dir / "memory-hook-gateway"
    gateway.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gateway.chmod(gateway.stat().st_mode | stat.S_IXUSR)
    init = command_dir / "memory-init"
    init.write_text(
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --target) shift; target=\"$1\" ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        "mkdir -p \"$target/memory/system\"\n",
        encoding="utf-8",
    )
    init.chmod(init.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(command_dir))
    return gateway, init


def test_install_codex_hooks_writes_wrapper_and_hooks_json(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    storage_root = tmp_path / "memory-store"
    gateway, init = _fake_memory_commands(tmp_path, monkeypatch)

    result = install_codex_hooks(codex_home=codex_home, storage_root=storage_root)

    wrapper = codex_home / "bin" / "memory-hook"
    hooks_path = codex_home / "hooks.json"
    assert result["success"] is True
    assert wrapper.is_file()
    assert hooks_path.is_file()
    assert os.stat(wrapper).st_mode & stat.S_IXUSR
    assert result["gateway_command"] == str(gateway)
    assert result["init_command"] == str(init)

    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert f"MEMORY_HOOK_GLOBAL_STATE_ROOT={storage_root}" in wrapper_text
    assert "python3 /Users/busiji/workbot/workspace/tools/memory_hook_gateway.py" not in wrapper_text
    assert str(gateway) in wrapper_text
    assert str(init) in wrapper_text
    assert "exec \"$MEMORY_HOOK_GATEWAY\" \"$@\"" in wrapper_text
    assert "MEMORY_HOOK_ORIGINAL_CWD" in wrapper_text
    assert "MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE" in wrapper_text
    assert "MEMORY_HOOK_STORAGE_ROOT" not in wrapper_text
    assert "memory-init" in wrapper_text or str(init) in wrapper_text

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for event_groups in hooks["hooks"].values()
        for group in event_groups
        for hook in group["hooks"]
    ]
    assert len(commands) == 3
    assert all(str(wrapper) in command for command in commands)


def test_wrapper_skips_exact_home_project_root_but_allows_child(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    fake_home = tmp_path / "home"
    child_project = fake_home / "workbot"
    child_project.mkdir(parents=True)
    _fake_memory_commands(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(fake_home))

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    home_proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=fake_home,
        text=True,
        capture_output=True,
        check=False,
    )

    assert home_proc.returncode == 0
    assert home_proc.stdout.strip() == "{}"
    assert not (fake_home / "memory" / "system").exists()
    assert not (fake_home / "memory" / "system").exists()

    child_proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=child_project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert child_proc.returncode == 0
    assert (child_project / "memory" / "system").is_dir()
    assert not (fake_home / "memory" / "system").exists()


def test_wrapper_initializes_project_memory_before_gateway(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    project = tmp_path / "project"
    project.mkdir()
    _fake_memory_commands(tmp_path, monkeypatch)

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert (project / "memory" / "system").is_dir()
    assert (project / "memory" / "system").is_dir()


def test_wrapper_initializes_git_project_root_from_subdirectory(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    project = tmp_path / "project"
    nested = project / "src" / "feature"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=nested,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert (project / "memory" / "system").is_dir()
    assert not (nested / "memory" / "system").exists()


def test_wrapper_skips_auto_init_for_memory_core_source_repo(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    # M3: wrapper execs gateway with READONLY=1 instead of printf '{}'; exit 0
    # Fake gateway outputs nothing, so stdout may be empty
    assert not (memory_repo / "memory" / "system").exists()
    assert not (memory_repo / "memory").exists()


def test_wrapper_skips_memory_core_source_repo_even_with_dot_memory(monkeypatch, tmp_path: Path) -> None:
    """Anti-pollution: wrapper should skip memory-core repo even if .memory exists."""
    codex_home = tmp_path / ".codex"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    (nested / "codex_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    # Create .memory directory - should still skip
    (memory_repo / "memory" / "system").mkdir(parents=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    # M3: wrapper execs gateway with READONLY=1 - pre-existing memory/system should be preserved
    assert (memory_repo / "memory" / "system").exists()
    assert not (memory_repo / "memory" / "artifacts").exists()


def test_wrapper_detects_memory_core_by_codex_global_hooks(monkeypatch, tmp_path: Path) -> None:
    """Anti-pollution: wrapper should detect memory-core by codex_global_hooks.py."""
    codex_home = tmp_path / ".codex"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    # Only codex_global_hooks.py marker
    (nested / "codex_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    # M3: wrapper execs gateway with READONLY=1
    assert not (memory_repo / "memory" / "system").exists()


def test_wrapper_detects_memory_core_by_factory_global_hooks(monkeypatch, tmp_path: Path) -> None:
    """Anti-pollution: wrapper should detect memory-core by factory_global_hooks.py."""
    codex_home = tmp_path / ".codex"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    # Only factory_global_hooks.py marker
    (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "global-state")
    wrapper = codex_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "codex", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    # M3: wrapper execs gateway with READONLY=1
    assert not (memory_repo / "memory" / "system").exists()


def test_install_codex_hooks_fails_without_installed_gateway(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    result = install_codex_hooks(codex_home=tmp_path / ".codex", dry_run=True)

    assert result["success"] is False
    assert any("gateway command not found" in warning for warning in result["warnings"])
    assert not (tmp_path / ".codex" / "hooks.json").exists()


def test_install_codex_hooks_backs_up_existing_hooks_json(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    hooks_path = codex_home / "hooks.json"
    existing_hooks = '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"keep-me"}]}]}}\n'
    hooks_path.write_text(existing_hooks, encoding="utf-8")
    _fake_memory_commands(tmp_path, monkeypatch)

    result = install_codex_hooks(codex_home=codex_home, storage_root=tmp_path / "store")

    assert result["success"] is True
    assert len(result["backups"]) == 1
    backup_path = Path(result["backups"][0])
    assert backup_path.is_file()
    assert backup_path.read_text(encoding="utf-8") == existing_hooks


def test_project_lifecycle_reuses_git_identity_after_project_path_is_deleted(tmp_path: Path) -> None:
    lifecycle_root = tmp_path / "lifecycle"
    project = tmp_path / "project-with-remote"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/deleted-project.git"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )

    active = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="codex",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-05-10T00:00:00+08:00",
    )
    active_record_path = Path(active["record_path"])
    shutil.rmtree(project)

    missing = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="codex",
        event="stop",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-05-10T00:01:00+08:00",
    )

    saved = json.loads(active_record_path.read_text(encoding="utf-8"))
    assert missing["project_id"] == active["project_id"]
    assert Path(missing["record_path"]) == active_record_path
    assert saved["status"] == "missing"
    assert saved["git_remote"] == "git@github.com:example/deleted-project.git"
    assert saved["identity_source"] == "git_remote"
    assert saved["first_observed_at"] == "2026-05-10T00:00:00+08:00"


def test_project_lifecycle_missing_path_preserves_existing_record(tmp_path: Path) -> None:
    lifecycle_root = tmp_path / "lifecycle"
    missing_path = tmp_path / "deleted-project"

    record = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=missing_path,
        host="codex",
        event="session-start",
        payload={"cwd": str(missing_path)},
        now_iso_fn=lambda: "2026-05-10T00:00:00+08:00",
    )
    record_path = Path(record["record_path"])
    sentinel = lifecycle_root / "projects" / "keep-existing-memory.txt"
    sentinel.write_text("do not delete", encoding="utf-8")

    second = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=missing_path,
        host="codex",
        event="stop",
        payload={"cwd": str(missing_path)},
        now_iso_fn=lambda: "2026-05-10T00:01:00+08:00",
    )

    saved = json.loads(record_path.read_text(encoding="utf-8"))
    assert saved["status"] == "missing"
    assert saved["retention_policy"] == "preserve-memory-on-missing-path"
    assert saved["first_observed_at"] == "2026-05-10T00:00:00+08:00"
    assert second["event"] == "stop"
    assert sentinel.read_text(encoding="utf-8") == "do not delete"
