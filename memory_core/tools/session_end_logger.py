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

import argparse
import json
import signal
import sys
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore

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


def _parse_jsonl_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp with Z suffix handling.

    Args:
        ts: Timestamp string (ISO 8601 format, may end with Z)

    Returns:
        Parsed datetime or None if invalid/empty
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_first_user_preview(msg: dict[str, Any] | None) -> str:
    """Extract text preview from first user message (max 200 chars).

    Strips system-reminder tags and truncates with '...' if needed.

    Args:
        msg: User message dict with 'content' field

    Returns:
        Text preview string (empty if no valid content)
    """
    if not msg or not isinstance(msg.get("content"), list):
        return ""

    for block in msg["content"]:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text", ""))
            # 去除 system-reminder
            if "<system-reminder>" in text:
                text = text.split("</system-reminder>")[-1].strip()
            preview = text[:200]
            if len(text) > 200:
                preview += "..."
            return preview
    return ""


def _extract_assistant_summary_preview(msg: dict[str, Any] | None) -> str:
    """Extract text preview from last assistant message (max 300 chars).

    Args:
        msg: Assistant message dict with 'content' field

    Returns:
        Text preview string (empty if no valid content)
    """
    if not msg or not isinstance(msg.get("content"), list):
        return ""

    for block in msg["content"]:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text", ""))
            preview = text[:300]
            if len(text) > 300:
                preview += "..."
            return preview
    return ""


def _collect_tool_uses(content: list[Any] | None) -> tuple[Counter[str], int]:
    """Count tool_use blocks in content list.

    Args:
        content: List of content blocks (may contain text, tool_use, etc.)

    Returns:
        Tuple of (Counter with tool name counts, total count)
    """
    if not content or not isinstance(content, list):
        return Counter(), 0

    counter: Counter[str] = Counter()
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_name = block.get("name", "Unknown")
            counter[tool_name] += 1
    return counter, sum(counter.values())


def _build_session_info_dict(
    session_id: str,
    title: str,
    model: str,
    start_time: datetime | None,
    end_time: datetime | None,
    user_prompt_preview: str,
    assistant_summary_preview: str,
    tool_calls: Counter[str],
    total_tool_calls: int,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Build the final 13-field session info dict.

    Args:
        session_id: Full session ID
        title: Session title
        model: Model name
        start_time: Session start datetime
        end_time: Session end datetime
        user_prompt_preview: First user message preview
        assistant_summary_preview: Last assistant message preview
        tool_calls: Counter of tool usage
        total_tool_calls: Total number of tool calls
        settings: Settings dict with token usage info

    Returns:
        Dict with 13 fields: session_id, full_session_id, title, model,
        duration, duration_seconds, input_tokens, output_tokens, tool_calls,
        total_tool_calls, user_prompt_preview, assistant_summary_preview
    """
    # Calculate duration
    duration_seconds = 0
    if start_time and end_time:
        duration_seconds = int((end_time - start_time).total_seconds())
    duration_str = _format_duration(duration_seconds)

    # Token usage from settings (fallback chain)
    token_usage = settings.get("inclusiveTokenUsage", {})
    if not token_usage:
        token_usage = settings.get("tokenUsage", {})
    input_tokens = token_usage.get("inputTokens", 0)
    output_tokens = token_usage.get("outputTokens", 0)

    return {
        "session_id": session_id[:8],
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


def _extract_session_info_streaming(
    jsonl_path: Path, settings: dict[str, Any], session_id: str
) -> dict[str, Any] | None:
    """从 JSONL 文件单遍流式提取 session 摘要信息。

    不构建 lines 列表，内存占用恒定为 O(1)。

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
                    parsed = _parse_jsonl_timestamp(ts)
                    if parsed:
                        start_time = parsed

                # message 事件
                elif event_type == "message":
                    msg = line.get("message", {})
                    role = msg.get("role", "")
                    content = msg.get("content", [])
                    ts = line.get("timestamp", "")

                    parsed_ts = _parse_jsonl_timestamp(ts)
                    if parsed_ts:
                        if end_time is None or parsed_ts > end_time:
                            end_time = parsed_ts

                    # 第一条 user message
                    if role == "user" and first_user_message is None:
                        first_user_message = msg

                    # 最后一条 assistant message (deque maxlen=1)
                    if role == "assistant":
                        last_assistant_deque.append(msg)

                        # 统计 tool_use (Counter 累加，全量遍历保证完整)
                        tc, count = _collect_tool_uses(content)
                        tool_calls.update(tc)
                        total_tool_calls += count

    except (OSError, IOError):
        return None

    # 从 deque 取出 last_assistant_message
    last_assistant_message = last_assistant_deque[0] if last_assistant_deque else None

    # Extract previews
    user_prompt_preview = _extract_first_user_preview(first_user_message)
    assistant_summary_preview = _extract_assistant_summary_preview(last_assistant_message)

    # Get title and model from session_start and settings
    title = ""
    if session_start:
        title = session_start.get("title", "") or session_start.get("sessionTitle", "")
    model = settings.get("model", "unknown")

    # Build and return the final dict
    return _build_session_info_dict(
        session_id=session_id,
        title=title,
        model=model,
        start_time=start_time,
        end_time=end_time,
        user_prompt_preview=user_prompt_preview,
        assistant_summary_preview=assistant_summary_preview,
        tool_calls=tool_calls,
        total_tool_calls=total_tool_calls,
        settings=settings,
    )




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
            "timestamp": now_iso(),
        }
        append_metrics_record(metrics_path, metrics_record)
    except Exception:
        pass  # Metrics write must never break the hook


