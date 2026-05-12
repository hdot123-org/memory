#!/usr/bin/env python3
"""Initialize a .memory/ directory skeleton in a target project.

Usage:
    python init_project_memory.py --target /path/to/project
    python init_project_memory.py --target /path/to/project --dry-run
    python init_project_memory.py --target /path/to/project --dry-run --json
    python init_project_memory.py --target /path/to/project --host claude
    python init_project_memory.py --target /path/to/project --force
    python init_project_memory.py --target /path/to/project --no-clobber

This tool creates the minimal .memory/ directory structure required by the
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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_core.constants import (
    CANONICAL_ADAPTER_VERSION,
    CANONICAL_MEMORY_LOCK_SCHEMA,
    CURRENT_MEMORY_VERSION,
    SUPPORTED_HOSTS,
)

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

# Directory structure to create under .memory/
DIRECTORY_STRUCTURE = [
    ".memory",
    ".memory/kb",
    ".memory/kb/projects",
    ".memory/kb/decisions",
    ".memory/kb/lessons",
    ".memory/kb/global",
    "project-map",
    "memory",
    "memory/kb",
    "memory/kb/global",
    "memory/kb/projects",
    "memory/kb/decisions",
    "memory/kb/lessons",
    "memory/docs",
    "memory/system",
    "memory/log",
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

    Reads the template from workspace/templates/.memory/adapter.toml and
    replaces placeholders with actual values.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        # Locate the memory-core repo root (parent of memory_core/)
        _repo_root = Path(__file__).resolve().parent.parent.parent
        _template_path = _repo_root / "workspace" / "templates" / ".memory" / "adapter.toml"

        if _template_path.is_file():
            content = _template_path.read_text(encoding="utf-8")
        else:
            # Fallback inline canonical template
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
canonical_files = ["CANONICAL.md", "STATE.md"]
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
    """Generate CANONICAL.md with frontmatter.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f"""\
---
type: "KB:PROJECT"
title: "{project_name} Project Canonical"
shortname: "{project_name}"
status: active
created: "{now}"
updated: "{now}"
scope: project
source: local-canonical
confidence: high
tags: [project, initialized]
---

# {project_name} Project Canonical

## 目标

项目记忆系统已初始化。

## 仓库

| 位置 | 路径 |
|------|------|
| 本地仓库 | `{Path.cwd()}` |

## Truth Basis

### Source Refs
- `workspace/INDEX.md`

### Authority Refs
- `.memory/CANONICAL.md`

### Conflict Status
- `active`

## 项目信息

| 字段 | 值 |
|------|-----|
| 项目名称 | {project_name} |
| 项目类型 | （待填写） |
| 主语言 | （待填写） |
| 创建日期 | {now} |

## 编码规范

（待填写：项目编码标准描述，如缩进、编码风格等）

## 架构约束

（待填写：架构层面的约束条件，如设计模式、分层要求等）

## 命名约定

（待填写：变量、函数、文件命名规则）

## 工具链

| 工具 | 版本/说明 |
|------|----------|
| （待填写） | （待填写） |

## 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| {now} | 1.0.0 | 初始规范建立 |
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in CANONICAL.md: {exc}")
        warnings.append(f"template_canonical_md: {exc}")
        # Safe fallback with placeholders
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
---
type: "KB:PROJECT"
title: "{{project_name}} Project Canonical"
shortname: "{{project_name}}"
status: active
created: "{now}"
updated: "{now}"
scope: project
source: local-canonical
confidence: high
tags: [project, initialized]
---

# {{project_name}} Project Canonical

## 目标

项目记忆系统已初始化。

## 仓库

| 位置 | 路径 |
|------|------|
| 本地仓库 | `{Path.cwd()}` |

## Truth Basis

### Source Refs
- `workspace/INDEX.md`

### Authority Refs
- `.memory/CANONICAL.md`

### Conflict Status
- `active`

## 项目信息

| 字段 | 值 |
|------|-----|
| 项目名称 | {{project_name}} |
| 项目类型 | （待填写） |
| 主语言 | （待填写） |
| 创建日期 | {now} |

## 编码规范

（待填写：项目编码标准描述，如缩进、编码风格等）

## 架构约束

（待填写：架构层面的约束条件，如设计模式、分层要求等）

## 命名约定

（待填写：变量、函数、文件命名规则）

## 工具链

| 工具 | 版本/说明 |
|------|----------|
| （待填写） | （待填写） |

## 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| {now} | 1.0.0 | 初始规范建立 |
"""
    return content, warnings


