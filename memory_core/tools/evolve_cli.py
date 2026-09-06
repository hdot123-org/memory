"""
evolve CLI 骨架：status / backup-paths 子命令

D6 stdout 纪律：stdout 只放载荷，诊断/告警走 stderr
D1 双入口：memory-evolve console script 与 python3 -m memory_core.tools.evolve_cli 等价
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from memory_core.evolution.registry import EvolutionRegistry


def _get_evolution_root() -> Path:
    """
    获取 evolution 运行时目录（D2）

    环境变量 MEMORY_CORE_EVOLUTION_ROOT 可覆盖默认 ~/.memory-core/evolution
    """
    env_root = os.environ.get("MEMORY_CORE_EVOLUTION_ROOT")
    if env_root:
        return Path(env_root)
    return Path.home() / ".memory-core" / "evolution"


def _get_last_run_stats(evolution_root: Path) -> dict[str, Any]:
    """
    读取上次运行统计（从 state.json 或 reports/）

    Returns:
        {"last_run_at": str|None, "projects_count": int, "candidates_count": int}
    """
    state_file = evolution_root / "state.json"
    stats: dict[str, Any] = {
        "last_run_at": None,
        "projects_count": 0,
        "candidates_count": 0,
    }

    if not state_file.exists():
        return stats

    try:
        with state_file.open(encoding="utf-8") as f:
            state_data = json.load(f)

        # 简单统计：项目数
        projects = state_data.get("projects", {})
        stats["projects_count"] = len(projects)

        # 尝试从最新报告读取候选数
        reports_dir = evolution_root / "reports"
        if reports_dir.exists():
            report_files = sorted(reports_dir.glob("*.json"), reverse=True)
            if report_files:
                try:
                    with report_files[0].open(encoding="utf-8") as f:
                        report_data = json.load(f)
                    stats["candidates_count"] = report_data.get("candidates_count", 0)
                    stats["last_run_at"] = report_data.get("run_at")
                except (json.JSONDecodeError, OSError):
                    pass
    except (json.JSONDecodeError, OSError):
        pass

    return stats


def _get_pending_count(global_kb_root: Path) -> int:
    """
    获取 pending/ 目录下的候选数量
    """
    pending_dir = global_kb_root / "pending"
    if not pending_dir.exists():
        return 0

    try:
        return len(list(pending_dir.glob("*.md")))
    except OSError:
        return 0


def cmd_status(args: argparse.Namespace) -> None:
    """status 子命令：列出全部注册项目 + 健康分类 + 上次运行统计 + pending 数量"""
    from memory_core.tools.global_kb_init import get_global_kb_root

    evolution_root = _get_evolution_root()
    global_kb_root = get_global_kb_root()

    # 读取注册表
    registry = EvolutionRegistry()
    entries = registry.get_all_entries()

    # 获取统计信息
    last_run_stats = _get_last_run_stats(evolution_root)
    pending_count = _get_pending_count(global_kb_root)

    if args.json:
        # D6: stdout 只放 JSON
        output = {
            "projects": [e.to_dict() for e in entries],
            "last_run": last_run_stats,
            "pending_count": pending_count,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # 人类可读格式
        print(f"== 注册项目（{len(entries)} 个） ==")
        for entry in entries:
            print(f"  {entry.git_root}  [{entry.health}]")

        print()
        print("== 上次运行统计 ==")
        if last_run_stats["last_run_at"]:
            print(f"  运行时间: {last_run_stats['last_run_at']}")
        else:
            print("  运行时间: 未运行")
        print(f"  项目数: {last_run_stats['projects_count']}")
        print(f"  候选数: {last_run_stats['candidates_count']}")

        print()
        print("== Pending 数量 ==")
        print(f"  {pending_count} 个候选待晋升")


def cmd_backup_paths(args: argparse.Namespace) -> None:
    """backup-paths 子命令：输出全部消费项目 memory 目录路径（D11: missing 剔除）"""
    registry = EvolutionRegistry()
    backup_paths = registry.get_backup_paths()

    if args.json:
        # D6: stdout 只放 JSON
        print(json.dumps(backup_paths, indent=2, ensure_ascii=False))
    else:
        # 每行一个路径
        for path in backup_paths:
            print(path)


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="memory-evolve", description="全局经验接口：每日项目分析提取 + 全局知识库沉淀"
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # status 子命令
    status_parser = subparsers.add_parser("status", help="列出全部注册项目 + 健康分类 + 上次运行统计")
    status_parser.add_argument("--json", action="store_true", help="输出 JSON 格式（D6: stdout 只放载荷）")

    # backup-paths 子命令
    backup_parser = subparsers.add_parser("backup-paths", help="输出全部消费项目 memory 目录路径（D11: missing 剔除）")
    backup_parser.add_argument("--json", action="store_true", help="输出 JSON 格式（D6: stdout 只放载荷）")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    if args.command == "status":
        cmd_status(args)
        return 0
    elif args.command == "backup-paths":
        cmd_backup_paths(args)
        return 0
    else:
        parser.print_help(sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
