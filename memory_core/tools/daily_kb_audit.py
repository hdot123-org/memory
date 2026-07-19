#!/usr/bin/env python3
"""每日记忆巡检脚本 — 检查所有接入项目的记忆纯度和完整性。

对 ~/.memory-core/project-lifecycle/path-index.json 里注册的所有项目，
执行以下 5 项检查，生成 JSON 报告到 ~/.memory-core/audit/ 目录。

检查项:
    1. manifest.json 哈希完整性（SHA-256 重新计算比对）
    2. memory/kb/ 下未签名文件（对比 manifest entries）
    3. 通用经验残留检测（项目 KB 文件 vs 全局 KB）
    4. 大文件/数据库文件违规（参考 no-database-files-in-repo.md）
    5. 三文件版本一致性（memory.lock / adapter.toml / ownership.toml）
    6. 基础设施健康检查（SSH / Docker / 端口 / HTTP / 数据库，
       清单来自 ~/.memory-core/infrastructure-inventory.yaml）

Usage:
    memory-audit-daily              # 扫描所有项目 + 基础设施
    memory-audit-daily --no-infra   # 跳过基础设施检查
    memory-audit-daily --json       # 输出 JSON 到 stdout
    memory-audit-daily --notify     # 扫描后通过 lark-cli 发飞书通知

设计原则:
    - 幂等、安全、只读（绝不修改任何项目文件）
    - 跳过不存在的项目路径（可能已删除）
    - 单个项目检查失败不影响其他项目
    - 基础设施清单文件缺失或 PyYAML 不可用时优雅降级（不崩溃）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from memory_core.constants import CURRENT_MEMORY_VERSION, SYSTEM_DIR

try:
    from memory_core.ownership import is_memory_core_source_repo
except ImportError:  # pragma: no cover - 防御性回退
    is_memory_core_source_repo = None  # type: ignore[assignment]

try:
    import yaml  # type: ignore[import-not-found]
    _HAS_YAML = True
except ImportError:  # pragma: no cover - 缺 PyYAML 时跳过基础设施检查
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False

# Import file utilities (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore


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
SSH_TIMEOUT = 10          # 顶层 SSH 探测 / docker ps 通过 SSH 的整体超时
SSH_CONNECT_TIMEOUT = 5   # ssh -o ConnectTimeout=...
TCP_TIMEOUT = 5           # 端口/数据库 TCP connect
HTTP_TIMEOUT = 5          # curl --max-time
# (任务规格里 6a 写 10 秒，6c 端口写 3 秒；TCP_TIMEOUT 常量值为 5，
#  check_ports 内部传入 3 以贴合规格。)

# 时区（本机 +08:00）
# _LOCAL_TZ_OFFSET removed - dead code, never used


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _now_iso_local() -> str:
    """当前本地时间 ISO8601 字符串（带时区）。"""
    return now_iso()


# Import shared sha256_file utility (Cluster F: deduplicated to _utils.py)
from ._utils import sha256_file

# Backward-compatible alias
_sha256_file = sha256_file


_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """去掉 Markdown 顶部的 YAML frontmatter（--- ... ---）。"""
    return _FRONTMATTER_RE.sub("", text, count=1)


def _normalize_for_compare(text: str) -> str:
    """去 frontmatter → 取前 N 字符 → 去所有空白 → 小写。"""
    body = _strip_frontmatter(text)
    head = body[:RESIDUE_COMPARE_CHARS]
    no_ws = re.sub(r"\s+", "", head)
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
        violations.append(_make_violation(
            "hash_mismatch",
            "critical",
            MANIFEST_PATH_REL,
            "manifest.json 不存在：项目未签名（缺少完整性清单）",
        ))
        return violations

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        violations.append(_make_violation(
            "hash_mismatch",
            "critical",
            MANIFEST_PATH_REL,
            f"manifest.json 解析失败：{e}",
        ))
        return violations

    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        violations.append(_make_violation(
            "hash_mismatch",
            "critical",
            MANIFEST_PATH_REL,
            "manifest.json entries 字段格式错误",
        ))
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
            violations.append(_make_violation(
                "hash_mismatch",
                "critical",
                rel_path,
                "manifest 签名的文件已缺失（可能被删除）",
            ))
            continue

        actual_sha = _sha256_file(abs_path)
        if actual_sha is None:
            violations.append(_make_violation(
                "hash_mismatch",
                "critical",
                rel_path,
                "签名文件无法读取（权限或 IO 错误）",
            ))
            continue

        if actual_sha != expected_sha:
            violations.append(_make_violation(
                "hash_mismatch",
                "critical",
                rel_path,
                "SHA-256 不匹配：文件被篡改（manifest 与实际内容不一致）",
            ))

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
        if md_path.name in KB_UNSIGNED_WHITELIST:
            continue
        try:
            rel_path = str(md_path.relative_to(project_root))
        except ValueError:
            rel_path = str(md_path)
        # 统一用 posix 风格分隔，和 manifest rel_path 一致
        rel_path_norm = rel_path.replace("\\", "/")
        if rel_path_norm not in signed_rel_paths:
            violations.append(_make_violation(
                "unsigned_file",
                "warning",
                rel_path_norm,
                "memory/kb 下未签名文件（不在 manifest entries 中，可能是违规新增）",
            ))

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
                violations.append(_make_violation(
                    "residue",
                    "warning",
                    rel_path.replace("\\", "/"),
                    f"疑似全局通用经验残留：内容与全局 KB {matched_global} 高度重复",
                ))

    return violations


# ---------------------------------------------------------------------------
# 检查 4: 大文件/数据库文件违规
# ---------------------------------------------------------------------------

def check_large_or_db_files(project_root: Path) -> list[dict[str, Any]]:
    """扫描项目根目录和 memory/kb/ 下的数据库/备份大文件。

    参考全局知识 no-database-files-in-repo.md 规则。
    命中即 critical（数据库文件不允许入仓库）。

    Note: 项目根 rglob 已覆盖 memory/kb/，此处显式列出 memory/kb/ 是
    按任务规格强调扫描范围；通过 seen 集合去重避免重复计数。
    """
    violations: list[dict[str, Any]] = []
    seen: set[Path] = set()

    scan_roots: list[Path] = []
    if project_root.is_dir():
        scan_roots.append(project_root)
    kb_dir = project_root / "memory" / "kb"
    if kb_dir.is_dir():
        scan_roots.append(kb_dir)

    for root in scan_roots:
        for item in root.rglob("*"):
            if not item.is_file():
                continue
            if item in seen:
                continue
            seen.add(item)
            # 跳过明显的依赖/构建产物目录，避免噪音
            try:
                parts = item.relative_to(project_root).parts
            except ValueError:
                parts = item.parts
            if any(seg in {".git", "node_modules", "__pycache__", ".venv", "venv",
                           "dist", "build", ".mypy_cache", ".pytest_cache"}
                   for seg in parts):
                continue

            name_lower = item.name.lower()
            suffix = item.suffix.lower()
            try:
                rel_for_report = str(item.relative_to(project_root)).replace("\\", "/")
            except ValueError:
                rel_for_report = str(item)

            # .sql 超过 1MB
            if suffix == ".sql":
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                if size > LARGE_SQL_THRESHOLD:
                    violations.append(_make_violation(
                        "large_file",
                        "critical",
                        rel_for_report,
                        f"大型 SQL 文件 ({size} bytes > 1MB)：数据 dump 不应入仓库",
                    ))
                continue

            # 其他数据库/备份后缀
            if any(name_lower.endswith(s) for s in DATABASE_FILE_SUFFIXES):
                violations.append(_make_violation(
                    "large_file",
                    "critical",
                    rel_for_report,
                    f"数据库/备份文件 {item.name}：禁止入仓库（见 no-database-files-in-repo.md）",
                ))

    # backups/ 目录存在（在项目根或 memory/kb 下）
    for base in (project_root, kb_dir):
        backups_dir = base / "backups"
        if backups_dir.is_dir():
            try:
                files = list(backups_dir.iterdir())
            except OSError:
                files = []
            if files:
                try:
                    rel = str(backups_dir.relative_to(project_root)).replace("\\", "/")
                except ValueError:
                    rel = str(backups_dir)
                violations.append(_make_violation(
                    "large_file",
                    "critical",
                    rel,
                    "backups/ 目录非空：数据库备份应放外部存储，不入仓库",
                ))

    return violations


# ---------------------------------------------------------------------------
# 检查 5: 三文件版本一致性
# ---------------------------------------------------------------------------

def _extract_version_from_toml(text: str) -> str | None:
    """从 TOML 文本里抽 memory_version / version 字段。

    优先 [memory].memory_version（memory.lock 风格），
    其次 [core].version（adapter.toml 风格），
    再次顶层 memory_version（ownership.toml 风格）。
    """
    # memory.lock: [memory] memory_version = "x"
    m = re.search(r'^\s*memory_version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if m:
        return m.group(1)
    # adapter.toml: [core] version = "x"
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
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
        violations.append(_make_violation(
            "version_mismatch",
            "critical",
            f"{SYSTEM_DIR}/{label}",
            f"{label} 缺失或无法解析版本号",
        ))

    # 比对：任一文件与期望值不同
    for label, ver in versions.items():
        if ver != CURRENT_MEMORY_VERSION:
            violations.append(_make_violation(
                "version_mismatch",
                "critical",
                f"{SYSTEM_DIR}/{label}",
                f"{label} 版本 {ver} 与期望 {CURRENT_MEMORY_VERSION} 不一致",
            ))

    # 三者互相不一致（即便都和期望相同，也校验一致性）
    unique_versions = set(versions.values())
    if len(unique_versions) > 1:
        violations.append(_make_violation(
            "version_mismatch",
            "critical",
            f"{SYSTEM_DIR}/",
            f"三文件版本不一致：{versions}",
        ))

    return violations


# ---------------------------------------------------------------------------
# 检查 6: 基础设施健康检查（服务器 / Docker / 端口 / HTTP / 数据库）
# ---------------------------------------------------------------------------

def _load_infra_inventory() -> dict[str, Any] | None:
    """加载基础设施清单 YAML。

    Returns:
        dict: 解析后的清单（含 servers / databases 键，可能为空列表）。
        None: 文件不存在、不可解析、或 PyYAML 不可用（调用方据此跳过）。
    """
    if not _HAS_YAML:
        print(
            "[infra] PyYAML 不可用，跳过基础设施检查 "
            "（可 `pip install pyyaml` 启用）",
            file=sys.stderr,
        )
        return None
    if not INFRA_INVENTORY.exists():
        print(
            f"[infra] 清单文件不存在：{INFRA_INVENTORY}，跳过基础设施检查",
            file=sys.stderr,
        )
        return None
    try:
        data = yaml.safe_load(INFRA_INVENTORY.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print(
            f"[infra] 清单解析失败：{e}，跳过基础设施检查",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print("[infra] 清单顶层不是 mapping，跳过基础设施检查", file=sys.stderr)
        return None
    return data


def _tcp_connect_ok(host: str, port: int, timeout: int = TCP_TIMEOUT) -> bool:
    """TCP connect 探测，成功返回 True，超时/拒绝/错误返回 False。"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _run_ssh(
    ssh_alias: str,
    remote_cmd: list[str],
    timeout: int = SSH_TIMEOUT,
) -> tuple[int, str, str]:
    """以 BatchMode 执行一条 SSH 命令，返回 (rc, stdout, stderr)。"""
    cmd = [
        "ssh",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-o", "BatchMode=yes",
        ssh_alias,
        *remote_cmd,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", "ssh 命令未找到"
    except subprocess.TimeoutExpired:
        return 124, "", f"SSH 超时（>{timeout}s）"
    return result.returncode, result.stdout, result.stderr


def check_ssh_reachable(ssh_alias: str) -> bool:
    """检查 SSH 是否可达（`ssh <alias> echo ok`）。"""
    rc, out, _ = _run_ssh(ssh_alias, ["echo", "ok"])
    return rc == 0 and out.strip() == "ok"


def check_disk_space(
    ssh_alias: str,
    server_name: str,
    disk_checks: list[dict[str, Any]],
    global_violations: list[dict[str, Any]],
    record_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """通过 SSH 检查磁盘空间使用率。

    用一条 SSH 命令执行 ``df -P`` 获取所有挂载点信息，
    然后逐个对比配置的阈值。超过 warn_pct 报 warning，
    超过 crit_pct 报 critical。

    磁盘满了会导致 MySQL 写入失败、Docker 构建失败、日志丢失等严重问题。

    Args:
        ssh_alias: SSH 别名。
        server_name: 服务器名（用于违规 file 字段前缀）。
        disk_checks: 磁盘检查配置列表，每项含 mount/pattern、warn_pct、crit_pct。
        global_violations: 全局违规列表（就地追加）。
        record_violations: 当前 server record 的违规列表（就地追加）。

    Returns:
        {mount_point: {size, used, avail, use_pct, status}} 磁盘使用情况。
    """
    result: dict[str, Any] = {}

    if not disk_checks:
        return result

    # 用一条 SSH 命令获取所有挂载点信息
    # df -P: POSIX 输出格式，保证一行一个文件系统
    rc, out, _err = _run_ssh(
        ssh_alias,
        ["df", "-h", "-P"],
    )
    if rc != 0:
        v = _make_violation(
            "disk_full",
            "warning",
            f"{server_name} (df)",
            f"df 命令执行失败 (rc={rc})，无法检查磁盘空间",
        )
        record_violations.append(v)
        global_violations.append(v)
        return result

    # 解析 df -h -P 输出:
    # Filesystem      Size  Used Avail Use% Mounted on
    # /dev/sda1        50G   35G   12G  75% /
    # overlay          50G   35G   12G  75% /
    filesystems: dict[str, dict[str, Any]] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("Filesystem"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        size = parts[1]
        used = parts[2]
        avail = parts[3]
        use_pct_str = parts[4].rstrip("%")
        mount = " ".join(parts[5:])  # mount path 可能有空格
        try:
            use_pct = int(use_pct_str)
        except ValueError:
            continue
        filesystems[mount] = {
            "size": size,
            "used": used,
            "avail": avail,
            "use_pct": use_pct,
        }

    # 逐个配置项检查
    for dc in disk_checks:
        if not isinstance(dc, dict):
            continue
        warn_pct = int(dc.get("warn_pct", 80))
        crit_pct = int(dc.get("crit_pct", 90))
        mount = dc.get("mount")
        pattern = dc.get("pattern")

        # 通过 mount 精确匹配或 pattern 正则匹配
        matched_mount: str | None = None
        if mount:
            matched_mount = mount if mount in filesystems else None
        elif pattern:
            for fs_mount in filesystems:
                if re.search(pattern, fs_mount):
                    matched_mount = fs_mount
                    break

        if matched_mount is None:
            label = mount or pattern or "?"
            v = _make_violation(
                "disk_full",
                "warning",
                f"{server_name}:{label}",
                f"未找到匹配的挂载点: {label}",
            )
            record_violations.append(v)
            global_violations.append(v)
            continue

        fs_info = filesystems[matched_mount]
        result[matched_mount] = fs_info

        use_pct = fs_info["use_pct"]
        fs_info["status"] = "ok"

        if use_pct >= crit_pct:
            fs_info["status"] = "critical"
            v = _make_violation(
                "disk_full",
                "critical",
                f"{server_name}:{matched_mount}",
                f"磁盘空间严重不足：{matched_mount} 使用 {use_pct}% "
                f"(>={crit_pct}%)，剩余 {fs_info['avail']}，"
                f"总量 {fs_info['size']}（MySQL/Docker 有写入失败风险）",
            )
            record_violations.append(v)
            global_violations.append(v)
        elif use_pct >= warn_pct:
            fs_info["status"] = "warning"
            v = _make_violation(
                "disk_full",
                "warning",
                f"{server_name}:{matched_mount}",
                f"磁盘空间不足：{matched_mount} 使用 {use_pct}% "
                f"(>={warn_pct}%)，剩余 {fs_info['avail']}，"
                f"总量 {fs_info['size']}",
            )
            record_violations.append(v)
            global_violations.append(v)

    return result


def _check_systemd_services(
    ssh_alias: str,
    server_name: str,
    services: list[str],
    global_violations: list[dict[str, Any]],
    record_violations: list[dict[str, Any]],
) -> dict[str, str]:
    """通过 SSH 批量查询 systemd 服务状态。

    用一条 SSH 命令遍历所有服务（`systemctl show ... --property=`），
    解析 LoadState/ActiveState/SubState，对每个期望服务判断：

        - ActiveState=active 且 SubState=running → "running"
        - LoadState=not-found → warning（服务未安装，可能不适用于此机）
        - 其他异常 → critical（service_down）
        - systemctl 命令执行失败 → warning（无法核对，疑似权限问题）

    Args:
        ssh_alias: SSH 别名。
        server_name: 服务器名（用于违规 file 字段前缀）。
        services: 期望检查的 systemd 服务名列表。
        global_violations: 全局违规列表（就地追加）。
        record_violations: 当前 server record 的违规列表（就地追加）。

    Returns:
        {service_name: status_str}，status_str 为 "running" / 状态描述。
        未解析到输出的服务记为 "unknown"。
    """
    statuses: dict[str, str] = {}

    if not services:
        return statuses

    # 批量查询：一条 SSH 命令遍历所有服务，避免多次往返。
    # 注意：必须把整段脚本作为「单个字符串」传给 _run_ssh（即单元素 list），
    # 否则 ssh 客户端会把多个 argv 用空格拼接后送远端 shell，导致
    # 多行脚本被重新分词而破坏（见 ssh(1) 的 command 拼接行为）。
    services_quoted = " ".join(_shell_quote(s) for s in services)
    remote_script = (
        f"for svc in {services_quoted}; do\n"
        '  echo "=== $svc ==="\n'
        '  systemctl show "$svc" '
        "--property=LoadState,ActiveState,SubState --no-pager\n"
        "done\n"
    )
    rc, out, _err = _run_ssh(ssh_alias, [remote_script])

    if rc != 0:
        # systemctl 整体不可用（权限/PATH 问题），逐个标 warning
        detail = (
            f"systemctl 批量查询执行失败 (rc={rc})，无法核对服务状态"
            f"（疑似权限或 systemd 未安装）"
        )
        v = _make_violation(
            "service_down",
            "warning",
            f"{server_name} (systemctl)",
            detail,
        )
        record_violations.append(v)
        global_violations.append(v)
        for svc in services:
            statuses[svc] = "unknown"
        return statuses

    # 解析输出：=== <svc> === 块，块内是 LoadState/ActiveState/SubState 三行
    current_svc: str | None = None
    current_props: dict[str, str] = {}
    blocks: dict[str, dict[str, str]] = {}

    for line in out.splitlines():
        line = line.strip()
        if line.startswith("=== ") and line.endswith(" ==="):
            # 保存上一个块
            if current_svc is not None:
                blocks[current_svc] = current_props
            current_svc = line[4:-4].strip()
            current_props = {}
        elif "=" in line and current_svc is not None:
            key, _, val = line.partition("=")
            current_props[key.strip()] = val.strip()
    # 收尾最后一个块
    if current_svc is not None:
        blocks[current_svc] = current_props

    # 逐个期望服务判定
    for svc in services:
        props = blocks.get(svc)
        if not props:
            statuses[svc] = "unknown"
            v = _make_violation(
                "service_down",
                "warning",
                f"{server_name}/{svc}",
                f"systemd 服务 {svc} 未在输出中找到（解析失败或未安装）",
            )
            record_violations.append(v)
            global_violations.append(v)
            continue

        load_state = props.get("LoadState", "")
        active_state = props.get("ActiveState", "")
        sub_state = props.get("SubState", "")

        # LoadState=not-found → 服务未安装，warning（可能不适用此机）
        if load_state == "not-found":
            statuses[svc] = "not-found"
            v = _make_violation(
                "service_down",
                "warning",
                f"{server_name}/{svc}",
                f"systemd 服务 {svc} 未安装（LoadState=not-found）",
            )
            record_violations.append(v)
            global_violations.append(v)
            continue

        # 正常运行
        if active_state == "active" and sub_state == "running":
            statuses[svc] = "running"
            continue

        # 其他异常状态 → critical
        statuses[svc] = f"{active_state}/{sub_state}"
        v = _make_violation(
            "service_down",
            "critical",
            f"{server_name}/{svc}",
            f"systemd 服务 {svc} 状态异常："
            f"ActiveState={active_state}, SubState={sub_state}",
        )
        record_violations.append(v)
        global_violations.append(v)

    return statuses


def _shell_quote(s: str) -> str:
    """POSIX shell 单引号转义，用于构造安全的远程脚本。"""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def check_server(
    server: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """对单台服务器跑 SSH / Docker / 端口 / HTTP 检查。

    Args:
        server: inventory 里的一条 server 记录。
        global_violations: 累积违规列表（就地追加，便于汇总 total）。

    Returns:
        该服务器的检查结果子树（host / ssh_ok / containers / ports /
        http_endpoints / violations）。
    """
    name = str(server.get("name", "unknown"))
    host = str(server.get("host", ""))
    checks = server.get("checks") or {}

    record: dict[str, Any] = {
        "host": host,
        "ssh_ok": None,
        "containers": {},
        "ports": {},
        "http_endpoints": {},
        "disk_space": {},
        "violations": [],
    }

    ssh_alias = server.get("ssh_alias")
    want_ssh = bool(checks.get("ssh")) and bool(ssh_alias)

    # 6a. SSH 连通性
    ssh_ok: bool | None = None
    if want_ssh:
        ssh_ok = check_ssh_reachable(str(ssh_alias))
        record["ssh_ok"] = ssh_ok
        if not ssh_ok:
            v = _make_violation(
                "server_unreachable",
                "critical",
                f"{host} ({ssh_alias})",
                f"SSH 不可达：{ssh_alias}",
            )
            record["violations"].append(v)
            global_violations.append(v)
    elif ssh_alias is None and bool(checks.get("ssh")):
        # 声明了 ssh=true 但缺 ssh_alias
        v = _make_violation(
            "server_unreachable",
            "critical",
            name,
            "checks.ssh=true 但缺少 ssh_alias 字段",
        )
        record["violations"].append(v)
        global_violations.append(v)

    # 6b. Docker 容器（依赖 SSH 可达）
    expected_containers = checks.get("docker_containers") or []
    if expected_containers:
        if ssh_ok:
            # 注意：_run_ssh 将 remote_cmd 用空格拼接发给远端 shell，
            # format 串含空格必须用单引号包裹，否则 shell 会拆成两个参数。
            rc, out, _err = _run_ssh(
                str(ssh_alias),
                ["docker", "ps", "--format", "'{{.Names}}: {{.Status}}'"],
            )
            running: dict[str, str] = {}
            if rc == 0:
                for line in out.splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    cname, _, cstatus = line.partition(":")
                    running[cname.strip()] = cstatus.strip()
            else:
                v = _make_violation(
                    "container_down",
                    "warning",
                    f"{name} ({ssh_alias})",
                    f"docker ps 执行失败 (rc={rc})，无法核对容器状态",
                )
                record["violations"].append(v)
                global_violations.append(v)

            # 对照期望列表
            for expected in expected_containers:
                expected = str(expected)
                status = running.get(expected)
                if status is None:
                    record["containers"][expected] = "DOWN"
                    v = _make_violation(
                        "container_down",
                        "critical",
                        f"{name}/{expected}",
                        f"期望容器未运行：{expected}",
                    )
                    record["violations"].append(v)
                    global_violations.append(v)
                else:
                    record["containers"][expected] = status
                    low = status.lower()
                    if "restarting" in low or "unhealthy" in low:
                        v = _make_violation(
                            "container_down",
                            "warning",
                            f"{name}/{expected}",
                            f"容器状态异常：{expected} -> {status}",
                        )
                        record["violations"].append(v)
                        global_violations.append(v)
        # else: SSH 已失败，在 6a 已标记，此处不再重复报错

    # 6b2. systemd 服务状态（依赖 SSH 可达）
    expected_systemd = checks.get("systemd_services") or []
    if expected_systemd:
        if ssh_ok:
            record["systemd_services"] = _check_systemd_services(
                ssh_alias=str(ssh_alias),
                server_name=name,
                services=[str(s) for s in expected_systemd],
                global_violations=global_violations,
                record_violations=record["violations"],
            )
        # else: SSH 已失败，在 6a 已标记，此处不再重复报错

    # 6b3. 磁盘空间检查（依赖 SSH 可达，防止磁盘满导致 MySQL/Docker 故障）
    disk_checks = checks.get("disk_space") or []
    if disk_checks and ssh_ok:
        record["disk_space"] = check_disk_space(
            ssh_alias=str(ssh_alias),
            server_name=name,
            disk_checks=[str(d) if not isinstance(d, dict) else d for d in disk_checks],
            global_violations=global_violations,
            record_violations=record["violations"],
        )
    # else: SSH 已失败或未配置 disk_space，跳过

    # 6c. 端口连通性（Python socket，超时 3s 贴合规格）
    for port in checks.get("ports") or []:
        port = int(port)
        ok = _tcp_connect_ok(host, port, timeout=3)
        record["ports"][str(port)] = ok
        if not ok:
            v = _make_violation(
                "port_closed",
                "critical",
                f"{host}:{port}",
                f"端口 {port} 不可达（TCP connect 失败）",
            )
            record["violations"].append(v)
            global_violations.append(v)

    # 6d. HTTP 端点健康检查（curl）
    for ep in checks.get("http_endpoints") or []:
        if not isinstance(ep, dict):
            continue
        url = ep.get("url")
        ep_name = str(ep.get("name") or url)
        expected_status = int(ep.get("expected_status", 200))
        if not url:
            continue
        cmd = [
            "curl", "-sf", "-o", "/dev/null",
            "-w", "%{http_code}",
            "--max-time", str(HTTP_TIMEOUT),
            str(url),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=HTTP_TIMEOUT + 2,
            )
            status_str = (result.stdout or "").strip()
            try:
                status_code = int(status_str) if status_str else 0
            except ValueError:
                status_code = 0
        except FileNotFoundError:
            status_code = -1
        except subprocess.TimeoutExpired:
            status_code = -2

        ep_record: dict[str, Any] = {
            "status": status_code,
            "expected": expected_status,
            "ok": status_code == expected_status,
        }
        record["http_endpoints"][ep_name] = ep_record

        if status_code == -2:
            v = _make_violation(
                "http_error",
                "critical",
                url,
                f"HTTP 端点超时（>{HTTP_TIMEOUT}s）：{ep_name}",
            )
            record["violations"].append(v)
            global_violations.append(v)
        elif status_code in (-1, 0):
            v = _make_violation(
                "http_error",
                "critical",
                url,
                f"HTTP 端点连接失败：{ep_name}",
            )
            record["violations"].append(v)
            global_violations.append(v)
        elif status_code != expected_status:
            v = _make_violation(
                "http_error",
                "warning",
                url,
                f"HTTP 状态码 {status_code} != 期望 {expected_status}：{ep_name}",
            )
            record["violations"].append(v)
            global_violations.append(v)

    return record


def check_database(
    database: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """对单个数据库做 TCP connect 探测（6e）。"""
    name = str(database.get("name", "unknown"))
    host = str(database.get("host", ""))
    port = int(database.get("port", 0))

    record: dict[str, Any] = {
        "host": host,
        "port": port,
        "connect_ok": None,
        "violations": [],
    }

    # check 字段兼容 tcp_connect / mysql_ping（当前只实现 tcp_connect）
    check_kind = str(database.get("check", "tcp_connect")).lower()
    if check_kind != "tcp_connect":
        # 未支持的检查类型，按 warning 提示但不阻塞
        v = _make_violation(
            "db_unreachable",
            "warning",
            f"{host}:{port}",
            f"不支持的 database.check={check_kind}，仅支持 tcp_connect",
        )
        record["connect_ok"] = False
        record["violations"].append(v)
        global_violations.append(v)
        return record

    ok = _tcp_connect_ok(host, port, timeout=TCP_TIMEOUT)
    record["connect_ok"] = ok
    if not ok:
        v = _make_violation(
            "db_unreachable",
            "critical",
            f"{host}:{port}",
            f"数据库不可达：{name} ({host}:{port}) TCP connect 失败",
        )
        record["violations"].append(v)
        global_violations.append(v)

    return record


def check_infrastructure() -> dict[str, Any]:
    """执行基础设施健康检查（第 6 项），返回报告 infrastructure 子树。

    结构:
        {
          "servers": { "<name>": {...} },
          "databases": { "<name>": {...} },
          "violations": [...]   # 全部基础设施违规（便于汇总）
        }
    """
    result: dict[str, Any] = {
        "servers": {},
        "databases": {},
        "violations": [],
    }

    data = _load_infra_inventory()
    if data is None:
        return result

    # 服务器
    for server in data.get("servers") or []:
        if not isinstance(server, dict):
            continue
        name = str(server.get("name", "unknown"))
        result["servers"][name] = check_server(server, result["violations"])

    # 数据库
    for database in data.get("databases") or []:
        if not isinstance(database, dict):
            continue
        name = str(database.get("name", "unknown"))
        result["databases"][name] = check_database(database, result["violations"])

    return result


# ---------------------------------------------------------------------------
# 单项目编排
# ---------------------------------------------------------------------------

def audit_project(
    project_name: str,
    project_root: Path,
    global_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """对单个项目跑全部 5 项检查，返回报告子树。"""
    record: dict[str, Any] = {
        "path": str(project_root),
        "violations": [],
    }

    # 跳过不存在的项目路径
    if not project_root.exists():
        record["violations"].append(_make_violation(
            "hash_mismatch",
            "warning",
            str(project_root),
            "项目路径不存在（可能已删除），跳过",
        ))
        record["skipped"] = True
        return record

    # memory-core 自身是只读源仓库，不持有业务 KB，跳过 KB 相关检查和版本一致性检查
    # （源仓库的版本号由自身维护，跑版本检查会产生误报）
    is_source_repo = (
        is_memory_core_source_repo is not None
        and is_memory_core_source_repo(project_root.resolve())
    )

    checks: Iterable[tuple[str, "Any"]] = []

    # 检查 1: 哈希完整性（所有项目都跑）
    def _c1() -> list[dict[str, Any]]:
        try:
            return check_manifest_integrity(project_root)
        except Exception as e:  # 单项目失败不影响其他项目
            return [_make_violation("hash_mismatch", "warning",
                                     MANIFEST_PATH_REL,
                                     f"检查异常：{e}")]

    checks = [("_c1", _c1)]

    # KB 相关检查（源仓库跳过，它没有消费项目 KB 结构）
    if not is_source_repo:
        def _c2() -> list[dict[str, Any]]:
            try:
                return check_unsigned_files(project_root)
            except Exception as e:
                return [_make_violation("unsigned_file", "warning",
                                         "memory/kb/",
                                         f"检查异常：{e}")]

        def _c3() -> list[dict[str, Any]]:
            try:
                return check_global_residue(project_root, global_fingerprints)
            except Exception as e:
                return [_make_violation("residue", "warning",
                                         "memory/kb/",
                                         f"检查异常：{e}")]

        def _c4() -> list[dict[str, Any]]:
            try:
                return check_large_or_db_files(project_root)
            except Exception as e:
                return [_make_violation("large_file", "warning",
                                         str(project_root),
                                         f"检查异常：{e}")]

        # 检查 5: 版本一致性（源仓库跳过，避免误报）
        def _c5() -> list[dict[str, Any]]:
            try:
                return check_version_consistency(project_root)
            except Exception as e:
                return [_make_violation("version_mismatch", "warning",
                                         f"{SYSTEM_DIR}/",
                                         f"检查异常：{e}")]

        checks = list(checks) + [("_c2", _c2), ("_c3", _c3), ("_c4", _c4), ("_c5", _c5)]

    for _, fn in checks:
        try:
            violations = fn()
        except Exception as e:  # 双保险
            violations = [_make_violation(
                "hash_mismatch", "warning", str(project_root),
                f"检查函数异常：{e}",
            )]
        if violations:
            record["violations"].extend(violations)

    if is_source_repo:
        record["note"] = "memory-core 源仓库：跳过 KB 未签名/残留/大文件检查"

    return record


# ---------------------------------------------------------------------------
# 报告 & 输出
# ---------------------------------------------------------------------------

def build_report(
    projects_results: dict[str, dict[str, Any]],
    infrastructure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装最终报告字典。

    Args:
        projects_results: 项目检查结果。
        infrastructure: 基础设施检查结果（可为 None 表示本次未执行）。
    """
    today = now_iso()[:10]  # Extract YYYY-MM-DD from full ISO timestamp
    project_violations = sum(
        len(r.get("violations", []))
        for r in projects_results.values()
    )
    infra_violations = 0
    if infrastructure is not None:
        infra_violations = len(infrastructure.get("violations", []))

    report: dict[str, Any] = {
        "audit_date": today,
        "audited_at": _now_iso_local(),
        "projects_checked": len(projects_results),
        "total_violations": project_violations + infra_violations,
        "projects": projects_results,
    }
    if infrastructure is not None:
        report["infrastructure_checked"] = True
        # 把汇总 violations 从子树里去掉后塞进报告（避免重复 + 便于消费者）
        infra_view = dict(infrastructure)
        infra_view.pop("violations", None)
        report["infrastructure"] = infra_view
    return report


def write_report(report: dict[str, Any]) -> Path:
    """把报告写入 ~/.memory-core/audit/daily-audit-YYYY-MM-DD.json。

    目录不存在则创建。返回写入路径。
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIT_DIR / f"daily-audit-{report['audit_date']}.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# 飞书通知（lark-cli）
# ---------------------------------------------------------------------------

def _summarize_report(report: dict[str, Any]) -> str:
    """生成飞书通知用的纯文本摘要。"""
    lines: list[str] = []
    lines.append(f"📋 每日记忆巡检报告 {report['audit_date']}")
    lines.append(f"检查项目数: {report['projects_checked']}")
    lines.append(f"违规总数: {report['total_violations']}")
    lines.append("")

    if report["total_violations"] == 0:
        lines.append("✅ 全部项目通过，无违规。")
        # 即便无违规，也附上基础设施摘要（若有）
        _append_infra_summary(lines, report)
        lines.append("")
        lines.append(
            f"详细报告: {AUDIT_DIR}/daily-audit-{report['audit_date']}.json"
        )
        return "\n".join(lines)

    critical_count = 0
    warning_count = 0

    # 项目违规
    for name, rec in report["projects"].items():
        viols = rec.get("violations", [])
        if not viols:
            continue
        c = sum(1 for v in viols if v.get("severity") == "critical")
        w = sum(1 for v in viols if v.get("severity") == "warning")
        critical_count += c
        warning_count += w
        lines.append(f"• {name}: {len(viols)} 条违规 (critical={c}, warning={w})")
        # 每个项目最多列 3 条详情，避免消息过长
        for v in viols[:3]:
            lines.append(f"    [{v.get('severity')}] {v.get('type')}: {v.get('detail')}")
        if len(viols) > 3:
            lines.append(f"    ...还有 {len(viols) - 3} 条")

    # 基础设施违规
    infra = report.get("infrastructure") or {}
    for kind in ("servers", "databases"):
        for _name, rec in (infra.get(kind) or {}).items():
            viols = rec.get("violations", [])
            if not viols:
                continue
            c = sum(1 for v in viols if v.get("severity") == "critical")
            w = sum(1 for v in viols if v.get("severity") == "warning")
            critical_count += c
            warning_count += w
            label = f"[infra/{kind}] {_name}"
            lines.append(
                f"• {label}: {len(viols)} 条违规 (critical={c}, warning={w})"
            )
            for v in viols[:3]:
                lines.append(
                    f"    [{v.get('severity')}] {v.get('type')}: {v.get('detail')}"
                )
            if len(viols) > 3:
                lines.append(f"    ...还有 {len(viols) - 3} 条")

    lines.insert(3, f"其中 critical={critical_count}, warning={warning_count}")

    # 基础设施摘要段
    _append_infra_summary(lines, report)

    lines.append("")
    lines.append(f"详细报告: {AUDIT_DIR}/daily-audit-{report['audit_date']}.json")
    return "\n".join(lines)


def _append_infra_summary(lines: list[str], report: dict[str, Any]) -> None:
    """向摘要里追加一段「🖥 基础设施」概览。无基础设施节点则跳过。"""
    infra = report.get("infrastructure")
    if not infra:
        return

    servers = infra.get("servers") or {}
    databases = infra.get("databases") or {}
    if not servers and not databases:
        return

    lines.append("")
    lines.append("🖥 基础设施:")

    for name, rec in servers.items():
        ssh_ok = rec.get("ssh_ok")
        # ssh_ok 可能为 None（未检查）
        ssh_mark = "✓" if ssh_ok else ("✗" if ssh_ok is False else "-")

        systemd = rec.get("systemd_services") or {}
        if systemd:
            up_n = sum(1 for s in systemd.values() if s == "running")
            s_summary = f"systemd {up_n}/{len(systemd)}"
        else:
            s_summary = "systemd -"

        containers = rec.get("containers") or {}
        if containers:
            up_n = sum(
                1 for s in containers.values()
                if s and s != "DOWN"
                and "restarting" not in s.lower()
                and "unhealthy" not in s.lower()
            )
            c_summary = f"容器 {up_n}/{len(containers)} 正常"
        else:
            c_summary = "容器 -"

        ports = rec.get("ports") or {}
        p_summary = (
            f"端口 {sum(1 for v in ports.values() if v)}/{len(ports)}"
            if ports else "端口 -"
        )

        https = rec.get("http_endpoints") or {}
        h_summary = (
            f"HTTP {sum(1 for v in https.values() if v.get('ok'))}/{len(https)}"
            if https else "HTTP -"
        )

        # 磁盘空间摘要
        disks = rec.get("disk_space") or {}
        if disks:
            disk_parts = []
            for d_mount, d_info in disks.items():
                pct = d_info.get("use_pct", 0)
                avail = d_info.get("avail", "?")
                mark = "🔴" if pct >= 90 else ("🟡" if pct >= 80 else "✓")
                disk_parts.append(f"{d_mount} {mark}{pct}% (剩{avail})")
            d_summary = "磁盘 " + ", ".join(disk_parts)
        else:
            d_summary = "磁盘 -"

        lines.append(
            f"  {name}: SSH {ssh_mark}, {s_summary}, {c_summary}, {p_summary}, {h_summary}"
        )
        lines.append(f"        {d_summary}")

    for name, rec in databases.items():
        ok = rec.get("connect_ok")
        mark = "✓" if ok else ("✗" if ok is False else "-")
        lines.append(f"  {name}: {mark}")


def notify_via_lark(report: dict[str, Any]) -> bool:
    """通过 lark-cli 发送飞书通知（bot 身份）。

    CHAT_ID 从环境变量 LARK_AUDIT_CHAT_ID 读取。
    只有存在违规或环境变量明确要求时才发。
    返回是否成功发送。
    """
    chat_id = os.environ.get(LARK_NOTIFY_ENV)
    if not chat_id:
        print(
            f"[notify] 跳过飞书通知：环境变量 {LARK_NOTIFY_ENV} 未设置",
            file=sys.stderr,
        )
        return False

    summary = _summarize_report(report)
    # lark-cli im +messages-send --chat-id <ID> --text "<TEXT>"
    cmd = [
        "lark-cli", "im", "+messages-send",
        "--chat-id", chat_id,
        "--text", summary,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=LARK_NOTIFY_TIMEOUT,
        )
    except FileNotFoundError:
        print("[notify] lark-cli 未安装，跳过飞书通知", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("[notify] lark-cli 执行超时，跳过飞书通知", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(
            f"[notify] lark-cli 失败 (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}",
            file=sys.stderr,
        )
        return False

    print(f"[notify] 已发送飞书通知到 chat {chat_id}")
    return True


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="memory-audit-daily",
        description="每日记忆巡检：检查所有接入项目的记忆纯度和完整性。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "检查项:\n"
            "  1. manifest.json 哈希完整性\n"
            "  2. memory/kb/ 下未签名文件\n"
            "  3. 通用经验残留检测（项目 KB vs 全局 KB）\n"
            "  4. 大文件/数据库文件违规\n"
            "  5. 三文件版本一致性\n"
            "  6. 基础设施健康检查（SSH / Docker / 端口 / HTTP / 数据库）\n"
            "\n"
            "示例:\n"
            "  memory-audit-daily              # 扫描所有项目 + 基础设施\n"
            "  memory-audit-daily --no-infra   # 跳过基础设施检查\n"
            "  memory-audit-daily --json       # 输出 JSON 到 stdout\n"
            "  memory-audit-daily --notify     # 扫描后通过 lark-cli 发飞书通知\n"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="将完整 JSON 报告输出到 stdout（仍会写文件）",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="扫描后通过 lark-cli 发飞书通知（需设置 LARK_AUDIT_CHAT_ID）",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="不写报告文件（仅 --json 或 --notify 时有意义）",
    )
    parser.add_argument(
        "--no-infra",
        action="store_true",
        help="跳过基础设施检查（只做项目记忆巡检）",
    )
    return parser.parse_args(argv)


def _count_critical_infra(infra: dict[str, Any] | None) -> int:
    """统计基础设施子树里 critical 违规数（servers + databases）。"""
    if not infra:
        return 0
    n = 0
    for kind in ("servers", "databases"):
        for _name, rec in (infra.get(kind) or {}).items():
            n += sum(
                1 for v in rec.get("violations", [])
                if v.get("severity") == "critical"
            )
    return n


def _count_warning_infra(infra: dict[str, Any] | None) -> int:
    """统计基础设施子树里 warning 违规数（servers + databases）。"""
    if not infra:
        return 0
    n = 0
    for kind in ("servers", "databases"):
        for _name, rec in (infra.get(kind) or {}).items():
            n += sum(
                1 for v in rec.get("violations", [])
                if v.get("severity") == "warning"
            )
    return n


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    Usage:
        memory-audit-daily              # 扫描所有项目 + 基础设施
        memory-audit-daily --no-infra   # 跳过基础设施检查
        memory-audit-daily --json       # 输出 JSON 到 stdout
        memory-audit-daily --notify     # 扫描后通过 lark-cli 发飞书通知

    Returns:
        0  全部通过（无违规）
        0  有 warning 级别违规（巡检本身成功，不阻断）
        1  有 critical 级别违规（项目或基础设施）或 巡检过程出错
    """
    args = _parse_args(argv)

    # 0. 基础设施检查（独立于项目检查，即便无项目也可执行）
    infra_results: dict[str, Any] | None = None
    if not args.no_infra:
        print("[audit] 基础设施检查开始…", file=sys.stderr)
        try:
            infra_results = check_infrastructure()
            infra_viol = len(infra_results.get("violations", []))
            print(
                f"[audit] 基础设施检查完成: "
                f"服务器={len(infra_results.get('servers', {}))} "
                f"数据库={len(infra_results.get('databases', {}))} "
                f"违规={infra_viol}",
                file=sys.stderr,
            )
        except Exception as e:  # 基础设施检查崩溃不能拖垮整个巡检
            print(f"[audit] 基础设施检查异常（已降级跳过）：{e}", file=sys.stderr)
            infra_results = None

    # 1. 加载注册项目
    projects = load_registered_projects()
    if not projects:
        print(
            f"[audit] 未发现注册项目（或 {LIFECYCLE_INDEX} 不存在）",
            file=sys.stderr,
        )
        # 仍写一份报告（含基础设施检查结果，若有），便于追踪
        report = build_report({}, infrastructure=infra_results)
        if not args.no_write:
            out = write_report(report)
            print(f"[audit] 空报告已写入: {out}")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.notify:
            notify_via_lark(report)
        # 即便无项目，基础设施 critical 也要让退出码反映
        infra_crit = _count_critical_infra(infra_results)
        return 1 if infra_crit > 0 else 0

    # 2. 预计算全局 KB 指纹（所有项目共用，只算一次）
    global_fingerprints = build_global_kb_fingerprints()
    print(
        f"[audit] 全局 KB 指纹: {len(global_fingerprints)} 个知识文件",
        file=sys.stderr,
    )

    # 3. 逐项目检查（单项目失败不影响其他）
    projects_results: dict[str, dict[str, Any]] = {}
    for name, root in projects:
        print(f"[audit] 检查项目: {name} ({root})", file=sys.stderr)
        try:
            projects_results[name] = audit_project(name, root, global_fingerprints)
        except Exception as e:
            # 兜底：保证单项目异常不影响整体
            projects_results[name] = {
                "path": str(root),
                "violations": [_make_violation(
                    "hash_mismatch", "warning", str(root),
                    f"项目巡检异常：{e}",
                )],
                "error": str(e),
            }

    # 4. 组装 + 写报告（含基础设施检查结果）
    report = build_report(projects_results, infrastructure=infra_results)
    out_path: Path | None = None
    if not args.no_write:
        out_path = write_report(report)
        print(f"[audit] 报告已写入: {out_path}", file=sys.stderr)

    # 5. 控制台摘要（项目 + 基础设施 critical/warning）
    crit = sum(
        1 for r in projects_results.values()
        for v in r.get("violations", [])
        if v.get("severity") == "critical"
    )
    warn = sum(
        1 for r in projects_results.values()
        for v in r.get("violations", [])
        if v.get("severity") == "warning"
    )
    if infra_results is not None:
        infra_crit = _count_critical_infra(infra_results)
        infra_warn = _count_warning_infra(infra_results)
        crit += infra_crit
        warn += infra_warn
    print(
        f"[audit] 完成: 项目={report['projects_checked']} "
        f"违规={report['total_violations']} (critical={crit}, warning={warn})",
        file=sys.stderr,
    )

    # 6. 可选：JSON 到 stdout
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # 7. 可选：飞书通知
    if args.notify:
        notify_via_lark(report)

    # 8. 退出码：有 critical（项目或基础设施）→ 1，否则 0
    return 1 if crit > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
