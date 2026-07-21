#!/usr/bin/env python3
"""Tool classification logic extracted from pretooluse_guard.py.

Contains the classify_tool_use function which handles the 6-tool
if-elif chain for Write, Edit, MultiEdit, NotebookEdit, Execute, Task.

Part of REF-001 strangler fig scaffold phase.
"""

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
from .doc_router import is_registered_doc_dir


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


def _extract_mv_path(match: re.Match[str]) -> list[str]:
    """Extract path from mv/git mv command."""
    args = _split_shell_args(match.group(1))
    return [args[-1]] if len(args) >= 2 else []


def _extract_rm_path(match: re.Match[str]) -> list[str]:
    """Extract paths from rm command (non-flag args)."""
    args = _split_shell_args(match.group(1))
    return [arg for arg in args if not arg.startswith("-")]


def _extract_cp_path(match: re.Match[str]) -> list[str]:
    """Extract destination path from cp command."""
    args = _split_shell_args(match.group(1))
    return [args[-1]] if len(args) >= 2 else []


def _extract_rsync_path(match: re.Match[str]) -> list[str]:
    """Extract destination path from rsync command."""
    args = _split_shell_args(match.group(1))
    return [args[-1]] if len(args) >= 2 else []


def _extract_mkdir_path(match: re.Match[str]) -> list[str]:
    """Extract paths from mkdir command (non-flag args)."""
    args = _split_shell_args(match.group(1))
    return [arg for arg in args if not arg.startswith("-")]


def _extract_touch_path(match: re.Match[str]) -> list[str]:
    """Extract paths from touch command (non-flag args)."""
    args = _split_shell_args(match.group(1))
    return [arg for arg in args if not arg.startswith("-")]


def _extract_python_path(match: re.Match[str]) -> list[str]:
    """Extract paths from python -c command."""
    code = match.group(1)
    paths: list[str] = []
    paths.extend(RE_PYTHON_OPEN.findall(code))
    paths.extend(RE_PYTHON_PATH.findall(code))
    return paths


def _extract_node_path(match: re.Match[str]) -> list[str]:
    """Extract paths from node -e command."""
    code = match.group(1)
    paths: list[str] = []
    paths.extend(RE_NODE_FS_WRITE.findall(code))
    paths.extend(RE_NODE_REQUIRE_FS.findall(code))
    return paths


def _extract_redirect_path(match: re.Match[str]) -> list[str]:
    """Extract path from shell redirect."""
    return [match.group(1)]


def _extract_tee_path(match: re.Match[str]) -> list[str]:
    """Extract paths from tee command (non-flag args)."""
    args = _split_shell_args(match.group(1))
    return [arg for arg in args if not arg.startswith("-")]


def _extract_heredoc_path(match: re.Match[str]) -> list[str]:
    """Extract target path from heredoc."""
    target = match.group(1).strip()
    return [target] if target else []


def _extract_dd_path(match: re.Match[str]) -> list[str]:
    """Extract path from dd command."""
    return [match.group(1)]


def _extract_install_path(match: re.Match[str]) -> list[str]:
    """Extract destination path from install command."""
    args = _split_shell_args(match.group(1))
    return [args[-1]] if len(args) >= 2 else []


def _extract_ln_path(match: re.Match[str]) -> list[str]:
    """Extract destination path from ln command."""
    args = _split_shell_args(match.group(1))
    return [args[-1]] if len(args) >= 2 else []


def _extract_path_from_execute(command: str) -> list[str]:
    """Extract target paths from Execute command.

    Dispatch table: 14 command patterns → path extraction handlers.
    """
    command = command.strip()
    if not command:
        return []

    # Dispatch table: (regex, handler)
    # Note: RE_REDIRECT uses search(), others use match()
    _DISPATCH = [
        (RE_MV, _extract_mv_path, False),
        (RE_RM, _extract_rm_path, False),
        (RE_CP, _extract_cp_path, False),
        (RE_RSYNC, _extract_rsync_path, False),
        (RE_MKDIR, _extract_mkdir_path, False),
        (RE_TOUCH, _extract_touch_path, False),
        (RE_PYTHON_C, _extract_python_path, False),
        (RE_NODE_E, _extract_node_path, False),
        (RE_REDIRECT, _extract_redirect_path, True),  # uses search()
        (RE_TEE, _extract_tee_path, False),
        (RE_HEREDOC, _extract_heredoc_path, False),
        (RE_DD, _extract_dd_path, False),
        (RE_INSTALL, _extract_install_path, False),
        (RE_LN, _extract_ln_path, False),
    ]

    for regex, handler, use_search in _DISPATCH:
        match = regex.search(command) if use_search else regex.match(command)
        if match:
            return handler(match)

    return []


