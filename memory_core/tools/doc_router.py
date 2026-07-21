# -*- coding: utf-8 -*-
"""文档分类路由引擎。

提供 DOC_CATEGORIES 路由表（single source of truth）和路径解析/校验 API。
Agent 调用 resolve_doc_path() 获取路径，不直接拼接路径。
"""

from pathlib import Path

DOC_CATEGORIES: dict[str, str] = {
    "decision": "memory/kb/decisions/",
    "lesson": "memory/kb/lessons/",
    "refactor-log": "memory/docs/refactor-logs/",
    "plan": "memory/docs/plans/",
    "runbook": "memory/docs/runbooks/",
    "bug-report": "memory/docs/bug-reports/",
    "audit": "memory/docs/audit/",
    "rfc": "memory/docs/rfcs/",
    "note": "memory/docs/notes/",
    "draft": "memory/docs/drafts/",
}

EXCEPTION_DIRS: frozenset[str] = frozenset({
    "memory/docs/archive/",
    "memory/docs/system/",
    "memory/kb/projects/",
})

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_doc_path(category: str, filename: str) -> Path:
    """给分类标签，返回完整路径。

    Args:
        category: 分类标签（如 "decision", "lesson", "refactor-log"）
        filename: 文件名（如 "D-001.md"）

    Returns:
        完整的文档路径（REPO_ROOT / 分类目录 / filename）
    """
    dir_path = DOC_CATEGORIES.get(category, DOC_CATEGORIES["draft"])
    return REPO_ROOT / dir_path / filename


def is_registered_doc_dir(path: Path) -> bool:
    """校验路径是否在注册目录或例外列表中。

    Args:
        path: 要校验的路径（可以是绝对路径或相对路径）

    Returns:
        True 如果路径在 DOC_CATEGORIES.values() 或 EXCEPTION_DIRS 中，False 否则
    """
    try:
        if path.is_absolute():
            rel = str(path.resolve().relative_to(REPO_ROOT)) + "/"
        else:
            rel = str(path)
            if not rel.endswith("/"):
                rel += "/"
    except ValueError:
        return False

    for cat_dir in DOC_CATEGORIES.values():
        if rel.startswith(cat_dir):
            return True

    for exc_dir in EXCEPTION_DIRS:
        if rel.startswith(exc_dir):
            return True

    return False