def template_plan_md(project_name: str) -> tuple[str, list[str]]:
    """Generate PLAN.md with frontmatter.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f"""\
---
type: "KB:PLAN"
title: "{project_name} Plan"
shortname: "{project_name}"
status: planning
created: "{now}"
---

# {project_name} Plan

## 任务概述

| 字段 | 值 |
|------|-----|
| 任务 ID | （待填写） |
| 任务名称 | （待填写） |
| 优先级 | （待填写：high / medium / low） |
| 创建日期 | {now} |

## 目标

（待填写）

## 范围

（待填写）

## 执行计划

| 步骤 | 描述 | 状态 | 完成日期 |
|------|------|------|----------|
| 1 | （待填写） | planning | - |
| 2 | （待填写） | planning | - |
| 3 | （待填写） | planning | - |

## 验收标准

- [ ] （待填写：验收条件 1）
- [ ] （待填写：验收条件 2）
- [ ] （待填写：验收条件 3）

## 风险与依赖

| 类型 | 描述 | 缓解措施 |
|------|------|----------|
| 风险 | （待填写） | （待填写） |
| 依赖 | （待填写） | （待填写） |

## 状态

- **当前状态**: planning
- **上次更新**: {now}
- **进度**: 0%
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in PLAN.md: {exc}")
        warnings.append(f"template_plan_md: {exc}")
        # Safe fallback with placeholders
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
---
type: "KB:PLAN"
title: "{{project_name}} Plan"
shortname: "{{project_name}}"
status: planning
created: "{now}"
---

# {{project_name}} Plan

## 任务概述

| 字段 | 值 |
|------|-----|
| 任务 ID | （待填写） |
| 任务名称 | （待填写） |
| 优先级 | （待填写：high / medium / low） |
| 创建日期 | {now} |

## 目标

（待填写）

## 范围

（待填写）

## 执行计划

| 步骤 | 描述 | 状态 | 完成日期 |
|------|------|------|----------|
| 1 | （待填写） | planning | - |
| 2 | （待填写） | planning | - |
| 3 | （待填写） | planning | - |

## 验收标准

- [ ] （待填写：验收条件 1）
- [ ] （待填写：验收条件 2）
- [ ] （待填写：验收条件 3）

## 风险与依赖

| 类型 | 描述 | 缓解措施 |
|------|------|----------|
| 风险 | （待填写） | （待填写） |
| 依赖 | （待填写） | （待填写） |

## 状态

- **当前状态**: planning
- **上次更新**: {now}
- **进度**: 0%
"""
    return content, warnings


def template_state_md(project_name: str) -> tuple[str, list[str]]:
    """Generate STATE.md with frontmatter.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f"""\
---
type: "KB:STATE"
title: "{project_name} State"
shortname: "{project_name}"
status: active
updated: "{now}"
---

# {project_name} State

> 最后更新：{now}
> 更新者：init_project_memory

## 项目状态

| 字段 | 值 |
|------|-----|
| 状态 | active |
| 最后更新 | {now} |
| 健康度 | green |

## 上下文摘要

（待填写：项目上下文概要，包括当前阶段、主要目标等）

## 关键决策

| 日期 | 决策 | 状态 | 备注 |
|------|------|------|------|
| {now} | 初始化项目记忆系统 | decided | 首次建立 .memory/ 目录 |

## 当前工作区

（待填写：当前工作区描述，如正在进行的任务、分支等）

## 待处理事项

- [ ] （待填写：待处理事项 1）
- [ ] （待填写：待处理事项 2）
- [ ] （待填写：待处理事项 3）

## 已完成的里程碑

- [x] {now}：项目记忆系统初始化完成
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in STATE.md: {exc}")
        warnings.append(f"template_state_md: {exc}")
        # Safe fallback with placeholders
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
---
type: "KB:STATE"
title: "{{project_name}} State"
shortname: "{{project_name}}"
status: active
updated: "{now}"
---

# {{project_name}} State

> 最后更新：{now}
> 更新者：init_project_memory

## 项目状态

| 字段 | 值 |
|------|-----|
| 状态 | active |
| 最后更新 | {now} |
| 健康度 | green |

## 上下文摘要

（待填写：项目上下文概要，包括当前阶段、主要目标等）

## 关键决策

| 日期 | 决策 | 状态 | 备注 |
|------|------|------|------|
| {now} | 初始化项目记忆系统 | decided | 首次建立 .memory/ 目录 |

## 当前工作区

（待填写：当前工作区描述，如正在进行的任务、分支等）

## 待处理事项

- [ ] （待填写：待处理事项 1）
- [ ] （待填写：待处理事项 2）
- [ ] （待填写：待处理事项 3）

## 已完成的里程碑

- [x] {now}：项目记忆系统初始化完成
"""
    return content, warnings


