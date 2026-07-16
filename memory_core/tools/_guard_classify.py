#!/usr/bin/env python3
"""Tool classification logic extracted from pretooluse_guard.py.

Contains the classify_tool_use function which handles the 6-tool
if-elif chain for Write, Edit, MultiEdit, NotebookEdit, Execute, Task.

Part of REF-001 strangler fig scaffold phase.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from memory_core.ownership import (
    classify_agents_md_block,
    classify_owned_path,
    load_memory_ownership,
)

from ._guard_patterns import (
    FORBIDDEN_DIRS,
    FORBIDDEN_SUFFIXES,
    RE_CP,
    RE_DD,
    RE_HEREDOC,
    RE_INSTALL,
    RE_LN,
    RE_MKDIR,
    RE_MV,
    RE_NODE_E,
    RE_NODE_FS_WRITE,
    RE_NODE_REQUIRE_FS,
    RE_PYTHON_C,
    RE_PYTHON_OPEN,
    RE_PYTHON_PATH,
    RE_REDIRECT,
    RE_RM,
    RE_RSYNC,
    RE_TEE,
    RE_TOUCH,
    UNCERTAIN_PATH_PATTERNS,
)
from ._rule_types import RuleResult


def _check_file_type_block(file_path: str) -> dict[str, str] | None:
    """检查文件路径是否命中文件类型黑名单。

    返回 block 结果 dict 表示被拦截，返回 None 表示放行。
    MEMORY_HOOK_FORCE=1 时跳过检查。
    """
    if os.environ.get("MEMORY_HOOK_FORCE") == "1":
        return None

    p = Path(file_path)
    name = p.name.lower()

    # 检查目录黑名单
    for part in p.parts:
        if part.lower() in FORBIDDEN_DIRS:
            return {
                "decision": "block",
                "reason": f"文件类型禁止入库：目录 {part} 被禁止",
            }

    # 检查后缀黑名单（.sql.gz 需要先匹配复合后缀）
    if name.endswith(".sql.gz"):
        return {
            "decision": "block",
            "reason": "文件类型禁止入库：.sql.gz",
        }
    for suffix in FORBIDDEN_SUFFIXES:
        if suffix == ".sql.gz":
            continue  # 已处理
        if name.endswith(suffix):
            return {
                "decision": "block",
                "reason": f"文件类型禁止入库：{suffix}",
            }

    return None


def _split_shell_args(arg_string: str) -> list[str]:
    """Split shell argument string, respecting quoted strings."""
    args: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    i = 0
    while i < len(arg_string):
        ch = arg_string[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
            else:
                current.append(ch)
        elif ch in ('"', "'"):
            in_quote = ch
        elif ch in (' ', '\t'):
            if current:
                args.append("".join(current))
                current = []
        else:
            current.append(ch)
        i += 1
    if current:
        args.append("".join(current))
    return args


def _extract_path_from_execute(command: str) -> list[str]:  # noqa: C901
    """Extract target paths from Execute command."""
    paths: list[str] = []
    command = command.strip()

    if not command:
        return paths

    # mv / git mv
    mv_match = RE_MV.match(command)
    if mv_match:
        args = _split_shell_args(mv_match.group(1))
        if len(args) >= 2:
            paths.append(args[-1])
        return paths

    # rm
    rm_match = RE_RM.match(command)
    if rm_match:
        args = _split_shell_args(rm_match.group(1))
        for arg in args:
            if not arg.startswith("-"):
                paths.append(arg)
        return paths

    # cp
    cp_match = RE_CP.match(command)
    if cp_match:
        args = _split_shell_args(cp_match.group(1))
        if len(args) >= 2:
            paths.append(args[-1])
        return paths

    # rsync
    rsync_match = RE_RSYNC.match(command)
    if rsync_match:
        args = _split_shell_args(rsync_match.group(1))
        if len(args) >= 2:
            paths.append(args[-1])
        return paths

    # mkdir
    mkdir_match = RE_MKDIR.match(command)
    if mkdir_match:
        args = _split_shell_args(mkdir_match.group(1))
        for arg in args:
            if not arg.startswith("-"):
                paths.append(arg)
        return paths

    # touch
    touch_match = RE_TOUCH.match(command)
    if touch_match:
        args = _split_shell_args(touch_match.group(1))
        for arg in args:
            if not arg.startswith("-"):
                paths.append(arg)
        return paths

    # python -c
    python_match = RE_PYTHON_C.match(command)
    if python_match:
        code = python_match.group(1)
        open_matches = RE_PYTHON_OPEN.findall(code)
        paths.extend(open_matches)
        path_write_matches = RE_PYTHON_PATH.findall(code)
        paths.extend(path_write_matches)
        return paths

    # node -e
    node_match = RE_NODE_E.match(command)
    if node_match:
        code = node_match.group(1)
        fs_write_matches = RE_NODE_FS_WRITE.findall(code)
        paths.extend(fs_write_matches)
        req_matches = RE_NODE_REQUIRE_FS.findall(code)
        paths.extend(req_matches)
        return paths

    # shell redirect
    redirect_match = RE_REDIRECT.search(command)
    if redirect_match:
        paths.append(redirect_match.group(1))
        return paths

    # tee
    tee_match = RE_TEE.match(command)
    if tee_match:
        args = _split_shell_args(tee_match.group(1))
        for arg in args:
            if not arg.startswith("-"):
                paths.append(arg)
        return paths

    # heredoc
    heredoc_match = RE_HEREDOC.match(command)
    if heredoc_match:
        target = heredoc_match.group(1).strip()
        if target:
            paths.append(target)
        return paths

    # dd
    dd_match = RE_DD.match(command)
    if dd_match:
        paths.append(dd_match.group(1))
        return paths

    # install
    install_match = RE_INSTALL.match(command)
    if install_match:
        args = _split_shell_args(install_match.group(1))
        if len(args) >= 2:
            paths.append(args[-1])
        return paths

    # ln
    ln_match = RE_LN.match(command)
    if ln_match:
        args = _split_shell_args(ln_match.group(1))
        if len(args) >= 2:
            paths.append(args[-1])
        return paths

    return paths


def _contains_owned_root_string(command: str) -> bool:
    """Check if command contains strings that might target owned paths."""
    owned_indicators = [
        "memory/",
        "memory/system/",
        "memory\\",
        "AGENTS.md",
    ]
    cmd_lower = command.lower()
    return any(indicator in cmd_lower for indicator in owned_indicators)


def _is_uncertain_path(path: str) -> bool:
    """Check if path is uncertain (contains wildcards, variables, etc.)."""
    return any(re.search(p, path) for p in UNCERTAIN_PATH_PATTERNS)


def _expand_env_vars(path: str) -> str:
    """Expand common environment variables in path strings."""
    env_map = {
        "$HOME": os.environ.get("HOME", ""),
        "$PWD": "",
        "$PROJECT_DIR": os.environ.get("FACTORY_PROJECT_DIR", ""),
        "~": os.environ.get("HOME", ""),
    }
    result = path
    for var, value in env_map.items():
        if var in result:
            result = result.replace(var, value)
    return result


def _parse_multiedit_paths(payload: dict[str, Any]) -> list[str]:
    """Extract file paths from MultiEdit payload."""
    paths: list[str] = []
    edits = payload.get("edits", [])
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                file_path = edit.get("file_path")
                if file_path:
                    paths.append(file_path)
    return paths


def _parse_task_paths(payload: dict[str, Any]) -> list[str]:
    """Extract potential owned path references from Task payload."""
    paths: list[str] = []
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str):
        return paths

    patterns = [
        r"memory/[\w\-/]+",
        r"AGENTS\.md",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, prompt)
        paths.extend(matches)

    return paths


def _build_ownership_policy_block(project_root: Path) -> str:
    """Build ownership policy block for Task tool injection."""
    ownership = load_memory_ownership(project_root)

    lines: list[str] = [
        "<!-- ownership-policy-injection -->",
        "## Ownership Protection Policy (auto-injected)",
        "",
        "The following domains and resources are protected by ownership policy.",
        "Do NOT modify, move, rename, delete, or overwrite any of these.",
        "",
        "### Protected Domains",
    ]
    for domain in ownership.domains:
        lines.append(f"- `{domain.path}/` ({domain.level.name}) — {domain.description}")
    lines.append("")
    lines.append("### Protected Resources")
    for resource in ownership.resources:
        lines.append(f"- `{resource.path}` ({resource.level.name}) — {resource.description}")
    lines.append("")
    lines.append("### Forbidden Instructions")
    lines.append("- Do not modify, move, rename, delete, or overwrite any protected domain or resource.")
    lines.append("- Do not attempt to weaken ownership protection (e.g., editing ownership.toml).")
    lines.append("- Do not bypass this policy via shell commands, scripts, or indirect writes.")
    lines.append("<!-- /ownership-policy-injection -->")
    return "\n".join(lines)


def _get_project_root_for_task(project_root: Path) -> Path:
    """Get the fixed project root for Task tool handling."""
    return project_root.resolve()


def classify_tool_use(payload: dict[str, Any], project_root: Path) -> RuleResult:  # noqa: C901
    """Classify a tool use and return RuleResult.

    This is the extracted 6-tool if-elif chain from pretooluse_guard.py.
    Handles Write, Edit, MultiEdit, NotebookEdit, Execute, Task tools.

    Returns RuleResult with:
    - matched: True if decision is 'block', False if 'allow'
    - severity: 'error' if block, 'info' if allow
    - message: human-readable reason
    - detail: dict with decision, scenario, item_results, injected_prompt
    """
    # Normalize payload: Factory hooks wrap tool params in tool_input, standalone tests don't
    if "tool_input" in payload:
        tool_input = payload.get("tool_input", {})
        for k, v in tool_input.items():
            payload.setdefault(k, v)

    tool_name = payload.get("tool_name", "")
    file_path = payload.get("file_path")

    if not tool_name:
        return RuleResult(
            matched=False,
            severity="info",
            message="No tool_name specified",
            detail={"decision": "allow"}
        )

    ownership = load_memory_ownership(project_root)

    # Handle different tool types
    if tool_name in ("Write", "Edit"):
        if not file_path:
            return RuleResult(
                matched=False,
                severity="info",
                message=f"{tool_name} without file_path",
                detail={"decision": "allow"}
            )

        # Special handling for AGENTS.md (5b.4: diff-aware)
        if Path(file_path).name == "AGENTS.md":
            content_before = payload.get("content_before") or payload.get("old_str")
            content_after = payload.get("content_after") or payload.get("content") or payload.get("new_str")

            full_path = project_root / file_path
            file_exists = full_path.exists()

            if file_exists and content_before is None:
                return RuleResult(
                    matched=True,
                    severity="error",
                    message="Cannot determine modification scope - full overwrite uncertain (AGENTS.md exists)",
                    detail={
                        "decision": "block",
                        "scenario": 4,
                    }
                )

            agents_result = classify_agents_md_block(file_path, content_before, content_after)
            decision = agents_result["decision"]
            return RuleResult(
                matched=(decision == "block"),
                severity="error" if decision == "block" else "info",
                message=agents_result["reason"],
                detail={
                    "decision": decision,
                    "scenario": agents_result.get("scenario"),
                }
            )

        # 文件类型黑名单检查
        ft_block = _check_file_type_block(file_path)
        if ft_block is not None:
            decision = ft_block["decision"]
            return RuleResult(
                matched=(decision == "block"),
                severity="error" if decision == "block" else "info",
                message=ft_block["reason"],
                detail={"decision": decision}
            )

        result = classify_owned_path(file_path, ownership, project_root)
        if hasattr(result, "level"):
            return RuleResult(
                matched=True,
                severity="error",
                message=f"Protected {result.level.name} path: {result.reason}",
                detail={"decision": "block"}
            )
        return RuleResult(
            matched=False,
            severity="info",
            message=result.reason,
            detail={"decision": "allow"}
        )

    elif tool_name == "MultiEdit":
        paths = _parse_multiedit_paths(payload)
        if not paths:
            return RuleResult(
                matched=False,
                severity="info",
                message="MultiEdit with no file paths",
                detail={"decision": "allow"}
            )

        item_results: list[dict[str, Any]] = []
        has_block = False

        edits = payload.get("edits", [])
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                continue
            path = edit.get("file_path", "")
            if not path:
                continue

            # 5b.4: AGENTS.md diff-aware for MultiEdit items
            if Path(path).name == "AGENTS.md":
                content_before = edit.get("content_before") or edit.get("old_str")
                content_after = edit.get("content_after") or edit.get("new_str")

                full_path = project_root / path
                file_exists = full_path.exists()

                if file_exists and content_before is None:
                    item_results.append({
                        "path": path,
                        "decision": "block",
                        "reason": "Cannot determine modification scope - full overwrite uncertain (AGENTS.md exists)",
                        "scenario": 4,
                    })
                    has_block = True
                    continue

                agents_result = classify_agents_md_block(path, content_before, content_after)
                item_results.append({
                    "path": path,
                    "decision": agents_result["decision"],
                    "reason": agents_result["reason"],
                    "scenario": agents_result.get("scenario"),
                })
                if agents_result["decision"] == "block":
                    has_block = True
                continue

            # 文件类型黑名单检查
            ft_block = _check_file_type_block(path)
            if ft_block is not None:
                item_results.append({
                    "path": path,
                    "decision": "block",
                    "reason": ft_block["reason"],
                })
                has_block = True
                continue

            # Normal path classification
            result = classify_owned_path(path, ownership, project_root)
            if hasattr(result, "level"):
                item_results.append({
                    "path": path,
                    "decision": "block",
                    "reason": f"Protected {result.level.name} path: {result.reason}",
                })
                has_block = True
            else:
                item_results.append({
                    "path": path,
                    "decision": "allow",
                    "reason": result.reason,
                })

        if has_block:
            blocked = [r for r in item_results if r["decision"] == "block"]
            blocked_paths = [r["path"] for r in blocked]
            return RuleResult(
                matched=True,
                severity="error",
                message=f"MultiEdit blocked items: {', '.join(blocked_paths)}",
                detail={
                    "decision": "block",
                    "item_results": item_results,
                }
            )
        return RuleResult(
            matched=False,
            severity="info",
            message="No owned paths in MultiEdit",
            detail={
                "decision": "allow",
                "item_results": item_results,
            }
        )

    elif tool_name == "NotebookEdit":
        notebook_path = payload.get("notebook_path")
        if not notebook_path:
            return RuleResult(
                matched=False,
                severity="info",
                message="NotebookEdit without notebook_path",
                detail={"decision": "allow"}
            )

        result = classify_owned_path(notebook_path, ownership, project_root)
        if hasattr(result, "level"):
            return RuleResult(
                matched=True,
                severity="error",
                message=f"Protected notebook: {result.reason}",
                detail={"decision": "block"}
            )
        return RuleResult(
            matched=False,
            severity="info",
            message=result.reason,
            detail={"decision": "allow"}
        )

    elif tool_name == "Execute":
        command = payload.get("command", "")
        if not command:
            return RuleResult(
                matched=False,
                severity="info",
                message="Execute without command",
                detail={"decision": "allow"}
            )

        paths = _extract_path_from_execute(command)

        if paths:
            for path in paths:
                if _is_uncertain_path(path):
                    if _contains_owned_root_string(command):
                        return RuleResult(
                            matched=True,
                            severity="error",
                            message=f"Uncertain path '{path}' targeting owned resources",
                            detail={"decision": "block"}
                        )
                    continue

                expanded = _expand_env_vars(path)

                ft_block = _check_file_type_block(expanded)
                if ft_block is not None:
                    decision = ft_block["decision"]
                    return RuleResult(
                        matched=(decision == "block"),
                        severity="error" if decision == "block" else "info",
                        message=ft_block["reason"],
                        detail={"decision": decision}
                    )

                check_path = expanded
                if not Path(expanded).is_absolute():
                    check_path = expanded

                result = classify_owned_path(check_path, ownership, project_root)
                if hasattr(result, "level"):
                    return RuleResult(
                        matched=True,
                        severity="error",
                        message=f"Execute targets protected path '{path}': {result.reason}",
                        detail={"decision": "block"}
                    )
            return RuleResult(
                matched=False,
                severity="info",
                message="No owned paths in Execute targets",
                detail={"decision": "allow"}
            )
        else:
            if _contains_owned_root_string(command):
                return RuleResult(
                    matched=True,
                    severity="error",
                    message="Cannot parse Execute command but contains owned resource references",
                    detail={"decision": "block"}
                )
            return RuleResult(
                matched=False,
                severity="info",
                message="No owned paths detected in Execute",
                detail={"decision": "allow"}
            )

    elif tool_name == "Task":
        fixed_root = _get_project_root_for_task(project_root)

        prompt = payload.get("prompt", "")
        policy_block = _build_ownership_policy_block(fixed_root)

        if isinstance(prompt, str) and "<!-- ownership-policy-injection -->" in prompt:
            injected_prompt = prompt
        else:
            injected_prompt = f"{policy_block}\n\n{prompt}" if isinstance(prompt, str) else prompt

        paths = _parse_task_paths(payload)
        if paths:
            for path in paths:
                result = classify_owned_path(path, load_memory_ownership(fixed_root), fixed_root)
                if hasattr(result, "level"):
                    return RuleResult(
                        matched=True,
                        severity="error",
                        message=f"Task references protected path '{path}': {result.reason}",
                        detail={
                            "decision": "block",
                            "injected_prompt": injected_prompt,
                        }
                    )
            return RuleResult(
                matched=False,
                severity="info",
                message="No owned paths in Task prompt",
                detail={
                    "decision": "allow",
                    "injected_prompt": injected_prompt,
                }
            )
        return RuleResult(
            matched=False,
            severity="info",
            message="Task without owned path references",
            detail={
                "decision": "allow",
                "injected_prompt": injected_prompt,
            }
        )

    # Unknown tool - allow
    return RuleResult(
        matched=False,
        severity="info",
        message=f"Unknown tool: {tool_name}",
        detail={"decision": "allow"}
    )


# Add rule_name property to the function (REF-001 RuleEvaluator Protocol integration)
classify_tool_use.rule_name = "classify_tool_use"  # type: ignore[attr-defined]
