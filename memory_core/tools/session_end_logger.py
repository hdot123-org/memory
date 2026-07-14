#!/usr/bin/env python3
"""Session end logger — append session summary to daily log.

在 Factory 的 SessionEnd hook 中被调用，轻量追加当前 session 摘要。

Usage:
    python session_end_logger.py \
        --session-dir ~/.factory/sessions/-Users-busiji-workbot \
        --session-id 491c46e7-7261-4444-a423-bba08ce2e4fb \
        --project-root ~/workbot

或者从 stdin 读取 gateway payload:
    echo '{"session_id": "...", "session_dir": "...", "project_root": "..."}' | \
        python session_end_logger.py --session-dir ... --session-id ... --project-root ...
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any

# C 层错误日志导入
try:
    from memory_core.tools.error_logger import write_error_log
except ImportError:
    write_error_log = None  # type: ignore[assignment]

# Metrics writing with file locking
from memory_core.tools.memory_hook_metrics import _resolve_metrics_path, append_metrics_record

# 超时处理：整体超时 2s
TIMEOUT_SECONDS = 2


def _set_timeout(seconds: int) -> None:
    """设置整体超时，超时后静默退出。"""
    def _handler(_signum: int, _frame: Any) -> None:
        # 超时静默退出，不阻塞 hook 链
        sys.exit(0)

    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析 CLI 参数。所有参数可选，缺失时从 stdin gateway payload 自动提取。"""
    parser = argparse.ArgumentParser(description="Session end logger for Factory.")
    parser.add_argument("--session-dir", default="", help="Session 目录路径（默认从 stdin payload 推断）")
    parser.add_argument("--session-id", default="", help="Session ID（默认从 stdin payload 的 task_context.session_id 提取）")
    parser.add_argument("--project-root", default="", help="项目根目录（默认从 stdin payload 的 cwd/repo_root 提取）")
    return parser.parse_args(argv)


def _read_stdin_payload() -> dict[str, Any]:
    """从 stdin 读取 gateway payload（如有）。"""
    try:
        if not sys.stdin.isatty():
            data = sys.stdin.read().strip()
            if data:
                result: dict[str, Any] = json.loads(data)
                return result
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _read_jsonl_lines(jsonl_path: Path) -> list[dict[str, Any]]:
    """读取 jsonl 文件，大文件只读前 500 行 + 最后 100 行。"""
    lines: list[dict[str, Any]] = []

    if not jsonl_path.exists():
        return lines

    try:
        size = jsonl_path.stat().st_size
        # 大文件优化：>10MB 只读前 500 行 + 最后 100 行
        if size > 10 * 1024 * 1024:
            with jsonl_path.open("r", encoding="utf-8") as f:
                first_lines = []
                for i, line in enumerate(f):
                    if i >= 500:
                        break
                    line = line.strip()
                    if line:
                        try:
                            first_lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            # 读取最后 100 行（使用 deque 流式读取，内存占用恒定）
            with jsonl_path.open("r", encoding="utf-8") as f:
                last_lines = list(deque(f, maxlen=100))

            lines = first_lines
            for line in last_lines:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        else:
            # 小文件直接读取
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
    except (OSError, IOError):
        pass

    return lines


def _read_settings(settings_path: Path) -> dict[str, Any]:
    """读取 settings.json。"""
    if not settings_path.exists():
        return {}
    try:
        with settings_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return dict(data)
    except (json.JSONDecodeError, OSError):
        return {}