def _check_doc_routing(file_path: str) -> dict[str, str] | None:
    """检查文件路径是否在注册的文档目录中。

    当路径匹配 memory/docs/ 或 memory/kb/ 前缀时，校验是否在注册目录。
    返回 block 结果 dict 表示被拦截，返回 None 表示放行。
    """
    p = Path(file_path)

    # 检查是否是 memory/docs/ 或 memory/kb/ 下的路径
    is_doc_path = False
    for i, part in enumerate(p.parts):
        if part in ("docs", "kb") and i > 0 and p.parts[i - 1] == "memory":
            is_doc_path = True
            break

    if not is_doc_path:
        return None

    # 校验是否在注册目录
    if not is_registered_doc_dir(p):
        return {
            "decision": "block",
            "reason": f"文档路径未注册：{file_path}（必须使用 DOC_CATEGORIES 或 EXCEPTION_DIRS 中的目录）",
        }

    return None


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


def _classify_agents_md(
    file_path: str,
    content_before: str | None,
    content_after: str | None,
    project_root: Path,
) -> dict[str, Any]:
    """Classify AGENTS.md modification (shared by Write/Edit and MultiEdit items).

    Returns dict with keys: path, decision, reason, scenario.
    """
    full_path = project_root / file_path
    file_exists = full_path.exists()

    if file_exists and content_before is None:
        return {
            "path": file_path,
            "decision": "block",
            "reason": "Cannot determine modification scope - full overwrite uncertain (AGENTS.md exists)",
            "scenario": 4,
        }

    agents_result = classify_agents_md_block(file_path, content_before, content_after)
    return {
        "path": file_path,
        "decision": agents_result["decision"],
        "reason": agents_result["reason"],
        "scenario": agents_result.get("scenario"),
    }


def _classify_write_edit(
    payload: dict[str, Any], project_root: Path, ownership: Any
) -> RuleResult:
    """Handle Write and Edit tool classification."""
    tool_name = payload.get("tool_name", "")
    file_path = payload.get("file_path")

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

        agents_result = _classify_agents_md(file_path, content_before, content_after, project_root)
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

    # 文档路由校验（memory/docs/ 或 memory/kb/ 下必须使用注册目录）
    dr_block = _check_doc_routing(file_path)
    if dr_block is not None:
        decision = dr_block["decision"]
        return RuleResult(
            matched=(decision == "block"),
            severity="error" if decision == "block" else "info",
            message=dr_block["reason"],
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


def _classify_multiedit(
    payload: dict[str, Any], project_root: Path, ownership: Any
) -> RuleResult:
    """Handle MultiEdit tool classification."""
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

            agents_result = _classify_agents_md(path, content_before, content_after, project_root)
            item_results.append(agents_result)
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

        # 文档路由校验（memory/docs/ 或 memory/kb/ 下必须使用注册目录）
        dr_block = _check_doc_routing(path)
        if dr_block is not None:
            item_results.append({
                "path": path,
                "decision": "block",
                "reason": dr_block["reason"],
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


def _classify_notebook(
    payload: dict[str, Any], project_root: Path, ownership: Any
) -> RuleResult:
    """Handle NotebookEdit tool classification."""
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


def _classify_execute(
    payload: dict[str, Any], project_root: Path, ownership: Any
) -> RuleResult:
    """Handle Execute tool classification."""
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


def _classify_task(
    payload: dict[str, Any], project_root: Path, ownership: Any
) -> RuleResult:
    """Handle Task tool classification."""
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


def _classify_unknown(
    payload: dict[str, Any], project_root: Path, ownership: Any
) -> RuleResult:
    """Handle unknown tool - allow."""
    tool_name = payload.get("tool_name", "")
    return RuleResult(
        matched=False,
        severity="info",
        message=f"Unknown tool: {tool_name}",
        detail={"decision": "allow"}
    )


def classify_tool_use(payload: dict[str, Any], project_root: Path) -> RuleResult:
    """Classify a tool use and return RuleResult.

    Dispatch table: normalize payload → load ownership → dispatch to handler.
    """
    # Normalize payload: Factory hooks wrap tool params in tool_input, standalone tests don't
    if "tool_input" in payload:
        tool_input = payload.get("tool_input", {})
        for k, v in tool_input.items():
            payload.setdefault(k, v)

    tool_name = payload.get("tool_name", "")
    if not tool_name:
        return RuleResult(
            matched=False,
            severity="info",
            message="No tool_name specified",
            detail={"decision": "allow"}
        )

    ownership = load_memory_ownership(project_root)

    _DISPATCH: dict[str, Any] = {
        "Write": _classify_write_edit,
        "Edit": _classify_write_edit,
        "MultiEdit": _classify_multiedit,
        "NotebookEdit": _classify_notebook,
        "Execute": _classify_execute,
        "Task": _classify_task,
    }
    handler = _DISPATCH.get(tool_name, _classify_unknown)
    return handler(payload, project_root, ownership)  # type: ignore[no-any-return]


# Add rule_name property to the function (REF-001 RuleEvaluator Protocol integration)
classify_tool_use.rule_name = "classify_tool_use"  # type: ignore[attr-defined]