def template_tasks_md(project_name: str) -> tuple[str, list[str]]:
    """Generate TASKS.md with frontmatter.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = f"""\
---
type: "KB:TASKS"
title: "{project_name} Tasks"
shortname: "{project_name}"
status: active
---

# {project_name} Tasks

## 活跃任务

| 任务 ID | 任务名称 | 优先级 | 状态 | 截止日期 |
|---------|----------|--------|------|----------|
| T-001 | （待填写） | medium | todo | - |

## 已完成任务

| 任务 ID | 任务名称 | 完成日期 | 备注 |
|---------|----------|----------|------|
| - | - | - | - |

## 已取消任务

| 任务 ID | 任务名称 | 取消日期 | 原因 |
|---------|----------|----------|------|
| - | - | - | - |

## 阻塞项

| 阻塞项 | 描述 | 依赖 | 预计解决 |
|--------|------|------|----------|
| （待填写） | （待填写） | （待填写） | （待填写） |
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in TASKS.md: {exc}")
        warnings.append(f"template_tasks_md: {exc}")
        # Safe fallback with placeholders
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
---
type: "KB:TASKS"
title: "{{project_name}} Tasks"
shortname: "{{project_name}}"
status: active
---

# {{project_name}} Tasks

## 活跃任务

| 任务 ID | 任务名称 | 优先级 | 状态 | 截止日期 |
|---------|----------|--------|------|----------|
| T-001 | （待填写） | medium | todo | - |

## 已完成任务

| 任务 ID | 任务名称 | 完成日期 | 备注 |
|---------|----------|----------|------|
| - | - | - | - |

## 已取消任务

| 任务 ID | 任务名称 | 取消日期 | 原因 |
|---------|----------|----------|------|
| - | - | - | - |

## 阻塞项

| 阻塞项 | 描述 | 依赖 | 预计解决 |
|--------|------|------|----------|
| （待填写） | （待填写） | （待填写） | （待填写） |
"""
    return content, warnings


def template_now_md(project_name: str) -> tuple[str, list[str]]:
    """Generate NOW.md with frontmatter for current task snapshot.

    Runtime required: referenced by memory_hook_core.py reads list.

    Returns:
        Tuple of (content, warnings_list)
    """
    now = _now_iso()
    warnings: list[str] = []
    try:
        content = f"""\
---
type: "KB:STATE"
title: "{project_name} Current State"
shortname: "{project_name}"
status: active
created: "{now}"
updated: "{now}"
---

# {project_name} 当前状态

> 最后更新：{now}

## 当前任务

（待填写：当前正在执行的主要任务）

## 下一步行动

- [ ] （待填写：下一步行动 1）
- [ ] （待填写：下一步行动 2）
- [ ] （待填写：下一步行动 3）

## 阻塞项

- （待填写：当前阻塞项）

## 上下文摘要

