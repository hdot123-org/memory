from __future__ import annotations

import json
import os
import stat
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


def test_install_codex_hooks_writes_wrapper_and_hooks_json(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    storage_root = tmp_path / "memory-store"

    result = install_codex_hooks(codex_home=codex_home, storage_root=storage_root)

    wrapper = codex_home / "bin" / "memory-hook"
    hooks_path = codex_home / "hooks.json"
    assert result["success"] is True
    assert wrapper.is_file()
    assert hooks_path.is_file()
    assert os.stat(wrapper).st_mode & stat.S_IXUSR

    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert f"MEMORY_HOOK_STORAGE_ROOT={storage_root}" in wrapper_text
    assert "memory_core/tools/memory_hook_gateway.py" not in wrapper_text
    assert "exec \"$MEMORY_HOOK_GATEWAY\" \"$@\"" in wrapper_text
    assert "MEMORY_HOOK_ORIGINAL_CWD" in wrapper_text
    assert "MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE" in wrapper_text

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for event_groups in hooks["hooks"].values()
        for group in event_groups
        for hook in group["hooks"]
    ]
    assert len(commands) == 3
    assert all(str(wrapper) in command for command in commands)


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
