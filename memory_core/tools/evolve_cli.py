"""
evolve CLI：status / backup-paths / run / gk-ensure 子命令

D6 stdout 纪律：stdout 只放载荷，诊断/告警走 stderr
D1 双入口：memory-evolve console script 与 python3 -m memory_core.tools.evolve_cli 等价
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_core.evolution.analyzer import IncrementalAnalyzer
from memory_core.evolution.config import load_or_create_config
from memory_core.evolution.extractor import LLMExtractor, NoLlmExtractor
from memory_core.evolution.registry import EvolutionRegistry
from memory_core.evolution.sediment import (
    git_commit_if_needed,
    gk_ensure,
    write_candidates,
    write_unrefined_candidates,
)


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
    """读取上次运行统计（从 state.json 或 reports/）"""
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

        projects = state_data.get("projects", {})
        stats["projects_count"] = len(projects)

        # 汇总所有项目的 candidates_count
        total_candidates = 0
        for proj_data in projects.values():
            proj_stats = proj_data.get("stats", {})
            total_candidates += proj_stats.get("candidates_count", 0)
        stats["candidates_count"] = total_candidates

        # 从最新报告读取 last_run_at
        reports_dir = evolution_root / "reports"
        if reports_dir.exists():
            report_files = sorted(reports_dir.glob("*.json"), reverse=True)
            if report_files:
                try:
                    with report_files[0].open(encoding="utf-8") as f:
                        report_data = json.load(f)
                    stats["last_run_at"] = report_data.get("run_at")
                except (json.JSONDecodeError, OSError):
                    pass
    except (json.JSONDecodeError, OSError):
        pass

    return stats


def _get_pending_count(global_kb_root: Path) -> int:
    """获取 pending/ 目录下的候选数量（排除脚手架 README.md）"""
    pending_dir = global_kb_root / "pending"
    if not pending_dir.exists():
        return 0

    try:
        count = 0
        for f in pending_dir.glob("*.md"):
            if f.name == "README.md":
                continue  # 排除脚手架文件
            count += 1
        return count
    except OSError:
        return 0


def _resolve_global_kb_root(args: argparse.Namespace) -> Path:
    """解析 global-kb root 三级优先级：flag > env > 默认"""
    if hasattr(args, "global_kb_root") and args.global_kb_root:
        return Path(args.global_kb_root)
    from memory_core.tools.global_kb_init import get_global_kb_root

    return get_global_kb_root()


def cmd_status(args: argparse.Namespace) -> None:
    """status 子命令：列出全部注册项目 + 健康分类 + 上次运行统计 + pending 数量"""
    evolution_root = _get_evolution_root()
    global_kb_root = _resolve_global_kb_root(args)

    registry = EvolutionRegistry()
    entries = registry.get_all_entries()

    last_run_stats = _get_last_run_stats(evolution_root)
    pending_count = _get_pending_count(global_kb_root)

    if args.json:
        output = {
            "projects": sorted([e.to_dict() for e in entries], key=lambda x: x["git_root"]),
            "last_run": last_run_stats,
            "pending_count": pending_count,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"== 注册项目（{len(entries)} 个） ==")
        for entry in sorted(entries, key=lambda e: str(e.git_root)):
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
    """backup-paths 子命令"""
    registry = EvolutionRegistry()
    backup_paths = registry.get_backup_paths()

    if args.json:
        print(json.dumps(backup_paths, indent=2, ensure_ascii=False))
    else:
        for path in backup_paths:
            print(path)


def _write_errors_log(evolution_root: Path, message: str) -> None:
    """追加错误到 errors.log"""
    errors_log = evolution_root / "errors.log"
    timestamp = datetime.now().isoformat()
    try:
        with errors_log.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError as e:
        print(f"Warning: Cannot write errors.log: {e}", file=sys.stderr)


def _write_report(
    evolution_root: Path,
    report: dict[str, Any],
) -> Path:
    """写入运行报告到 reports/，返回报告路径"""
    reports_dir = evolution_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"run_{timestamp}.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report_path


def cmd_gk_ensure(args: argparse.Namespace) -> int:
    """gk-ensure 子命令：全局库 git 归位（D8）"""
    global_kb_root = _resolve_global_kb_root(args)
    exit_code, message = gk_ensure(global_kb_root)
    if exit_code != 0:
        print(f"gk-ensure: {message}", file=sys.stderr)
    else:
        print(f"gk-ensure: {message}", file=sys.stderr)
    return exit_code


def _print_dry_run_plan(
    projects_to_process: list[Path],
    analyzer: IncrementalAnalyzer,
    global_kb_root: Path,
) -> int:
    """D3: dry-run 只打印 resolved root 与执行计划，零写入零游标推进"""
    plan: dict[str, Any] = {
        "mode": "dry-run",
        "resolved_global_kb_root": str(global_kb_root),
        "projects_count": len(projects_to_process),
        "projects": [],
    }
    for proj in projects_to_process:
        result = analyzer.analyze_project(proj)
        plan["projects"].append(
            {
                "project": str(proj),
                "changed_files": [fc.rel_path for fc in result.changed_files],
                "changed_count": len(result.changed_files),
                "skipped_by_cap": result.skipped_by_cap,
                "error": result.error,
            }
        )
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


def _run_projects(
    projects_to_process: list[Path],
    analyzer: IncrementalAnalyzer,
    no_llm: bool,
    no_llm_extractor: NoLlmExtractor | None,
    llm_extractor: LLMExtractor | None,
    is_single_project: bool,
    evolution_root: Path,
    run_report: dict[str, Any],
    all_candidates: list[dict[str, Any]],
) -> tuple[bool, list[tuple[Path, list[dict[str, Any]]]]]:
    """逐项目执行 分析→提取；--all 下失败隔离、--project 下致命（D4）

    返回: (had_fatal_error, pending_cursor_updates)
    pending_cursor_updates: [(project_root, [FileChange_dicts])]，
    由调用方在沉淀成功后推进游标（修复：游标应在沉淀成功后推进，沉淀失败文件下轮重析）
    """
    had_fatal_error = False
    pending_cursor_updates: list[tuple[Path, list[dict[str, Any]]]] = []

    for proj in projects_to_process:
        proj_report: dict[str, Any] = {
            "project": str(proj),
            "changed_files": [],
            "candidates": [],
            "skipped_by_cap": 0,
            "error": None,
        }

        # 分析
        result = analyzer.analyze_project(proj)

        if result.error:
            proj_report["error"] = result.error
            _write_errors_log(evolution_root, f"项目 {proj} 分析失败: {result.error}")
            run_report["errors"].append(
                {
                    "project": str(proj),
                    "error": result.error,
                }
            )

            if is_single_project:
                # D4: --project 下失败即致命
                had_fatal_error = True
            # --all 下继续处理其他项目
            run_report["projects"].append(proj_report)
            continue

        proj_report["changed_files"] = [fc.rel_path for fc in result.changed_files]
        proj_report["skipped_by_cap"] = result.skipped_by_cap

        if not result.changed_files:
            run_report["projects"].append(proj_report)
            continue

        # 提取候选
        changed_dicts = [
            {
                "abs_path": fc.abs_path,
                "rel_path": fc.rel_path,
                "project_root": fc.project_root,
                "sha256": fc.sha256,
            }
            for fc in result.changed_files
        ]

        if no_llm:
            assert no_llm_extractor is not None
            candidates = no_llm_extractor.extract_from_files(changed_dicts, proj)
        else:
            assert llm_extractor is not None
            # FIX: 必须传递 project_root 参数，否则 LLM prompt 缺少项目上下文
            candidates = llm_extractor.extract_from_files(changed_dicts, proj)

        # 转换为 dict
        for cand in candidates:
            cand_dict = {
                "title": cand.title,
                "domain": cand.domain,
                "content": cand.content,
                "confidence": cand.confidence,
                "source_refs": cand.source_refs,
                "genericity": cand.genericity,
                "unrefined": cand.unrefined,
            }
            all_candidates.append(cand_dict)
            proj_report["candidates"].append(
                {
                    "title": cand.title,
                    "domain": cand.domain,
                    "confidence": cand.confidence,
                    "genericity": cand.genericity,
                    "unrefined": cand.unrefined,
                    "source_refs": cand.source_refs,
                }
            )

        # FIX: 不在这里推进游标！将游标更新推迟到沉淀成功后
        # 将本轮处理的文件信息暂存，等待调用方在沉淀成功后推进
        pending_cursor_updates.append((proj, changed_dicts))

        analyzer.update_stats(
            proj,
            candidates_count=len(candidates),
            changed_count=len(result.changed_files),
            skipped_by_cap=result.skipped_by_cap,
        )

        run_report["projects"].append(proj_report)

    return had_fatal_error, pending_cursor_updates


def _resolve_project_list(
    args: argparse.Namespace,
    registry: EvolutionRegistry,
) -> tuple[list[Path], bool]:
    """解析项目列表（D5：--all 与 --project 互斥）

    Returns:
        (projects_to_process, is_single_project)
    """
    has_project = getattr(args, "project", None) is not None
    max_projects = getattr(args, "max_projects", None)

    if has_project:
        project_path = Path(args.project)
        if not project_path.exists():
            print(f"Error: 项目路径不存在: {project_path}", file=sys.stderr)
            return [], True
        projects_to_process = [project_path]
        is_single_project = True
    else:
        entries = registry.get_all_entries()
        projects_to_process = [e.git_root for e in entries if e.health != "missing"]
        is_single_project = False

    # max_projects 限额
    if max_projects is not None:
        projects_to_process = projects_to_process[:max_projects]

    return projects_to_process, is_single_project


def cmd_run(args: argparse.Namespace) -> int:
    """run 子命令：编排分析→提取→沉淀"""
    # D5: --all 与 --project 互斥且必选其一
    has_all = getattr(args, "all", False)
    has_project = getattr(args, "project", None) is not None

    if has_all == has_project:
        # 都给或都不给
        print("Error: 必须且只能提供 --all 或 --project <path> 之一", file=sys.stderr)
        return 2

    evolution_root = _get_evolution_root()
    global_kb_root = _resolve_global_kb_root(args)

    dry_run = getattr(args, "dry_run", False)
    no_llm = getattr(args, "no_llm", False)

    # 加载配置（首跑自动生成）
    config = load_or_create_config(evolution_root)
    state_file = evolution_root / "state.json"

    # 解析项目列表
    registry = EvolutionRegistry()
    projects_to_process, is_single_project = _resolve_project_list(args, registry)

    # 检查项目路径是否存在
    if getattr(args, "project", None) is not None and not projects_to_process:
        _write_errors_log(evolution_root, f"项目路径不存在: {args.project}")
        return 1  # D4: 致命失败

    analyzer = IncrementalAnalyzer(state_file, config)

    # D3: dry-run 模式（必须在 gk-ensure 之前早退，dry-run 零写入——D3/D8 边界）
    if dry_run:
        # 打印 resolved root 与执行计划，零写入
        return _print_dry_run_plan(projects_to_process, analyzer, global_kb_root)

    # 自动前置 gk-ensure（VAL-SED-005）——dry-run 之后、写入阶段之前
    exit_code, message = gk_ensure(global_kb_root)
    if exit_code != 0:
        # D4: 脏工作区 → exit 1 零写入
        return 1

    # 实际运行
    run_report: dict[str, Any] = {
        "run_at": datetime.now().isoformat(),
        "mode": "no-llm" if no_llm else "llm",
        "resolved_global_kb_root": str(global_kb_root),
        "projects": [],
        "total_candidates": 0,
        "total_written": 0,
        "total_skipped_duplicate": 0,
        "total_merged": 0,  # FIX: 初始化 total_merged（VAL-SED-002 场景 C）
        "errors": [],
        "llm_tokens_used": 0,
    }

    # 初始化提取器
    no_llm_extractor = NoLlmExtractor(config) if no_llm else None
    llm_extractor: LLMExtractor | None = None
    if not no_llm:
        llm_extractor = LLMExtractor(config)

    all_candidates: list[dict[str, Any]] = []

    had_fatal_error, pending_cursor_updates = _run_projects(
        projects_to_process,
        analyzer,
        no_llm,
        no_llm_extractor,
        llm_extractor,
        is_single_project,
        evolution_root,
        run_report,
        all_candidates,
    )

    # 更新 LLM 统计
    if llm_extractor is not None:
        run_report["llm_tokens_used"] = llm_extractor.tokens_used
        run_report["llm_calls"] = llm_extractor.llm_calls
        if not llm_extractor.budget.can_call():
            run_report["budget_exceeded"] = True
            run_report["budget_limit"] = llm_extractor.budget.daily_budget_tokens

    # 沉淀写入（全部项目处理完后统一写入）
    sediment_succeeded = False
    if all_candidates:
        # 分离 refined 和 unrefined 候选
        refined_candidates = [c for c in all_candidates if not c["unrefined"]]
        unrefined_candidates = [c for c in all_candidates if c["unrefined"]]

        # 写入 refined 候选（走置信度分层）
        if refined_candidates:
            write_stats = write_candidates(refined_candidates, global_kb_root, config)
            run_report["total_written"] += write_stats["written"]
            run_report["total_skipped_duplicate"] += write_stats["skipped_duplicate"]
            run_report["total_merged"] += write_stats.get("merged", 0)

        # 写入 unrefined 候选（全部进 pending）
        if unrefined_candidates:
            write_stats_unrefined = write_unrefined_candidates(unrefined_candidates, global_kb_root, config)
            run_report["total_written"] += write_stats_unrefined["written"]
            run_report["total_skipped_duplicate"] += write_stats_unrefined["skipped_duplicate"]
            # FIX: unrefined 路径 merged 也计入 total_merged（VAL-SED-002 场景 C）
            run_report["total_merged"] += write_stats_unrefined.get("merged", 0)

        run_report["total_candidates"] = len(all_candidates)
        run_report["refined_count"] = len(refined_candidates)
        run_report["unrefined_count"] = len(unrefined_candidates)

        # git 提交
        git_commit_if_needed(global_kb_root, config)
        sediment_succeeded = True

    # FIX: 游标在沉淀成功后推进（沉淀失败文件下轮重析）
    if sediment_succeeded:
        for proj, changed_dicts in pending_cursor_updates:
            from memory_core.evolution.analyzer import FileChange

            file_changes = [
                FileChange(
                    abs_path=Path(cd["abs_path"]),
                    rel_path=cd["rel_path"],
                    project_root=Path(cd["project_root"]) if cd.get("project_root") else proj,
                    sha256=cd["sha256"],
                )
                for cd in changed_dicts
            ]
            analyzer.update_cursors(proj, file_changes)

    # 写入报告
    report_path = _write_report(evolution_root, run_report)
    print(f"报告已写入: {report_path}", file=sys.stderr)

    if had_fatal_error:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="memory-evolve",
        description="全局经验接口：每日项目分析提取 + 全局知识库沉淀",
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # status 子命令
    status_parser = subparsers.add_parser("status", help="列出全部注册项目 + 健康分类 + 上次运行统计")
    status_parser.add_argument("--json", action="store_true", help="输出 JSON 格式（D6: stdout 只放载荷）")
    status_parser.add_argument(
        "--global-kb-root",
        default=None,
        help="覆盖全局库根路径（优先级最高）",
    )

    # backup-paths 子命令
    backup_parser = subparsers.add_parser("backup-paths", help="输出全部消费项目 memory 目录路径（D11: missing 剔除）")
    backup_parser.add_argument("--json", action="store_true", help="输出 JSON 格式（D6: stdout 只放载荷）")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行管道：分析→提取→沉淀")
    run_group = run_parser.add_mutually_exclusive_group()
    run_group.add_argument("--all", action="store_true", help="处理全部注册项目（D5）")
    run_group.add_argument("--project", type=str, default=None, help="处理指定项目路径（D5）")
    run_parser.add_argument("--dry-run", action="store_true", help="只打印执行计划，不实际写入（D3）")
    run_parser.add_argument("--no-llm", action="store_true", help="禁用 LLM 蒸馏，原样捕获到 pending/")
    run_parser.add_argument(
        "--global-kb-root",
        default=None,
        help="覆盖全局库根路径（优先级最高，架构 §3.7）",
    )
    run_parser.add_argument(
        "--max-projects",
        type=int,
        default=None,
        help="限制单轮处理项目数",
    )

    # gk-ensure 子命令
    gk_parser = subparsers.add_parser("gk-ensure", help="全局库 git 归位（D8: 幂等）")
    gk_parser.add_argument(
        "--global-kb-root",
        default=None,
        help="覆盖全局库根路径（优先级最高）",
    )

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
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "gk-ensure":
        return cmd_gk_ensure(args)
    else:
        parser.print_help(sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
