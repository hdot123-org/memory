"""Hooks.json and AGENTS.md generation for memory initialization."""

import json
import logging
from pathlib import Path
from typing import Any

from ._init_config import (
    _LEGACY_HOST_PATTERNS,
    CLAUDE_HOOK_EVENTS,
    MEMORY_HOOK_BEGIN_MARKER,
    MEMORY_HOOK_END_MARKER,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hooks / AGENTS.md helpers
# ---------------------------------------------------------------------------


# Markers for identifying old bare gateway commands that should be replaced
def _is_old_bare_gateway_command(command: str) -> bool:
    """Check if a command is an old bare memory-hook-gateway command (not using wrapper)."""
    if "memory-hook-gateway" not in command:
        return False
    # If it uses the wrapper (memory-hook), it's not a bare gateway command
    if "memory-hook --host" in command:
        return False
    # If it's a bare gateway command (direct python path or bare gateway)
    return "memory_hook_gateway.py" in command or command.strip().startswith("memory-hook-gateway")


def template_hooks_json(host: str = "claude") -> dict[str, Any]:
    """Generate hooks.json content as a dict using the protected wrapper.

    Uses ~/.claude/bin/memory-hook wrapper instead of bare gateway command
    to ensure proper project lifecycle management and anti-pollution guards.
    """
    hooks: list[dict[str, Any]] = []
    for claude_event, gateway_event in CLAUDE_HOOK_EVENTS:
        hooks.append(
            {
                "event": claude_event,
                "command": f"~/.claude/bin/memory-hook --host {host} --event {gateway_event}",
                "stdin": True,
            }
        )
    return {"hooks": hooks}


def generate_hooks_json(
    target: Path,
    *,
    host: str = "claude",
    result: dict[str, Any] | None = None,
) -> None:
    """Create or update .claude/hooks.json in the target project.

    Uses the protected wrapper-based approach. Replaces old bare gateway
    entries while preserving non-memory hooks.
    """
    hooks_dir = target / ".claude"
    hooks_path = hooks_dir / "hooks.json"

    if result is None:
        return

    desired = template_hooks_json(host)

    if hooks_path.exists():
        try:
            existing = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
            result["warnings"].append("hooks.json corrupt or non-standard, treated as empty")

        existing_hooks: list[dict[str, Any]] = existing.get("hooks", [])
        if not isinstance(existing_hooks, list):
            result["warnings"].append("hooks.json corrupt or non-standard, treated as empty")
            existing_hooks = []

        # Filter out old bare gateway commands and existing memory hooks
        filtered_hooks: list[dict[str, Any]] = []
        for h in existing_hooks:
            if not isinstance(h, dict):
                filtered_hooks.append(h)
                continue
            cmd = h.get("command", "")
            # Skip old bare gateway commands and existing wrapper commands
            if _is_old_bare_gateway_command(cmd) or "--host claude --event" in cmd:
                continue
            filtered_hooks.append(h)

        # Add desired wrapper-based hooks
        existing_keys = {(h["event"], h["command"]) for h in filtered_hooks}
        for hook in desired["hooks"]:
            if (hook["event"], hook["command"]) not in existing_keys:
                filtered_hooks.append(hook)

        existing["hooks"] = filtered_hooks
        content = json.dumps(existing, indent=2, ensure_ascii=False) + "\n"
    else:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(desired, indent=2, ensure_ascii=False) + "\n"

    hooks_path.write_text(content, encoding="utf-8")
    result["created"].append("file:.claude/hooks.json")


def template_agents_md_block() -> str:
    """Generate the AGENTS.md memory hook instruction block.

    Host-neutral: references only the factory wrapper (the sole supported host).
    No project-level hooks.json references (host hooks are global-only).
    """
    return f"""{MEMORY_HOOK_BEGIN_MARKER}
## Memory Hook

This project uses the memory-core protected wrapper for hooks.
The wrapper is installed at `~/.factory/bin/memory-hook` and handles:
- Project lifecycle tracking
- HOME directory anti-pollution guards
- Source repository detection (skips memory-core itself)
- Git root normalization

Project memory rules are stored under `memory/` and loaded regardless of host.
Do NOT use bare `memory-hook-gateway` commands directly.

For manual testing:
```bash
~/.factory/bin/memory-hook --host factory --event session-start
```

## 路由规则

路由规则仅由以下文件定义，AGENTS.md 只做方向性引用，不嵌入任何路由逻辑。

**读取链**：Agent 启动 → AGENTS.md (行为约束) → 三层架构路由 → Layer 3 项目层优先 → Layer 2 全局 fallback

| 层 | 职责 | 路径 |
|----|------|------|
| 全局知识库 (Layer 2) | 跨项目通用知识、全局 fallback | `~/.memory/global-kb/` |
| 项目知识库 (Layer 3) | 项目专属知识 | `<project>/memory/kb/` |

具体路由规则（如 scope resolution、fallback）请查阅上述路径下的 INDEX.md。

## 执行前置规则

**任何涉及知识库的读取或写入操作前，必须先读取本文件确认术语到路径的映射。不可凭记忆或上下文推断路径。**

| 操作场景 | 前置要求 |
|----------|---------|
| 写入 `memory/kb/`、`docs/`、`~/.memory/global-kb/` | 先查路由表确认目标层和正确路径 |
| 读取项目知识库 | 先确认 Layer 3 → Layer 2 fallback 顺序 |
| 用户说"记下来"/"写文档"/"记录决策" | 先读项目 AGENTS.md 确认分类规则，再执行写入 |
{MEMORY_HOOK_END_MARKER}
"""


def _cleanup_legacy_hooks_json(target: Path, result: dict[str, Any] | None) -> None:
    """Delete legacy .codex/hooks.json and .claude/hooks.json files (VAL-P4-011).

    These legacy host directories are superseded by factory (the sole supported
    host; see SUPPORTED_HOSTS), which uses ~/.factory/bin/memory-hook instead.

    This is a no-op in adopt mode (preserves existing files) and runs in
    create/update/repair modes.
    """
    if result is None:
        return
    legacy_paths = [target / ".codex" / "hooks.json", target / ".claude" / "hooks.json"]
    for legacy_path in legacy_paths:
        if legacy_path.exists():
            try:
                legacy_path.unlink()
                result["created"].append(f"removed legacy file:{legacy_path.relative_to(target)}")
            except Exception as exc:
                result["warnings"].append(f"failed to remove legacy hooks.json {legacy_path}: {exc}")


# Legacy host reference patterns to scrub from AGENTS.md (VAL-P4-010)
# (_LEGACY_HOST_PATTERNS imported from ._init_config)


def _scrub_legacy_refs(text: str) -> tuple[str, bool]:
    """Remove legacy codex/claude hook references from AGENTS.md.

    These legacy hosts are superseded by factory (the sole supported host).
    Returns (scrubbed_text, was_modified).
    """
    modified = False
    for pattern in _LEGACY_HOST_PATTERNS:
        if pattern in text:
            text = text.replace(pattern, "")
            modified = True
    # Clean up any resulting double-blank lines from removals
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text, modified


def _update_existing_agents_md(
    agents_path: Path,
    content: str,
    new_block: str,
    result: dict[str, Any],
    mode: str,
) -> bool:
    """Update AGENTS.md file that already has markers.

    Returns True if update was performed, False if skipped.
    """
    begin_idx = content.index(MEMORY_HOOK_BEGIN_MARKER)
    end_idx = content.index(MEMORY_HOOK_END_MARKER) + len(MEMORY_HOOK_END_MARKER)
    before = content[:begin_idx].rstrip("\n")
    after = content[end_idx:].lstrip("\n")

    # VAL-P4-010: Scrub legacy host references
    before, before_modified = _scrub_legacy_refs(before)
    after, after_modified = _scrub_legacy_refs(after)

    # Strip trailing/leading newlines appropriately
    if before:
        before += "\n"
    if after:
        after = "\n" + after

    new_content = before + new_block + after

    if new_content == content and not before_modified and not after_modified:
        result["skipped"].append("file:AGENTS.md (hook block up-to-date)")
        return False

    # Mode check: adopt/update/repair should not modify markers in adopt mode
    if mode == "adopt":
        result["skipped"].append("file:AGENTS.md (existing marker preserved in adopt mode)")
        return False

    agents_path.write_text(new_content, encoding="utf-8")
    result["created"].append("file:AGENTS.md (hook block updated)")
    return True


def _handle_no_markers_agents_md(
    agents_path: Path,
    content: str,
    new_block: str,
    result: dict[str, Any],
    mode: str,
) -> None:
    """Handle AGENTS.md file that exists but has no markers."""
    if mode == "adopt":
        # adopt mode: do not append to files without markers (safe default)
        result["skipped"].append(f"file:AGENTS.md (no marker in {mode} mode, not appending)")
        return

    if mode == "update":
        # update mode: scrub legacy refs only, do not create full block
        scrubbed, was_modified = _scrub_legacy_refs(content)
        if was_modified:
            agents_path.write_text(scrubbed, encoding="utf-8")
            result["created"].append("file:AGENTS.md (legacy host references scrubbed)")
        else:
            result["skipped"].append("file:AGENTS.md (no legacy references found)")
        return

    if mode == "create":
        # create mode: append to existing content
        new_content = content.rstrip("\n") + "\n\n" + new_block
        agents_path.write_text(new_content, encoding="utf-8")
        result["created"].append("file:AGENTS.md (hook block appended)")
        return

    # repair mode: do not append to files without markers
    result["skipped"].append(f"file:AGENTS.md (no marker in {mode} mode, not appending)")


def update_agents_md(
    target: Path,
    *,
    host: str = "factory",
    result: dict[str, Any] | None = None,
    mode: str = "create",
) -> None:
    """Insert or update the Memory Hook instruction block in AGENTS.md.

    Idempotent: if the markers already exist, the block content is replaced
    in-place rather than appended.

    Mode-aware:
    - create: Create new AGENTS.md or append block if no markers
    - adopt: Only add block if markers don't exist, never overwrite; skip files without markers
    - update: Replace existing marked block only; also creates AGENTS.md when absent
    - repair: Create AGENTS.md when absent; update existing markers when present (never overwrite entire file)

    Legacy scrubbing (VAL-P4-010): In update mode, removes any references to
    ~/.codex/bin/memory-hook or ~/.claude/bin/memory-hook from the AGENTS.md
    content (both inside and outside the hook block). These legacy hosts are
    superseded by factory (the sole supported host; see SUPPORTED_HOSTS), which
    uses ~/.factory/bin/memory-hook.
    """
    if result is None:
        return

    agents_path = target / "AGENTS.md"
    new_block = template_agents_md_block()

    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        has_begin = MEMORY_HOOK_BEGIN_MARKER in content
        has_end = MEMORY_HOOK_END_MARKER in content

        if has_begin and has_end:
            _update_existing_agents_md(agents_path, content, new_block, result, mode)
        else:
            _handle_no_markers_agents_md(agents_path, content, new_block, result, mode)
        return

    # File doesn't exist
    if mode == "adopt":
        # adopt mode: don't create new AGENTS.md
        result["skipped"].append(f"file:AGENTS.md (not created in {mode} mode)")
        return

    # create/update/repair mode: create AGENTS.md when absent
    agents_path.write_text(new_block, encoding="utf-8")
    result["created"].append("file:AGENTS.md")


# ---------------------------------------------------------------------------
# Initialization logic
# ---------------------------------------------------------------------------
