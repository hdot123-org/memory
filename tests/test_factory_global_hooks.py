from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

from memory_core.tools.factory_global_hooks import install_factory_hooks, merge_factory_settings
from memory_core.tools.project_lifecycle import record_project_lifecycle


def test_merge_replaces_existing_memory_hooks_and_preserves_unrelated_settings(tmp_path: Path) -> None:
    wrapper = tmp_path / ".factory" / "bin" / "memory-hook"
    existing = {
        "model": "custom-model",
        "reasoningEffort": "high",
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": "custom-session-start", "timeout": 3},
                        {
                            "type": "command",
                            "command": "python3 /tmp/memory_hook_gateway.py --host factory --event session-start",
                            "timeout": 10,
                        },
                    ]
                }
            ],
            "PreToolUse": [{"matcher": "Execute", "hooks": [{"type": "command", "command": "keep-me"}]}],
        },
    }

    merged = merge_factory_settings(
        existing,
        {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": f"{wrapper} --host factory --event session-start"}]}
                ],
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": f"{wrapper} --host factory --event prompt-submit"}]}
                ],
                "Stop": [{"hooks": [{"type": "command", "command": f"{wrapper} --host factory --event stop"}]}],
                "Notification": [
                    {"hooks": [{"type": "command", "command": f"{wrapper} --host factory --event notification"}]}
                ],
            }
        },
    )

    assert merged["model"] == "custom-model"
    assert merged["reasoningEffort"] == "high"
    session_commands = [h["command"] for g in merged["hooks"]["SessionStart"] for h in g["hooks"]]
    assert "custom-session-start" in session_commands
    assert all("memory_hook_gateway.py --host factory" not in cmd for cmd in session_commands)
    assert f"{wrapper} --host factory --event session-start" in session_commands
    assert merged["hooks"]["PreToolUse"] == existing["hooks"]["PreToolUse"]


