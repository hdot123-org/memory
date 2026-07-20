#!/usr/bin/env python3
"""每日日志数据报告生成器 — 读取 A 层 session 记录 + B 层 transcript，生成结构化数据报告。

Usage:
    python daily_summary_generator.py --date 2026-05-28 --project ~/my-project
    python daily_summary_generator.py --today --project ~/my-project
    python daily_summary_generator.py --today --all-projects
    python daily_summary_generator.py --today --project ~/my-project --dry-run
    python daily_summary_generator.py --today --all-projects --fallback-days 7
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# C 层错误日志导入
try:
    from memory_core.tools.error_logger import write_error_log
except ImportError:
    write_error_log = None  # type: ignore[misc,assignment]

# F5: 签名模块导入（ImportError 时静默跳过）
# 使用模块级导入避免 stale binding 问题（monkeypatch 能正确看到 patched 版本）
try:
    from memory_core.tools import memory_hook_integrity_keys as _integrity_keys
    from memory_core.tools import memory_hook_integrity_manifest as _integrity
except ImportError:
    _integrity = None  # type: ignore[misc,assignment]
    _integrity_keys = None  # type: ignore[misc,assignment]

# ---------------------------------------------------------------------------
# 常量 & 配置
# ---------------------------------------------------------------------------

SESSIONS_HOME = Path.home() / ".factory" / "sessions"
LIFECYCLE_INDEX = Path.home() / ".memory-core" / "project-lifecycle" / "path-index.json"


# ---------------------------------------------------------------------------
# CLI 参数
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="每日工作日志总结生成器")
    parser.add_argument("--date", type=str, help="目标日期 (YYYY-MM-DD)")
    parser.add_argument("--today", action="store_true", help="使用今天日期")
    parser.add_argument("--project", type=str, help="项目根目录路径")
    parser.add_argument("--all-projects", action="store_true", help="扫描所有已知消费项目")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    parser.add_argument("--fallback-days", type=int, default=3,
                        help="兜底检查前 N 天未生成的日志（默认 3）")
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Step 1: 读取 A 层数据
# ---------------------------------------------------------------------------

import re

# 正则：匹配 session 标题行（### 后接 8 位 hex 字符）
_SESSION_HEADER_RE = re.compile(r'^### ([0-9a-f]{8})$')


# ---------------------------------------------------------------------------
# _read_a_layer field handlers (dispatch table)
# ---------------------------------------------------------------------------


def _handle_title_line(line: str, current: dict[str, Any]) -> None:
    """Handle `- **标题**: ...` field line."""
    current["title"] = line.split(": ", 1)[1] if ": " in line else ""


def _handle_model_line(line: str, current: dict[str, Any]) -> None:
    """Handle `- **模型**: ...` field line (includes duration parse)."""
    rest = line.split(": ", 1)[1] if ": " in line else ""
    # "GLM-5.1 (官方) | 时长: 2m35s"
    parts = rest.split(" | ")
    current["model"] = parts[0].strip() if parts else ""
    for p in parts:
        if "时长" in p:
            current["duration"] = p.split(": ", 1)[1].strip()


def _handle_token_line(line: str, current: dict[str, Any]) -> None:
    """Handle `- **Token**: ...` field line (input=... output=...)."""
    rest = line.split(": ", 1)[1] if ": " in line else ""
    for token_part in rest.split():
        if "=" in token_part:
            k, v = token_part.split("=", 1)
            try:
                current[f"{k}_tokens"] = int(v)
            except ValueError:
                pass


def _handle_tool_calls_line(line: str, current: dict[str, Any]) -> None:
    """Handle `- **工具调用**: ...` field line."""
    current["tool_calls_raw"] = line.split(": ", 1)[1] if ": " in line else ""


def _handle_user_prompt_line(line: str, current: dict[str, Any]) -> None:
    """Handle `- **用户意图**: ...` field line."""
    current["user_prompt_preview"] = line.split(": ", 1)[1] if ": " in line else ""


def _handle_assistant_summary_line(line: str, current: dict[str, Any]) -> None:
    """Handle `- **助手摘要**: ...` field line."""
    current["assistant_summary_preview"] = line.split(": ", 1)[1] if ": " in line else ""


# Dispatch table: prefix → handler(current, line)
# Order matters: first matching prefix wins (though prefixes are disjoint here).
_LAYER_FIELD_HANDLERS: list[tuple[str, Any]] = [
    ("- **标题**: ", _handle_title_line),
    ("- **模型**: ", _handle_model_line),
    ("- **Token**: ", _handle_token_line),
    ("- **工具调用**: ", _handle_tool_calls_line),
    ("- **用户意图**: ", _handle_user_prompt_line),
    ("- **助手摘要**: ", _handle_assistant_summary_line),
]


def _dispatch_layer_field(line: str, current: dict[str, Any]) -> bool:
    """Dispatch a field line to the appropriate handler.

    Returns True if a handler matched, False otherwise.
    """
    for prefix, handler in _LAYER_FIELD_HANDLERS:
        if line.startswith(prefix):
            handler(line, current)
            return True
    return False


def _read_a_layer(project_root: Path, target_date: str) -> list[dict[str, Any]] | None:
    """读取 {project}/memory/log/{date}-sessions.md，解析 session 记录。

    返回 list[dict] 每个包含 session_id (full), title, model, duration,
    input_tokens, output_tokens, health 等信息。
    """
    log_path = project_root / "memory" / "log" / f"{target_date}-sessions.md"
    if not log_path.exists():
        return None

    raw = log_path.read_text(encoding="utf-8")
    sessions: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for line in raw.splitlines():
        line = line.strip()
        # 严格匹配 session 标题：### <8位hex>
        header_match = _SESSION_HEADER_RE.match(line)
        if header_match:
            # 新 session 开始，保存旧的
            if current and current.get("full_session_id"):
                sessions.append(current)
            current = {"full_session_id": header_match.group(1)}
            continue
        # 通过 dispatch table 分发字段行（覆盖全部 7 字段分支）
        if current:
            _dispatch_layer_field(line, current)

    # 保存最后一个
    if current and current.get("full_session_id"):
        sessions.append(current)

    return sessions


# ---------------------------------------------------------------------------
# Step 2: 读取 B 层数据 (session transcript)
# ---------------------------------------------------------------------------

def _find_session_jsonl(session_id: str) -> Path | None:
    """在 ~/.factory/sessions/ 下搜索所有已知 session 目录，找到对应 jsonl。

    支持完整 UUID 或 8 位前缀匹配（A 层存储短 ID）。
    """
    if not SESSIONS_HOME.exists():
        return None

    for session_dir in SESSIONS_HOME.iterdir():
        if not session_dir.is_dir():
            continue
        # 精确匹配
        candidate = session_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
        # 前缀匹配（8 位短 ID）
        for jsonl_file in session_dir.glob("*.jsonl"):
            if jsonl_file.stem.startswith(session_id):
                return jsonl_file
    return None


def _extract_transcript_summary(jsonl_path: Path) -> dict[str, Any]:
    """从 session jsonl 提取 user/assistant 文本 + 工具名列表。"""
    user_parts: list[str] = []
    assistant_parts: list[str] = []
    tool_names: list[str] = []

    try:
        size = jsonl_path.stat().st_size
        if size > 5 * 1024 * 1024:
            # 大文件：只读前 200 行 + 最后 50 行
            lines_to_process = _read_partial_jsonl(jsonl_path, 200, 50)
        else:
            lines_to_process = _read_full_jsonl(jsonl_path)
    except OSError:
        return {}

    for line in lines_to_process:
        if not line.get("type") == "message":
            continue

        msg = line.get("message", {})
        role = msg.get("role", "")
        content = msg.get("content", [])

        if role == "user":
            texts = _extract_text_blocks(content)
            user_parts.extend(texts)
        elif role == "assistant":
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            assistant_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tname = block.get("name", "")
                            if tname:
                                tool_names.append(tname)

    # 合并并截取
    user_text = "".join(user_parts)
    assistant_text = "".join(assistant_parts)

    return {
        "user_messages": user_text[:800] if user_text else "",
        "assistant_messages": assistant_text[:800] if assistant_text else "",
        "tool_names": tool_names,
    }


def _read_partial_jsonl(jsonl_path: Path, first_n: int, last_n: int) -> list[dict[str, Any]]:
    """大文件只读前 N 行 + 最后 M 行。"""
    results: list[dict[str, Any]] = []

    with jsonl_path.open("r", encoding="utf-8") as f:
        first_lines: list[dict[str, Any]] = []
        for i, raw_line in enumerate(f):
            if i >= first_n:
                break
            raw_line = raw_line.strip()
            if raw_line:
                try:
                    first_lines.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    continue

    with jsonl_path.open("r", encoding="utf-8") as f:
        all_lines = f.readlines()
        last_lines = all_lines[-last_n:] if len(all_lines) > last_n else all_lines

    results.extend(first_lines)
    for raw_line in last_lines:
        raw_line = raw_line.strip()
        if raw_line:
            try:
                obj = json.loads(raw_line)
                # 避免重复（如果文件行数少于 first_n + last_n）
                if obj not in results:
                    results.append(obj)
            except json.JSONDecodeError:
                continue

    return results


def _read_full_jsonl(jsonl_path: Path) -> list[dict[str, Any]]:
    """读取全部 jsonl 行。"""
    results: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if raw_line:
                try:
                    results.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    continue
    return results


def _extract_text_blocks(content: Any) -> list[str]:
    """从 message content 数组中提取所有 text block。"""
    texts: list[str] = []
    if not isinstance(content, list):
        return texts
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text", "")
            # 去除 system-reminder 标签
            if "<system-reminder>" in t:
                t = t.split("</system-reminder>")[-1].strip()
            texts.append(t)
    return texts





# ---------------------------------------------------------------------------
# Step 4: 写入最终日志
# ---------------------------------------------------------------------------

def _try_sign_file(project_root: Path, rel_path: str) -> None:
    """F5: 尝试对指定文件进行增量签名，失败不阻塞主流程。"""
    if _integrity is None or _integrity_keys is None:
        return
    try:
        key = _integrity_keys.load_key()
        if key is None:
            return
        _integrity.sign_project_incremental(project_root, key, changed_paths=[rel_path])
    except Exception as exc:
        # 签名失败 warning 但不阻塞
        try:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("daily_summary_generator: sign_project_incremental failed: %s", exc)
        except Exception:
            pass

def _generate_data_report(session_data_list: list[dict[str, Any]], target_date: str) -> str:
    """生成结构化数据报告，包含 A+B 层完整数据。

    A 层数据：session 标题、模型、时长、token、用户意图、助手摘要
    B 层数据：用户消息摘录、助手消息摘录、工具列表
    """
    total_in = sum(s.get("input_tokens", 0) for s in session_data_list)
    total_out = sum(s.get("output_tokens", 0) for s in session_data_list)
    count = len(session_data_list)

    lines = [
        f"# {target_date} Daily Report",
        "",
        "## 统计概览",
        f"- Sessions: {count}",
        f"- 总 Token: in={total_in} out={total_out}",
        "",
        "## Session 详情",
        "",
    ]

    for i, s in enumerate(session_data_list, 1):
        sid = s.get("full_session_id", "")[:8]
        title = s.get("title", "(无标题)")
        model = s.get("model", "")
        duration = s.get("duration", "")
        in_tok = s.get("input_tokens", 0)
        out_tok = s.get("output_tokens", 0)
        tool_calls = s.get("tool_calls_raw", "")
        user_preview = s.get("user_prompt_preview", "")
        assistant_preview = s.get("assistant_summary_preview", "")

        # B 层数据
        b_user = s.get("user_messages", "")
        b_assistant = s.get("assistant_messages", "")
        b_tools = s.get("tool_names", [])
        b_tools_str = ", ".join(b_tools) if b_tools else ""

        lines.append(f"### Session {i}: {sid}")
        lines.append(f"- **标题**: {title}")
        if model:
            lines.append(f"- **模型**: {model} | 时长: {duration}")
        lines.append(f"- **Token**: in={in_tok} out={out_tok}")
        if tool_calls:
            lines.append(f"- **工具调用**: {tool_calls}")
        if user_preview:
            lines.append(f"- **用户意图**: {user_preview}")
        if assistant_preview:
            lines.append(f"- **助手摘要**: {assistant_preview}")

        # B 层数据
        if b_user:
            lines.append(f"- **B层用户消息**: {b_user[:200]}")
        if b_assistant:
            lines.append(f"- **B层助手消息**: {b_assistant[:200]}")
        if b_tools_str:
            lines.append(f"- **B层工具列表**: {b_tools_str}")

        lines.append("")

    return "\n".join(lines)


def _write_daily_log(
    project_root: Path,
    target_date: str,
    session_data: list[dict[str, Any]],
    dry_run: bool = False,
) -> Path:
    """生成并写入 {project}/memory/log/{date}.md。"""
    log_dir = project_root / "memory" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    output_path = log_dir / f"{target_date}.md"
    rel_path = f"memory/log/{target_date}.md"

    content = _generate_data_report(session_data, target_date)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content += f"\n---\n*由 daily_summary_generator.py 自动生成于 {timestamp}*\n"

    if dry_run:
        print(f"\n{'='*60}")
        print(f"[DRY RUN] 将写入: {output_path}")
        print(f"{'='*60}")
        print(content)
        print(f"{'='*60}")
    else:
        try:
            output_path.write_text(content, encoding="utf-8")
            print(f"  ✓ 已写入: {output_path}")
            # F5: 写入成功后调用增量签名
            _try_sign_file(project_root, rel_path)
        except OSError as e:
            if write_error_log is not None:
                write_error_log(
                    str(project_root),
                    "file_write_failed",
                    {"file_path": str(output_path), "error": str(e)},
                    f"failed to write daily summary: {output_path}",
                )
            raise

    return output_path


# ---------------------------------------------------------------------------
# Step 5: 兜底检查
# ---------------------------------------------------------------------------

def _fallback_check(
    project_root: Path,
    fallback_days: int,
    dry_run: bool = False,
) -> list[str]:
    """检查前 N 天是否有 A 层数据但缺少每日总结，有则补生成。

    返回补生成的日期列表。
    """
    generated: list[str] = []
    today = date.today()

    for i in range(1, fallback_days + 1):
        check_date = (today - timedelta(days=i)).isoformat()
        a_layer_path = project_root / "memory" / "log" / f"{check_date}-sessions.md"
        daily_path = project_root / "memory" / "log" / f"{check_date}.md"

        if a_layer_path.exists() and not daily_path.exists():
            print(f"  [fallback] 发现缺失日志: {check_date}，补生成...")
            a_sessions = _read_a_layer(project_root, check_date)
            if a_sessions is None:
                continue

            # 尝试读取 B 层，生成数据报告
            session_data = _enrich_with_b_layer(a_sessions)
            _write_daily_log(project_root, check_date, session_data, dry_run)
            generated.append(check_date)

    return generated


# ---------------------------------------------------------------------------
# 核心流程编排
# ---------------------------------------------------------------------------

def _enrich_with_b_layer(a_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为每个 A 层 session 补充 B 层 transcript 数据。"""
    enriched: list[dict[str, Any]] = []
    for s in a_sessions:
        full_id = s.get("full_session_id", "")
        if not full_id:
            enriched.append(s)
            continue

        jsonl_path = _find_session_jsonl(full_id)
        if jsonl_path is None:
            enriched.append(s)
            continue

        try:
            b_data = _extract_transcript_summary(jsonl_path)
            merged = {**s, **b_data}
            enriched.append(merged)
        except Exception as e:
            print(f"  [warn] B 层读取失败 {full_id[:8]}: {e}", file=sys.stderr)
            enriched.append(s)

    return enriched


