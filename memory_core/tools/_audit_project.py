#!/usr/bin/env python3.12
"""审计基础层：路径常量、工具函数、项目解析、全局 KB 指纹。

依赖层级：无内部依赖（最底层）。
daily_kb_audit 拆分的公共基础模块，被其余 _audit_* 模块复用。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION, SYSTEM_DIR

try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore[no-redef]

# Import shared sha256_file utility (Cluster F: deduplicated to _utils.py)
from ._utils import sha256_file

__all__ = [
    # 路径常量
    "MEMORY_CORE_HOME",
    "LIFECYCLE_INDEX",
    "AUDIT_DIR",
    "GLOBAL_KB_ROOT",
    "GLOBAL_KB_DOMAINS",
    "MANIFEST_FILENAME",
    "MANIFEST_PATH_REL",
    "KB_UNSIGNED_WHITELIST",
    "GLOBAL_KB_SKIP",
    "RESIDUE_COMPARE_CHARS",
    "LARGE_SQL_THRESHOLD",
    "DATABASE_FILE_SUFFIXES",
    "LARK_NOTIFY_ENV",
    "LARK_NOTIFY_TIMEOUT",
    "INFRA_INVENTORY",
    "SSH_TIMEOUT",
    "SSH_CONNECT_TIMEOUT",
    "TCP_TIMEOUT",
    "HTTP_TIMEOUT",
    "CURRENT_MEMORY_VERSION",
    # 工具函数
    "_now_iso_local",
    "sha256_file",
    "_sha256_file",
    "_FRONTMATTER_RE",
    "_strip_frontmatter",
    "_normalize_for_compare",
    "_read_text_safe",
    "_make_violation",
    # 项目解析 / 指纹
    "load_registered_projects",
    "build_global_kb_fingerprints",
]


# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

MEMORY_CORE_HOME = Path.home() / ".memory-core"
LIFECYCLE_INDEX = MEMORY_CORE_HOME / "project-lifecycle" / "path-index.json"
AUDIT_DIR = MEMORY_CORE_HOME / "audit"

GLOBAL_KB_ROOT = Path.home() / ".memory" / "global-kb"
GLOBAL_KB_DOMAINS = ("operations", "engineering", "collaboration")

MANIFEST_FILENAME = "manifest.json"
MANIFEST_PATH_REL = f"{SYSTEM_DIR}/{MANIFEST_FILENAME}"  # memory/system/manifest.json

# memory/kb/ 下无需签名的模板文件（和 init_project_memory 保持一致）
KB_UNSIGNED_WHITELIST = {".keep", "README.md", "INDEX.md"}

# 全局 KB 跳过的非知识文件
GLOBAL_KB_SKIP = {".keep", "README.md", "INDEX.md"}

# 残留检测时去 frontmatter / 去空白后比较的字符数
RESIDUE_COMPARE_CHARS = 200

# 数据库/大文件违规规则（参考 no-database-files-in-repo.md）
LARGE_SQL_THRESHOLD = 1024 * 1024  # 1MB
DATABASE_FILE_SUFFIXES = (".sql.gz", ".dump", ".bak", ".sqlite", ".db")

# 飞书通知
LARK_NOTIFY_ENV = "LARK_AUDIT_CHAT_ID"
LARK_NOTIFY_TIMEOUT = 15  # 秒

# ---------------------------------------------------------------------------
# 基础设施健康检查常量（第 6 项检查）
# ---------------------------------------------------------------------------

# 资产清单文件：MEMORY_CORE_HOME / "infrastructure-inventory.yaml"
INFRA_INVENTORY = MEMORY_CORE_HOME / "infrastructure-inventory.yaml"

# 超时（秒）
SSH_TIMEOUT = 10  # 顶层 SSH 探测 / docker ps 通过 SSH 的整体超时
SSH_CONNECT_TIMEOUT = 5  # ssh -o ConnectTimeout=...
TCP_TIMEOUT = 5  # 端口/数据库 TCP connect
HTTP_TIMEOUT = 5  # curl --max-time
# (任务规格里 6a 写 10 秒，6c 端口写 3 秒；TCP_TIMEOUT 常量值为 5，
#  check_ports 内部传入 3 以贴合规格。)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _now_iso_local() -> str:
    """当前本地时间 ISO8601 字符串（带时区）。"""
    return now_iso()


# Backward-compatible alias
_sha256_file = sha256_file


_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """去掉 Markdown 顶部的 YAML frontmatter（--- ... ---）。"""
    return _FRONTMATTER_RE.sub("", text, count=1)


def _normalize_for_compare(text: str) -> str:
    """去 frontmatter → 全文归一化 → 去所有空白 → 小写。

    修复指纹碰撞：原实现仅取前 200 字符，导致共享模板头但正文不同的文档假阳性。
    现改为全文归一化，确保区分性。
    """
    body = _strip_frontmatter(text)
    no_ws = re.sub(r"\s+", "", body)
    return no_ws.lower()


def _read_text_safe(path: Path) -> str | None:
    """读 UTF-8 文本，失败返回 None。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _make_violation(
    vtype: str,
    severity: str,
    file: str,
    detail: str,
) -> dict[str, Any]:
    """构造一条违规记录。"""
    return {
        "type": vtype,
        "severity": severity,
        "file": file,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# 项目路径解析
# ---------------------------------------------------------------------------


def load_registered_projects() -> list[tuple[str, Path]]:
    """从 path-index.json 读取所有注册项目，返回 [(name, path), ...]。

    跳过不存在或无法解析的条目。返回顺序按 path-index.json 的 key 排序，
    保证报告幂等。
    """
    if not LIFECYCLE_INDEX.exists():
        return []

    try:
        idx = json.loads(LIFECYCLE_INDEX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    paths_dict = idx.get("paths", {})
    if not isinstance(paths_dict, dict):
        return []

    # 排除非业务项目（Droid 运行环境配置目录，非消费项目）
    EXCLUDE_PATHS = {str(Path.home() / ".factory")}

    projects: list[tuple[str, Path]] = []
    for raw_path in sorted(paths_dict.keys()):
        if raw_path in EXCLUDE_PATHS:
            continue
        meta = paths_dict.get(raw_path) or {}
        name = meta.get("project_name") or Path(raw_path).name or raw_path
        projects.append((str(name), Path(raw_path).expanduser()))
    return projects


# ---------------------------------------------------------------------------
# 全局 KB 内容指纹（用于残留检测）
# ---------------------------------------------------------------------------


def build_global_kb_fingerprints() -> dict[str, str]:
    """对全局 KB 三个域下每个知识文件计算“归一化指纹”。

    Returns:
        {normalized_fingerprint: global_kb_rel_path}
    """
    fingerprints: dict[str, str] = {}
    if not GLOBAL_KB_ROOT.exists():
        return fingerprints

    for domain in GLOBAL_KB_DOMAINS:
        domain_dir = GLOBAL_KB_ROOT / domain
        if not domain_dir.is_dir():
            continue
        for md_path in sorted(domain_dir.rglob("*.md")):
            if md_path.name in GLOBAL_KB_SKIP:
                continue
            text = _read_text_safe(md_path)
            if text is None:
                continue
            fp = _normalize_for_compare(text)
            if not fp:
                continue
            rel = str(md_path.relative_to(GLOBAL_KB_ROOT))
            fingerprints.setdefault(fp, rel)
    return fingerprints
