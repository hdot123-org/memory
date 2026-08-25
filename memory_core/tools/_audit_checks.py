#!/usr/bin/env python3.12
"""项目完整性检查（检查 1-5）：manifest / 未签名 / 残留 / 大文件 / 版本一致性。

依赖层级：依赖 _audit_project（常量与工具函数）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION, SYSTEM_DIR

from ._audit_project import (
    DATABASE_FILE_SUFFIXES,
    KB_UNSIGNED_WHITELIST,
    LARGE_SQL_THRESHOLD,
    MANIFEST_PATH_REL,
    _make_violation,
    _normalize_for_compare,
    _read_text_safe,
    _sha256_file,
)

__all__ = [
    # 经 _audit_project 引入并再导出的常量（大文件规则）
    "DATABASE_FILE_SUFFIXES",
    "LARGE_SQL_THRESHOLD",
    "check_manifest_integrity",
    "check_unsigned_files",
    "check_global_residue",
    "check_large_or_db_files",
    "check_version_consistency",
    "_is_excludable_path",
    "_check_single_file",
    "_check_backups_dir",
    "_extract_version_from_toml",
    "_EXCLUDED_DIR_SEGMENTS",
]


# ---------------------------------------------------------------------------
# 检查 1: manifest.json 哈希完整性
# ---------------------------------------------------------------------------


def check_manifest_integrity(project_root: Path) -> list[dict[str, Any]]:
    """重新计算 manifest entries 每个文件的 SHA-256，和记录值比对。

    manifest.json 不存在 → 未签名（critical）。
    哈希不匹配 → 文件被篡改（critical）。
    文件缺失 → 单独标记（critical）。
    """
    violations: list[dict[str, Any]] = []
    manifest_path = project_root / MANIFEST_PATH_REL

    if not manifest_path.exists():
        violations.append(
            _make_violation(
                "hash_mismatch",
                "critical",
                MANIFEST_PATH_REL,
                "manifest.json 不存在：项目未签名（缺少完整性清单）",
            )
        )
        return violations

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        violations.append(
            _make_violation(
                "hash_mismatch",
                "critical",
                MANIFEST_PATH_REL,
                f"manifest.json 解析失败：{e}",
            )
        )
        return violations

    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        violations.append(
            _make_violation(
                "hash_mismatch",
                "critical",
                MANIFEST_PATH_REL,
                "manifest.json entries 字段格式错误",
            )
        )
        return violations

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("rel_path")
        expected_sha = entry.get("sha256")
        if not rel_path or not expected_sha:
            continue

        abs_path = project_root / rel_path
        if not abs_path.exists():
            violations.append(
                _make_violation(
                    "hash_mismatch",
                    "critical",
                    rel_path,
                    "manifest 签名的文件已缺失（可能被删除）",
                )
            )
            continue

        actual_sha = _sha256_file(abs_path)
        if actual_sha is None:
            violations.append(
                _make_violation(
                    "hash_mismatch",
                    "critical",
                    rel_path,
                    "签名文件无法读取（权限或 IO 错误）",
                )
            )
            continue

        if actual_sha != expected_sha:
            violations.append(
                _make_violation(
                    "hash_mismatch",
                    "critical",
                    rel_path,
                    "SHA-256 不匹配：文件被篡改（manifest 与实际内容不一致）",
                )
            )

    return violations


# ---------------------------------------------------------------------------
# 检查 2: memory/kb/ 下未签名文件
# ---------------------------------------------------------------------------


def check_unsigned_files(project_root: Path) -> list[dict[str, Any]]:
    """扫描 memory/kb/ 下所有 .md 文件，对比 manifest entries。

    不在签名列表里的 = 未签名文件（可能是违规新增）。warning 级别。
    排除 .keep / README.md / INDEX.md。
    """
    violations: list[dict[str, Any]] = []
    kb_dir = project_root / "memory" / "kb"
    if not kb_dir.is_dir():
        return violations

    manifest_path = project_root / MANIFEST_PATH_REL
    signed_rel_paths: set[str] = set()
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest.get("entries", []) or []:
                if isinstance(entry, dict) and entry.get("rel_path"):
                    signed_rel_paths.add(entry["rel_path"])
        except (json.JSONDecodeError, OSError):
            # manifest 自身有问题在检查 1 已标记，这里只跳过比对
            pass

    for md_path in sorted(kb_dir.rglob("*.md")):
        # VAL-AUDIT-011/012: 仅顶层 README.md/INDEX.md 豁免，深层同名不再豁免
        is_top_level = md_path.parent == kb_dir
        if is_top_level and md_path.name in KB_UNSIGNED_WHITELIST:
            continue
        try:
            rel_path = str(md_path.relative_to(project_root))
        except ValueError:
            rel_path = str(md_path)
        # 统一用 posix 风格分隔，和 manifest rel_path 一致
        rel_path_norm = rel_path.replace("\\", "/")
        if rel_path_norm not in signed_rel_paths:
            violations.append(
                _make_violation(
                    "unsigned_file",
                    "warning",
                    rel_path_norm,
                    "memory/kb 下未签名文件（不在 manifest entries 中，可能是违规新增）",
                )
            )

    return violations


# ---------------------------------------------------------------------------
# 检查 3: 通用经验残留检测
# ---------------------------------------------------------------------------


def check_global_residue(
    project_root: Path,
    global_fingerprints: dict[str, str],
) -> list[dict[str, Any]]:
    """检测项目 kb/lessons|decisions 下是否有全局 KB 内容残留。

    比较规则：项目文件去 frontmatter、去空白、取前 200 字符后，
    如果和全局 KB 某文件指纹完全相同 → 疑似残留。warning 级别。
    """
    violations: list[dict[str, Any]] = []
    if not global_fingerprints:
        return violations

    candidate_dirs = [
        project_root / "memory" / "kb" / "lessons",
        project_root / "memory" / "kb" / "decisions",
    ]

    for cdir in candidate_dirs:
        if not cdir.is_dir():
            continue
        for md_path in sorted(cdir.rglob("*.md")):
            if md_path.name in KB_UNSIGNED_WHITELIST:
                continue
            text = _read_text_safe(md_path)
            if text is None:
                continue
            fp = _normalize_for_compare(text)
            if not fp:
                continue
            matched_global = global_fingerprints.get(fp)
            if matched_global:
                try:
                    rel_path = str(md_path.relative_to(project_root))
                except ValueError:
                    rel_path = str(md_path)
                violations.append(
                    _make_violation(
                        "residue",
                        "warning",
                        rel_path.replace("\\", "/"),
                        f"疑似全局通用经验残留：内容与全局 KB {matched_global} 高度重复",
                    )
                )

    return violations


# ---------------------------------------------------------------------------
# 检查 4: 大文件/数据库文件违规
# ---------------------------------------------------------------------------

_EXCLUDED_DIR_SEGMENTS = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache", ".pytest_cache"}
)


def _is_excludable_path(item: Path, project_root: Path) -> bool:
    """检查路径是否在排除目录列表中（.git/node_modules 等）。"""
    try:
        parts = item.relative_to(project_root).parts
    except ValueError:
        parts = item.parts
    return any(seg in _EXCLUDED_DIR_SEGMENTS for seg in parts)


def _check_single_file(item: Path, project_root: Path) -> dict[str, Any] | None:
    """检查单个文件是否违反大文件/数据库规则。

    Returns:
        violation dict if violated, None otherwise.
    """
    try:
        rel_for_report = str(item.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        rel_for_report = str(item)

    suffix = item.suffix.lower()
    name_lower = item.name.lower()

    # .sql 超过 1MB
    if suffix == ".sql":
        try:
            size = item.stat().st_size
        except OSError:
            size = 0
        if size > LARGE_SQL_THRESHOLD:
            return _make_violation(
                "large_file",
                "critical",
                rel_for_report,
                f"大型 SQL 文件 ({size} bytes > 1MB)：数据 dump 不应入仓库",
            )
        return None

    # 其他数据库/备份后缀
    if any(name_lower.endswith(s) for s in DATABASE_FILE_SUFFIXES):
        return _make_violation(
            "large_file",
            "critical",
            rel_for_report,
            f"数据库/备份文件 {item.name}：禁止入仓库（见 no-database-files-in-repo.md）",
        )

    return None


def _check_backups_dir(base: Path, project_root: Path) -> dict[str, Any] | None:
    """检查 backups/ 目录是否存在且非空。

    Returns:
        violation dict if violated, None otherwise.
    """
    backups_dir = base / "backups"
    if not backups_dir.is_dir():
        return None
    try:
        files = list(backups_dir.iterdir())
    except OSError:
        files = []
    if not files:
        return None
    try:
        rel = str(backups_dir.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        rel = str(backups_dir)
    return _make_violation(
        "large_file",
        "critical",
        rel,
        "backups/ 目录非空：数据库备份应放外部存储，不入仓库",
    )


def check_large_or_db_files(project_root: Path) -> list[dict[str, Any]]:
    """扫描项目根目录和 memory/kb/ 下的数据库/备份大文件。

    参考全局知识 no-database-files-in-repo.md 规则。
    命中即 critical（数据库文件不允许入仓库）。

    Note: 项目根 rglob 已覆盖 memory/kb/，此处显式列出 memory/kb/ 是
    按任务规格强调扫描范围；通过 seen 集合去重避免重复计数。

    backups 目录检测：递归任意段（VAL-AUDIT-013/014）——遍历时检查路径任意段
    为 "backups"，与 guard 侧 FORBIDDEN_DIRS 语义对齐。
    """
    violations: list[dict[str, Any]] = []
    seen: set[Path] = set()
    seen_backups_dirs: set[Path] = set()

    scan_roots: list[Path] = []
    if project_root.is_dir():
        scan_roots.append(project_root)
    kb_dir = project_root / "memory" / "kb"
    if kb_dir.is_dir():
        scan_roots.append(kb_dir)

    for root in scan_roots:
        for item in root.rglob("*"):
            if item in seen:
                continue
            seen.add(item)
            if _is_excludable_path(item, project_root):
                continue

            # VAL-AUDIT-013/014: 任意段为 "backups" 的目录非空即报
            if item.is_dir():
                try:
                    rel_path = item.relative_to(project_root)
                    parts = rel_path.parts
                except (ValueError, OSError):
                    parts = item.parts
                if "backups" in parts and item not in seen_backups_dirs:
                    seen_backups_dirs.add(item)
                    try:
                        contents = list(item.iterdir())
                    except OSError:
                        contents = []
                    if contents:
                        try:
                            rel = str(item.relative_to(project_root)).replace("\\", "/")
                        except (ValueError, OSError):
                            rel = str(item).replace("\\", "/")
                        violations.append(
                            _make_violation(
                                "large_file",
                                "critical",
                                rel,
                                "backups/ 目录非空：数据库备份应放外部存储，不入仓库",
                            )
                        )
                continue

            if not item.is_file():
                continue

            v = _check_single_file(item, project_root)
            if v is not None:
                violations.append(v)

    return violations


# ---------------------------------------------------------------------------
# 检查 5: 三文件版本一致性
# ---------------------------------------------------------------------------


def _extract_version_from_toml(text: str) -> str | None:
    """从 TOML 文本里抽 memory_version / version 字段。

    优先级序（权威语义，表位置优先）：
    1. [memory].memory_version（memory.lock 风格）
    2. [core].version（adapter.toml 风格）
    3. 顶层 memory_version（ownership.toml 风格）
    4. 顶层 version（兜底，仅当前三者未命中）

    任意其他 table 的 version/memory_version 键不参与匹配。
    解析失败时回退正则保持健壮性。
    """
    import tomllib

    # Try tomllib parsing first
    try:
        data = tomllib.loads(text)
    except Exception:
        # Fallback to regex for malformed TOML
        data = None

    if data is not None:
        # Priority 1: [memory].memory_version
        memory_table = data.get("memory")
        if isinstance(memory_table, dict):
            mv = memory_table.get("memory_version")
            if isinstance(mv, str):
                return mv

        # Priority 2: [core].version
        core_table = data.get("core")
        if isinstance(core_table, dict):
            cv = core_table.get("version")
            if isinstance(cv, str):
                return cv

        # Priority 3: top-level memory_version
        top_mv = data.get("memory_version")
        if isinstance(top_mv, str):
            return top_mv

        # Priority 4: top-level version (fallback)
        top_v = data.get("version")
        if isinstance(top_v, str):
            return top_v

        return None

    # Fallback: regex for malformed TOML
    # memory.lock: [memory] memory_version = "x" or 'x'
    m = re.search(r'^\s*memory_version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if m:
        return m.group(1)
    # adapter.toml: [core] version = "x" or 'x'
    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def check_version_consistency(project_root: Path) -> list[dict[str, Any]]:
    """检查 memory.lock / adapter.toml / ownership.toml 版本号是否一致。

    期望全部为 CURRENT_MEMORY_VERSION。不一致 → version_mismatch (critical)。
    """
    violations: list[dict[str, Any]] = []

    files = {
        "memory.lock": project_root / SYSTEM_DIR / "memory.lock",
        "adapter.toml": project_root / SYSTEM_DIR / "adapter.toml",
        "ownership.toml": project_root / SYSTEM_DIR / "ownership.toml",
    }

    versions: dict[str, str] = {}
    missing: list[str] = []
    for label, fpath in files.items():
        if not fpath.exists():
            missing.append(label)
            continue
        text = _read_text_safe(fpath)
        if text is None:
            missing.append(label)
            continue
        ver = _extract_version_from_toml(text)
        if ver is None:
            missing.append(label)
        else:
            versions[label] = ver

    for label in missing:
        violations.append(
            _make_violation(
                "version_mismatch",
                "critical",
                f"{SYSTEM_DIR}/{label}",
                f"{label} 缺失或无法解析版本号",
            )
        )

    # 比对：任一文件与期望值不同
    for label, ver in versions.items():
        if ver != CURRENT_MEMORY_VERSION:
            violations.append(
                _make_violation(
                    "version_mismatch",
                    "critical",
                    f"{SYSTEM_DIR}/{label}",
                    f"{label} 版本 {ver} 与期望 {CURRENT_MEMORY_VERSION} 不一致",
                )
            )

    # 三者互相不一致（即便都和期望相同，也校验一致性）
    unique_versions = set(versions.values())
    if len(unique_versions) > 1:
        violations.append(
            _make_violation(
                "version_mismatch",
                "critical",
                f"{SYSTEM_DIR}/",
                f"三文件版本不一致：{versions}",
            )
        )

    return violations
