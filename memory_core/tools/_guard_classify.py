#!/usr/bin/env python3.12
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
    _normalize_to_project_relative,
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
        elif ch in (" ", "\t"):
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
    """Extract path from mv/git mv command.

    N3: Handle -t/--target-directory= flag (destination is the target, not last arg)
    """
    args = _split_shell_args(match.group(1))
    # Check for -t or --target-directory= flag
    for i, arg in enumerate(args):
        if arg == "-t" and i + 1 < len(args):
            return [args[i + 1]]  # destination is after -t
        if arg.startswith("--target-directory="):
            return [arg.split("=", 1)[1]]  # destination is in the flag
    # Default: last argument is destination
    return [args[-1]] if len(args) >= 2 else []


def _extract_rm_path(match: re.Match[str]) -> list[str]:
    """Extract paths from rm command (non-flag args)."""
    args = _split_shell_args(match.group(1))
    return [arg for arg in args if not arg.startswith("-")]


def _extract_cp_path(match: re.Match[str]) -> list[str]:
    """Extract path from cp command.

    N3: Handle -t/--target-directory= flag (destination is the target, not last arg)
    """
    args = _split_shell_args(match.group(1))
    # Check for -t or --target-directory= flag
    for i, arg in enumerate(args):
        if arg == "-t" and i + 1 < len(args):
            return [args[i + 1]]  # destination is after -t
        if arg.startswith("--target-directory="):
            return [arg.split("=", 1)[1]]  # destination is in the flag
    # Default: last argument is destination
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
    """Extract all redirect targets from command.

    N3: Use findall to capture all redirects (not just first)
    Returns list of all redirect targets found.
    """
    # Find all redirect operators in the command
    redirect_pattern = re.compile(r"(?<!&)[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
    targets = redirect_pattern.findall(match.string)
    return targets if targets else [match.group(1)]


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


def _check_doc_routing(file_path: str, project_root: Path | None = None) -> dict[str, str] | None:
    """检查文件路径是否在注册的文档目录中。

    当路径匹配 memory/docs/ 或 memory/kb/ 前缀时，校验是否在注册目录。
    返回 block 结果 dict 表示被拦截，返回 None 表示放行。

    绝对路径先归一化为 project-relative（复用 _normalize_to_project_relative
    单一真源），避免仓库根目录名恰好为 "memory" 等协议目录名时误判。
    """
    # 归一化：绝对路径转 project-relative，避免根目录名碰巧为协议目录名
    # （如 /Users/busiji/memory/docs/specs/x.md 中的 "memory"）导致 parts 误匹配
    normalized_path = _normalize_to_project_relative(file_path, project_root) if project_root is not None else file_path
    p = Path(normalized_path)

    # 检查是否是 memory/docs/ 或 memory/kb/ 下的路径
    # 归一化后 "docs" 或 "kb" 必须不在首位（首位是 "memory"）才视为协议路径
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


def _classify_write_edit(payload: dict[str, Any], project_root: Path, ownership: Any) -> RuleResult:
    """Handle Write and Edit tool classification."""
    tool_name = payload.get("tool_name", "")
    file_path = payload.get("file_path")

    if not file_path:
        return RuleResult(
            matched=False, severity="info", message=f"{tool_name} without file_path", detail={"decision": "allow"}
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
            },
        )

    # 文件类型黑名单检查
    ft_block = _check_file_type_block(file_path)
    if ft_block is not None:
        decision = ft_block["decision"]
        return RuleResult(
            matched=(decision == "block"),
            severity="error" if decision == "block" else "info",
            message=ft_block["reason"],
            detail={"decision": decision},
        )

    # 文档路由校验（memory/docs/ 或 memory/kb/ 下必须使用注册目录）
    dr_block = _check_doc_routing(file_path, project_root)
    if dr_block is not None:
        decision = dr_block["decision"]
        return RuleResult(
            matched=(decision == "block"),
            severity="error" if decision == "block" else "info",
            message=dr_block["reason"],
            detail={"decision": decision},
        )

    # classify_owned_path normalizes absolute paths to project-relative
    # internally via _normalize_to_project_relative (single source of truth).
    result = classify_owned_path(file_path, ownership, project_root)
    if hasattr(result, "level"):
        return RuleResult(
            matched=True,
            severity="error",
            message=f"Protected {result.level.name} path: {result.reason}",
            detail={"decision": "block"},
        )
    return RuleResult(matched=False, severity="info", message=result.reason, detail={"decision": "allow"})


