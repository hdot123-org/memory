"""Auto-fill detection and template population logic."""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _fill_canonical_table(content: str, project_info: Any) -> str:
    """Fill CANONICAL.md table fields (language, type, toolchain, repo)."""
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
        remote_row = f"| 远程仓库 | `{project_info.git_remote_url}` |"
        if "远程仓库" not in content:
            content = re.sub(
                r'(\| 本地仓库 \| .+? \|)\n',
                rf'\g<1>\n{remote_row}\n',
                content,
                count=1,
            )

    return content


def _fill_scope_fields(content: str, project_info: Any) -> str:
    """Fill project scope .md fields (language, framework, database, overview)."""
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

    # Fill CANONICAL.md table fields
    content = _fill_canonical_table(content, project_info)

    # Fill project scope .md fields
    content = _fill_scope_fields(content, project_info)

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
    Enhanced (Phase 2): reads package.json / tsconfig.json / pyproject.toml to
    detect tech stack, fills {{PROJECT_TYPE}}, {{PRIMARY_LANGUAGE}}, etc. in
    scope sub-directory templates. Unrecognized placeholders are replaced with
    「（待补充：xxx）」 rather than leaving bare {{PLACEHOLDER}} strings.
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

    # --- Enhance project_info with tech-stack detection from config files ---
    _enrich_project_info_from_config(target, project_info)

    # NOTE: CANONICAL.md generation removed in v0.5.0 — no auto-fill needed there

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

    # Fill scope sub-directory templates (CANONICAL.md, PLAN.md, STATE.md, TASKS.md)
    _fill_scope_subdir_templates(target, project_info, result, project_name=project_name)

    # Log what was detected
    if project_info.primary_language:
        result["created"].append(f"detected:primary_language={project_info.primary_language}")
    if project_info.framework:
        result["created"].append(f"detected:framework={project_info.framework}")
    if project_info.git_remote_url:
        result["created"].append(f"detected:git_remote_url={project_info.git_remote_url}")
    if project_info.project_type:
        result["created"].append(f"detected:project_type={project_info.project_type}")


def _detect_from_pyproject(target: Path, project_info: Any) -> None:
    """Detect Python language and project type from pyproject.toml."""
    pyproject = target / "pyproject.toml"
    if not pyproject.is_file() or project_info.primary_language:
        return
    try:
        pyproject_text = pyproject.read_text(encoding="utf-8")
        python_markers = [
            "setuptools", "poetry", "hatch", "flit", "pdm", "maturin",
            "scikit-build", "cython",
        ]
        if any(m in pyproject_text for m in python_markers) or "[project]" in pyproject_text:
            project_info.primary_language = "Python"
            if not project_info.project_type:
                if any(m in pyproject_text for m in ["fastapi", "flask", "django", "starlette"]):
                    project_info.project_type = "web/api"
                elif "pytest" in pyproject_text or "pyproject" in pyproject_text:
                    project_info.project_type = "library"
    except Exception as exc:
        logger.debug("init_project_memory._detect_from_pyproject: pyproject parsing failed: %s", exc)


def _detect_from_package_json(target: Path, project_info: Any) -> None:
    """Detect JavaScript/TypeScript language, project type, and toolchain from package.json."""
    package_json = target / "package.json"
    if not package_json.is_file():
        return
    try:
        import json as _json
        pkg_data = _json.loads(package_json.read_text(encoding="utf-8"))
        if not project_info.primary_language:
            project_info.primary_language = "JavaScript"

        if not project_info.project_type:
            deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            dep_keys = list(deps.keys())

            if any(d in dep_keys for d in ["next", "gatsby", "remix"]) or any(d in dep_keys for d in ["react", "vue", "svelte", "angular"]):
                project_info.project_type = "frontend"
            elif any(d in dep_keys for d in ["express", "koa", "fastify", "hapi"]):
                project_info.project_type = "web/api"
            elif pkg_data.get("main") or pkg_data.get("types"):
                project_info.project_type = "library"
            else:
                project_info.project_type = "node"

        # Toolchain from npm scripts
        if not project_info.toolchain:
            scripts = pkg_data.get("scripts", {})
            toolchain = []
            if "build" in scripts:
                toolchain.append({"name": "npm", "config": "npm run build"})
            if "test" in scripts:
                toolchain.append({"name": "npm", "config": "npm test"})
            # Check if TypeScript is present (need to re-check dep_keys)
            deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            dep_keys = list(deps.keys())
            if any(d in dep_keys for d in ["typescript", "ts-node"]):
                project_info.primary_language = "TypeScript"
                toolchain.append({"name": "TypeScript", "config": "tsconfig.json"})
            project_info.toolchain = toolchain
    except Exception as exc:
        logger.debug("init_project_memory._detect_from_package_json: package.json parsing failed: %s", exc)


