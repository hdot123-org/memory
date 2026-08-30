#!/usr/bin/env python3.12
"""每日记忆巡检脚本 — 检查所有接入项目的记忆纯度和完整性。

M3 拆分：本文件仅做向后兼容的 re-export 门面，全部实现移入单一职责模块：

- _audit_project: 路径常量、工具函数、项目解析、全局 KB 指纹（最底层）
- _audit_checks:  检查 1-5（manifest / 未签名 / 残留 / 大文件 / 版本一致性）
- _audit_infra:   基础设施清单加载、SSH、TCP、磁盘、systemd 服务
- _audit_server:  服务器/数据库检查、单项目编排 audit_project
- _audit_report:  报告组装、文件写入、飞书通知摘要
- _audit_cli:     CLI 入口 main() 与编排

对 ~/.memory-core/project-lifecycle/path-index.json 里注册的所有项目，
执行以下检查，生成 JSON 报告到 ~/.memory-core/audit/ 目录。

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

兼容性：
- 包内导入使用相对导入（``from ._audit_project import ...``）
- 裸模块导入（把 tools 目录加进 sys.path 的场景）回退到绝对导入
"""

from __future__ import annotations

import socket as socket  # noqa: F401 — 测试 patch 目标（re-export）
import subprocess as subprocess  # noqa: F401 — 测试 patch 目标（re-export）
import sys

from memory_core.constants import (
    CURRENT_MEMORY_VERSION as CURRENT_MEMORY_VERSION,  # noqa: F401 — 测试 patch 目标
)
from memory_core.constants import (
    SYSTEM_DIR as SYSTEM_DIR,  # noqa: F401 — re-export（原模块顶层名）
)

if __package__:
    # ── 包内导入（正常路径）──────────────────────────────────────────
    from ._audit_checks import (  # noqa: F401
        _EXCLUDED_DIR_SEGMENTS,
        DATABASE_FILE_SUFFIXES,
        LARGE_SQL_THRESHOLD,
        _check_single_file,
        _extract_version_from_toml,
        _is_excludable_path,
        check_global_residue,
        check_large_or_db_files,
        check_manifest_integrity,
        check_unsigned_files,
        check_version_consistency,
    )
    from ._audit_cli import (  # noqa: F401
        _audit_all_projects,
        _count_critical_infra,
        _count_warning_infra,
        _handle_no_projects,
        _parse_args,
        _run_infra_check,
        _summarize_to_console,
        main,
    )
    from ._audit_infra import (  # noqa: F401
        _HAS_YAML,
        INFRA_INVENTORY,
        SSH_CONNECT_TIMEOUT,
        SSH_TIMEOUT,
        TCP_TIMEOUT,
        _check_systemd_services,
        _find_matching_mount,
        _load_infra_inventory,
        _parse_df_output,
        _run_ssh,
        _shell_quote,
        _tcp_connect_ok,
        check_disk_space,
        check_ssh_reachable,
    )
    from ._audit_infra import (
        yaml as yaml,
    )
    from ._audit_patch_redirect import install_redirect as install_redirect  # noqa: F401
    from ._audit_project import (  # noqa: F401
        _FRONTMATTER_RE,
        AUDIT_DIR,
        GLOBAL_KB_DOMAINS,
        GLOBAL_KB_ROOT,
        GLOBAL_KB_SKIP,
        HTTP_TIMEOUT,
        KB_UNSIGNED_WHITELIST,
        LARK_NOTIFY_ENV,
        LARK_NOTIFY_TIMEOUT,
        LIFECYCLE_INDEX,
        MANIFEST_FILENAME,
        MANIFEST_PATH_REL,
        MEMORY_CORE_HOME,
        _make_violation,
        _normalize_for_compare,
        _now_iso_local,
        _read_text_safe,
        _sha256_file,
        _strip_frontmatter,
        build_global_kb_fingerprints,
        load_registered_projects,
        sha256_file,
    )
    from ._audit_report import (  # noqa: F401
        _append_infra_summary,
        _summarize_containers,
        _summarize_database_entry,
        _summarize_disks,
        _summarize_http,
        _summarize_ports,
        _summarize_report,
        _summarize_server_entry,
        _summarize_ssh,
        _summarize_systemd,
        _summarize_violation_block,
        build_report,
        notify_via_lark,
        write_report,
    )
    from ._audit_server import (  # noqa: F401
        _append_violation,
        _check_server_docker,
        _check_server_http_endpoints,
        _check_server_ports,
        _check_server_ssh,
        _safe_check,
        audit_project,
        check_database,
        check_infrastructure,
        check_server,
        is_memory_core_source_repo,
    )
    from ._file_utils import now_iso as now_iso  # noqa: F401 — re-export（原模块顶层名）