def _resolve_jsonl_path(
    args: argparse.Namespace,
    stdin_payload: dict[str, Any],
) -> tuple[str, str, str, Path | None]:
    """Resolve session_id, project_root, transcript_path, and jsonl_path.

    Returns:
        Tuple of (session_id, project_root_str, transcript_path, jsonl_path or None)
        jsonl_path is None when resolution fails (caller should return 0)
    """
    session_id = args.session_id or stdin_payload.get("session_id", "")
    project_root_str = args.project_root or stdin_payload.get("cwd", "")
    transcript_path = stdin_payload.get("transcript_path", "")

    # Fallback: infer from factory sessions dir
    if not transcript_path and session_id and project_root_str:
        project_name = Path(project_root_str).name
        sessions_base = Path.home() / ".factory" / "sessions"
        if sessions_base.exists():
            for d in sessions_base.iterdir():
                if d.is_dir() and d.name.endswith(f"-{project_name}"):
                    transcript_path = str(d / f"{session_id}.jsonl")
                    break

    # Missing required params
    if not session_id or not project_root_str:
        return ("", "", "", None)

    # Resolve jsonl path
    if transcript_path:
        jsonl_path = Path(transcript_path).expanduser().resolve()
    elif args.session_dir:
        session_dir = Path(args.session_dir).expanduser().resolve()
        jsonl_path = session_dir / f"{session_id}.jsonl"
    else:
        return (session_id, project_root_str, transcript_path, None)

    return (session_id, project_root_str, transcript_path, jsonl_path)


def _safe_run_session_end(
    session_id: str,
    project_root_str: str,
    jsonl_path: Path,
) -> int:
    """Execute session end logic with error handling.

    Reads settings, extracts session info, writes logs and metrics.
    All exceptions are caught and logged to C-layer error logger.

    Returns:
        0 on success or any error (never propagates exceptions)
    """
    try:
        project_root = Path(project_root_str).expanduser().resolve()

        # Check jsonl exists
        if not jsonl_path.exists():
            if write_error_log is not None:
                write_error_log(
                    project_root_str,
                    "transcript_missing",
                    {"session_id": session_id, "expected_path": str(jsonl_path)},
                    f"transcript not found: {jsonl_path}",
                )
            return 0

        # Read settings
        settings_path = jsonl_path.parent / f"{session_id}.settings.json"
        settings = _read_settings(settings_path)

        # Extract session info (single-pass, O(1) memory)
        info = _extract_session_info_streaming(jsonl_path, settings, session_id)
        if info is None:
            return 0

        # Write logs and metrics
        _write_daily_log(project_root, info)
        _write_session_metrics(project_root, info)

        return 0

    except SystemExit:
        # SIGALRM timeout
        if write_error_log is not None:
            write_error_log(
                project_root_str,
                "hook_timeout",
                {"session_id": session_id, "timeout_seconds": TIMEOUT_SECONDS},
                f"session_end_logger timed out after {TIMEOUT_SECONDS}s",
            )
        sys.exit(0)
    except Exception as exc:
        # Any exception: log and return 0 (never block hook chain)
        if write_error_log is not None:
            error_type = "unknown_error"
            if isinstance(exc, json.JSONDecodeError):
                error_type = "json_parse_error"
            write_error_log(
                project_root_str,
                error_type,
                {"error_class": type(exc).__name__, "session_id": session_id},
                f"session_end_logger unexpected error: {exc}",
            )
        return 0


def main(argv: list[str] | None = None) -> int:
    """主入口。"""
    # 设置超时
    _set_timeout(TIMEOUT_SECONDS)

    args = _parse_args(argv)
    stdin_payload = _read_stdin_payload()

    # Resolve paths
    session_id, project_root_str, transcript_path, jsonl_path = _resolve_jsonl_path(
        args, stdin_payload
    )

    # Missing required params → silent exit
    if not session_id or jsonl_path is None:
        return 0

    # Execute session end logic with error handling
    return _safe_run_session_end(session_id, project_root_str, jsonl_path)


if __name__ == "__main__":
    raise SystemExit(main())
