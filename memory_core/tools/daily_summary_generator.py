#!/usr/bin/env python3
"""每日日志总结生成器 — 读取 A 层 session 记录 + B 层 transcript，调 LLM 生成分类总结。

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
import os
import subprocess
import sys
import textwrap
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
try:
    from memory_core.tools.memory_hook_integrity_keys import load_key
    from memory_core.tools.memory_hook_integrity_manifest import sign_project_incremental
except ImportError:
    sign_project_incremental = None  # type: ignore[misc,assignment]
    load_key = None  # type: ignore[misc,assignment]

# ---------------------------------------------------------------------------
# 常量 & 配置
# ---------------------------------------------------------------------------

LLM_ENDPOINT = os.environ.get("MEMORY_LLM_ENDPOINT", "")
LLM_MODEL = "glm-5.1"
LLM_TIMEOUT = 120  # 秒（大 prompt 需要更长超时）
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
        elif line.startswith("- **标题**: "):
            current["title"] = line.split(": ", 1)[1] if ": " in line else ""
        elif line.startswith("- **模型**: "):
            rest = line.split(": ", 1)[1] if ": " in line else ""
            # "GLM-5.1 (官方) | 时长: 2m35s"
            parts = rest.split(" | ")
            current["model"] = parts[0].strip() if parts else ""
            for p in parts:
                if "时长" in p:
                    current["duration"] = p.split(": ", 1)[1].strip()
        elif line.startswith("- **Token**: "):
            rest = line.split(": ", 1)[1] if ": " in line else ""
            # "input=123 output=456"
            for token_part in rest.split():
                if "=" in token_part:
                    k, v = token_part.split("=", 1)
                    try:
                        current[f"{k}_tokens"] = int(v)
                    except ValueError:
                        pass
        elif line.startswith("- **工具调用**: "):
            current["tool_calls_raw"] = line.split(": ", 1)[1] if ": " in line else ""
        elif line.startswith("- **用户意图**: "):
            current["user_prompt_preview"] = line.split(": ", 1)[1] if ": " in line else ""
        elif line.startswith("- **助手摘要**: "):
            current["assistant_summary_preview"] = line.split(": ", 1)[1] if ": " in line else ""

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
# Step 3: 调用 BYOK LLM
# ---------------------------------------------------------------------------

def _build_llm_prompt(session_data_list: list[dict[str, Any]]) -> str:
    """构建 LLM prompt，拼装所有 session 的 A+B 层数据。"""
    parts: list[str] = []
    for i, sd in enumerate(session_data_list, 1):
        sid = sd.get("full_session_id", "")[:8]
        title = sd.get("title", "(无标题)")
        model = sd.get("model", "")
        duration = sd.get("duration", "")
        input_tok = sd.get("input_tokens", 0)
        output_tok = sd.get("output_tokens", 0)
        tool_calls = sd.get("tool_calls_raw", "")
        user_preview = sd.get("user_prompt_preview", "")
        assistant_preview = sd.get("assistant_summary_preview", "")
        b_user = sd.get("b_user_messages", "")
        b_assistant = sd.get("b_assistant_messages", "")
        b_tools = ", ".join(sd.get("b_tool_names", []))

        entry = textwrap.dedent(f"""\
        ### Session {i}: {sid}
        - 标题: {title}
        - 模型: {model} | 时长: {duration}
        - Token: input={input_tok} output={output_tok}
        - 工具调用: {tool_calls or "无"}
        - B层用户输入(前800字符): {b_user[:200] if b_user else "(无)"}
        - B层助手输出(前800字符): {b_assistant[:200] if b_assistant else "(无)"}
        - B层工具列表: {b_tools or "无"}
        - A层用户意图: {user_preview or "(无)"}
        - A层助手摘要: {assistant_preview or "(无)"}
        """)
        parts.append(entry)

    all_sessions = "\n".join(parts)

    prompt = textwrap.dedent(f"""\
    你是每日工作日志分类器。根据以下 session 数据，按工作主题灵活归类，生成每日总结。

    要求：
    1. 自动识别主题（如"文档审查"、"代码重构"、"Bug修复"、"架构设计"、"测试"、"CI/CD"等），不要用固定分类
    2. 每个主题下列出具体条目，每个条目包含：session ID（前8位）、做了什么、用了什么工具、关键结果
    3. 最后附一个"今日经验教训"段落，从所有 session 中提取通用经验
    4. 用中文输出

    ## Session 数据
    {all_sessions}
    """)
    return prompt


def _get_factory_api_key(project_root: str = "") -> str:
    """从 Factory settings.json 提取 GLM 模型的 apiKey。"""
    settings_path = Path.home() / ".factory" / "settings.json"
    if not settings_path.exists():
        return ""
    try:
        s = json.loads(settings_path.read_text(encoding="utf-8"))
        for m in s.get("customModels", []):
            if "glm" in m.get("id", "").lower() and "5.1" in m.get("id", ""):
                return m.get("apiKey", "")
    except Exception as e:
        if write_error_log is not None and project_root:
            write_error_log(
                project_root,
                "settings_read_failed",
                {"settings_path": str(settings_path), "error": str(e)},
                f"failed to read Factory settings: {e}",
            )
        pass
    return ""


def _call_llm(prompt: str, project_root: str = "") -> str | None:
    """调用 BYOK LLM，返回生成的总结文本。失败时返回 None。"""
    # 优先从 Factory settings.json 提取 apiKey，回退到 GLM_API_KEY 环境变量
    api_key = _get_factory_api_key(project_root) or os.environ.get("GLM_API_KEY")
    if not api_key:
        print("  [warn] GLM_API_KEY 未设置，降级为纯统计报告", file=sys.stderr)
        return None

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    })

    try:
        result = subprocess.run(
            [
                "curl", "-sk", "--max-time", str(LLM_TIMEOUT),
                "-X", "POST", LLM_ENDPOINT,
                "-H", "Content-Type: application/json",
                "-H", f"Authorization: Bearer {api_key}",
                "-d", payload,
            ],
            capture_output=True, text=True, timeout=LLM_TIMEOUT + 5,
        )
        if result.returncode != 0:
            print(f"  [warn] curl 返回非零 ({result.returncode}): {result.stderr[:200]}", file=sys.stderr)
            if write_error_log is not None and project_root:
                write_error_log(
                    project_root,
                    "llm_api_error",
                    {"http_status": result.returncode, "stderr": result.stderr[:200]},
                    f"LLM API curl error: {result.stderr[:200]}",
                )
            return None
        resp = json.loads(result.stdout)
        choices = resp.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        # 检查 API error
        err = resp.get("error", {})
        if err:
            err_msg = err.get("message", "")[:200]
            print(f"  [warn] LLM API 错误: {err_msg}", file=sys.stderr)
            if write_error_log is not None and project_root:
                write_error_log(
                    project_root,
                    "llm_api_error",
                    {"http_status": resp.get("status", 0), "error": err_msg},
                    f"LLM API returned error: {err_msg}",
                )
        return None
    except subprocess.TimeoutExpired as e:
        print(f"  [warn] LLM 调用超时: {e}，降级为纯统计报告", file=sys.stderr)
        if write_error_log is not None and project_root:
            write_error_log(
                project_root,
                "llm_timeout",
                {"timeout_seconds": LLM_TIMEOUT},
                f"LLM call timed out after {LLM_TIMEOUT}s",
            )
        return None
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warn] LLM 调用失败: {e}，降级为纯统计报告", file=sys.stderr)
        if write_error_log is not None and project_root:
            write_error_log(
                project_root,
                "llm_api_error",
                {"error_class": type(e).__name__, "error": str(e)},
                f"LLM call failed: {e}",
            )
        return None
    except Exception:
        print("  [warn] LLM 调用异常，降级为纯统计报告", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Step 4: 写入最终日志
# ---------------------------------------------------------------------------

def _try_sign_file(project_root: Path, rel_path: str) -> None:
    """F5: 尝试对指定文件进行增量签名，失败不阻塞主流程。"""
    if sign_project_incremental is None or load_key is None:
        return
    try:
        key = load_key()
        if key is None:
            return
        sign_project_incremental(project_root, key, changed_paths=[rel_path])
    except Exception as exc:
        # 签名失败 warning 但不阻塞
        try:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("daily_summary_generator: sign_project_incremental failed: %s", exc)
        except Exception:
            pass

def _generate_fallback_report(a_sessions: list[dict[str, Any]], target_date: str) -> str:
    """降级报告：纯 A 层统计，不含 LLM 分类总结。"""
    total_in = sum(s.get("input_tokens", 0) for s in a_sessions)
    total_out = sum(s.get("output_tokens", 0) for s in a_sessions)
    count = len(a_sessions)
    ok_count = count  # 没有健康状态数据，默认 OK
    degraded_count = 0

    lines = [
        f"# {target_date} Daily Facts",
        "",
        "## 统计概览",
        f"- Sessions: {count}",
        f"- 总 Token: in={total_in} out={total_out}",
        f"- 健康状态: OK={ok_count} Degraded={degraded_count}",
        "",
        "> **注意**: LLM 总结未生成（API key 缺失或请求失败）",
        "> 以下为原始 session 列表",
        "",
    ]

    for s in a_sessions:
        sid = s.get("full_session_id", "")[:8]
        title = s.get("title", "(无标题)")
        model = s.get("model", "")
        duration = s.get("duration", "")
        in_tok = s.get("input_tokens", 0)
        out_tok = s.get("output_tokens", 0)
        user_preview = s.get("user_prompt_preview", "")[:100]

        lines.append(f"- **{sid}** {title}")
        if model:
            lines.append(f"  - 模型: {model} | 时长: {duration}")
        lines.append(f"  - Token: in={in_tok} out={out_tok}")
        if user_preview:
            lines.append(f"  - 用户意图: {user_preview}")
        lines.append("")

    return "\n".join(lines)


def _write_daily_log(
    project_root: Path,
    target_date: str,
    a_sessions: list[dict[str, Any]],
    llm_summary: str | None,
    dry_run: bool = False,
) -> Path:
    """生成并写入 {project}/memory/log/{date}.md。"""
    log_dir = project_root / "memory" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    output_path = log_dir / f"{target_date}.md"
    rel_path = f"memory/log/{target_date}.md"

    if llm_summary:
        # 有 LLM 总结
        total_in = sum(s.get("input_tokens", 0) for s in a_sessions)
        total_out = sum(s.get("output_tokens", 0) for s in a_sessions)
        count = len(a_sessions)
        ok_count = count
        degraded_count = 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content = textwrap.dedent(f"""\
        # {target_date} Daily Facts

        ## 统计概览
        - Sessions: {count}
        - 总 Token: in={total_in} out={total_out}
        - 健康状态: OK={ok_count} Degraded={degraded_count}

        {llm_summary}

        ---
        *由 daily_summary_generator.py 自动生成于 {timestamp}*
        """)
    else:
        content = _generate_fallback_report(a_sessions, target_date)
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

            # 尝试读取 B 层
            session_data = _enrich_with_b_layer(a_sessions)
            llm_summary = _call_llm(_build_llm_prompt(session_data), str(project_root))
            _write_daily_log(project_root, check_date, a_sessions, llm_summary, dry_run)
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

    # Step 3: 调用 LLM
    llm_prompt = _build_llm_prompt(enriched)
    llm_summary = _call_llm(llm_prompt, str(project_root))
    if llm_summary:
        print(f"  LLM: 总结生成成功 ({len(llm_summary)} 字符)")
    else:
        print("  LLM: 降级为纯统计报告")

    # Step 4: 写入最终日志
    _write_daily_log(project_root, target_date, a_sessions, llm_summary, dry_run)

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