def _detect_from_tsconfig(target: Path, project_info: Any) -> None:
    """Detect TypeScript from tsconfig.json."""
    tsconfig = target / "tsconfig.json"
    if not tsconfig.is_file() or project_info.primary_language:
        return
    project_info.primary_language = "TypeScript"
    if not project_info.toolchain:
        project_info.toolchain = [{"name": "TypeScript", "config": "tsconfig.json"}]


def _detect_from_cargo(target: Path, project_info: Any) -> None:
    """Detect Rust from Cargo.toml."""
    cargo_toml = target / "Cargo.toml"
    if not cargo_toml.is_file() or project_info.primary_language:
        return
    project_info.primary_language = "Rust"
    if not project_info.project_type:
        project_info.project_type = "library"


def _enrich_project_info_from_config(target: Path, project_info: Any) -> None:
    """Detect tech stack from package.json / tsconfig.json / pyproject.toml.

    Mutates project_info in-place to fill primary_language, project_type,
    and toolchain fields when they are currently empty.
    """
    try:
        from .project_probe import ProjectInfo as _ProjectInfo
    except ImportError:
        from memory_core.tools.project_probe import ProjectInfo as _ProjectInfo

    if not isinstance(project_info, _ProjectInfo):
        return

    _detect_from_pyproject(target, project_info)
    _detect_from_package_json(target, project_info)
    _detect_from_tsconfig(target, project_info)
    _detect_from_cargo(target, project_info)


def _fill_scope_subdir_templates(
    target: Path,
    project_info: Any,
    result: dict[str, Any],
    *,
    project_name: str,
) -> None:
    """Fill {{PLACEHOLDER}} strings in scope sub-directory templates.

    Reads CANONICAL.md, PLAN.md, STATE.md, TASKS.md under
    memory/kb/projects/{project_name}/ and replaces known placeholders
    with detected values. Unknown placeholders become 「（待补充：xxx）」.
    """
    scope_dir = target / "memory" / "kb" / "projects" / project_name
    if not scope_dir.is_dir():
        return

    # Build a fill map from project_info
    fill_map: dict[str, str] = {}

    try:
        from .project_probe import ProjectInfo as _ProjectInfo
    except ImportError:
        from memory_core.tools.project_probe import ProjectInfo as _ProjectInfo

    if isinstance(project_info, _ProjectInfo):
        if project_info.primary_language:
            fill_map["{{PRIMARY_LANGUAGE}}"] = project_info.primary_language
        if project_info.project_type:
            fill_map["{{PROJECT_TYPE}}"] = project_info.project_type

    # Additional runtime fill
    fill_map["{{CREATED_AT}}"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    fill_map["{{UPDATED_AT}}"] = fill_map["{{CREATED_AT}}"]

    # Process each template file in the scope directory
    for template_file in ["CANONICAL.md", "PLAN.md", "STATE.md", "TASKS.md"]:
        file_path = scope_dir / template_file
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            original = content

            # 1) Fill known placeholders
            for placeholder, value in fill_map.items():
                content = content.replace(placeholder, value)

            # 2) Replace any remaining {{UPPER_SNAKE_CASE}} placeholders
            #    with 「（待补充：placeholder_name）」
            import re as _re
            remaining = _re.findall(r"\{\{([A-Z_]+)\}\}", content)
            for name in remaining:
                replacement = f"（待补充：{name.lower()}）"
                content = content.replace(f"{{{{{name}}}}}", replacement)

            if content != original:
                file_path.write_text(content, encoding="utf-8")
                result["created"].append(f"file:memory/kb/projects/{project_name}/{template_file} (placeholders filled)")
        except Exception as exc:
            result["warnings"].append(f"scope subdir fill failed for {template_file}: {exc}")


# ---------------------------------------------------------------------------
# File registry
# ---------------------------------------------------------------------------

# Minimum viable templates for Knowledge Base and Project Map
