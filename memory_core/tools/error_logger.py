#!/usr/bin/env python3
"""C 层错误日志模块 — JSON Lines 格式全局错误记录。

被 A 层 (session_end_logger.py) 和 B 层 (daily_summary_generator.py) 调用。

Usage:
    from memory_core.tools.error_logger import write_error_log

    result = write_error_log(
        project_root="/path/to/project",
        error_type="transcript_missing",
        context={"session_id": "abc123", "expected_path": "/path/to/transcript.jsonl"},
        error_msg="transcript file not found"
    )
    # result: True if written successfully, False on internal error
"""

import inspect
import json
import re
from pathlib import Path
from typing import Any

# F5: 签名模块导入（ImportError 时静默跳过）
# 使用模块级导入避免 stale binding 问题（monkeypatch 能正确看到 patched 版本）
try:
    from memory_core.tools import memory_hook_integrity_keys as _integrity_keys
    from memory_core.tools import memory_hook_integrity_manifest as _integrity
except ImportError:
    _integrity = None  # type: ignore[assignment]
    _integrity_keys = None  # type: ignore[assignment]

# Import now_iso from _file_utils for consistent timestamp generation
try:
    from memory_core.tools._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore

# 错误消息最大长度
MAX_MSG_LENGTH = 500

# API key 脱敏正则：匹配 sk- 开头后接至少 4 个字母数字的字符串
_API_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9]{4,}")

# 支持的错误类型枚举
VALID_ERROR_TYPES = frozenset({
    "transcript_missing",
    "hook_timeout",
    "json_parse_error",
    "directory_creation_failed",
    "file_write_failed",
    "llm_api_error",
    "llm_timeout",
    "settings_read_failed",
})


def _detect_calling_script() -> str:
    """通过调用栈自动检测调用方脚本名。"""
    try:
        for frame_info in inspect.stack():
            filename = frame_info.filename
            # 跳过 error_logger.py 自身
            if "error_logger" in filename:
                continue
            # 提取文件名（不含路径和后缀）
            basename = Path(filename).stem
            if basename and not basename.startswith("<"):
                return basename
    except Exception:
        pass
    return "unknown"


def _redact_api_keys(text: str) -> str:
    """将文本中的 API key 脱敏为 sk-...****。"""
    return _API_KEY_PATTERN.sub("sk-...****", text)


def _redact_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """递归脱敏 context 中所有字符串值的 API key。"""
    result: dict[str, Any] = {}
    for key, value in ctx.items():
        if isinstance(value, str):
            result[key] = _redact_api_keys(value)
        elif isinstance(value, dict):
            result[key] = _redact_context(value)
        elif isinstance(value, list):
            result[key] = [
                _redact_api_keys(item) if isinstance(item, str)
                else _redact_context(item) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def _try_sign_file(project_root: Path, rel_path: str) -> None:
    """F5: 尝试对指定文件进行增量签名，失败不阻塞主流程。"""
    if _integrity is None or _integrity_keys is None:
        return
    try:
        key = _integrity_keys.load_key()
        if key is None:
            return
        _integrity.sign_project_incremental(project_root, key, changed_paths=[rel_path])
    except Exception:
        # 签名失败静默跳过，不阻塞主流程
        pass


def write_error_log(
    project_root: str,
    error_type: str,
    context: dict[str, Any],
    error_msg: str,
) -> bool:
    """写入一条错误日志到项目的 error JSONL 文件。

    Args:
        project_root: 项目根目录路径
        error_type: 错误类型（必须是 8 种之一）
        context: 上下文键值对，会被 JSON 序列化
        error_msg: 错误消息，超过 500 字符会被截断

    Returns:
        True 表示写入成功，False 表示内部异常（静默返回，不抛出异常）
    """
    try:
        # 验证错误类型
        if error_type not in VALID_ERROR_TYPES:
            return False

        # 解析项目根目录
        root = Path(project_root).expanduser().resolve()

        # 构建输出路径
        # Extract date part (YYYY-MM-DD) from ISO timestamp
        today = now_iso()[:10]
        log_dir = root / "memory" / "log"
        log_path = log_dir / f"{today}-errors.jsonl"

        # 自动创建目录
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        # 截断错误消息
        truncated_msg = error_msg if len(error_msg) <= MAX_MSG_LENGTH else error_msg[:MAX_MSG_LENGTH]

        # 脱敏处理
        redacted_msg = _redact_api_keys(truncated_msg)
        redacted_ctx = _redact_context(context)

        # 自动检测调用方脚本名
        calling_script = _detect_calling_script()

        # 构建日志条目
        entry = {
            "ts": now_iso(),
            "type": error_type,
            "script": calling_script,
            "project": str(root),
            "ctx": redacted_ctx,
            "msg": redacted_msg,
        }

        # 序列化为 JSON 行
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))

        # 追加写入文件
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        # F5: 写入成功后调用增量签名
        rel_path = f"memory/log/{today}-errors.jsonl"
        _try_sign_file(root, rel_path)

        return True

    except Exception:
        # 内部异常静默返回 False
        return False
