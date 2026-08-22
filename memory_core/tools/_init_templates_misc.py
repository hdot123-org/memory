"""Miscellaneous templates: migrations, inbox, ownership, project scope."""

import logging
from datetime import UTC

from memory_core.constants import CURRENT_MEMORY_VERSION

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current date in ISO format (YYYY-MM-DD)."""
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%d")


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

临时任务捕获区。用于快速记录待处理事项，后续应整理到 Linear（唯一任务管理面板）。

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

临时任务捕获区。用于快速记录待处理事项，后续应整理到 Linear（唯一任务管理面板）。

## 待处理事项

- [ ] （待填写）

## 已归档

（已处理并归档的项）
"""
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
            lines.extend(
                [
                    "",
                    "[[domains]]",
                    f'name = "{domain.name}"',
                    f'path = "{domain.path}"',
                    f'level = "{domain.level.name.lower()}"',
                    f"recursive = {str(domain.recursive).lower()}",
                ]
            )
            if domain.description:
                lines.append(f'description = "{domain.description}"')

        lines.extend(
            [
                "",
                "# Resources: specific files under ownership protection",
            ]
        )

        # Add default resources
        from memory_core.ownership import DEFAULT_OWNERSHIP_RESOURCES

        for resource in DEFAULT_OWNERSHIP_RESOURCES:
            lines.extend(
                [
                    "",
                    "[[resources]]",
                    f'name = "{resource.name}"',
                    f'path = "{resource.path}"',
                    f'level = "{resource.level.name.lower()}"',
                ]
            )
            if resource.domain:
                lines.append(f'domain = "{resource.domain}"')
            if resource.description:
                lines.append(f'description = "{resource.description}"')

        lines.extend(
            [
                "",
                "# Policy: optional key-value pairs for ownership policy",
                "[policy]",
                f'project_name = "{project_name}"',
                "",
            ]
        )

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