else:
    # ── 裸模块导入回退（tools 目录在 sys.path 上时）─────────────────
    from memory_core.tools._audit_checks import (  # noqa: F401
        _EXCLUDED_DIR_SEGMENTS,
        DATABASE_FILE_SUFFIXES,
        LARGE_SQL_THRESHOLD,
        _check_single_file,
        _extract_version_from_toml,
        _is_excludable_path,
        check_global_residue,
        check_large_or_db_files,
        check_manifest_integrity,
        check_unsigned_files,
        check_version_consistency,
    )
    from memory_core.tools._audit_cli import (  # noqa: F401
        _audit_all_projects,
        _count_critical_infra,
        _count_warning_infra,
        _handle_no_projects,
        _parse_args,
        _run_infra_check,
        _summarize_to_console,
        main,
    )
    from memory_core.tools._audit_infra import (  # noqa: F401
        _HAS_YAML,
        INFRA_INVENTORY,
        SSH_CONNECT_TIMEOUT,
        SSH_TIMEOUT,
        TCP_TIMEOUT,
        _check_systemd_services,
        _find_matching_mount,
        _load_infra_inventory,
        _parse_df_output,
        _run_ssh,
        _shell_quote,
        _tcp_connect_ok,
        check_disk_space,
        check_ssh_reachable,
    )
    from memory_core.tools._audit_infra import (
        yaml as yaml,
    )
    from memory_core.tools._audit_patch_redirect import (  # noqa: F401
        install_redirect as install_redirect,
    )
    from memory_core.tools._audit_project import (  # noqa: F401
        _FRONTMATTER_RE,
        AUDIT_DIR,
        GLOBAL_KB_DOMAINS,
        GLOBAL_KB_ROOT,
        GLOBAL_KB_SKIP,
        HTTP_TIMEOUT,
        KB_UNSIGNED_WHITELIST,
        LARK_NOTIFY_ENV,
        LARK_NOTIFY_TIMEOUT,
        LIFECYCLE_INDEX,
        MANIFEST_FILENAME,
        MANIFEST_PATH_REL,
        MEMORY_CORE_HOME,
        _make_violation,
        _normalize_for_compare,
        _now_iso_local,
        _read_text_safe,
        _sha256_file,
        _strip_frontmatter,
        build_global_kb_fingerprints,
        load_registered_projects,
        sha256_file,
    )
    from memory_core.tools._audit_report import (  # noqa: F401
        _append_infra_summary,
        _summarize_containers,
        _summarize_database_entry,
        _summarize_disks,
        _summarize_http,
        _summarize_ports,
        _summarize_report,
        _summarize_server_entry,
        _summarize_ssh,
        _summarize_systemd,
        _summarize_violation_block,
        build_report,
        notify_via_lark,
        write_report,
    )
    from memory_core.tools._audit_server import (  # noqa: F401
        _append_violation,
        _check_server_docker,
        _check_server_http_endpoints,
        _check_server_ports,
        _check_server_ssh,
        _safe_check,
        audit_project,
        check_database,
        check_infrastructure,
        check_server,
        is_memory_core_source_repo,
    )
    from memory_core.tools._file_utils import now_iso as now_iso  # noqa: F401 — re-export（原模块顶层名）