def _fake_memory_commands(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    command_dir = tmp_path / "bin"
    command_dir.mkdir()
    gateway = command_dir / "memory-hook-gateway"
    gateway.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gateway.chmod(gateway.stat().st_mode | stat.S_IXUSR)
    init = command_dir / "memory-init"
    init.write_text(
        "#!/bin/sh\n"
        "host=\"\"\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --target) shift; target=\"$1\" ;;\n"
        "    --host) shift; host=\"$1\" ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        "mkdir -p \"$target/memory/system\"\n"
        "echo \"$host\" > \"$target/memory/system/init-host\"\n",
        encoding="utf-8",
    )
    init.chmod(init.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(command_dir))
    return gateway, init


def test_install_factory_hooks_writes_wrapper_and_settings_json(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    storage_root = tmp_path / "memory-store"
    gateway, init = _fake_memory_commands(tmp_path, monkeypatch)

    result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)

    wrapper = factory_home / "bin" / "memory-hook"
    settings_path = factory_home / "settings.json"
    assert result["success"] is True
    assert wrapper.is_file()
    assert settings_path.is_file()
    assert os.stat(wrapper).st_mode & stat.S_IXUSR
    assert result["gateway_command"] == str(gateway)
    assert result["init_command"] == str(init)

    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert f"MEMORY_HOOK_GLOBAL_STATE_ROOT={storage_root}" in wrapper_text
    assert "FACTORY_PROJECT_DIR" in wrapper_text
    assert "--host factory" in wrapper_text
    assert str(gateway) in wrapper_text
    assert str(init) in wrapper_text
    assert "exec \"$MEMORY_HOOK_GATEWAY\" \"$@\"" in wrapper_text

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert set(settings["hooks"]) == {"SessionStart", "UserPromptSubmit", "Stop", "Notification", "PreToolUse", "PostToolUse", "SubagentStop", "PreCompact", "SessionEnd"}
    commands = [
        hook["command"]
        for event_groups in settings["hooks"].values()
        for group in event_groups
        for hook in group["hooks"]
    ]
    assert len(commands) == 9
    assert all(str(wrapper) in command for command in commands)
    assert all("--host factory" in command for command in commands)

    # Verify PreToolUse hook exists with correct event
    pretooluse_hooks = settings["hooks"].get("PreToolUse", [])
    assert len(pretooluse_hooks) >= 1
    pretooluse_commands = [
        h["command"]
        for g in pretooluse_hooks
        for h in g.get("hooks", [])
    ]
    assert any("--event pre-tool-use" in cmd for cmd in pretooluse_commands)


def test_wrapper_skips_exact_home_project_root_but_allows_child(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    fake_home = tmp_path / "home"
    child_project = fake_home / "tool"
    child_project.mkdir(parents=True)
    _fake_memory_commands(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(fake_home))

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    home_proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
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
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=child_project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert child_proc.returncode == 0
    assert (child_project / "memory" / "system").is_dir()
    assert not (fake_home / "memory" / "system").exists()


def test_wrapper_initializes_project_memory_with_factory_host(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    project = tmp_path / "project"
    project.mkdir()
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert (project / "memory" / "system").is_dir()
    assert (project / "memory" / "system").is_dir()
    assert (project / "memory" / "system" / "init-host").read_text(encoding="utf-8").strip() == "factory"


def test_wrapper_uses_factory_project_dir(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    project = tmp_path / "project"
    unrelated = tmp_path / "unrelated"
    project.mkdir()
    unrelated.mkdir()
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=unrelated,
        env={**os.environ, "FACTORY_PROJECT_DIR": str(project)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert (project / "memory" / "system").is_dir()
    assert not (unrelated / "memory" / "system").exists()


def test_wrapper_initializes_git_project_root_from_subdirectory(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    project = tmp_path / "project"
    nested = project / "src" / "feature"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=nested,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert (project / "memory" / "system").is_dir()
    assert not (nested / "memory" / "system").exists()


def test_wrapper_skips_auto_init_for_memory_core_source_repo(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
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
    factory_home = tmp_path / ".factory"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    # Create .memory directory - should still skip
    (memory_repo / "memory" / "system").mkdir(parents=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    # Should not create memory/ or artifacts/ - pre-existing memory/system should be preserved
    assert (memory_repo / "memory" / "system").exists()
    assert not (memory_repo / "memory" / "artifacts").exists()


def test_wrapper_detects_memory_core_by_factory_global_hooks(monkeypatch, tmp_path: Path) -> None:
    """Anti-pollution: wrapper should detect memory-core by factory_global_hooks.py."""
    factory_home = tmp_path / ".factory"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    # Only factory_global_hooks.py marker
    (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert not (memory_repo / "memory" / "system").exists()


def test_wrapper_detects_memory_core_by_ownership_marker(monkeypatch, tmp_path: Path) -> None:
    """Anti-pollution: wrapper should detect memory-core by ownership.py."""
    factory_home = tmp_path / ".factory"
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core"
    nested.mkdir(parents=True)
    # Only ownership.py marker
    (nested / "ownership.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    _fake_memory_commands(tmp_path, monkeypatch)

    install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "global-state")
    wrapper = factory_home / "bin" / "memory-hook"

    proc = subprocess.run(
        [str(wrapper), "--host", "factory", "--event", "session-start"],
        cwd=memory_repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert not (memory_repo / "memory" / "system").exists()


def test_install_factory_hooks_fails_without_installed_gateway(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    result = install_factory_hooks(factory_home=tmp_path / ".factory", dry_run=True)

    assert result["success"] is False
    assert any("gateway command not found" in warning for warning in result["warnings"])
    assert not (tmp_path / ".factory" / "settings.json").exists()


def test_install_factory_hooks_backs_up_existing_settings_json(monkeypatch, tmp_path: Path) -> None:
    factory_home = tmp_path / ".factory"
    factory_home.mkdir()
    settings_path = factory_home / "settings.json"
    existing_settings = '{"model":"keep","hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"keep-me"}]}]}}\n'
    settings_path.write_text(existing_settings, encoding="utf-8")
    _fake_memory_commands(tmp_path, monkeypatch)

    result = install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "store")

    assert result["success"] is True
    assert len(result["backups"]) == 1
    backup_path = Path(result["backups"][0])
    assert backup_path.is_file()
    assert backup_path.read_text(encoding="utf-8") == existing_settings
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["model"] == "keep"


def test_project_lifecycle_reuses_git_identity_for_factory_after_project_path_is_deleted(tmp_path: Path) -> None:
    lifecycle_root = tmp_path / "lifecycle"
    project = tmp_path / "factory-project-with-remote"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/factory-project.git"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )

    active = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-05-12T00:00:00+08:00",
    )
    active_record_path = Path(active["record_path"])
    shutil.rmtree(project)

    missing = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="stop",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-05-12T00:01:00+08:00",
    )

    saved = json.loads(active_record_path.read_text(encoding="utf-8"))
    assert missing["project_id"] == active["project_id"]
    assert Path(missing["record_path"]) == active_record_path
    assert saved["status"] == "missing"
    assert saved["host"] == "factory"
    assert saved["git_remote"] == "git@github.com:example/factory-project.git"


def test_pretooluse_hook_registered_in_settings_json(monkeypatch, tmp_path: Path) -> None:
    """Verify PreToolUse hook appears in install output (5a.7)."""
    factory_home = tmp_path / ".factory"
    storage_root = tmp_path / "memory-store"
    _fake_memory_commands(tmp_path, monkeypatch)

    result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)

    assert result["success"] is True
    settings_path = factory_home / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    # Verify PreToolUse hook exists
    assert "PreToolUse" in settings["hooks"]
    pretooluse_hooks = settings["hooks"]["PreToolUse"]
    assert len(pretooluse_hooks) >= 1

    # Verify the command uses pre-tool-use event
    commands = [
        h["command"]
        for g in pretooluse_hooks
        for h in g.get("hooks", [])
    ]
    assert any("--event pre-tool-use" in cmd for cmd in commands)


def test_pretooluse_existing_user_hooks_preserved(monkeypatch, tmp_path: Path) -> None:
    """Verify existing PreToolUse user hooks are preserved (5a.7)."""
    factory_home = tmp_path / ".factory"
    factory_home.mkdir()
    settings_path = factory_home / "settings.json"

    # Create existing settings with user PreToolUse hooks
    existing_settings = {
        "model": "custom-model",
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Execute",
                    "hooks": [{"type": "command", "command": "user-custom-guard"}],
                }
            ],
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "old-session-hook"}]}
            ],
        },
    }
    settings_path.write_text(json.dumps(existing_settings), encoding="utf-8")
    _fake_memory_commands(tmp_path, monkeypatch)

    result = install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "store")

    assert result["success"] is True
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    # User PreToolUse hooks should be preserved
    assert "PreToolUse" in settings["hooks"]
    pretooluse_hooks = settings["hooks"]["PreToolUse"]
    user_hooks = [h for g in pretooluse_hooks for h in g.get("hooks", []) if "user-custom-guard" in str(h.get("command", ""))]
    assert len(user_hooks) >= 1

    # Memory hooks should also be present
    memory_hooks = [
        h
        for g in pretooluse_hooks
        for h in g.get("hooks", [])
        if "memory-hook" in str(h.get("command", ""))
    ]
    assert len(memory_hooks) >= 1
