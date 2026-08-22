"""Configuration constants for memory initialization."""

from typing import Any

from ._init_templates_core import template_memory_lock
from ._init_templates_misc import template_migrations_log

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
    "memory/kb/global",
    "project-map",
    "memory/kb",
    "memory/kb/projects",
    "memory/kb/decisions",
    "memory/kb/lessons",
    "memory/kb/patterns",
    "memory/docs",
    "memory/log",
]

# Per-scope directories created during init (relative to target root)
# These require the scope name and are created dynamically in init_project_memory().

# ---------------------------------------------------------------------------
# File templates
# ---------------------------------------------------------------------------


KB_TEMPLATES: dict[str, Any] = {
    "project-map/INDEX.md": lambda scope: (
        "# 合法目录地图索引\n\n"
        "- 唯一合法入口\n"
        "- 只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。\n"
        "- 同次 `git commit` 提交后才生效\n"
        "- project-map/legal-core-map.md: active-legal\n",
        [],
    ),
    "project-map/legal-core-map.md": lambda scope: (
        "# 合法核心地图\n\n"
        "- active-legal\n"
        "- 只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。\n"
        "- project-map/INDEX.md: active-legal\n"
        "- truth-model.md: active-legal\n"
        "- memory-system.md: active-legal\n",
        [],
    ),
    "project-map/ingestion-registry-map.md": lambda scope: (
        "# 摄入登记地图\n\n"
        "- project-map/**: incoming-raw\n"
        "- memory/kb/global/**: incoming-raw\n"
        "- memory/kb/projects/**: compatibility-only\n"
        "- memory/docs/**: incoming-raw\n"
        "- memory/log/**: compatibility-only\n"
        "- memory_core/projects/**: compatibility-only\n"
        "- memory_core/tools/**: compatibility-only\n"
        "- tests/**: compatibility-only\n"
        "- 状态：`absorbed`，`retired`\n"
        "- 同次 `git commit` 提交后才生效\n",
        [],
    ),
    # VAL-INIT-001: Governance stubs at memory/kb/global/ (system-level)
    "memory/kb/global/truth-model.md": lambda scope: (
        "# 唯一真相模型\n\n"
        "本项目的事实来源与验证规则。\n\n"
        "## Truth Basis\n\n"
        "### Source Refs\n\n"
        "- memory/docs/记忆系统全景文档.md\n\n"
        "### Authority Refs\n\n"
        "- project-map/INDEX.md\n"
        "- project-map/legal-core-map.md\n\n"
        "### Evidence Refs\n\n"
        "- tests/.memory-anchor.md\n"
        "- tools/health-check.sh\n\n"
        "### Conflict Status\n\n"
        "- resolved\n",
        [],
    ),
    "memory/kb/global/memory-system.md": lambda scope: (
        "# 记忆系统规则\n\n"
        "active-legal\n\n"
        "## Truth Basis\n\n"
        "### Source Refs\n\n"
        "- memory/docs/记忆系统全景文档.md\n\n"
        "### Authority Refs\n\n"
        "- memory/kb/global/truth-model.md\n"
        "- memory/kb/global/memory-routing.md\n\n"
        "### Evidence Refs\n\n"
        "- tests/.memory-anchor.md\n\n"
        "### Conflict Status\n\n"
        "- resolved\n",
        [],
    ),
    "memory/kb/global/memory-routing.md": lambda scope: (
        "# 记忆路由规则\n\n"
        "## Truth Basis\n\n"
        "### Source Refs\n\n"
        "- memory/docs/记忆系统全景文档.md\n\n"
        "### Authority Refs\n\n"
        "- project-map/INDEX.md\n"
        "- memory/kb/global/hook-contract.md\n\n"
        "### Evidence Refs\n\n"
        "- tools/health-check.sh\n"
        "- tests/.memory-anchor.md\n\n"
        "### Conflict Status\n\n"
        "- resolved\n",
        [],
    ),
    "memory/kb/global/hook-contract.md": lambda scope: (
        "# Hook 契约\n\n"
        "- gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。\n"
        "- 未完成提交的登记不得生效\n\n"
        "## Truth Basis\n\n"
        "### Source Refs\n\n"
        "- memory/docs/记忆系统全景文档.md\n\n"
        "### Authority Refs\n\n"
        "- memory/kb/global/project-map-governance.md\n\n"
        "### Evidence Refs\n\n"
        "- tests/.memory-anchor.md\n\n"
        "### Conflict Status\n\n"
        "- resolved\n",
        [],
    ),
    "memory/kb/global/project-map-governance.md": lambda scope: (
        "# 项目地图治理\n\n"
        "- 未经过唯一真相系统清洗\n"
        "- 只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。\n"
        "- 未完成同次 `git commit` 的目录登记，不得视为生效。\n\n"
        "## Truth Basis\n\n"
        "### Source Refs\n\n"
        "- memory/docs/记忆系统全景文档.md\n\n"
        "### Authority Refs\n\n"
        "- project-map/INDEX.md\n"
        "- memory/kb/global/memory-system.md\n\n"
        "### Evidence Refs\n\n"
        "- tests/.memory-anchor.md\n\n"
        "### Conflict Status\n\n"
        "- resolved\n",
        [],
    ),
    "memory/kb/INDEX.md": lambda scope: (
        "# 知识库索引\n\n"
        "Non-Legal Material\n"
        "See project-map/ingestion-registry-map.md for registration rules.\n\n"
        "本索引列出知识库各子目录及其用途。\n\n"
        "## 目录结构\n\n"
        "- `projects/` — 项目专属知识\n"
        "- `decisions/` — 决策记录\n"
        "- `lessons/` — 经验教训\n\n"
        "## 全局治理文件\n\n"
        "- `memory/kb/global/truth-model.md` — 唯一真相模型\n\n"
        "## 使用说明\n\n"
        "- 只有被地图标为 `active-legal` 的条目或目录，才是合法资料\n"
        "- 目录登记和状态迁移必须与相关文件同次 `git commit` 才生效\n",
        [],
    ),
    "memory/kb/global/INDEX.md": lambda scope: (
        "# 全局知识库索引\n\n"
        "Non-Legal Material\n"
        "See project-map/ingestion-registry-map.md for registration rules.\n\n"
        "## 全局治理文件\n\n"
        "- `truth-model.md` — 唯一真相模型\n"
        "- `memory-system.md` — 记忆系统规则\n"
        "- `memory-routing.md` — 记忆路由规则\n"
        "- `hook-contract.md` — Hook 契约\n"
        "- `project-map-governance.md` — 项目地图治理\n\n"
        "## 使用说明\n\n"
        "- 只有被地图标为 `active-legal` 的条目或目录，才是合法资料\n"
        "- 目录登记和状态迁移必须与相关文件同次 `git commit` 才生效\n",
        [],
    ),
    "INDEX.md": lambda scope: (
        "# 工作区索引\n\n"
        "- project-map/INDEX.md\n"
        "- 只有被地图标为 `active-legal` 的条目或目录，才是合法资料；仅进入登记册不授予合法性。\n"
        "- 目录登记和目录状态迁移必须与相关文件同次 `git commit` 才生效。\n"
        "- memory/kb/global/truth-model.md\n",
        [],
    ),
    "memory/docs/INDEX.md": lambda scope: ("# 文档索引\n\n- incoming-raw\n- 未被地图明确吸收\n", []),
    # I-F: Overview doc referenced by ProjectMapValidator.validate_unique_legal_system_contract
    "memory/docs/记忆系统全景文档.md": lambda scope: (
        "# 记忆系统全景文档\n\n"
        "本文档提供记忆系统的全景视图，包括所有合法入口和核心文件。\n\n"
        "## 合法入口\n\n"
        "- project-map/INDEX.md: 项目地图唯一合法入口\n"
        "- project-map/legal-core-map.md: 合法核心地图\n\n"
        "## 系统结构\n\n"
        "- memory/kb/ — 知识库\n"
        "- memory/docs/ — 系统文档\n"
        "- memory/log/ — 会话日志\n"
        "- memory/system/ — 系统配置\n"
        "- project-map/ — 项目地图\n"
        "- tests/ — 测试锚点\n",
        [],
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
]

# Additional runtime files created outside of KB_TEMPLATES and FILE_TEMPLATES
RUNTIME_EXTRA_FILES = [
    "memory/inbox.md",  # L531, L1374 workbot adapter action target
    "tests/.memory-anchor.md",  # I-A: Evidence ref for Truth Basis sections
    "tools/health-check.sh",  # I-A: Evidence ref for Truth Basis (lower-layer tooling support)
]

# Legacy host patterns to scrub from AGENTS.md (VAL-P4-010)
_LEGACY_HOST_PATTERNS = [
    "~/.codex/bin/memory-hook",
    "~/.claude/bin/memory-hook",
    ".codex/hooks.json",
    ".claude/hooks.json",
]
