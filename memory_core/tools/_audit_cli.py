#!/usr/bin/env python3.12
"""CLI 入口：参数解析、巡检编排、控制台摘要、退出码。

依赖层级：位于拆分链顶层，依赖 _audit_project、_audit_server、_audit_report。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ._audit_project import (
    LIFECYCLE_INDEX,
    _make_violation,
    build_global_kb_fingerprints,
    load_registered_projects,
)
from ._audit_report import (
    build_report,
    notify_via_lark,
    write_report,
)
from ._audit_server import audit_project, check_infrastructure

__all__ = [
    "_parse_args",
    "_count_critical_infra",
    "_count_warning_infra",
    "_run_infra_check",
    "_handle_no_projects",
    "_audit_all_projects",
    "_summarize_to_console",
    "main",
]


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
            n += sum(1 for v in rec.get("violations", []) if v.get("severity") == "critical")
    return n


def _count_warning_infra(infra: dict[str, Any] | None) -> int:
    """统计基础设施子树里 warning 违规数（servers + databases）。"""
    if not infra:
        return 0
    n = 0
    for kind in ("servers", "databases"):
        for _name, rec in (infra.get(kind) or {}).items():
            n += sum(1 for v in rec.get("violations", []) if v.get("severity") == "warning")
    return n


def _run_infra_check(no_infra: bool) -> dict[str, Any] | None:
    """执行基础设施检查，异常时降级返回 None。"""
    if no_infra:
        return None
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
        return infra_results
    except Exception as e:
        print(f"[audit] 基础设施检查异常（已降级跳过）：{e}", file=sys.stderr)
        return None


def _handle_no_projects(infra_results: dict[str, Any] | None, args: argparse.Namespace) -> int:
    """处理无注册项目场景，返回退出码。"""
    print(
        f"[audit] 未发现注册项目（或 {LIFECYCLE_INDEX} 不存在）",
        file=sys.stderr,
    )
    report = build_report({}, infrastructure=infra_results)
    if not args.no_write:
        out = write_report(report)
        print(f"[audit] 空报告已写入: {out}", file=sys.stderr)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.notify:
        notify_via_lark(report)
    infra_crit = _count_critical_infra(infra_results)
    return 1 if infra_crit > 0 else 0


def _audit_all_projects(
    projects: list[tuple[str, Path]], global_fingerprints: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """逐项目审计，单项目异常不影响整体。"""
    projects_results: dict[str, dict[str, Any]] = {}
    for name, root in projects:
        print(f"[audit] 检查项目: {name} ({root})", file=sys.stderr)
        try:
            projects_results[name] = audit_project(name, root, global_fingerprints)
        except Exception as e:
            projects_results[name] = {
                "path": str(root),
                "violations": [
                    _make_violation(
                        "hash_mismatch",
                        "warning",
                        str(root),
                        f"项目巡检异常：{e}",
                    )
                ],
                "error": str(e),
            }
    return projects_results


def _summarize_to_console(
    projects_results: dict[str, dict[str, Any]],
    infra_results: dict[str, Any] | None,
    report: dict[str, Any],
) -> int:
    """打印控制台摘要，返回 critical 计数。"""
    crit = sum(1 for r in projects_results.values() for v in r.get("violations", []) if v.get("severity") == "critical")
    warn = sum(1 for r in projects_results.values() for v in r.get("violations", []) if v.get("severity") == "warning")
    if infra_results is not None:
        crit += _count_critical_infra(infra_results)
        warn += _count_warning_infra(infra_results)
    print(
        f"[audit] 完成: 项目={report['projects_checked']} "
        f"违规={report['total_violations']} (critical={crit}, warning={warn})",
        file=sys.stderr,
    )
    return crit


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

    # 0. 基础设施检查
    infra_results = _run_infra_check(args.no_infra)

    # 1. 加载注册项目
    projects = load_registered_projects()
    if not projects:
        return _handle_no_projects(infra_results, args)

    # 2. 预计算全局 KB 指纹
    global_fingerprints = build_global_kb_fingerprints()
    print(
        f"[audit] 全局 KB 指纹: {len(global_fingerprints)} 个知识文件",
        file=sys.stderr,
    )

    # 3. 逐项目检查
    projects_results = _audit_all_projects(projects, global_fingerprints)

    # 4. 组装 + 写报告
    report = build_report(projects_results, infrastructure=infra_results)
    if not args.no_write:
        out_path = write_report(report)
        print(f"[audit] 报告已写入: {out_path}", file=sys.stderr)

    # 5. 控制台摘要
    crit = _summarize_to_console(projects_results, infra_results, report)

    # 6. 可选：JSON 到 stdout
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # 7. 可选：飞书通知
    if args.notify:
        notify_via_lark(report)

    # 8. 退出码
    return 1 if crit > 0 else 0