def _classify_multiedit(payload: dict[str, Any], project_root: Path, ownership: Any) -> RuleResult:
    """Handle MultiEdit tool classification."""
    paths = _parse_multiedit_paths(payload)
    if not paths:
        return RuleResult(
            matched=False, severity="info", message="MultiEdit with no file paths", detail={"decision": "allow"}
        )

    item_results: list[dict[str, Any]] = []
    has_block = False

    edits = payload.get("edits", [])
    for _i, edit in enumerate(edits):
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
            item_results.append(
                {
                    "path": path,
                    "decision": "block",
                    "reason": ft_block["reason"],
                }
            )
            has_block = True
            continue

        # 文档路由校验（memory/docs/ 或 memory/kb/ 下必须使用注册目录）
        dr_block = _check_doc_routing(path, project_root)
        if dr_block is not None:
            item_results.append(
                {
                    "path": path,
                    "decision": "block",
                    "reason": dr_block["reason"],
                }
            )
            has_block = True
            continue

        # Normal path classification
        # classify_owned_path normalizes absolute paths to project-relative
        # internally via _normalize_to_project_relative (single source of truth).
        result = classify_owned_path(path, ownership, project_root)
        if hasattr(result, "level"):
            item_results.append(
                {
                    "path": path,
                    "decision": "block",
                    "reason": f"Protected {result.level.name} path: {result.reason}",
                }
            )
            has_block = True
        else:
            item_results.append(
                {
                    "path": path,
                    "decision": "allow",
                    "reason": result.reason,
                }
            )

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
            },
        )
    return RuleResult(
        matched=False,
        severity="info",
        message="No owned paths in MultiEdit",
        detail={
            "decision": "allow",
            "item_results": item_results,
        },
    )


def _classify_notebook(payload: dict[str, Any], project_root: Path, ownership: Any) -> RuleResult:
    """Handle NotebookEdit tool classification."""
    notebook_path = payload.get("notebook_path")
    if not notebook_path:
        return RuleResult(
            matched=False, severity="info", message="NotebookEdit without notebook_path", detail={"decision": "allow"}
        )

    # classify_owned_path normalizes absolute paths to project-relative
    # internally via _normalize_to_project_relative (single source of truth).
    result = classify_owned_path(notebook_path, ownership, project_root)
    if hasattr(result, "level"):
        return RuleResult(
            matched=True, severity="error", message=f"Protected notebook: {result.reason}", detail={"decision": "block"}
        )
    return RuleResult(matched=False, severity="info", message=result.reason, detail={"decision": "allow"})


def _handle_quote_state(ch: str, in_quote: str | None) -> str | None:
    """Update quote state based on current character.

    Returns the new in_quote state (None if quote closed, the quote char if opened/continuing).
    """
    if in_quote:
        # Inside a quote - check if it closes
        return None if ch == in_quote else in_quote
    elif ch in ('"', "'"):
        # Opening a quote
        return ch
    return in_quote


def _split_command_segments(command: str) -> list[str]:
    """Split command by shell operators respecting quote boundaries.

    Fix-2: Splits by &&, ||, ;, |, &, and newlines, but NOT inside quotes.
    B4: Single '&' (background operator) now also splits, while '&&' and '&>'
    are preserved (&& = two-char operator, &> = redirect not split point).
    Returns list of command segments.
    """
    segments = []
    current = []
    in_quote = None
    i = 0
    n = len(command)

    while i < n:
        ch = command[i]

        # Handle quote state
        new_in_quote = _handle_quote_state(ch, in_quote)
        if in_quote or ch in ('"', "'"):
            current.append(ch)
            if new_in_quote != in_quote:
                in_quote = new_in_quote
            i += 1
            continue

        # Check for operators
        if ch == "&" and i + 1 < n and command[i + 1] == "&":
            # && (two-char operator, NOT background)
            if current:
                segments.append("".join(current).strip())
                current = []
            i += 1  # skip second &
        elif ch == "&" and i + 1 < n and command[i + 1] == ">":
            # &> redirect — NOT a split point, append as-is
            current.append(ch)
        elif ch == "&":
            # Single & (background operator) — B4 fix: split here
            # NB-2: But don't split if it's part of >& (fd duplication like 2>&1)
            if current and current[-1] == ">":
                # Part of >& pattern, don't split
                current.append(ch)
            elif current:
                segments.append("".join(current).strip())
                current = []
        elif ch == "|" and i + 1 < n and command[i + 1] == "|":
            # ||
            if current:
                segments.append("".join(current).strip())
                current = []
            i += 1  # skip second |
        elif ch in ("|", ";", "\n"):
            # Single | or ; or newline
            if current:
                segments.append("".join(current).strip())
                current = []
        else:
            current.append(ch)

        i += 1

    if current:
        segments.append("".join(current).strip())

    return [s for s in segments if s]