（待填写：当前上下文简要描述）
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in NOW.md: {exc}")
        warnings.append(f"template_now_md: {exc}")
        content = f"""\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
---
type: "KB:STATE"
title: "{{project_name}} Current State"
shortname: "{{project_name}}"
status: active
created: "{now}"
updated: "{now}"
---

# {{project_name}} 当前状态

> 最后更新：{now}

## 当前任务

（待填写：当前正在执行的主要任务）

## 下一步行动

- [ ] （待填写：下一步行动 1）
- [ ] （待填写：下一步行动 2）
- [ ] （待填写：下一步行动 3）

## 阻塞项

- （待填写：当前阻塞项）

## 上下文摘要

（待填写：当前上下文简要描述）
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
        "- memory_core/project-map/**: incoming-raw\n"
        "- memory_core/memory/kb/global/**: active-legal\n"
        "- memory_core/memory/kb/projects/**: compatibility-only\n"
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
    # Runtime required: NOW.md referenced by memory_hook_core.py L226-236
    "NOW.md": lambda scope: template_now_md(scope),
}

FILE_TEMPLATES: dict[str, Any] = {
    "memory.lock": lambda pn: template_memory_lock(pn),
    "CANONICAL.md": lambda pn: template_canonical_md(pn),
    "PLAN.md": lambda pn: template_plan_md(pn),
    "STATE.md": lambda pn: template_state_md(pn),
    "TASKS.md": lambda pn: template_tasks_md(pn),
    "migrations.log": lambda pn: template_migrations_log(pn),
}

# Essential files that must be checked for --no-clobber
ESSENTIAL_FILES = [
    "memory.lock",
    "CANONICAL.md",
    "PLAN.md",
    "STATE.md",
    "TASKS.md",
    "migrations.log",
    "adapter.toml",
]

# Runtime required KB files (under workspace_root, not .memory/)
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

def template_hooks_json(host: str = "claude") -> dict[str, Any]:
    """Generate hooks.json content as a dict."""
    hooks: list[dict[str, Any]] = []
    for claude_event, gateway_event in CLAUDE_HOOK_EVENTS:
        hooks.append({
            "event": claude_event,
            "command": f"memory-hook-gateway --host {host} --event {gateway_event}",
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

    If the file already exists, only append missing memory hook entries
    (idempotent — does not overwrite existing hooks from other tools).
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
        existing_keys = {(h["event"], h["command"]) for h in existing_hooks}
        missing_keys = desired_keys - existing_keys

        if not missing_keys:
            result["skipped"].append("file:.claude/hooks.json (up-to-date)")
            return

        for hook in desired["hooks"]:
            if (hook["event"], hook["command"]) in missing_keys:
                existing_hooks.append(hook)
        existing["hooks"] = existing_hooks
        content = json.dumps(existing, indent=2, ensure_ascii=False) + "\n"
    else:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(desired, indent=2, ensure_ascii=False) + "\n"

    hooks_path.write_text(content, encoding="utf-8")
    result["created"].append("file:.claude/hooks.json")


def template_agents_md_block(host: str = "codex") -> str:
    """Generate the AGENTS.md memory hook instruction block."""
    return f"""{MEMORY_HOOK_BEGIN_MARKER}
## Memory Hook

When starting a session, run the memory hook gateway to load project context:

```bash
memory-hook-gateway --host {host} --event session-start
```
{MEMORY_HOOK_END_MARKER}
"""


def update_agents_md(
    target: Path,
    *,
    host: str = "codex",
    result: dict[str, Any] | None = None,
) -> None:
    """Insert or update the Memory Hook instruction block in AGENTS.md.

    Idempotent: if the markers already exist, the block content is replaced
    in-place rather than appended.
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

            agents_path.write_text(new_content, encoding="utf-8")
            result["created"].append("file:AGENTS.md (hook block updated)")
            return

        new_content = content.rstrip("\n") + "\n\n" + new_block
    else:
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
) -> dict[str, Any]:
    """Initialize .memory/ directory skeleton in the target project.

    Args:
        target: Path to the target project root.
        scope: Explicit project scope name (auto-discovered if omitted).
        host: Host platform for hook config ("codex" or "claude").
        dry_run: If True, only report what would be created.
        json_output: If True, return structured output dict.
        force: If True, overwrite existing files.
        no_clobber: If True, error if any essential file already exists.

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
        "mode": "create",
        "warnings": [],
        "force_overwrite": False,
    }

    memory_root = target / ".memory"
    project_name = _project_name(target, scope)

    # Check for existing essential files for --no-clobber
    if no_clobber:
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
                f"refused to clobber existing .memory; use --force to overwrite "
                f"or remove existing files first. Existing files: {', '.join(existing_essential)}"
            )
            result["mode"] = "error"
            return result

    # Check dry-run mode
    if dry_run:
        result["success"] = True
        dry_run_output: dict[str, Any] = {
            "would_create_dirs": list(DIRECTORY_STRUCTURE),
            "would_create_files": [],
            "project_name": project_name,
        }
        # Check which files would be created/overwritten (under .memory/)
        for fname in ESSENTIAL_FILES:
            file_path = memory_root / fname
            if file_path.exists():
                if force:
                    dry_run_output["would_create_files"].append(f"{fname} (overwrite)")
                else:
                    dry_run_output["would_create_files"].append(f"{fname} (skip - exists)")
            else:
                dry_run_output["would_create_files"].append(f"{fname} (create)")
        # Check runtime KB files (under workspace_root)
        for fname in RUNTIME_KB_FILES:
            file_path = target / fname
            if file_path.exists():
                if force:
                    dry_run_output["would_create_files"].append(f"{fname} (overwrite)")
                else:
                    dry_run_output["would_create_files"].append(f"{fname} (skip - exists)")
            else:
                dry_run_output["would_create_files"].append(f"{fname} (create)")
        # Check project scope file
        scope_file = f"memory/kb/projects/{project_name}.md"
        scope_path = target / scope_file
        if scope_path.exists():
            if force:
                dry_run_output["would_create_files"].append(f"{scope_file} (overwrite)")
            else:
                dry_run_output["would_create_files"].append(f"{scope_file} (skip - exists)")
        else:
            dry_run_output["would_create_files"].append(f"{scope_file} (create)")
        # Check KB_TEMPLATES files
        for fname in KB_TEMPLATES:
            file_path = target / fname
            if file_path.exists():
                if force:
                    dry_run_output["would_create_files"].append(f"{fname} (overwrite)")
                else:
                    dry_run_output["would_create_files"].append(f"{fname} (skip - exists)")
            else:
                dry_run_output["would_create_files"].append(f"{fname} (create)")
        # Check extra runtime files
        for fname in RUNTIME_EXTRA_FILES:
            file_path = target / fname
            if file_path.exists():
                if force:
                    dry_run_output["would_create_files"].append(f"{fname} (overwrite)")
                else:
                    dry_run_output["would_create_files"].append(f"{fname} (skip - exists)")
            else:
                dry_run_output["would_create_files"].append(f"{fname} (create)")
        result["dry_run_output"] = dry_run_output
        result["force_overwrite"] = force
        result["mode"] = "dry-run"
        return result

    # Safety guard: do NOT initialize inside the memory repo itself
    repo_root = _find_repo_root(target)
    if repo_root and _is_memory_repo(repo_root):
        result["errors"].append(
            "Refusing to initialize .memory/ inside the memory repository itself. "
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
        if dir_rel == ".memory":
            continue
        keep_path = target / dir_rel / ".keep"
        if not keep_path.exists():
            try:
                keep_path.write_text("", encoding="utf-8")
                result["created"].append(f"file:{dir_rel}/.keep")
            except Exception as exc:
                result["errors"].append(f"failed to create {dir_rel}/.keep: {exc}")

    # Create template files
    any_overwritten = False
    any_skipped = False

    # 1. Write KB and Project Map templates first
    for fname, template_fn in KB_TEMPLATES.items():
        file_path = target / fname
        if file_path.exists():
            if force:
                try:
                    content, warnings = template_fn(project_name)
                    file_path.write_text(content, encoding="utf-8")
                    result["created"].append(f"file:{fname} (overwritten)")
                    any_overwritten = True
                except Exception as exc:
                    result["errors"].append(f"failed to overwrite {fname}: {exc}")
            else:
                result["skipped"].append(f"file:{fname} (already exists)")
                any_skipped = True
            continue
        try:
            content, warnings = template_fn(project_name)
            file_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:{fname}")
        except Exception as exc:
            result["errors"].append(f"failed to create {fname}: {exc}")

    # 2. Write legacy .memory/ templates
    for fname, template_fn in FILE_TEMPLATES.items():
        file_path = memory_root / fname
        if file_path.exists():
            if force:
                try:
                    content, warnings = template_fn(project_name)
                    file_path.write_text(content, encoding="utf-8")
                    result["created"].append(f"file:{fname} (overwritten)")
                    result["warnings"].extend(warnings)
                    any_overwritten = True
                except Exception as exc:
                    result["errors"].append(f"failed to overwrite {fname}: {exc}")
            else:
                result["skipped"].append(f"file:{fname} (already exists)")
                any_skipped = True
            continue
        try:
            content, warnings = template_fn(project_name)
            file_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:{fname}")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create {fname}: {exc}")

    # Create adapter.toml separately (requires host parameter)
    adapter_path = memory_root / "adapter.toml"
    if adapter_path.exists():
        if force:
            try:
                content, warnings = template_adapter_toml(project_name, host=host)
                adapter_path.write_text(content, encoding="utf-8")
                result["created"].append("file:adapter.toml (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite adapter.toml: {exc}")
        else:
            result["skipped"].append("file:adapter.toml (already exists)")
            any_skipped = True
    else:
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
    if inbox_path.exists():
        if force:
            try:
                content, warnings = template_inbox_md(project_name)
                inbox_path.write_text(content, encoding="utf-8")
                result["created"].append("file:memory/inbox.md (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite memory/inbox.md: {exc}")
        else:
            result["skipped"].append("file:memory/inbox.md (already exists)")
            any_skipped = True
    else:
        try:
            content, warnings = template_inbox_md(project_name)
            inbox_path.write_text(content, encoding="utf-8")
            result["created"].append("file:memory/inbox.md")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create memory/inbox.md: {exc}")

    # 4. memory/kb/global/memory-hook-policy-pack.json - Runtime required by memory_hook_impls.py L281
    policy_pack_path = target / "memory" / "kb" / "global" / "memory-hook-policy-pack.json"
    if policy_pack_path.exists():
        if force:
            try:
                content, warnings = template_policy_pack_json(project_name)
                policy_pack_path.write_text(content, encoding="utf-8")
                result["created"].append("file:memory/kb/global/memory-hook-policy-pack.json (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite memory-hook-policy-pack.json: {exc}")
        else:
            result["skipped"].append("file:memory/kb/global/memory-hook-policy-pack.json (already exists)")
            any_skipped = True
    else:
        try:
            content, warnings = template_policy_pack_json(project_name)
            policy_pack_path.write_text(content, encoding="utf-8")
            result["created"].append("file:memory/kb/global/memory-hook-policy-pack.json")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create memory-hook-policy-pack.json: {exc}")

    # 5. memory/kb/projects/{scope}.md - Runtime required by memory_hook_core.py L207-210
    scope_md_path = target / "memory" / "kb" / "projects" / f"{project_name}.md"
    if scope_md_path.exists():
        if force:
            try:
                content, warnings = template_project_scope_md(project_name)
                scope_md_path.write_text(content, encoding="utf-8")
                result["created"].append(f"file:memory/kb/projects/{project_name}.md (overwritten)")
                result["warnings"].extend(warnings)
                any_overwritten = True
            except Exception as exc:
                result["errors"].append(f"failed to overwrite memory/kb/projects/{project_name}.md: {exc}")
        else:
            result["skipped"].append(f"file:memory/kb/projects/{project_name}.md (already exists)")
            any_skipped = True
    else:
        try:
            content, warnings = template_project_scope_md(project_name)
            scope_md_path.write_text(content, encoding="utf-8")
            result["created"].append(f"file:memory/kb/projects/{project_name}.md")
            result["warnings"].extend(warnings)
        except Exception as exc:
            result["errors"].append(f"failed to create memory/kb/projects/{project_name}.md: {exc}")

    result["success"] = len(result["errors"]) == 0
    result["force_overwrite"] = force

    # Set mode based on what happened
    if any_overwritten:
        result["mode"] = "overwrite"
    elif any_skipped:
        result["mode"] = "skip"
    else:
        result["mode"] = "create"

    # Generate hooks.json and AGENTS.md after .memory/ is ready
    if result["success"]:
        generate_hooks_json(target, host=host, result=result)
        update_agents_md(target, host=host, result=result)

        # L2: Sign initial manifest after .memory/ is scaffolded
        try:
            from .memory_hook_integrity_keys import load_or_create_key
            from .memory_hook_integrity_manifest import sign_project
            key = load_or_create_key()
            sign_project(target, key)
            result["created"].append("file:.memory/manifest.json (signed)")
        except Exception as exc:
            # Non-blocking: integrity signing is best-effort
            result["warnings"].append(f"integrity signing skipped: {exc}")

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
    """Heuristic: is this repo the memory repo?"""
    indicators = [
        repo_root / "memory_core" / "tools" / "memory_hook_gateway.py",
        repo_root / "memory_core" / "memory",
    ]
    return any(p.is_file() or p.is_dir() for p in indicators)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize a .memory/ directory skeleton in a target project."
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
    )

    if args.json or args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Project Memory Initialization Report")
        print("=" * 60)
        if result["dry_run"]:
            print(f"  [DRY RUN] Would initialize .memory/ under: {result['target']}")
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
        if result.get("mode"):
            print(f"  Mode: {result['mode']}")
        if result.get("force_overwrite"):
            print("  Force overwrite: True")
        print("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