def _extract_session_info_streaming(
    jsonl_path: Path, settings: dict[str, Any], session_id: str
) -> dict[str, Any] | None:
    """从 JSONL 文件单遍流式提取 session 摘要信息。

    与 _read_jsonl_lines + _extract_session_info 两步流程等价，
    但不构建 lines 列表，内存占用恒定为 O(1)。

    - last_assistant_message: collections.deque(maxlen=1)
    - tool_calls: Counter 累加
    - 对任意大小文件保证 tool_calls 统计完整性（全量遍历）
    """
    if not jsonl_path.exists():
        return None

    session_start: dict[str, Any] | None = None
    first_user_message: dict[str, Any] | None = None
    last_assistant_deque: deque[dict[str, Any]] = deque(maxlen=1)
    start_time: datetime | None = None
    end_time: datetime | None = None
    tool_calls: Counter[str] = Counter()
    total_tool_calls = 0

    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    line = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                event_type = line.get("type")

                # session_start
                if event_type == "session_start":
                    session_start = line
                    ts = line.get("timestamp", "")
                    if ts:
                        try:
                            start_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        except ValueError:
                            pass

                # message 事件
                elif event_type == "message":
                    msg = line.get("message", {})
                    role = msg.get("role", "")
                    content = msg.get("content", [])
                    ts = line.get("timestamp", "")

                    if ts:
                        try:
                            msg_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if end_time is None or msg_time > end_time:
                                end_time = msg_time
                        except ValueError:
                            pass

                    # 第一条 user message
                    if role == "user" and first_user_message is None:
                        first_user_message = msg

                    # 最后一条 assistant message (deque maxlen=1)
                    if role == "assistant":
                        last_assistant_deque.append(msg)

                        # 统计 tool_use (Counter 累加，全量遍历保证完整)
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_use":
                                    tool_name = block.get("name", "Unknown")
                                    tool_calls[tool_name] += 1
                                    total_tool_calls += 1

    except (OSError, IOError):
        return None

    # 从 deque 取出 last_assistant_message
    last_assistant_message = last_assistant_deque[0] if last_assistant_deque else None

    # 计算时长
    duration_seconds = 0
    if start_time and end_time:
        duration_seconds = int((end_time - start_time).total_seconds())

    # 格式化时长
    duration_str = _format_duration(duration_seconds)

    # 提取用户意图预览（第一条 user message 的 text content，前 200 字符）
    user_prompt_preview = ""
    if first_user_message and isinstance(first_user_message.get("content"), list):
        for block in first_user_message["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                # 去除 system-reminder
                if "<system-reminder>" in text:
                    text = text.split("</system-reminder>")[-1].strip()
                user_prompt_preview = text[:200]
                if len(text) > 200:
                    user_prompt_preview += "..."
                break

    # 提取助手摘要预览（最后一条 assistant message 的 text content，前 300 字符）
    assistant_summary_preview = ""
    if last_assistant_message and isinstance(last_assistant_message.get("content"), list):
        for block in last_assistant_message["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                assistant_summary_preview = text[:300]
                if len(text) > 300:
                    assistant_summary_preview += "..."
                break

    # token usage 从 settings.json
    token_usage = settings.get("inclusiveTokenUsage", {})
    if not token_usage:
        token_usage = settings.get("tokenUsage", {})

    input_tokens = token_usage.get("inputTokens", 0)
    output_tokens = token_usage.get("outputTokens", 0)

    # model 从 settings.json
    model = settings.get("model", "unknown")

    # title 从 session_start
    title = ""
    if session_start:
        title = session_start.get("title", "") or session_start.get("sessionTitle", "")

    return {
        "session_id": session_id[:8],  # 取前 8 位
        "full_session_id": session_id,
        "title": title,
        "model": model,
        "duration": duration_str,
        "duration_seconds": duration_seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": dict(tool_calls),
        "total_tool_calls": total_tool_calls,
        "user_prompt_preview": user_prompt_preview,
        "assistant_summary_preview": assistant_summary_preview,
    }


def _extract_session_info(
    lines: list[dict[str, Any]], settings: dict[str, Any], session_id: str
) -> dict[str, Any] | None:
    """从 jsonl 和 settings 中提取 session 摘要信息。"""
    # session_start 信息
    session_start: dict[str, Any] | None = None
    first_user_message: dict[str, Any] | None = None
    last_assistant_message: dict[str, Any] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    # 工具调用统计
    tool_calls: dict[str, int] = {}
    total_tool_calls = 0

    for line in lines:
        event_type = line.get("type")

        # session_start
        if event_type == "session_start":
            session_start = line
            ts = line.get("timestamp", "")
            if ts:
                try:
                    start_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    pass

        # message 事件
        elif event_type == "message":
            msg = line.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", [])
            ts = line.get("timestamp", "")

            if ts:
                try:
                    msg_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if end_time is None or msg_time > end_time:
                        end_time = msg_time
                except ValueError:
                    pass

            # 第一条 user message
            if role == "user" and first_user_message is None:
                first_user_message = msg

            # 最后一条 assistant message
            if role == "assistant":
                last_assistant_message = msg

                # 统计 tool_use
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_name = block.get("name", "Unknown")
                            tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1
                            total_tool_calls += 1

    # 计算时长
    duration_seconds = 0
    if start_time and end_time:
        duration_seconds = int((end_time - start_time).total_seconds())

    # 格式化时长
    duration_str = _format_duration(duration_seconds)

    # 提取用户意图预览（第一条 user message 的 text content，前 200 字符）
    user_prompt_preview = ""
    if first_user_message and isinstance(first_user_message.get("content"), list):
        for block in first_user_message["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                # 去除 system-reminder
                if "<system-reminder>" in text:
                    text = text.split("</system-reminder>")[-1].strip()
                user_prompt_preview = text[:200]
                if len(text) > 200:
                    user_prompt_preview += "..."
                break

    # 提取助手摘要预览（最后一条 assistant message 的 text content，前 300 字符）
    assistant_summary_preview = ""
    if last_assistant_message and isinstance(last_assistant_message.get("content"), list):
        for block in last_assistant_message["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                assistant_summary_preview = text[:300]
                if len(text) > 300:
                    assistant_summary_preview += "..."
                break

    # token usage 从 settings.json
    token_usage = settings.get("inclusiveTokenUsage", {})
    if not token_usage:
        token_usage = settings.get("tokenUsage", {})

    input_tokens = token_usage.get("inputTokens", 0)
    output_tokens = token_usage.get("outputTokens", 0)

    # model 从 settings.json
    model = settings.get("model", "unknown")

    # title 从 session_start
    title = ""
    if session_start:
        title = session_start.get("title", "") or session_start.get("sessionTitle", "")

    return {
        "session_id": session_id[:8],  # 取前 8 位
        "full_session_id": session_id,
        "title": title,
        "model": model,
        "duration": duration_str,
        "duration_seconds": duration_seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "total_tool_calls": total_tool_calls,
        "user_prompt_preview": user_prompt_preview,
        "assistant_summary_preview": assistant_summary_preview,
    }


def _format_duration(seconds: int) -> str:
    """格式化时长为可读字符串。"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m{secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h{minutes}m"


def _format_tool_calls(tool_calls: dict[str, int]) -> str:
    """格式化工具调用统计。"""
    if not tool_calls:
        return "无"

    # 按调用次数排序
    sorted_calls = sorted(tool_calls.items(), key=lambda x: -x[1])
    parts = [f"{name}={count}" for name, count in sorted_calls[:6]]  # 最多显示 6 个
    return " | ".join(parts)


def _write_daily_log(project_root: Path, info: dict[str, Any]) -> bool:
    """追加写入 daily log 文件。"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = project_root / "memory" / "log"
    log_path = log_dir / f"{today}-sessions.md"

    # 确保目录存在
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if write_error_log is not None:
            write_error_log(
                str(project_root),
                "directory_creation_failed",
                {"dir_path": str(log_dir), "error": str(e)},
                f"failed to create log directory: {log_dir}",
            )
        return False

    # 如果文件不存在，写入头部
    is_new_file = not log_path.exists()

    # 构建 markdown 内容
    lines = []
    if is_new_file:
        lines.append(f"# Sessions Log — {today}\n")
        lines.append("")

    lines.append(f"### {info['session_id']}")
    lines.append(f"- **标题**: {info['title'] or '(无标题)'}")
    lines.append(f"- **模型**: {info['model']} | **时长**: {info['duration']}")
    lines.append(f"- **Token**: input={info['input_tokens']} output={info['output_tokens']}")
    lines.append(f"- **工具调用**: {_format_tool_calls(info['tool_calls'])}")
    lines.append(f"- **用户意图**: {info['user_prompt_preview'] or '(无)'}")
    lines.append(f"- **助手摘要**: {info['assistant_summary_preview'] or '(无)'}")
    lines.append("---")
    lines.append("")

    content = "\n".join(lines)

    # 追加写入
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(content)
        return True
    except OSError as e:
        if write_error_log is not None:
            write_error_log(
                str(project_root),
                "file_write_failed",
                {"file_path": str(log_path), "error": str(e)},
                f"failed to write session log: {log_path}",
            )
        return False


def _write_session_metrics(project_root: Path, info: dict[str, Any]) -> None:
    """Write session metrics to local JSONL file.

    Extracted from main() for testability. Writes metrics record with event='session-end'.
    Never raises exceptions (metrics write must never break the hook).

    Args:
        project_root: Project root directory
        info: Session info dict with duration_seconds, input_tokens, output_tokens, total_tool_calls
    """
    try:
        metrics_path = _resolve_metrics_path(project_root / "memory" / "artifacts" / "memory-hook")
        duration_ms = int(info.get("duration_seconds", 0) * 1000)
        metrics_record = {
            "event": "session-end",
            "duration_seconds": info.get("duration_seconds", 0),
            "input_tokens": info.get("input_tokens", 0),
            "output_tokens": info.get("output_tokens", 0),
            "total_tool_calls": info.get("total_tool_calls", 0),
            "duration_ms": duration_ms,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        append_metrics_record(metrics_path, metrics_record)
    except Exception:
        pass  # Metrics write must never break the hook


def main(argv: list[str] | None = None) -> int:
    """主入口。"""
    # 设置超时
    _set_timeout(TIMEOUT_SECONDS)

    try:
        args = _parse_args(argv)
        stdin_payload = _read_stdin_payload()

        # Factory hook stdin 直接提供 session_id / cwd / transcript_path
        session_id = args.session_id or stdin_payload.get("session_id", "")
        project_root_str = args.project_root or stdin_payload.get("cwd", "")
        transcript_path = stdin_payload.get("transcript_path", "")

        # 兜底：如果没有 transcript_path，按 session-dir 推断
        if not transcript_path and session_id and project_root_str:
            project_name = Path(project_root_str).name
            sessions_base = Path.home() / ".factory" / "sessions"
            for d in sessions_base.iterdir():
                if d.is_dir() and d.name.endswith(f"-{project_name}"):
                    transcript_path = str(d / f"{session_id}.jsonl")
                    break

        # 参数不完整 → 静默退出
        if not session_id or not project_root_str:
            return 0

        project_root = Path(project_root_str).expanduser().resolve()

        # jsonl 路径：优先用 transcript_path，否则用 session-dir 推断
        if transcript_path:
            jsonl_path = Path(transcript_path).expanduser().resolve()
        elif args.session_dir:
            session_dir = Path(args.session_dir).expanduser().resolve()
            jsonl_path = session_dir / f"{session_id}.jsonl"
        else:
            return 0

        # jsonl 不存在 → 静默退出
        if not jsonl_path.exists():
            if write_error_log is not None:
                write_error_log(
                    project_root_str,
                    "transcript_missing",
                    {
                        "session_id": session_id,
                        "expected_path": str(jsonl_path),
                    },
                    f"transcript not found: {jsonl_path}",
                )
            return 0

        # settings.json 路径（同目录下）
        settings_path = jsonl_path.parent / f"{session_id}.settings.json"

        # 读取 settings
        settings = _read_settings(settings_path)

        # 流式提取信息（单遍遍历，O(1) 内存）
        info = _extract_session_info_streaming(jsonl_path, settings, session_id)
        if info is None:
            return 0

        # 写入日志
        _write_daily_log(project_root, info)

        # Write metrics to local JSONL (replaces PostHog telemetry)
        _write_session_metrics(project_root, info)

        return 0

    except SystemExit:
        # SIGALRM 触发超时，记录到 C 层后静默退出
        if write_error_log is not None:
            write_error_log(
                project_root_str if "project_root_str" in dir() else "",
                "hook_timeout",
                {
                    "session_id": session_id if "session_id" in dir() else "",
                    "timeout_seconds": TIMEOUT_SECONDS,
                },
                f"session_end_logger timed out after {TIMEOUT_SECONDS}s",
            )
        sys.exit(0)
    except Exception as exc:
        # 任何异常静默退出，不阻塞 hook 链
        # 记录到 C 层错误日志
        if write_error_log is not None:
            error_type = "unknown_error"
            if isinstance(exc, json.JSONDecodeError):
                error_type = "json_parse_error"
            write_error_log(
                project_root_str if "project_root_str" in dir() else "",
                error_type,
                {"error_class": type(exc).__name__, "session_id": session_id if "session_id" in dir() else ""},
                f"session_end_logger unexpected error: {exc}",
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