def _segment_has_write_intent(segment: str) -> bool:  # noqa: C901
    """Determine if a command segment has write intent.

    Fix-1: Returns True if segment contains:
    - Write commands as first word (mv, rm, cp, etc.)
    - Write verbs (Fix-3 vocabulary)
    - Readonly commands with redirects to owned paths
    - Unknown commands (fail-closed)

    Readonly commands (grep, cat, echo, git, etc.) without redirects to owned
    paths always return False, even if they mention owned strings.
    """
    # N2: Command substitution detection — $(...) or backticks indicate dynamic content
    # Must check BEFORE readonly commands to catch echo $(rm ...) etc.
    # Use regex to match actual command substitution patterns, not just substring matches
    if re.search(r"\$\([^)]+\)|`[^`]+`", segment):
        return True

    # Get first command word
    first_word = segment.split()[0] if segment.split() else ""

    # Known safe read-only commands (architecture §2.2 safe set + common tools)
    readonly_commands = {
        "cat",
        "ls",
        "grep",
        "rg",  # B3: rg is read-only (architecture §2.2 lists grep/rg)
        "head",
        "tail",
        "echo",
        "printf",
        "stat",
        "wc",
        "diff",
        "awk",
        "sort",  # B3: sort is read-only
        "pytest",
        "ruff",
        "mypy",
    }
    # R3-6: ruff format / ruff check --fix are write operations
    if first_word == "ruff":
        words = segment.split()
        if len(words) >= 2:
            ruff_subcmd = words[1]
            # format subcommand is always write
            if ruff_subcmd == "format":
                return True
            # check with --fix is write
            if ruff_subcmd == "check" and any(w == "--fix" for w in words[2:]):
                return True
            # Other ruff subcommands (check without --fix) are readonly
        return False

    if first_word in readonly_commands:
        # R3-4: sort with -o/--output= is write operation
        if first_word == "sort" and any(w == "-o" or w.startswith("--output=") for w in segment.split()[1:]):
            return True

        # Readonly commands only have write intent if redirecting to owned paths
        # R3-1: Use updated redirect pattern that handles &>/>&
        # First check &> redirects (bash combined stdout+stderr)
        amp_redirect_pattern = re.compile(r"&>>?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
        for match in amp_redirect_pattern.finditer(segment):
            target = match.group(1)
            target_lower = target.lower()
            if any(ind in target_lower for ind in ["memory/", "memory\\", "agents.md"]):
                return True
            ft_block = _check_file_type_block(target)
            if ft_block is not None:
                return True

        # Check >& redirects (but not >&N fd duplication)
        gt_amp_redirect_pattern = re.compile(r">&>?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
        for match in gt_amp_redirect_pattern.finditer(segment):
            target = match.group(1)
            # Skip fd duplication targets (digits like 1, 2)
            if target.isdigit():
                continue
            target_lower = target.lower()
            if any(ind in target_lower for ind in ["memory/", "memory\\", "agents.md"]):
                return True
            ft_block = _check_file_type_block(target)
            if ft_block is not None:
                return True

        # Then standard redirects (> >>, but not &> or >& which are handled above)
        redirect_pattern = re.compile(r"(?<![&>])[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
        for match in redirect_pattern.finditer(segment):
            target = match.group(1)
            target_lower = target.lower()
            # Check if redirect target contains owned indicators (substring match)
            if any(ind in target_lower for ind in ["memory/", "memory\\", "agents.md"]):
                return True
            # Also check file-type blacklist (backups dir, .sql suffix etc.)
            ft_block = _check_file_type_block(target)
            if ft_block is not None:
                return True
        return False

    # B3 + R3-3: sed with -n/--quiet is read-only; sed -i/--in-place is write
    if first_word == "sed":
        words = segment.split()
        has_inplace = any(
            w == "-i" or w.startswith("-i") and len(w) > 2 and "i" in w[1:] for w in words[1:] if w.startswith("-")
        )
        # Also check combined short flags like -in, -ni etc.
        for w in words[1:]:
            if w.startswith("-") and not w.startswith("--") and "i" in w[1:]:
                has_inplace = True
                break
        # R3-3: Check --in-place long flag (with optional =SUFFIX)
        for w in words[1:]:
            if w == "--in-place" or w.startswith("--in-place="):
                has_inplace = True
                break
        if has_inplace:
            return True  # sed -i / --in-place is write
        return _has_redirect_to_owned(segment)  # sed -n etc. is readonly

    # git subcommand check: B2 + R3-2 — narrow readonly to explicitly safe set
    if first_word == "git":
        words = segment.split()
        if len(words) >= 2:
            git_subcmd = words[1]
            # Explicitly safe read-only git subcommands
            git_readonly_subcmds = {
                "status",
                "log",
                "show",
                "diff",
                "blame",
                "cat-file",
                "rev-parse",
                "ls-files",
                "grep",
                "config",
                "describe",
                "tag",
                "branch",
                "remote",
                "shortlog",
                "whatchanged",
                # R3-2: stash removed from readonly - stash push/pop write to working tree
            }
            if git_subcmd in git_readonly_subcmds:
                return _has_redirect_to_owned(segment)
            # commit message containing owned strings is readonly
            if git_subcmd == "commit":
                return _has_redirect_to_owned(segment)
            # All other git subcommands (add/clean/apply/checkout/restore/
            # push/pull/merge/rebase/reset/init/clone/stash etc.) are write
            return True
        return False  # bare 'git' with no subcommand

    # Check for redirect operators (only relevant for non-readonly commands)
    if re.search(r"[12]?>[>]?", segment):
        return True

    # Write command set (sed removed — handled specially above for -i vs -n)
    write_commands = {
        "mv",
        "rm",
        "cp",
        "rsync",
        "mkdir",
        "touch",
        "dd",
        "install",
        "ln",
        "tee",
        "tar",
        "find",
        "chmod",
        "chown",
        "truncate",
        "cd",  # cd to owned directories is suspicious
    }

    # Check if first word is a write command
    if first_word in write_commands:
        return True

    # Check for interpreters (opaque, can't analyze further)
    interpreters = {"python", "python3", "node", "sh", "bash"}
    if first_word in interpreters:
        return True

    # N4: Token-aware write verb matching
    # Commands that support -t/--target-directory= for destination
    t_flag_commands = {"mv", "cp", "install", "rsync"}
    # Check for -t / --target-directory= only when first word supports it
    if first_word in t_flag_commands and re.search(r"(?:^|\s)(?:-t\s|--target-directory=)", segment):
        return True

    # find -delete / -fprintf are write verbs only in find context
    if first_word == "find" and ("-delete" in segment or "-fprintf" in segment):
        return True

    # Python/node API write verbs (always suspicious regardless of command)
    api_write_verbs = [
        "os.replace",
        "os.rename",
        "shutil.move",
        "shutil.copy",
        "shutil.rmtree",
        "os.remove",
        "os.unlink",
        "unlinkSync",
        "rmSync",
        "rmdirSync",
        "renameSync",
        "cpSync",
        ".write_text",
        ".write_bytes",
    ]
    for verb in api_write_verbs:
        if verb in segment:
            return True

    # N2: Command substitution detection — $(...) or backticks contain write intent
    if "$(" in segment or "`" in segment:
        return True

    # Unknown command: fail-closed
    return True


def _has_redirect_to_owned(segment: str) -> bool:  # noqa: C901
    """Check if segment has redirects targeting owned paths or forbidden types.

    Used by _segment_has_write_intent for readonly commands.
    Extracts redirect targets and checks if any contain owned indicators or hit file-type blacklist.

    R3-1: Handles &>/>& redirect operators (not just >/>>)
    R3-5: Checks file-type blacklist (FORBIDDEN_DIRS/FORBIDDEN_SUFFIXES) for redirect targets
    """
    # R3-1: Handle &> and >& (bash combined stdout+stderr redirect)
    # &> or &>> : combined redirect (bash)
    amp_redirect = re.compile(r"&>>?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
    for match in amp_redirect.finditer(segment):
        target = match.group(1)
        target_lower = target.lower()
        # Check owned indicators
        if any(ind in target_lower for ind in ["memory/", "memory\\", "agents.md"]):
            return True
        # R3-5: Check file-type blacklist
        if _check_file_type_block(target) is not None:
            return True

    # >& or >&> : combined redirect (bash alternative syntax)
    # But NOT >&N (fd duplication like 2>&1 where N is a digit)
    gt_amp_redirect = re.compile(r">&>?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
    for match in gt_amp_redirect.finditer(segment):
        target = match.group(1)
        # Skip fd duplication targets (digits like 1, 2)
        if target.isdigit():
            continue
        target_lower = target.lower()
        if any(ind in target_lower for ind in ["memory/", "memory\\", "agents.md"]):
            return True
        if _check_file_type_block(target) is not None:
            return True

    # Standard redirects: >, >>, 1>, 2>, 1>>, 2>>
    # Exclude &> and >& which are handled above
    redirect_pattern = re.compile(r"(?<![&>])[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
    for match in redirect_pattern.finditer(segment):
        target = match.group(1)
        target_lower = target.lower()
        # Check if redirect target contains owned indicators
        if any(ind in target_lower for ind in ["memory/", "memory\\", "agents.md"]):
            return True
        # R3-5: Check file-type blacklist (backups/.sql/.bak etc.)
        if _check_file_type_block(target) is not None:
            return True
    return False


def _check_owned_in_segment(segment: str) -> bool:
    """Check if segment contains owned resource references.

    Fix-1: Returns True if segment contains any owned indicator string.
    Special handling for `cd` segments: bare `memory` argument also matches.
    """
    # All indicators must be lowercased to match segment_lower
    indicators = ["memory/", "memory\\", "agents.md"]
    segment_lower = segment.lower()
    if any(ind in segment_lower for ind in indicators):
        return True

    # cd special case: `cd memory` should be detected even without trailing slash
    parts = segment.split()
    if parts and parts[0] == "cd" and len(parts) >= 2:
        cd_target = parts[1].lower()
        # Check if cd target matches owned directory names
        if cd_target == "memory" or cd_target.startswith("memory/") or cd_target.startswith("memory\\"):
            return True
        # Check if target contains agents.md
        if "agents.md" in cd_target:
            return True

    return False


def _classify_execute(payload: dict[str, Any], project_root: Path, ownership: Any) -> RuleResult:
    """Handle Execute tool classification with compound command handling.

    Fix-1: Segment-level write intent gate (unconditional)
    Fix-2: Split compound commands by operators respecting quotes
    Fix-3: Extended vocabulary (GNU -t, python/node APIs, cd, find -delete, etc.)
    B1: Run legacy extraction per write-intent segment (not just single-segment commands)
    """
    command = payload.get("command", "")
    if not command:
        return RuleResult(
            matched=False, severity="info", message="Execute without command", detail={"decision": "allow"}
        )

    # Fix-2: Split into segments
    segments = _split_command_segments(command)

    # Check segments and track write intent
    segment_result, any_write_intent = _check_command_segments(segments)
    if segment_result is not None:
        return segment_result

    # B1 fix: Run legacy extraction per segment with write intent
    # This catches file-type blacklists, uncertain paths, and owned paths
    # that segment-level write intent gate doesn't detect
    for segment in segments:
        if _segment_has_write_intent(segment):
            # Pass full command for context (needed for uncertain path checks)
            legacy_result = _legacy_path_extraction(segment, ownership, project_root, full_command_context=command)
            if legacy_result.matched:
                return legacy_result

    # All segments passed both write intent gate and legacy extraction
    return RuleResult(
        matched=False,
        severity="info",
        message="All command segments passed write intent gate",
        detail={"decision": "allow"},
    )


def _check_command_segments(segments: list[str]) -> tuple[RuleResult | None, bool]:
    """Check command segments for owned resource references.

    Returns:
        tuple: (RuleResult if a segment triggers block decision, else None),
               (bool indicating if any segment had write intent)
    """
    any_write_intent = False
    for i, segment in enumerate(segments):
        parts = segment.split()
        if not parts:
            continue

        first_word = parts[0]

        # Special handling for cd commands
        if first_word == "cd" and len(parts) >= 2:
            cd_result = _handle_cd_segment(segment, parts, i, segments)
            if cd_result is not None:
                return cd_result, any_write_intent
            continue

        # Check for write intent
        has_write_intent = _segment_has_write_intent(segment)
        if has_write_intent:
            any_write_intent = True

        # Check if segment has owned references
        has_owned_refs = _check_owned_in_segment(segment)

        # If this segment has write intent and owned refs, block
        if has_write_intent and has_owned_refs:
            return (
                RuleResult(
                    matched=True,
                    severity="error",
                    message=f"Command segment has write intent targeting owned resources: {segment[:50]}...",
                    detail={"decision": "block"},
                ),
                any_write_intent,
            )

    return None, any_write_intent


def _handle_cd_segment(segment: str, parts: list[str], i: int, segments: list[str]) -> RuleResult | None:
    """Handle cd command segment with owned directory check.

    N1: Skip no-op cd (cd . / cd ./) in look-ahead to prevent bypass
    Returns RuleResult if cd targets owned directory, None otherwise.
    """
    cd_target = parts[1]

    # N1: Detect no-op cd (cd . or cd ./)
    is_noop_cd = cd_target in (".", "./")

    # Check if cd target is an owned directory
    if _check_owned_in_segment(segment):
        # Look ahead: if next segment is also a cd command, allow this one
        # (because the cwd will change, so this is a residual case)
        if i + 1 < len(segments):
            next_parts = segments[i + 1].split()
            # N1: Don't skip if next cd is no-op (cd . / cd ./)
            if next_parts and next_parts[0] == "cd" and len(next_parts) >= 2:
                next_cd_target = next_parts[1]
                # If next cd is no-op, don't skip this owned cd
                if next_cd_target not in (".", "./"):
                    # Next segment is a real cd, so allow this cd (residual case)
                    return None
        # Otherwise, block this cd command
        return RuleResult(
            matched=True,
            severity="error",
            message=f"cd to owned directory: {cd_target}",
            detail={"decision": "block"},
        )
    # N1: If this is no-op cd, don't mark as write intent
    if is_noop_cd:
        return None
    return None


def _legacy_path_extraction(
    command: str, ownership: Any, project_root: Path, full_command_context: str | None = None
) -> RuleResult:
    """Legacy path extraction for single-segment commands.

    Handles uncertain paths, file type blocking, and owned path classification.

    Args:
        command: The segment or command to analyze
        ownership: Ownership policy
        project_root: Project root path
        full_command_context: Optional full command for context (used when checking
            uncertain paths in multi-segment commands — if owned strings appear
            anywhere in the full command, uncertain paths are more suspicious)
    """
    # Use full command context for owned string checks if provided
    context_for_owned_check = full_command_context if full_command_context is not None else command

    paths = _extract_path_from_execute(command)
    if not paths:
        if _contains_owned_root_string(context_for_owned_check):
            return RuleResult(
                matched=True,
                severity="error",
                message="Cannot parse Execute command but contains owned resource references",
                detail={"decision": "block"},
            )
        return RuleResult(
            matched=False, severity="info", message="No owned paths detected in Execute", detail={"decision": "allow"}
        )

    for path in paths:
        if _is_uncertain_path(path):
            # B1: Check full command context for owned strings when uncertain path detected
            if _contains_owned_root_string(context_for_owned_check):
                return RuleResult(
                    matched=True,
                    severity="error",
                    message=f"Uncertain path '{path}' targeting owned resources",
                    detail={"decision": "block"},
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
                detail={"decision": decision},
            )

        result = classify_owned_path(expanded, ownership, project_root)
        if hasattr(result, "level"):
            return RuleResult(
                matched=True,
                severity="error",
                message=f"Execute targets protected path '{path}': {result.reason}",
                detail={"decision": "block"},
            )

    return RuleResult(
        matched=False, severity="info", message="No owned paths in Execute targets", detail={"decision": "allow"}
    )


def _classify_task(payload: dict[str, Any], project_root: Path, ownership: Any) -> RuleResult:
    """Handle Task tool classification.

    Always allows the Task (with ownership policy injection).
    Actual file-level protection is enforced by Write/Edit/MultiEdit handlers.
    Blocking based on path strings in the prompt causes false positives for
    analysis tasks that merely reference protected paths.
    """
    fixed_root = _get_project_root_for_task(project_root)

    prompt = payload.get("prompt", "")
    policy_block = _build_ownership_policy_block(fixed_root)

    if isinstance(prompt, str) and "<!-- ownership-policy-injection -->" in prompt:
        injected_prompt = prompt
    else:
        injected_prompt = f"{policy_block}\n\n{prompt}" if isinstance(prompt, str) else prompt

    return RuleResult(
        matched=False,
        severity="info",
        message="Task allowed with ownership policy injection",
        detail={
            "decision": "allow",
            "injected_prompt": injected_prompt,
        },
    )


def _classify_unknown(payload: dict[str, Any], project_root: Path, ownership: Any) -> RuleResult:
    """Handle unknown tool - allow."""
    tool_name = payload.get("tool_name", "")
    return RuleResult(
        matched=False, severity="info", message=f"Unknown tool: {tool_name}", detail={"decision": "allow"}
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
            matched=False, severity="info", message="No tool_name specified", detail={"decision": "allow"}
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