# ---------------------------------------------------------------------------
# __all__（re-export 声明）与 monkeypatch 目标重定向安装
# ---------------------------------------------------------------------------
__all__ = [
    # _audit_project 路径/规则常量
    "MEMORY_CORE_HOME",
    "LIFECYCLE_INDEX",
    "AUDIT_DIR",
    "GLOBAL_KB_ROOT",
    "GLOBAL_KB_DOMAINS",
    "GLOBAL_KB_SKIP",
    "MANIFEST_FILENAME",
    "MANIFEST_PATH_REL",
    "KB_UNSIGNED_WHITELIST",
    "LARGE_SQL_THRESHOLD",
    "DATABASE_FILE_SUFFIXES",
    "LARK_NOTIFY_ENV",
    "LARK_NOTIFY_TIMEOUT",
    "INFRA_INVENTORY",
    "SSH_TIMEOUT",
    "SSH_CONNECT_TIMEOUT",
    "TCP_TIMEOUT",
    "HTTP_TIMEOUT",
    # _audit_project 工具函数
    "_now_iso_local",
    "sha256_file",
    "_sha256_file",
    "_FRONTMATTER_RE",
    "_strip_frontmatter",
    "_normalize_for_compare",
    "_read_text_safe",
    "_make_violation",
    "load_registered_projects",
    "build_global_kb_fingerprints",
    # _audit_checks 检查 1-5
    "check_manifest_integrity",
    "check_unsigned_files",
    "check_global_residue",
    "check_large_or_db_files",
    "check_version_consistency",
    "_is_excludable_path",
    "_check_single_file",
    "_extract_version_from_toml",
    "_EXCLUDED_DIR_SEGMENTS",
    # _audit_infra 基础设施底层
    "_load_infra_inventory",
    "_tcp_connect_ok",
    "_run_ssh",
    "check_ssh_reachable",
    "_parse_df_output",
    "_find_matching_mount",
    "check_disk_space",
    "_check_systemd_services",
    "_shell_quote",
    "_HAS_YAML",
    "yaml",
    # _audit_server 服务器/数据库/编排
    "_append_violation",
    "_check_server_ssh",
    "_check_server_docker",
    "_check_server_ports",
    "_check_server_http_endpoints",
    "check_server",
    "check_database",
    "check_infrastructure",
    "_safe_check",
    "audit_project",
    "is_memory_core_source_repo",
    # _audit_report 报告/通知
    "build_report",
    "write_report",
    "_summarize_violation_block",
    "_summarize_report",
    "_summarize_ssh",
    "_summarize_systemd",
    "_summarize_containers",
    "_summarize_ports",
    "_summarize_http",
    "_summarize_disks",
    "_summarize_database_entry",
    "_summarize_server_entry",
    "_append_infra_summary",
    "notify_via_lark",
    # _audit_cli CLI
    "_parse_args",
    "_count_critical_infra",
    "_count_warning_infra",
    "_run_infra_check",
    "_handle_no_projects",
    "_audit_all_projects",
    "_summarize_to_console",
    "main",
    # 重导出（测试 patch 目标 / 原模块顶层名）
    "CURRENT_MEMORY_VERSION",
    "socket",
    "subprocess",
    "SYSTEM_DIR",
    "now_iso",
    # 兼容层
    "install_redirect",
]

# ---------------------------------------------------------------------------
# M3 兼容层：把对门面符号的 monkeypatch/patch.object 写入重定向到实际
# 查找该符号的子模块（保持旧测试打桩语义，详见 _audit_patch_redirect）。
# ---------------------------------------------------------------------------
install_redirect(sys.modules[__name__])

if __name__ == "__main__":
    sys.exit(main())
