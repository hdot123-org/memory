"""Create and manage the global knowledge base physical structure.

This module provides the foundation for the global knowledge base layer (Layer 2)
in the three-tier memory architecture:
- Layer 1: ~/.memory-core/ (runtime)
- Layer 2: ~/.memory/global-kb/ (global knowledge base) - NEW
- Layer 3: <project>/memory/kb/ (project knowledge)

The global KB contains cross-project reusable knowledge organized into four domains:
- operations/: Operations knowledge (servers, deployment, SSH, network, database)
- engineering/: Engineering knowledge (CI/CD, toolchain, architecture decisions)
- collaboration/: Collaboration knowledge (agent collaboration, team processes)
- pending/: Auto-captured candidates awaiting manual promotion

This structure is created once and shared across all projects that enable global KB.
"""
from pathlib import Path
from typing import Any

# Domain definitions with descriptions
DOMAIN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "operations": {
        "title": "Operations Knowledge",
        "description": "运维域知识:服务器配置、部署流程、SSH/Tailscale、网络配置、数据库运维、Docker/K8s、监控告警等",
        "examples": ["SSH 连接问题排查", "Tailscale 组网配置", "Docker 容器部署最佳实践"],
    },
    "engineering": {
        "title": "Engineering Knowledge",
        "description": "工程域知识:CI/CD 配置、工具链选择、代码质量、测试策略、架构决策、性能优化等",
        "examples": ["GitLab CI 缓存优化", "Python 虚拟环境管理", "代码审查流程"],
    },
    "collaboration": {
        "title": "Collaboration Knowledge",
        "description": "协作域知识:Agent 协作模式、Orchestrator-Worker 流程、团队沟通、文档规范、知识共享等",
        "examples": ["多 Agent 任务分配策略", "Factory Droid 使用技巧", "跨项目知识同步"],
    },
    "pending": {
        "title": "Pending Candidates",
        "description": "待确认候选区:自动捕获的知识点,需经 memory-promote 人工确认后才能进入正式分类",
        "examples": [],
    },
}


