#!/usr/bin/env python3
"""Initialize a memory/system/ directory skeleton in a target project.

Usage:
    python init_project_memory.py --target /path/to/project
    python init_project_memory.py --target /path/to/project --dry-run
    python init_project_memory.py --target /path/to/project --dry-run --json
    python init_project_memory.py --target /path/to/project --host claude
    python init_project_memory.py --target /path/to/project --force
    python init_project_memory.py --target /path/to/project --no-clobber
    python init_project_memory.py --target /path/to/project --no-auto-fill

This tool creates the minimal memory/system/ directory structure required by the
memory system. It is designed to run against a *business project* repository,
NOT against the memory repository itself.

Key guarantees:
    - Default target is the business project repository
    - Does NOT write real project state into the memory repository
    - Generated skeleton passes validate_project_memory.py
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .index_schema import build_headers, inject_headers, read_project_version
except ImportError:
    from memory_core.tools.index_schema import (  # type: ignore
        build_headers,
        inject_headers,
        read_project_version,
    )


def _is_index_md(fname: str) -> bool:
    return fname == "INDEX.md" or fname.endswith("/INDEX.md")


def _decorate_index_content(fname: str, content: str) -> str:
    """Inject memory-core + index-schema headers into INDEX.md content."""
    if not _is_index_md(fname):
        return content
    headers = build_headers(read_project_version())
    return inject_headers(content, headers)

from memory_core.constants import (
    CANONICAL_ADAPTER_VERSION,
    CANONICAL_MEMORY_LOCK_SCHEMA,
    CURRENT_MEMORY_VERSION,
    SUPPORTED_HOSTS,
)
from memory_core.ownership import (
    Owned,
    classify_owned_path,
    load_memory_ownership,
)
from memory_core.tools.denied_project_roots import is_denied_project_root

# Setup logging for template warnings
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Claude hook event mapping: (Claude event name -> gateway event flag)
CLAUDE_HOOK_EVENTS: list[tuple[str, str]] = [
    ("SessionStart", "session-start"),
    ("UserPromptSubmit", "prompt-submit"),
    ("Notification", "notification"),
    ("Stop", "stop"),
]

MEMORY_HOOK_BEGIN_MARKER = "<!-- MEMORY_HOOK_BEGIN -->"
MEMORY_HOOK_END_MARKER = "<!-- MEMORY_HOOK_END -->"

# Directory structure to create under memory/system/
DIRECTORY_STRUCTURE = [
    "memory",
    "memory/system",
    "memory/system/kb",
    "memory/system/kb/projects",
    "memory/system/kb/decisions",
    "memory/system/kb/lessons",
    "memory/system/kb/global",
    "project-map",
    "memory/kb",
    "memory/kb/global",
    "memory/kb/projects",
    "memory/kb/decisions",
    "memory/kb/lessons",
    "memory/docs",
    "memory/log",
]

# Per-scope directories created during init (relative to target root)
# These require the scope name and are created dynamically in init_project_memory().
PER_SCOPE_DIRECTORIES = [
    "memory/kb/projects/{scope}",
]

# ---------------------------------------------------------------------------
# File templates
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _slug(text: str) -> str:
    """Normalize a string to a safe project slug: lowercase, hyphens to underscores."""
    return text.lower().replace("-", "_")


def _project_name(target: Path, scope: str | None = None) -> str:
    """Derive a short project name from the target path.

    Priority:
        1. Explicit --scope parameter
        2. git remote origin URL (last segment, stripped of .git)
        3. Target directory name (lowercase)
    """
    if scope:
        return _slug(scope)

    # Try git remote
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(target), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip().rstrip("/")
            # Strip .git suffix
            if url.endswith(".git"):
                url = url[:-4]
            # Extract last path segment (after last / or :)
            segment = url.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            if segment:
                return _slug(segment)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        # Fallback to directory name is by-design: init must work without git.
        # But we log the failure so it's observable during troubleshooting.
        logger.debug("git remote query failed: %s", exc)

    # Fallback: directory name, lowercase
    return _slug(target.resolve().name)


def template_memory_lock(project_name: str) -> tuple[str, list[str]]:
    """Generate memory.lock content in canonical TOML format.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f'''\
# memory.lock -- project binding to memory-core

[memory]
project = "{project_name}"
memory_version = "{CURRENT_MEMORY_VERSION}"
schema_version = "{CANONICAL_MEMORY_LOCK_SCHEMA}"
adapter_version = "{CANONICAL_ADAPTER_VERSION}"
locked_at = "{now}"
lock_reason = "initial"
'''
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in memory.lock: {exc}")
        warnings.append(f"template_memory_lock: {exc}")
        # Safe fallback with placeholders
        content = f'''\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# memory.lock -- project binding to memory-core

[memory]
project = "{{project_name}}"
memory_version = "{CURRENT_MEMORY_VERSION}"
schema_version = "{CANONICAL_MEMORY_LOCK_SCHEMA}"
adapter_version = "{CANONICAL_ADAPTER_VERSION}"
locked_at = "{now}"
lock_reason = "initial"
'''
    return content, warnings


def template_adapter_toml(project_name: str, host: str = "codex") -> tuple[str, list[str]]:
    """Generate adapter.toml content conforming to the canonical schema.

    Uses inline canonical template (no external template file needed).

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = """\
# adapter.toml — canonical layout (memory-core v0.2.x)
# 由 memory-init 在初始化时填充实际值

[core]
version = "{{memory_version}}"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "{{project_name}}"
project_scope = "{{project_scope}}"
host = "{{host}}"
"""

        # Replace placeholders
        content = content.replace("{{memory_version}}", CURRENT_MEMORY_VERSION)
        content = content.replace("{{project_name}}", project_name)
        content = content.replace("{{project_scope}}", project_name)
        content = content.replace("{{host}}", host)

    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in adapter.toml: {exc}")
        warnings.append(f"template_adapter_toml: {exc}")
        # Safe fallback with placeholders
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# Memory Adapter Configuration
# Auto-generated by init_project_memory.py
# Schema: [core] + [policy] + [routing]

[core]
# Adapter protocol version and type
version = "{CURRENT_MEMORY_VERSION}"
adapter = "default"

[policy]
# How the gateway resolves legal source documents
legality_source_policy = "map-only"
# When registration commits happen relative to absorption
registration_commit_policy = "same-commit"
# Commit phase declaration (post = after context build)
registration_commit_phase = "post"

[routing]
# Project identity — drives scope resolution and canonical lookup
project_name = "{project_name}"
project_scope = "{project_name}"
# Host platform: codex | claude | factory
host = "{host}"
"""
    return content, warnings


def template_canonical_md(project_name: str) -> tuple[str, list[str]]:
    """Generate CANONICAL.md content — project specification file.

    Defines coding standards, architecture constraints, naming conventions.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    now = _now_iso()
    try:
        content = f"""\
# CANONICAL.md — 项目规范文件
# 作用：定义业务项目的编码规范、架构约束、命名约定

## 项目信息

- **项目名称**：{project_name}
- **项目类型**：{{PROJECT_TYPE}}
- **主语言**：{{PRIMARY_LANGUAGE}}
- **创建日期**：{now}

## 编码规范

{{CODING_STANDARDS}}

## 架构约束

{{ARCHITECTURE_CONSTRAINTS}}

## 命名约定

{{NAMING_CONVENTIONS}}

## 工具链

{{TOOLCHAIN}}

## 变更日志