def _resolve_projects(args: argparse.Namespace) -> list[Path]:
    """解析需要扫描的项目列表。"""
    projects: list[Path] = []

    if args.project:
        projects.append(Path(args.project).expanduser().resolve())
    elif args.all_projects:
        if LIFECYCLE_INDEX.exists():
            try:
                idx = json.loads(LIFECYCLE_INDEX.read_text())
                paths_dict = idx.get("paths", {})
                # paths 是 dict，key 是路径
                projects = [Path(p).resolve() for p in paths_dict.keys()]
            except (json.JSONDecodeError, OSError):
                pass

        # 兜底：扫描常见项目根
        if not projects:
            for base in [Path.home()]:
                for p in base.iterdir():
                    if p.is_dir() and (p / "memory" / "system").exists():
                        projects.append(p)
    else:
        # 默认：当前目录的项目根
        cwd = Path.cwd().resolve()
        current = cwd
        while current != current.parent:
            if (current / "memory" / "system").exists():
                projects.append(current)
                break
            if (current / ".git").is_dir():
                projects.append(current)
                break
            current = current.parent
        if not projects:
            projects.append(cwd)

    return projects


def process_project(
    project_root: Path,
    target_date: str,
    dry_run: bool = False,
    fallback_days: int = 3,
) -> bool:
    """处理单个项目的每日总结生成。返回是否成功。"""
    print(f"\n{'='*60}")
    print(f"项目: {project_root}")
    print(f"日期: {target_date}")
    print(f"{'='*60}")

    # Step 1: 读取 A 层
    a_sessions = _read_a_layer(project_root, target_date)
    if a_sessions is None:
        print(f"  [skip] A 层数据不存在: {target_date}-sessions.md")
        return False

    if not a_sessions:
        print("  [skip] A 层数据为空")
        return False

    print(f"  A 层: 找到 {len(a_sessions)} 个 session")

    # Step 2: 读取 B 层
    enriched = _enrich_with_b_layer(a_sessions)
    b_count = sum(1 for s in enriched if s.get("user_messages") or s.get("assistant_messages"))
    print(f"  B 层: {b_count}/{len(enriched)} 个 session 有 transcript 数据")

    # Step 3: 生成数据报告
    report = _generate_data_report(enriched, target_date)
    print(f"  数据报告: 生成成功 ({len(report)} 字符)")

    # Step 4: 写入最终日志
    _write_daily_log(project_root, target_date, enriched, dry_run=dry_run)

    # Step 5: 兜底检查
    if fallback_days > 0:
        generated = _fallback_check(project_root, fallback_days, dry_run)
        if generated:
            print(f"  [fallback] 补生成了 {len(generated)} 天: {', '.join(generated)}")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)

        # 解析日期
        if args.today:
            target_date = date.today().isoformat()
        elif args.date:
            target_date = args.date
        else:
            print("Error: 请指定 --date YYYY-MM-DD 或 --today", file=sys.stderr)
            return 1

        # 解析项目列表
        projects = _resolve_projects(args)
        if not projects:
            print("Error: 未找到可扫描的项目", file=sys.stderr)
            return 1

        print(f"每日日志总结生成器 — {target_date}")
        print(f"扫描 {len(projects)} 个项目: {', '.join(str(p.name) for p in projects)}")

        success_count = 0
        for proj in projects:
            try:
                if process_project(proj, target_date, args.dry_run, args.fallback_days):
                    success_count += 1
            except Exception as e:
                print(f"  [error] 处理项目 {proj} 失败: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

        print(f"\n完成: {success_count}/{len(projects)} 个项目成功")
        return 0

    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
