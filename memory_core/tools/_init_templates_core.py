"""Core template helpers and essential file templates."""

import logging
from datetime import UTC, datetime
from pathlib import Path

try:
    from .index_schema import build_headers, inject_headers, read_project_version
except ImportError:
    from memory_core.tools.index_schema import (
        build_headers,
        inject_headers,
        read_project_version,
    )

from memory_core.constants import (
    CANONICAL_ADAPTER_VERSION,
    CANONICAL_MEMORY_LOCK_SCHEMA,
    CURRENT_MEMORY_VERSION,
)

# Keep the historical logger name (memory_core.tools.init_project_memory) so
# caplog filters and log-based assertions in consumers/tests keep working
# after the module split.
logger = logging.getLogger("memory_core.tools.init_project_memory")


def _is_index_md(fname: str) -> bool:
    return fname == "INDEX.md" or fname.endswith("/INDEX.md")


def _decorate_index_content(fname: str, content: str) -> str:
    """Inject memory-core + index-schema headers into INDEX.md content."""
    if not _is_index_md(fname):
        return content
    headers = build_headers(read_project_version())
    return inject_headers(content, headers)


def _now_iso() -> str:
    """Return current date in ISO format (YYYY-MM-DD)."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


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
            capture_output=True,
            text=True,
            timeout=5,
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


def template_adapter_toml(project_name: str) -> tuple[str, list[str]]:
    """Generate adapter.toml content conforming to the canonical schema.

    Uses inline canonical template (no external template file needed).
    Host is fixed to "factory" (INV-1, INV-6).

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

[global_kb]
enabled = true
root = "~/.memory/global-kb"
"""

        # Replace placeholders
        content = content.replace("{{memory_version}}", CURRENT_MEMORY_VERSION)
        content = content.replace("{{project_name}}", project_name)
        content = content.replace("{{project_scope}}", project_name)
        content = content.replace("{{host}}", "factory")  # Fixed to factory (INV-1, INV-6)

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
# Host platform (fixed to factory)
host = "factory"
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