def create_global_kb_structure(
    global_kb_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    """
    Create the global knowledge base directory structure.

    This function creates the complete physical structure for the global KB:
    - Four domain directories (operations, engineering, collaboration, pending)
    - README.md in each domain explaining its purpose
    - INDEX.md in the root with domain classification list

    The function is idempotent:
    - If global_kb_root already exists, it does not overwrite existing files
    - If INDEX.md already exists, it is preserved (not overwritten)
    - If domain directories exist, they are not modified

    Args:
        global_kb_root: Root path for global KB (typically ~/.memory/global-kb)
        force: If True, overwrite existing README files (but never INDEX.md)

    Returns:
        Dictionary with:
        - success: bool indicating success
        - created_paths: List of paths created
        - skipped_paths: List of paths skipped (already existed)
        - errors: List of error messages (empty if success)
    """
    result: dict[str, Any] = {
        "success": False,
        "global_kb_root": str(global_kb_root),
        "created_paths": [],
        "skipped_paths": [],
        "errors": [],
    }

    try:
        # Create root directory
        if not global_kb_root.exists():
            global_kb_root.mkdir(parents=True, exist_ok=True)
            result["created_paths"].append(str(global_kb_root))
        else:
            result["skipped_paths"].append(str(global_kb_root))

        # Create domain directories
        for domain in ["operations", "engineering", "collaboration", "pending"]:
            domain_dir = global_kb_root / domain

            if not domain_dir.exists():
                domain_dir.mkdir(parents=True, exist_ok=True)
                result["created_paths"].append(str(domain_dir))
            else:
                result["skipped_paths"].append(str(domain_dir))

            # Create README.md for this domain
            readme_path = domain_dir / "README.md"
            if not readme_path.exists() or force:
                readme_content = _generate_domain_readme(domain)
                readme_path.write_text(readme_content, encoding="utf-8")
                result["created_paths"].append(str(readme_path))
            else:
                result["skipped_paths"].append(str(readme_path))

        # Create root INDEX.md (only if it doesn't exist - idempotent)
        index_path = global_kb_root / "INDEX.md"
        if not index_path.exists():
            index_content = _generate_index_md()
            index_path.write_text(index_content, encoding="utf-8")
            result["created_paths"].append(str(index_path))
        else:
            result["skipped_paths"].append(str(index_path))

        result["success"] = True

    except Exception as e:
        result["errors"].append(f"Failed to create global KB structure: {str(e)}")

    return result


def _generate_domain_readme(domain: str) -> str:
    """
    Generate README.md content for a specific domain.

    Args:
        domain: Domain name (operations, engineering, collaboration, pending)

    Returns:
        Markdown content for the README
    """
    if domain not in DOMAIN_DEFINITIONS:
        return f"# {domain.title()}\n\nDomain definition not found."

    definition = DOMAIN_DEFINITIONS[domain]

    lines = [
        f"# {definition['title']}",
        "",
        definition["description"],
        "",
    ]

    # Add examples section if domain has examples
    if definition["examples"]:
        lines.extend([
            "## 示例知识点",
            "",
        ])
        for example in definition["examples"]:
            lines.append(f"- {example}")
        lines.append("")

    # Add special note for pending domain
    if domain == "pending":
        lines.extend([
            "## 提升流程",
            "",
            "`pending/` 目录中的知识点是自动捕获的候选内容,需要通过 `memory-promote` 命令进行人工确认后才能进入正式分类:",
            "",
            "1. 查看待确认知识点: `memory-promote --list`",
            "2. 提升到指定域: `memory-promote <file> --to operations|engineering|collaboration`",
            "3. 确认后知识点会被移动到对应的正式分类目录",
            "",
            "**注意**: 只有经过人工确认的知识点才会进入全局知识库的正式分类,自动捕获的内容不会直接写入 operations/engineering/collaboration 目录。",
            "",
        ])
    else:
        lines.extend([
            "## 写入方式",
            "",
            "本目录的内容通过 `memory-promote` 命令从 `pending/` 目录提升而来,",
            "不允许自动捕获直接写入。",
            "",
        ])

    return "\n".join(lines)


def _generate_index_md() -> str:
    """
    Generate INDEX.md content for the global KB root.

    Returns:
        Markdown content for the INDEX
    """
    lines = [
        "# 全局知识库 (Global Knowledge Base)",
        "",
        "全局知识库是三层记忆架构的第二层,存储跨项目通用的知识和经验。",
        "",
        "## 架构位置",
        "",
        "- **Layer 1**: `~/.memory-core/` - 运行时状态",
        "- **Layer 2**: `~/.memory/global-kb/` - 全局知识库 (本目录)",
        "- **Layer 3**: `<project>/memory/kb/` - 项目知识库",
        "",
        "## 域分类",
        "",
        "全局知识库按职责分为四个域:",
        "",
    ]

    # Add domain sections
    for domain in ["operations", "engineering", "collaboration", "pending"]:
        definition = DOMAIN_DEFINITIONS[domain]
        lines.extend([
            f"### [{domain}/](./{domain}/)",
            "",
            f"**{definition['title']}**",
            "",
            definition["description"],
            "",
        ])

    # Add usage instructions
    lines.extend([
        "## 使用方式",
        "",
        "### 读取知识",
        "",
        "项目启用全局知识库后,路由会自动 fallback 到全局知识库查找缺失的知识:",
        "",
        "1. 项目层优先: 先查找 `<project>/memory/kb/`",
        "2. 全局 fallback: 项目层缺失时,查找 `~/.memory/global-kb/` 对应域",
        "",
        "### 贡献知识",
        "",
        "1. 项目产生经验后,自动捕获到 `pending/` 目录",
        "2. 使用 `memory-promote` 命令人工确认并提升到正式分类",
        "3. 提升后的知识对所有启用全局知识库的项目可见",
        "",
        "### 配置",
        "",
        "在项目的 `memory/system/adapter.toml` 中配置:",
        "",
        "```toml",
        "[global_kb]",
        "enabled = true",
        "root = \"~/.memory/global-kb\"",
        "```",
        "",
    ])

    return "\n".join(lines)


def get_global_kb_root() -> Path:
    """
    Get the default global KB root path.

    Returns:
        Path to ~/.memory/global-kb
    """
    return Path.home() / ".memory" / "global-kb"


def is_global_kb_initialized(global_kb_root: Path | None = None) -> bool:
    """
    Check if the global KB structure has been initialized.

    Args:
        global_kb_root: Optional custom root path (defaults to ~/.memory/global-kb)

    Returns:
        True if all required directories and files exist
    """
    if global_kb_root is None:
        global_kb_root = get_global_kb_root()

    if not global_kb_root.exists():
        return False

    # Check all domain directories exist
    for domain in ["operations", "engineering", "collaboration", "pending"]:
        if not (global_kb_root / domain).is_dir():
            return False
        if not (global_kb_root / domain / "README.md").is_file():
            return False

    # Check INDEX.md exists
    if not (global_kb_root / "INDEX.md").is_file():
        return False

    return True