| 日期 | 变更内容 | 作者 |
|------|----------|------|
| {now} | 初始化 | {{AUTHOR}} |
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in CANONICAL.md: {exc}")
        warnings.append(f"template_canonical_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# CANONICAL.md — 项目规范文件

## 项目信息

- **项目名称**：{{PROJECT_NAME}}
- **项目类型**：{{PROJECT_TYPE}}
- **主语言**：{{PRIMARY_LANGUAGE}}
- **创建日期**：{{CREATED_AT}}

## 编码规范

{{CODING_STANDARDS}}

## 架构约束

{{ARCHITECTURE_CONSTRAINTS}}

## 命名约定

{{NAMING_CONVENTIONS}}

## 工具链

{{TOOLCHAIN}}

## 变更日志

| 日期 | 变更内容 | 作者 |
|------|----------|------|
| {{DATE}} | 初始化 | {{AUTHOR}} |
"""
    return content, warnings


def template_plan_md(project_name: str) -> tuple[str, list[str]]:
    """Generate PLAN.md content — project plan file.

    Records current iteration/task execution plan, milestones, acceptance criteria.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    now = _now_iso()
    try:
        content = f"""\
# PLAN.md — 项目计划文件
# 作用：记录当前迭代/任务的执行计划、里程碑、验收标准

## 任务概述

- **任务 ID**：{{TASK_ID}}
- **任务名称**：{{TASK_NAME}}
- **优先级**：{{PRIORITY}}
- **创建日期**：{now}

## 目标

{{GOALS}}

## 执行计划

| 步骤 | 描述 | 状态 | 完成日期 |
|------|------|------|----------|
| 1    | {{STEP_1}} | pending | - |
| 2    | {{STEP_2}} | pending | - |

## 验收标准

{{ACCEPTANCE_CRITERIA}}

## 风险与依赖

{{RISK_AND_DEPENDENCIES}}

## 状态

- **当前状态**：planning
- **上次更新**：{now}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in PLAN.md: {exc}")
        warnings.append(f"template_plan_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# PLAN.md — 项目计划文件

## 任务概述

- **任务 ID**：{{TASK_ID}}
- **任务名称**：{{TASK_NAME}}
- **优先级**：{{PRIORITY}}
- **创建日期**：{{CREATED_AT}}

## 目标

{{GOALS}}

## 执行计划

| 步骤 | 描述 | 状态 | 完成日期 |
|------|------|------|----------|
| 1    | {{STEP_1}} | pending | - |
| 2    | {{STEP_2}} | pending | - |

## 验收标准

{{ACCEPTANCE_CRITERIA}}

## 风险与依赖

{{RISK_AND_DEPENDENCIES}}

## 状态

- **当前状态**：planning
- **上次更新**：{{UPDATED_AT}}
"""
    return content, warnings


def template_state_md(project_name: str) -> tuple[str, list[str]]:
    """Generate STATE.md content — project state file.

    Records current state, context summary, key decisions.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    now = _now_iso()
    try:
        content = f"""\
# STATE.md — 项目状态文件
# 作用：记录业务项目的当前状态、上下文摘要、关键决策

## 项目状态

- **状态**：{{STATUS}}
- **最后更新**：{now}
- **健康度**：{{HEALTH}}

## 上下文摘要

{{CONTEXT_SUMMARY}}

## 关键决策

| 日期 | 决策 | 理由 |
|------|------|------|
| {now} | {{DECISION}} | {{RATIONALE}} |

## 当前工作区

{{CURRENT_WORKSPACE}}

## 待处理事项

{{PENDING_ITEMS}}

## 已完成的里程碑

{{COMPLETED_MILESTONES}}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in STATE.md: {exc}")
        warnings.append(f"template_state_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# STATE.md — 项目状态文件

## 项目状态

- **状态**：{{STATUS}}
- **最后更新**：{{LAST_UPDATED}}
- **健康度**：{{HEALTH}}

## 上下文摘要

{{CONTEXT_SUMMARY}}

## 关键决策

| 日期 | 决策 | 理由 |
|------|------|------|
| {{DATE}} | {{DECISION}} | {{RATIONALE}} |

## 当前工作区

{{CURRENT_WORKSPACE}}

## 待处理事项

{{PENDING_ITEMS}}

## 已完成的里程碑

{{COMPLETED_MILESTONES}}
"""
    return content, warnings


def template_tasks_md(project_name: str) -> tuple[str, list[str]]:
    """Generate TASKS.md content — task list file.

    Tracks all tasks, subtasks, and statuses for the current project.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = """\
# TASKS.md — 任务清单文件
# 作用：跟踪当前项目下的所有任务、子任务、状态

## 活跃任务

| ID | 任务 | 优先级 | 状态 | 负责人 | 截止日期 |
|----|------|--------|------|--------|----------|
| T-001 | {{TASK_1}} | P2 | pending | {{ASSIGNEE}} | {{DUE}} |

## 已完成任务

| ID | 任务 | 完成日期 | 备注 |
|----|------|----------|------|
| - | - | - | - |

## 已取消任务

| ID | 任务 | 取消原因 |
|----|------|----------|
| - | - | - |

## 阻塞项

{{BLOCKERS}}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in TASKS.md: {exc}")
        warnings.append(f"template_tasks_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# TASKS.md — 任务清单文件

## 活跃任务

| ID | 任务 | 优先级 | 状态 | 负责人 | 截止日期 |
|----|------|--------|------|--------|----------|
| T-001 | {{TASK_1}} | P2 | pending | {{ASSIGNEE}} | {{DUE}} |

## 已完成任务

| ID | 任务 | 完成日期 | 备注 |
|----|------|----------|------|
| - | - | - | - |

## 已取消任务

| ID | 任务 | 取消原因 |
|----|------|----------|
| - | - | - |

## 阻塞项

{{BLOCKERS}}
"""
    return content, warnings


def template_now_md(project_name: str) -> tuple[str, list[str]]:
    """Generate NOW.md content — current workspace status file.

    Provides a snapshot of current mission, today's work, next actions, and blockers.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = """\
# NOW.md

## Mission
- {{MISSION}}

## Today
- {{TODAY}}

## Next 3 Actions
1. {{ACTION_1}}
2. {{ACTION_2}}
3. {{ACTION_3}}

## Blockers
- {{BLOCKERS}}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in NOW.md: {exc}")
        warnings.append(f"template_now_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# NOW.md

## Mission
- {{MISSION}}

## Today
- {{TODAY}}

## Next 3 Actions
1. {{ACTION_1}}
2. {{ACTION_2}}
3. {{ACTION_3}}

## Blockers
- {{BLOCKERS}}
"""
    return content, warnings


def template_migrations_log(project_name: str) -> tuple[str, list[str]]:
    """Generate initial migrations.log.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f"""\
# Migrations Log
# Format: TIMESTAMP | VERSION_FROM | VERSION_TO | STATUS | NOTES

{now}T00:00:00Z | none | {CURRENT_MEMORY_VERSION} | applied | initial scaffold
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in migrations.log: {exc}")
        warnings.append(f"template_migrations_log: {exc}")
        # Safe fallback - this template doesn't use project_name, so just return the same content
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# Migrations Log
# Format: TIMESTAMP | VERSION_FROM | VERSION_TO | STATUS | NOTES

{now}T00:00:00Z | none | {CURRENT_MEMORY_VERSION} | applied | initial scaffold
"""
    return content, warnings


def template_inbox_md(project_name: str) -> tuple[str, list[str]]:
    """Generate inbox.md for temporary task capture.

    Runtime required: referenced by memory_hook_impls.py L531, L1374 (workbot adapter).

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = """\
# 收件箱

临时任务捕获区。用于快速记录待处理事项，后续应整理到正式任务管理系统。

## 待处理事项

- [ ] （待填写）

## 已归档

（已处理并归档的项）
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in inbox.md: {exc}")
        warnings.append(f"template_inbox_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# 收件箱

临时任务捕获区。用于快速记录待处理事项，后续应整理到正式任务管理系统。

## 待处理事项

- [ ] （待填写）

## 已归档

（已处理并归档的项）
"""
    return content, warnings


def template_policy_pack_json(project_name: str) -> tuple[str, list[str]]:
    """Generate default memory-hook-policy-pack.json.

    Runtime required: referenced by memory_hook_impls.py L281 DEFAULT_POLICY_PACK_PATH.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        policy_pack = {
            "policies": [],
            "version": "1.0"
        }
        content = json.dumps(policy_pack, indent=2, ensure_ascii=False) + "\n"
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in memory-hook-policy-pack.json: {exc}")
        warnings.append(f"template_policy_pack_json: {exc}")
        content = '{"policies": [], "version": "1.0"}\n'
    return content, warnings


def template_ownership_toml(project_name: str) -> tuple[str, list[str]]:
    """Generate ownership.toml content for memory-core ownership declaration.

    Uses manual string construction (no tomli_w or tomlkit dependency).

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        lines: list[str] = [
            "# ownership.toml -- memory-core ownership declaration",
            "",
            'schema_version = "memory-ownership-v1"',
            f'memory_version = "{CURRENT_MEMORY_VERSION}"',
            "",
            "# Domains: directories under ownership protection",
        ]

        # Add default domains
        from memory_core.ownership import DEFAULT_OWNERSHIP_DOMAINS
        for domain in DEFAULT_OWNERSHIP_DOMAINS:
            lines.extend([
                "",
                "[[domains]]",
                f'name = "{domain.name}"',
                f'path = "{domain.path}"',
                f'level = "{domain.level.name.lower()}"',
                f'recursive = {str(domain.recursive).lower()}',
            ])
            if domain.description:
                lines.append(f'description = "{domain.description}"')

        lines.extend([
            "",
            "# Resources: specific files under ownership protection",
        ])

        # Add default resources
        from memory_core.ownership import DEFAULT_OWNERSHIP_RESOURCES
        for resource in DEFAULT_OWNERSHIP_RESOURCES:
            lines.extend([
                "",
                "[[resources]]",
                f'name = "{resource.name}"',
                f'path = "{resource.path}"',
                f'level = "{resource.level.name.lower()}"',
            ])
            if resource.domain:
                lines.append(f'domain = "{resource.domain}"')
            if resource.description:
                lines.append(f'description = "{resource.description}"')

        lines.extend([
            "",
            "# Policy: optional key-value pairs for ownership policy",
            "[policy]",
            f'project_name = "{project_name}"',
            "",
        ])

        content = "\n".join(lines)
    except (ValueError, TypeError, ImportError) as exc:
        logger.warning(f"Template render error in ownership.toml: {exc}")
        warnings.append(f"template_ownership_toml: {exc}")
        # Safe fallback
        content = f'''# ownership.toml -- memory-core ownership declaration

schema_version = "memory-ownership-v1"
memory_version = "{CURRENT_MEMORY_VERSION}"

# Domains and resources omitted due to render error
[policy]
project_name = "{project_name}"
'''
    return content, warnings


def template_project_scope_md(project_name: str) -> tuple[str, list[str]]:
    """Generate project scope knowledge file.

    Runtime required: referenced by memory_hook_core.py L207-210.
    Filename uses scope parameter.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f"""\
---
type: "KB:PROJECT"
title: "{project_name} Project Knowledge"
shortname: "{project_name}"
status: active
created: "{now}"
updated: "{now}"
scope: project
source: local-canonical
confidence: high
tags: [project, knowledge]
---

# {project_name} 项目知识

## 项目概述

（待填写：项目简要描述）

## 技术栈

- 语言：（待填写）
- 框架：（待填写）
- 数据库：（待填写）

## 关键模块

| 模块 | 描述 | 状态 |
|------|------|------|
| （待填写） | （待填写） | active |

## 决策记录

（链接到 decisions/ 目录下的相关决策）

## 经验教训

（链接到 lessons/ 目录下的相关经验）
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in project scope md: {exc}")
        warnings.append(f"template_project_scope_md: {exc}")
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
---
type: "KB:PROJECT"
title: "{{project_name}} Project Knowledge"
shortname: "{{project_name}}"
status: active
created: "{now}"
updated: "{now}"
scope: project
source: local-canonical
confidence: high
tags: [project, knowledge]
---

# {{project_name}} 项目知识

## 项目概述

（待填写：项目简要描述）

## 技术栈

- 语言：（待填写）
- 框架：（待填写）
- 数据库：（待填写）

## 关键模块

| 模块 | 描述 | 状态 |
|------|------|------|
| （待填写） | （待填写） | active |

## 决策记录

（链接到 decisions/ 目录下的相关决策）

## 经验教训

（链接到 lessons/ 目录下的相关经验）
"""
    return content, warnings


# ---------------------------------------------------------------------------
# Auto-fill helpers
# ---------------------------------------------------------------------------

def fill_template_fields(content: str, project_info: Any) -> str:
    """Fill detected project information into template content.

    Replaces '（待填写）' placeholders with actual values from ProjectInfo.
    Only replaces placeholders, never overwrites existing filled values.

    Args:
        content: The template content to fill.
        project_info: ProjectInfo instance with detected values.

    Returns:
        Filled content with placeholders replaced.
    """
    if project_info is None:
        return content

    # Import ProjectInfo for type checking
    try:
        from .project_probe import ProjectInfo as _ProjectInfo
    except ImportError:
        from memory_core.tools.project_probe import ProjectInfo as _ProjectInfo

    if not isinstance(project_info, _ProjectInfo):
        return content

    # Fill CANONICAL.md fields
    # 主语言
    if project_info.primary_language:
        content = re.sub(
            r'(\| 主语言 \| )（待填写）( \|)',
            rf'\g<1>{project_info.primary_language}\2',
            content,
        )

    # 项目类型
    if project_info.project_type:
        content = re.sub(
            r'(\| 项目类型 \| )（待填写）( \|)',
            rf'\g<1>{project_info.project_type}\2',
            content,
        )

    # 工具链 - replace the placeholder row with actual tools
    if project_info.toolchain:
        toolchain_rows = []
        for tool in project_info.toolchain[:6]:  # Limit to 6 tools
            tool_name = tool.get("name", "")
            tool_config = tool.get("config", "")
            if tool_name:
                toolchain_rows.append(f"| {tool_name} | {tool_config} |")

        if toolchain_rows:
            tools_content = "\n".join(toolchain_rows)
            content = re.sub(
                r'\| （待填写） \| （待填写） \|',
                tools_content,
                content,
                count=1,
            )

    # 仓库 - add git remote URL
    if project_info.git_remote_url:
        # Add a new row for remote URL in the 仓库 section
        remote_row = f"| 远程仓库 | `{project_info.git_remote_url}` |"
        # Check if there's already a remote row (already filled)
        if "远程仓库" not in content:
            content = re.sub(
                r'(\| 本地仓库 \| .+? \|)\n',
                rf'\g<1>\n{remote_row}\n',
                content,
                count=1,
            )

    # Fill project scope .md fields
    # 语言
    if project_info.primary_language:
        content = re.sub(
            r'(- 语言：)（待填写）',
            rf'\g<1>{project_info.primary_language}',
            content,
        )

    # 框架
    if project_info.framework:
        content = re.sub(
            r'(- 框架：)（待填写）',
            rf'\g<1>{project_info.framework}',
            content,
        )

    # 数据库
    if project_info.databases:
        db_str = "、".join(project_info.databases)
        content = re.sub(
            r'(- 数据库：)（待填写）',
            rf'\g<1>{db_str}',
            content,
        )

    # 项目概述
    if project_info.project_overview:
        content = re.sub(
            r'（待填写：项目简要描述）',
            project_info.project_overview,
            content,
        )

    return content


def _apply_auto_fill(
    target: Path,
    project_info: Any,
    result: dict[str, Any],
    *,
    project_name: str,
) -> None:
    """Apply auto-fill to generated template files.

    This function reads the just-created files and fills in detected values.
    """
    if project_info is None:
        return

    # Import ProjectInfo for type checking
    try:
        from .project_probe import ProjectInfo as _ProjectInfo
    except ImportError:
        from memory_core.tools.project_probe import ProjectInfo as _ProjectInfo

    if not isinstance(project_info, _ProjectInfo):
        return

    # NOTE: CANONICAL.md generation removed in v0.5.0 — no auto-fill needed

    # Fill project scope .md
    scope_path = target / "memory" / "kb" / "projects" / f"{project_name}.md"
    if scope_path.exists():
        try:
            content = scope_path.read_text(encoding="utf-8")
            filled = fill_template_fields(content, project_info)
            if filled != content:
                scope_path.write_text(filled, encoding="utf-8")
                result["created"].append(f"file:memory/kb/projects/{project_name}.md (auto-filled)")
        except Exception as exc:
            result["warnings"].append(f"project scope .md auto-fill failed: {exc}")

    # Log what was detected
    if project_info.primary_language:
        result["created"].append(f"detected:primary_language={project_info.primary_language}")
    if project_info.framework:
        result["created"].append(f"detected:framework={project_info.framework}")
    if project_info.git_remote_url:
        result["created"].append(f"detected:git_remote_url={project_info.git_remote_url}")


# ---------------------------------------------------------------------------
# File registry
# ---------------------------------------------------------------------------

# Minimum viable templates for Knowledge Base and Project Map
KB_TEMPLATES: dict[str, Any] = {
    "project-map/INDEX.md": lambda scope: (
        "# 合法目录地图索引\n\n"
        "- 唯一合法入口\n"
        "- 只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。\n"
        "- 同次 `git commit` 提交后才生效\n"
        "- project-map/legal-core-map.md: active-legal\n",
        []
    ),
    "project-map/legal-core-map.md": lambda scope: (
        "# 合法核心地图\n\n"
        "- active-legal\n"
        "- 只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。\n"
        "- truth-model.md: active-legal\n"
        "- memory-system.md: active-legal\n",
        []
    ),
    "project-map/ingestion-registry-map.md": lambda scope: (
        "# 摄入登记地图\n\n"
        "- project-map/**: incoming-raw\n"
        "- memory/kb/global/**: active-legal\n"
        "- memory/kb/projects/**: compatibility-only\n"
        "- 状态：`absorbed`，`retired`\n"
        "- 同次 `git commit` 提交后才生效\n",
        []
    ),
    "memory/kb/global/truth-model.md": lambda scope: (
        "# 唯一真相模型\n\n"
        "本项目的事实来源与验证规则。\n",
        []
    ),
    "memory/kb/global/memory-system.md": lambda scope: (
        "# 记忆系统规则\n\n"
        "active-legal\n",
        []
    ),
    "memory/kb/global/memory-routing.md": lambda scope: (
        "# 记忆路由规则\n\n",
        []
    ),
    "memory/kb/global/hook-contract.md": lambda scope: (
        "# Hook 契约\n\n"
        "- gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。\n"
        "- 未完成提交的登记不得生效\n",
        []
    ),
    "memory/kb/global/project-map-governance.md": lambda scope: (
        "# 项目地图治理\n\n"
        "- 未经过唯一真相系统清洗\n"
        "- 只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。\n"
        "- 未完成同次 `git commit` 的目录登记，不得视为生效。\n",
        []
    ),
    # Runtime required: knowledge base root index referenced by memory_hook_core.py L226-236
    "memory/kb/INDEX.md": lambda scope: (
        "# 知识库索引\n\n"
        "本索引列出知识库各子目录及其用途。\n\n"
        "## 目录结构\n\n"
        "- `global/` — 全局知识（truth-model, memory-system, routing, hook-contract 等）\n"
        "- `projects/` — 项目专属知识\n"
        "- `decisions/` — 决策记录\n"
        "- `lessons/` — 经验教训\n\n"
        "## 使用说明\n\n"
        "- 只有被地图标为 `active-legal` 的条目或目录，才是合法资料\n"
        "- 目录登记和状态迁移必须与相关文件同次 `git commit` 才生效\n",
        []
    ),
    "INDEX.md": lambda scope: (
        "# 工作区索引\n\n"
        "- project-map/INDEX.md\n"
        "- 只有被地图标为 `active-legal` 的条目或目录，才是合法资料；仅进入登记册不授予合法性。\n"
        "- 目录登记和目录状态迁移必须与相关文件同次 `git commit` 才生效。\n"
        "- memory/kb/global/truth-model.md\n",
        []
    ),
    "memory/docs/INDEX.md": lambda scope: (
        "# 文档索引\n\n"
        "- incoming-raw\n"
        "- 未被地图明确吸收\n",
        []
    ),
    "memory/kb/global/INDEX.md": lambda scope: (
        "# 全局知识索引\n\n"
        "- Non-Legal Material\n"
        "- ingestion-registry-map.md\n"
        "- truth-model.md\n",
        []
    ),
}

FILE_TEMPLATES: dict[str, Any] = {
    "memory.lock": lambda pn: template_memory_lock(pn),
    "migrations.log": lambda pn: template_migrations_log(pn),
}

# Essential files that must be checked for --no-clobber
ESSENTIAL_FILES = [
    "memory.lock",
    "migrations.log",
    "adapter.toml",
]

# Runtime required KB files (under workspace_root, not memory/system/)
RUNTIME_KB_FILES = [
    "memory/kb/INDEX.md",  # L226-236 reads list
    "memory/kb/global/memory-hook-policy-pack.json",  # L281 DEFAULT_POLICY_PACK_PATH
]

# Additional runtime files created outside of KB_TEMPLATES and FILE_TEMPLATES
RUNTIME_EXTRA_FILES = [
    "memory/inbox.md",  # L531, L1374 workbot adapter action target
]

# ---------------------------------------------------------------------------
# Keep files
# ---------------------------------------------------------------------------

def template_keep() -> str:
    """Generate a .keep file content."""
    return ""



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
    if "memory_hook_gateway.py" in command or command.strip().startswith("memory-hook-gateway"):
        return True
    return False


def template_hooks_json(host: str = "claude") -> dict[str, Any]:
    """Generate hooks.json content as a dict using the protected wrapper.

    Uses ~/.claude/bin/memory-hook wrapper instead of bare gateway command
    to ensure proper project lifecycle management and anti-pollution guards.
    """
    hooks: list[dict[str, Any]] = []
    for claude_event, gateway_event in CLAUDE_HOOK_EVENTS:
        hooks.append({
            "event": claude_event,
            "command": f"~/.claude/bin/memory-hook --host {host} --event {gateway_event}",
            "stdin": True,
        })
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
    desired_keys = {(h["event"], h["command"]) for h in desired["hooks"]}

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


def template_agents_md_block(host: str = "codex") -> str:
    """Generate the AGENTS.md memory hook instruction block.

    Recommends using the protected wrapper instead of bare gateway commands
    to ensure proper project lifecycle management and anti-pollution guards.
    """
    return f"""{MEMORY_HOOK_BEGIN_MARKER}
## Memory Hook

This project uses the memory-core protected wrapper for {host.title()} hooks.
The wrapper is installed at `~/.{host}/bin/memory-hook` and handles:
- Project lifecycle tracking
- HOME directory anti-pollution guards
- Source repository detection (skips memory-core itself)
- Git root normalization

Project-level hooks are configured in `.{host}/hooks.json`.
Do NOT use bare `memory-hook-gateway` commands directly.

For manual testing:
```bash
~/.{host}/bin/memory-hook --host {host} --event session-start
```

## 路由规则

路由规则仅由以下文件定义，AGENTS.md 只做方向性引用，不嵌入任何路由逻辑。

**读取链**：Agent 启动 → AGENTS.md (行为约束) → 指向性引用 → memory-routing.md (路由规则) → project-map (合法入口) → memory/kb (实际知识)。

| 文件 | 职责 | 路径 |
|------|------|------|
| memory-routing.md | 记忆请求路由、作用域解析、降级策略 | `memory/kb/global/memory-routing.md` |
| project-map/INDEX.md | 项目地图唯一合法入口、合法性校验 | `project-map/INDEX.md` |

具体路由规则（如 scope resolution、fallback）请查阅上述文件，不要在此文件中寻找。
{MEMORY_HOOK_END_MARKER}
"""


def update_agents_md(
    target: Path,
    *,
    host: str = "codex",
    result: dict[str, Any] | None = None,
    mode: str = "create",
) -> None:
    """Insert or update the Memory Hook instruction block in AGENTS.md.

    Idempotent: if the markers already exist, the block content is replaced
    in-place rather than appended.

    Mode-aware:
    - create: Create new AGENTS.md or append block if no markers
    - adopt: Only add block if markers don't exist, never overwrite; skip files without markers
    - update: Replace existing marked block only; skip files without markers (safe default)
    - repair: Same as update (only update markers, don't create new blocks)
    """
    if result is None:
        return

    agents_path = target / "AGENTS.md"
    new_block = template_agents_md_block(host)

    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        has_begin = MEMORY_HOOK_BEGIN_MARKER in content
        has_end = MEMORY_HOOK_END_MARKER in content

        if has_begin and has_end:
            begin_idx = content.index(MEMORY_HOOK_BEGIN_MARKER)
            end_idx = content.index(MEMORY_HOOK_END_MARKER) + len(MEMORY_HOOK_END_MARKER)
            before = content[:begin_idx]
            after = content[end_idx:]

            # Strip trailing newlines from before, prepend a single newline
            before = before.rstrip("\n")
            if before:
                before = before + "\n"

            # Strip leading newlines from after, append a single newline
            after = after.lstrip("\n")
            if after:
                after = "\n" + after

            new_content = before + new_block + after

            if new_content == content:
                result["skipped"].append("file:AGENTS.md (hook block up-to-date)")
                return

            # Mode check: adopt/update/repair should not modify markers in adopt mode
            if mode == "adopt":
                result["skipped"].append("file:AGENTS.md (existing marker preserved in adopt mode)")
                return

            agents_path.write_text(new_content, encoding="utf-8")
            result["created"].append("file:AGENTS.md (hook block updated)")
            return

        # No markers found - mode-aware handling
        if mode in ("adopt", "update", "repair"):
            # adopt/update/repair mode: do not append to files without markers (safe default)
            result["skipped"].append(f"file:AGENTS.md (no marker in {mode} mode, not appending)")
            return

        # create mode: append to existing content
        new_content = content.rstrip("\n") + "\n\n" + new_block
    else:
        # File doesn't exist
        if mode in ("adopt", "update", "repair"):
            # These modes don't create new AGENTS.md
            result["skipped"].append(f"file:AGENTS.md (not created in {mode} mode)")
            return

        new_content = new_block

    agents_path.write_text(new_content, encoding="utf-8")
    result["created"].append("file:AGENTS.md")


# ---------------------------------------------------------------------------
# Initialization logic
# ---------------------------------------------------------------------------

def init_project_memory(
    target: Path,
    *,
    scope: str | None = None,
    host: str = "codex",
    dry_run: bool = False,
    json_output: bool = False,
    force: bool = False,
    no_clobber: bool = False,
    mode: str = "create",
    sync_enabled: bool = False,
    sync_source_remote: str = "origin",
    sync_mirror_remote: str = "",
    sync_mirror_url: str = "",
    auto_fill: bool = True,
) -> dict[str, Any]:
    """Initialize memory/system/ directory skeleton in the target project.

    Args:
        target: Path to the target project root.
        scope: Explicit project scope name (auto-discovered if omitted).
        host: Host platform for hook config ("codex" or "claude").
        dry_run: If True, only report what would be created.
        json_output: If True, return structured output dict.
        force: If True, overwrite existing files.
        no_clobber: If True, error if any essential file already exists.
        mode: One of "create", "adopt", "update", "repair".
            - create: Standard initialization (default).
            - adopt: Adopt existing project without overwriting business files.
            - update: Update existing memory structure, replace marked blocks.
            - repair: Repair missing required files only.
        auto_fill: If True (default), auto-detect project info and fill templates.
            Set to False to keep all placeholders ("（待填写）").

    Returns:
        Dict with 'success', 'created', 'skipped', 'errors', 'mode', 'warnings' keys.
    """
    result: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "target": str(target.resolve()),
        "created": [],
        "skipped": [],
        "errors": [],
        "mode": "dry-run" if dry_run else mode,
        "requested_mode": mode,
        "warnings": [],
        "force_overwrite": False,
    }

    # Mode-aware handling: adopt/update/repair have different semantics
    if mode not in ("create", "adopt", "update", "repair"):
        result["errors"].append(f"Invalid mode: {mode}. Must be one of: create, adopt, update, repair")
        result["mode"] = "error"
        return result

    memory_root = target / "memory" / "system"
    project_name = _project_name(target, scope)

    if is_denied_project_root(target):
        result["errors"].append(f"Refusing to initialize memory in denied project root: {target.resolve()}")
        result["mode"] = "error"
        return result

    # Mode-aware: adopt/update/repair should not fail on existing files
    # but create mode with --no-clobber should
    if no_clobber and mode == "create":
        existing_essential = []
        for fname in ESSENTIAL_FILES:
            file_path = memory_root / fname
            if file_path.exists():
                existing_essential.append(fname)
        # Also check runtime KB files
        for fname in RUNTIME_KB_FILES:
            file_path = target / fname
            if file_path.exists():
                existing_essential.append(fname)
        # Check project scope file
        scope_file = f"memory/kb/projects/{project_name}.md"
        if (target / scope_file).exists():
            existing_essential.append(scope_file)
        if existing_essential:
            result["errors"].append(
                f"refused to clobber existing memory/system/; use --force to overwrite "
                f"or remove existing files first. Existing files: {', '.join(existing_essential)}"
            )
            result["mode"] = "error"
            return result

    # Mode-aware: check for business files that should not be overwritten in adopt/update/repair
    index_md_path = target / "INDEX.md"
    has_business_index = index_md_path.exists() and "project-map" not in index_md_path.read_text(encoding="utf-8", errors="ignore").lower()

    if mode in ("adopt", "update", "repair") and has_business_index:
        # These modes: never overwrite business INDEX.md
        result["warnings"].append(f"{mode} mode: skipping business INDEX.md (not a memory file)")

    if mode in ("adopt", "update", "repair"):
        # These modes should not fail if memory/system/ already exists
        # They work with existing structures
        pass

    # Check dry-run mode - NEVER write files in dry-run
    if dry_run:
        result["success"] = True
        dry_run_output: dict[str, Any] = {
            "would_create_dirs": list(DIRECTORY_STRUCTURE),
            "would_create_files": [],
            "project_name": project_name,
        }

        # Mode-aware dry-run: determine what would happen in this mode
        def _dry_run_action(file_path: Path, is_business_file: bool = False, is_marker_protected: bool = False) -> str:
            """Determine action based on mode, file existence, and file type."""
            exists = file_path.exists()

            if mode == "adopt":
                # adopt: never overwrite business files or memory files
                if exists:
                    return "skip - exists (adopt mode preserves existing)"
                return "create"

            elif mode == "update":
                # update: never overwrite business files (INDEX.md, project-map)
                if is_business_file:
                    return "skip - business file (update mode preserves)"
                # update: replace marker-protected files (AGENTS.md handled separately)
                if exists:
                    if is_marker_protected:
                        return "replace marker block"
                    return "skip - exists (update mode preserves non-marker files)"
                return "create"

            elif mode == "repair":
                # repair: only create missing required files
                if exists:
                    return "skip - exists (repair mode never overwrites)"
                return "create"

            else:  # create mode
                if exists:
                    if force:
                        return "overwrite"
                    return "skip - exists"
                return "create"

        # Check which files would be created/overwritten (under memory/system/)
        for fname in ESSENTIAL_FILES:
            file_path = memory_root / fname
            action = _dry_run_action(file_path, is_business_file=False)
            dry_run_output["would_create_files"].append(f"{fname} ({action})")

        # Check runtime KB files (under workspace_root)
        for fname in RUNTIME_KB_FILES:
            file_path = target / fname
            action = _dry_run_action(file_path, is_business_file=False)
            dry_run_output["would_create_files"].append(f"{fname} ({action})")

        # Check project scope file
        scope_file = f"memory/kb/projects/{project_name}.md"
        scope_path = target / scope_file
        action = _dry_run_action(scope_path, is_business_file=False)
        dry_run_output["would_create_files"].append(f"{scope_file} ({action})")

        # Check KB_TEMPLATES files - INDEX.md and project-map are business files
        for fname in KB_TEMPLATES:
            file_path = target / fname
            is_business = fname == "INDEX.md" or fname.startswith("project-map/")
            action = _dry_run_action(file_path, is_business_file=is_business)
            dry_run_output["would_create_files"].append(f"{fname} ({action})")

        # Check extra runtime files
        for fname in RUNTIME_EXTRA_FILES:
            file_path = target / fname
            action = _dry_run_action(file_path, is_business_file=False)
            dry_run_output["would_create_files"].append(f"{fname} ({action})")

        # Check per-scope control loop files (memory/kb/projects/{scope}/)
        per_scope_dir = f"memory/kb/projects/{project_name}"
        dry_run_output["would_create_dirs"].append(f"{per_scope_dir}/")
        for scope_file in ("CANONICAL.md", "STATE.md", "PLAN.md", "TASKS.md"):
            scope_path = target / per_scope_dir / scope_file
            action = _dry_run_action(scope_path, is_business_file=False)
            dry_run_output["would_create_files"].append(f"{per_scope_dir}/{scope_file} ({action})")

        # NOW.md at project root
        now_path = target / "NOW.md"
        now_action = _dry_run_action(now_path, is_business_file=False)
        dry_run_output["would_create_files"].append(f"NOW.md ({now_action})")

        result["dry_run_output"] = dry_run_output
        result["force_overwrite"] = force
        result["action_taken"] = "dry-run"
        return result

    # Safety guard: do NOT initialize inside the memory repo itself
    repo_root = _find_repo_root(target)
    if repo_root and _is_memory_repo(repo_root):
        result["errors"].append(
            "Refusing to initialize memory/system/ inside the memory repository itself. "
            "This tool is for business project repositories only."
        )
        return result

    # Create directories
    for dir_rel in DIRECTORY_STRUCTURE:
        dir_path = target / dir_rel
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            result["created"].append(f"dir:{dir_rel}")
        except Exception as exc:
            result["errors"].append(f"failed to create {dir_rel}: {exc}")

    # Create .keep files in empty directories
    for dir_rel in DIRECTORY_STRUCTURE:
        # Skip the top-level memory directories
        if dir_rel in ("memory", "memory/system"):
            continue
        keep_path = target / dir_rel / ".keep"
        if not keep_path.exists():
            try:
                keep_path.write_text("", encoding="utf-8")
                result["created"].append(f"file:{dir_rel}/.keep")
            except Exception as exc:
                result["errors"].append(f"failed to create {dir_rel}/.keep: {exc}")

    # Create template files with mode-aware handling
    any_overwritten = False
    any_skipped = False

    # Load ownership configuration for force restriction checks
    ownership = load_memory_ownership(target)
    authorized_maintenance = mode == "repair" or os.environ.get("MEMORY_INIT_RUNNING") == "1"

    # Helper function to determine if we should skip/overwrite based on mode
    def _should_skip_file(file_path: Path, fname: str, is_business_file: bool = False) -> tuple[bool, str]:
        """Determine if file should be skipped based on mode.

        Returns (should_skip, reason)
        """
        if not file_path.exists():
            return False, "create"

        if mode == "adopt":
            # adopt: never overwrite any existing files
            return True, f"{mode} mode preserves existing"

        elif mode == "update":
            # update: never overwrite business files (INDEX.md, project-map)
            if is_business_file:
                return True, f"{mode} mode preserves business files"
            # update: can overwrite memory files with force
            if force:
                return False, "overwrite"
            return True, f"{mode} mode preserves existing (use --force to overwrite)"

        elif mode == "repair":
            # repair: never overwrite any existing files
            return True, f"{mode} mode only creates missing files"

        else:  # create mode
            if force:
                # Step 2.2: Check ownership before allowing force overwrite
                try:
                    rel_path = file_path.relative_to(target).as_posix()
                except ValueError:
                    rel_path = str(file_path)
                classification = classify_owned_path(rel_path, ownership=ownership)
                if isinstance(classification, Owned) and not authorized_maintenance:
                    # Owned file - reject force overwrite
                    result["errors"].append(
                        f"Force overwrite rejected: {rel_path} is owned "
                        f"({classification.reason})"
                    )
                    return True, "force rejected - owned file"
                return False, "overwrite"
            return True, "already exists"

    # 1. Write KB and Project Map templates first
    for fname, template_fn in KB_TEMPLATES.items():
        file_path = target / fname
        is_business = fname == "INDEX.md" or fname.startswith("project-map/")

        should_skip, reason = _should_skip_file(file_path, fname, is_business_file=is_business)

        if file_path.exists() and should_skip:
            result["skipped"].append(f"file:{fname} ({reason})")
            any_skipped = True
            continue

        if file_path.exists() and not should_skip:
            # Overwrite
            try:
                content, warnings = template_fn(project_name)
                content = _decorate_index_content(fname, content)
                file_path.write_text(content, encoding="utf-8")
                result["created"].append(f"file:{fname} (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite {fname}: {exc}")
            continue

        # Create new file
        try:
            content, warnings = template_fn(project_name)
            content = _decorate_index_content(fname, content)
            file_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:{fname}")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create {fname}: {exc}")

    # 2. Write memory/system/ templates
    for fname, template_fn in FILE_TEMPLATES.items():
        file_path = memory_root / fname
        should_skip, reason = _should_skip_file(file_path, fname, is_business_file=False)

        if file_path.exists() and should_skip:
            result["skipped"].append(f"file:{fname} ({reason})")
            any_skipped = True
            continue

        if file_path.exists() and not should_skip:
            # Overwrite
            try:
                content, warnings = template_fn(project_name)
                file_path.write_text(content, encoding="utf-8")
                result["created"].append(f"file:{fname} (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite {fname}: {exc}")
            continue

        # Create new file
        try:
            content, warnings = template_fn(project_name)
            file_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:{fname}")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create {fname}: {exc}")

    # Create adapter.toml separately (requires host parameter)
    adapter_path = memory_root / "adapter.toml"
    should_skip, reason = _should_skip_file(adapter_path, "adapter.toml", is_business_file=False)

    if adapter_path.exists() and should_skip:
        result["skipped"].append(f"file:adapter.toml ({reason})")
        any_skipped = True
    elif adapter_path.exists() and not should_skip:
        # Overwrite
        try:
            content, warnings = template_adapter_toml(project_name, host=host)
            adapter_path.write_text(content, encoding="utf-8")
            result["created"].append("file:adapter.toml (overwritten)")
            result["warnings"].extend(warnings)
            any_overwritten = True
        except Exception as exc:
            result["errors"].append(f"failed to overwrite adapter.toml: {exc}")
    else:
        # Create new
        try:
            content, warnings = template_adapter_toml(project_name, host=host)
            adapter_path.write_text(content, encoding="utf-8")
            result["created"].append("file:adapter.toml")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create adapter.toml: {exc}")

    # Create runtime required files not covered by FILE_TEMPLATES or KB_TEMPLATES
    # 3. memory/inbox.md - Runtime required by memory_hook_impls.py L531, L1374
    inbox_path = target / "memory" / "inbox.md"
    should_skip, reason = _should_skip_file(inbox_path, "memory/inbox.md", is_business_file=False)

    if inbox_path.exists() and should_skip:
        result["skipped"].append(f"file:memory/inbox.md ({reason})")
        any_skipped = True
    elif inbox_path.exists() and not should_skip:
        # Overwrite
        try:
            content, warnings = template_inbox_md(project_name)
            inbox_path.write_text(content, encoding="utf-8")
            result["created"].append("file:memory/inbox.md (overwritten)")
            result["warnings"].extend(warnings)
            any_overwritten = True
        except Exception as exc:
            result["errors"].append(f"failed to overwrite memory/inbox.md: {exc}")
    else:
        # Create new
        try:
            content, warnings = template_inbox_md(project_name)
            inbox_path.write_text(content, encoding="utf-8")
            result["created"].append("file:memory/inbox.md")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create memory/inbox.md: {exc}")

    # 4. memory/kb/global/memory-hook-policy-pack.json - Runtime required by memory_hook_impls.py L281
    policy_pack_path = target / "memory" / "kb" / "global" / "memory-hook-policy-pack.json"
    should_skip, reason = _should_skip_file(policy_pack_path, "memory/kb/global/memory-hook-policy-pack.json", is_business_file=False)

    if policy_pack_path.exists() and should_skip:
        result["skipped"].append(f"file:memory/kb/global/memory-hook-policy-pack.json ({reason})")
        any_skipped = True
    elif policy_pack_path.exists() and not should_skip:
        # Overwrite
        try:
            content, warnings = template_policy_pack_json(project_name)
            policy_pack_path.write_text(content, encoding="utf-8")
            result["created"].append("file:memory/kb/global/memory-hook-policy-pack.json (overwritten)")
            result["warnings"].extend(warnings)
            any_overwritten = True
        except Exception as exc:
            result["errors"].append(f"failed to overwrite memory-hook-policy-pack.json: {exc}")
    else:
        # Create new
        try:
            content, warnings = template_policy_pack_json(project_name)
            policy_pack_path.write_text(content, encoding="utf-8")
            result["created"].append("file:memory/kb/global/memory-hook-policy-pack.json")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create memory-hook-policy-pack.json: {exc}")

    # 5. memory/kb/projects/{scope}.md - Runtime required by memory_hook_core.py L207-210
    scope_md_path = target / "memory" / "kb" / "projects" / f"{project_name}.md"
    should_skip, reason = _should_skip_file(scope_md_path, f"memory/kb/projects/{project_name}.md", is_business_file=False)

    if scope_md_path.exists() and should_skip:
        result["skipped"].append(f"file:memory/kb/projects/{project_name}.md ({reason})")
        any_skipped = True
    elif scope_md_path.exists() and not should_skip:
        # Overwrite
        try:
            content, warnings = template_project_scope_md(project_name)
            scope_md_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:memory/kb/projects/{project_name}.md (overwritten)")
            result["warnings"].extend(warnings)
            any_overwritten = True
        except Exception as exc:
            result["errors"].append(f"failed to overwrite memory/kb/projects/{project_name}.md: {exc}")
    else:
        # Create new
        try:
            content, warnings = template_project_scope_md(project_name)
            scope_md_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:memory/kb/projects/{project_name}.md")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create memory/kb/projects/{project_name}.md: {exc}")

    result["success"] = len(result["errors"]) == 0

    # 6. Create per-scope control loop directory: memory/kb/projects/{scope}/
    #    and generate CANONICAL.md, STATE.md, PLAN.md, TASKS.md
    scope_dir = target / "memory" / "kb" / "projects" / project_name
    try:
        scope_dir.mkdir(parents=True, exist_ok=True)
        result["created"].append(f"dir:memory/kb/projects/{project_name}/")
    except Exception as exc:
        result["errors"].append(f"failed to create per-scope directory: {exc}")

    # Helper to write a per-scope template file with idempotency
    def _write_per_scope_template(
        fname: str,
        template_fn: Any,
        content_label: str,
    ) -> None:
        nonlocal any_overwritten, any_skipped
        file_path = scope_dir / fname
        should_skip, reason = _should_skip_file(
            file_path, f"memory/kb/projects/{project_name}/{fname}", is_business_file=False,
        )
        if file_path.exists() and should_skip:
            result["skipped"].append(f"file:memory/kb/projects/{project_name}/{fname} ({reason})")
            any_skipped = True
            return
        if file_path.exists() and not should_skip:
            try:
                content, warnings = template_fn(project_name)
                file_path.write_text(content, encoding="utf-8")
                result["created"].append(f"file:memory/kb/projects/{project_name}/{fname} (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite {content_label}: {exc}")
            return
        # Create new
        try:
            content, warnings = template_fn(project_name)
            file_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:memory/kb/projects/{project_name}/{fname}")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create {content_label}: {exc}")

    _write_per_scope_template("CANONICAL.md", template_canonical_md, "CANONICAL.md")
    _write_per_scope_template("STATE.md", template_state_md, "STATE.md")
    _write_per_scope_template("PLAN.md", template_plan_md, "PLAN.md")
    _write_per_scope_template("TASKS.md", template_tasks_md, "TASKS.md")

    # 7. NOW.md at project root
    now_md_path = target / "NOW.md"
    should_skip, reason = _should_skip_file(now_md_path, "NOW.md", is_business_file=False)
    if now_md_path.exists() and should_skip:
        result["skipped"].append(f"file:NOW.md ({reason})")
        any_skipped = True
    elif now_md_path.exists() and not should_skip:
        try:
            content, warnings = template_now_md(project_name)
            now_md_path.write_text(content, encoding="utf-8")
            result["created"].append("file:NOW.md (overwritten)")
            result["warnings"].extend(warnings)
            any_overwritten = True
        except Exception as exc:
            result["errors"].append(f"failed to overwrite NOW.md: {exc}")
    else:
        try:
            content, warnings = template_now_md(project_name)
            now_md_path.write_text(content, encoding="utf-8")
            result["created"].append("file:NOW.md")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create NOW.md: {exc}")

    result["force_overwrite"] = force

    # Preserve legacy mode outcomes for create mode while exposing the requested mode separately.
    result["action_taken"] = "overwrite" if any_overwritten else ("skip" if any_skipped else "create")
    if not dry_run:
        result["mode"] = result["action_taken"] if mode == "create" else mode

    # Auto-fill: detect project info and fill templates (default: enabled)
    if result["success"] and auto_fill and not dry_run:
        try:
            from .project_probe import ProjectProbe
            probe = ProjectProbe(target)
            project_info = probe.probe()
            _apply_auto_fill(target, project_info, result, project_name=project_name)
        except Exception as exc:
            result["warnings"].append(f"auto-fill skipped: {exc}")

    # Generate hooks.json and AGENTS.md after memory/system/ is ready
    if result["success"]:
        # Generate memory-init-fill skill YAML (unconditional, no --sync needed)
        try:
            from .template_sync import generate_skill_memory_init_fill_yaml
            _fill_skill_content = generate_skill_memory_init_fill_yaml(project_name)
            if _fill_skill_content:
                _fill_skills_dir = target / "memory" / "system" / "skills"
                _fill_skills_dir.mkdir(parents=True, exist_ok=True)
                _fill_skill_path = _fill_skills_dir / "memory-init-fill.yaml"
                if not _fill_skill_path.exists() or force:
                    _fill_skill_path.write_text(_fill_skill_content, encoding="utf-8")
                    result["created"].append("file:memory/system/skills/memory-init-fill.yaml")
                else:
                    result["skipped"].append("file:memory/system/skills/memory-init-fill.yaml (exists)")
        except Exception as exc:
            result["warnings"].append(f"memory-init-fill skill generation skipped: {exc}")

        generate_hooks_json(target, host=host, result=result)
        update_agents_md(target, host=host, result=result, mode=mode)

        # Sync configuration: write CI template + docs (protocol layer only)
        if sync_enabled:
            _generate_sync_files(
                target,
                project_name=project_name,
                source_remote=sync_source_remote,
                mirror_remote=sync_mirror_remote,
                mirror_url=sync_mirror_url,
                result=result,
                force=force,
            )

        # L2: Sign initial manifest after memory/system/ is scaffolded
        # F2: Use sign_project_incremental with changed_paths=所有新建文件相对路径
        # First run: manifest doesn't exist, falls back to full sign automatically
        try:
            from .memory_hook_integrity_keys import load_or_create_key
            from .memory_hook_integrity_manifest import sign_project_incremental

            key = load_or_create_key()

            # Collect all newly created file relative paths from result["created"]
            changed_paths: list[str] = []
            for entry in result.get("created", []):
                if entry.startswith("file:"):
                    # Strip "file:" prefix and any " (detail)" suffix
                    path_part = entry[len("file:"):]
                    paren_idx = path_part.find(" (")
                    if paren_idx >= 0:
                        path_part = path_part[:paren_idx]
                    changed_paths.append(path_part)

            sign_project_incremental(
                target, key, changed_paths=changed_paths,
                reason="memory-init baseline",
            )
            result["created"].append("file:memory/system/manifest.json (signed)")
        except Exception as exc:
            # Non-blocking: integrity signing is best-effort
            result["warnings"].append(f"integrity signing skipped: {exc}")

        # Create initial integrity-audit.jsonl
        try:
            import json as _json
            _audit_path = memory_root / "integrity-audit.jsonl"
            if not _audit_path.exists():
                _audit_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "action": "init",
                    "version": CURRENT_MEMORY_VERSION,
                    "project": project_name,
                    "reason": "initial scaffold",
                }
                _audit_path.write_text(
                    _json.dumps(_audit_entry, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                result["created"].append("file:memory/system/integrity-audit.jsonl")
        except Exception as exc:
            result["warnings"].append(f"integrity-audit.jsonl creation skipped: {exc}")

        # Step 2.1: Generate ownership.toml (after integrity signing, only if not dry_run)
        if not dry_run:
            try:
                ownership_path = memory_root / "ownership.toml"
                should_skip, _ = _should_skip_file(ownership_path, "ownership.toml", is_business_file=False)
                if not should_skip:
                    content, warnings = template_ownership_toml(project_name)
                    ownership_path.write_text(content, encoding="utf-8")
                    result["created"].append("file:ownership.toml")
                    result["warnings"].extend(warnings)
                else:
                    if ownership_path.exists():
                        # In update mode, patch memory_version instead of full skip
                        if mode == "update":
                            try:
                                from .version_sync import patch_ownership_memory_version
                            except ImportError:
                                from memory_core.tools.version_sync import (
                                    patch_ownership_memory_version,  # type: ignore
                                )
                            if patch_ownership_memory_version(ownership_path, CURRENT_MEMORY_VERSION):
                                result["created"].append(f"file:ownership.toml (memory_version patched to {CURRENT_MEMORY_VERSION})")
                            else:
                                result["skipped"].append("file:ownership.toml (already up-to-date)")
                        else:
                            result["skipped"].append("file:ownership.toml (already exists)")
            except Exception as exc:
                result["errors"].append(f"failed to create ownership.toml: {exc}")

        # Post-write evidence ref check: verify all KB evidence refs exist on disk
        if not dry_run:
            try:
                from memory_core.tools.evidence_ref_validator import validate_evidence_refs_on_disk
                ref_errors = validate_evidence_refs_on_disk(target)
                for err in ref_errors:
                    result["warnings"].append(
                        f"evidence ref check: {err.kb_file} has {len(err.missing_refs)} missing refs: "
                        f"{', '.join(err.missing_refs[:3])}"
                    )
            except Exception as exc:
                # Non-blocking: best-effort check
                result["warnings"].append(f"evidence ref check skipped: {exc}")

    return result


def _find_repo_root(path: Path) -> Path | None:
    """Walk up from path to find the git repository root."""
    current = path.resolve()
    while current != current.parent:
        if (current / ".git").is_dir():
            return current
        current = current.parent
    return None


def _is_memory_repo(repo_root: Path) -> bool:
    """Heuristic: is this repo the memory repo?

    Requires the memory_hook_gateway.py marker (unique to this repo)
    AND either the memory/ directory or memory_core/ package.
    """
    gateway_marker = repo_root / "memory_core" / "tools" / "memory_hook_gateway.py"
    if not gateway_marker.is_file():
        return False
    # Memory repo has both: gateway + repo-root memory/ directory
    return (repo_root / "memory").is_dir()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize a memory/system/ directory skeleton in a target project."
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project root (business project repository).",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default=None,
        help="Explicit project scope name. If omitted, auto-discovered from git remote or directory name.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be created without writing files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="codex",
        choices=SUPPORTED_HOSTS,
        help="Host platform for hook gateway configuration (default: codex).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing files (default: skip existing files).",
    )
    parser.add_argument(
        "--no-clobber",
        action="store_true",
        default=False,
        help="Error if any essential file already exists (mutually exclusive with --force).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="create",
        choices=["create", "adopt", "update", "repair"],
        help="Initialization mode: create (default), adopt, update, or repair.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        default=False,
        help="Enable sync configuration (source-to-mirror CI pipeline + iron rule docs).",
    )
    parser.add_argument(
        "--sync-source-remote",
        type=str,
        default="origin",
        help="Source remote name (default: origin). Used with --sync.",
    )
    parser.add_argument(
        "--sync-mirror-remote",
        type=str,
        default="",
        help="Mirror remote name (e.g. github). Used with --sync.",
    )
    parser.add_argument(
        "--sync-mirror-url",
        type=str,
        default="",
        help="Mirror URL (e.g. github.com/org/repo). Used with --sync.",
    )
    parser.add_argument(
        "--no-auto-fill",
        action="store_true",
        default=False,
        help="Disable automatic project info detection and template filling.",
    )
    try:
        _pkg_version = importlib.metadata.version("memory-core")
    except importlib.metadata.PackageNotFoundError:
        _pkg_version = "unknown"
    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version}")
    args = parser.parse_args(argv)

    # Validate mutually exclusive options
    if args.force and args.no_clobber:
        print(
            "Error: --force and --no-clobber are mutually exclusive. "
            "Use --force to overwrite, or --no-clobber to error on existing files.",
            file=sys.stderr,
        )
        return 2

    target = args.target.resolve()
    if not target.is_dir():
        print(f"Error: target path does not exist or is not a directory: {target}", file=sys.stderr)
        return 2

    result = init_project_memory(
        target,
        scope=args.scope,
        host=args.host,
        dry_run=args.dry_run,
        json_output=args.json,
        force=args.force,
        no_clobber=args.no_clobber,
        mode=args.mode,
        sync_enabled=args.sync,
        sync_source_remote=args.sync_source_remote,
        sync_mirror_remote=args.sync_mirror_remote,
        sync_mirror_url=args.sync_mirror_url,
        auto_fill=not args.no_auto_fill,
    )

    if args.json or args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Project Memory Initialization Report")
        print("=" * 60)
        if result["dry_run"]:
            print(f"  [DRY RUN] Would initialize memory/system/ under: {result['target']}")
            do = result.get("dry_run_output", {})
            print(f"  Project name: {do.get('project_name', 'N/A')}")
            print(f"  Would create {len(do.get('would_create_dirs', []))} directories")
            print(f"  Would create {len(do.get('would_create_files', []))} files")
        else:
            for path in result.get("created", []):
                print(f"  [CREATE] {path}")
            for path in result.get("skipped", []):
                print(f"  [SKIP]   {path}")
            for err in result.get("errors", []):
                print(f"  [ERROR]  {err}")
            for warning in result.get("warnings", []):
                print(f"  [WARN]   {warning}")
        print("-" * 60)
        status = "SUCCESS" if result["success"] else "FAILED"
        print(f"  Status: {status}")
        print(f"  Init Mode: {result.get('mode', 'create')}")
        if result.get("force_overwrite"):
            print("  Force overwrite: True")
        print("=" * 60)

        if result["success"] and not result["dry_run"]:
            _print_post_init_health_summary(target)

    return 0 if result["success"] else 1


def _generate_sync_files(
    target: Path,
    *,
    project_name: str,
    source_remote: str,
    mirror_remote: str,
    mirror_url: str,
    result: dict[str, Any],
    force: bool = False,
) -> None:
    """Write sync-related files: .gitlab-ci.yml, adapter.toml [sync], docs blocks.

    Pure text generation -- no remote API calls.
    """
    try:
        from .adapter_toml_schema import SyncConfig, dump_sync_toml
        from .template_sync import (
            generate_agents_md_sync_block,
            generate_contributing_sync_block,
            generate_gitlab_ci_yml,
            generate_skill_workflow_yaml,
        )
    except ImportError:
        from memory_core.tools.adapter_toml_schema import (  # type: ignore
            SyncConfig,
            dump_sync_toml,
        )
        from memory_core.tools.template_sync import (  # type: ignore
            generate_agents_md_sync_block,
            generate_contributing_sync_block,
            generate_gitlab_ci_yml,
            generate_skill_workflow_yaml,
        )

    sync = SyncConfig(
        enabled=True,
        source_remote=source_remote,
        mirror_remote=mirror_remote,
        mirror_url=mirror_url,
    )

    # 1. .gitlab-ci.yml
    ci_path = target / ".gitlab-ci.yml"
    if not ci_path.exists() or force:
        ci_content = generate_gitlab_ci_yml(sync, project_slug=project_name)
        ci_path.write_text(ci_content, encoding="utf-8")
        result["created"].append("file:.gitlab-ci.yml (sync)")
    else:
        result["skipped"].append("file:.gitlab-ci.yml (exists, use --force)")

    # 2. Skill workflow template
    skills_dir = target / "memory" / "system" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skills_dir / "gitlab_sync_workflow.yaml"
    if not skill_path.exists() or force:
        skill_content = generate_skill_workflow_yaml(sync)
        skill_path.write_text(skill_content, encoding="utf-8")
        result["created"].append("file:memory/system/skills/gitlab_sync_workflow.yaml")
    else:
        result["skipped"].append("file:memory/system/skills/gitlab_sync_workflow.yaml (exists, use --force)")

    # 3. Append [sync] to adapter.toml
    adapter_path = target / "memory" / "system" / "adapter.toml"
    if adapter_path.exists():
        existing = adapter_path.read_text(encoding="utf-8")
        toml_additions = ""
        if "[sync]" not in existing:
            toml_additions += dump_sync_toml(sync)

        if toml_additions:
            adapter_path.write_text(existing + toml_additions, encoding="utf-8")
            result["created"].append("file:memory/system/adapter.toml [sync] section")
        else:
            result["skipped"].append("file:memory/system/adapter.toml [sync] (exists)")
    else:
        result["warnings"].append("adapter.toml not found; [sync] not written")

    # 4. Append iron rule block to AGENTS.md
    agents_path = target / "AGENTS.md"
    sync_block = generate_agents_md_sync_block(sync)
    if sync_block and agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        if "SYNC_IRON_RULE_BEGIN" not in content:
            agents_path.write_text(content.rstrip("\n") + "\n\n" + sync_block, encoding="utf-8")
            result["created"].append("file:AGENTS.md (sync iron rule)")
        else:
            result["skipped"].append("file:AGENTS.md (sync iron rule exists)")

    # 5. Append contributing section
    contrib_path = target / "CONTRIBUTING.md"
    contrib_block = generate_contributing_sync_block(sync)
    if contrib_block and contrib_path.exists():
        content = contrib_path.read_text(encoding="utf-8")
        if "Sync Rule" not in content:
            contrib_path.write_text(content.rstrip("\n") + "\n\n" + contrib_block, encoding="utf-8")
            result["created"].append("file:CONTRIBUTING.md (sync rule)")
        else:
            result["skipped"].append("file:CONTRIBUTING.md (sync rule exists)")


def _print_post_init_health_summary(target: Path) -> None:
    """Print a brief post-init consumer self-check summary.

    Best-effort: any failure is swallowed so it never breaks init.
    """
    try:
        try:
            from .verify_consumer import verify
        except ImportError:
            from memory_core.tools.verify_consumer import verify  # type: ignore
        report = verify(target)
        passed = sum(1 for c in report.checks if c.passed)
        total = len(report.checks)
        marker = "OK" if report.all_passed else "ATTENTION"
        print()
        print(f"Post-init consumer self-check: {marker} ({passed}/{total} checks passed)")
        if not report.all_passed:
            print("  Failed checks:")
            for c in report.checks:
                if not c.passed:
                    print(f"    - {c.name}: {c.detail}")
            print(f"  Run 'memory-verify-consumer --path {target}' for full details.")
    except Exception:  # pragma: no cover - never break init
        return


if __name__ == "__main__":
    raise SystemExit(main())
