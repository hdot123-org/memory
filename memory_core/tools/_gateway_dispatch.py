#!/usr/bin/env python3.12
"""Gateway 调度层：delegate 执行、输出格式化与生命周期记录。

依赖层级：依赖 _gateway_config（REPO_ROOT/WORKSPACE_ROOT 等常量）、
_gateway_artifacts（append_error_log）、_gateway_policy（build_context_package）。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ._gateway_config import REPO_ROOT, PROJECT_LIFECYCLE_ROOT, ARTIFACT_ROOT, EVENT_LOG, _FORCE_HOOK
from ._gateway_artifacts import append_error_log

# Lazy import for _get_host_delegate to avoid circular dependency
def _get_host_delegate(host: str):
    """Get host delegate (lazy import to avoid circular dependency)."""
    from ._gateway_config import _get_host_delegate as _impl
    return _impl(host)

try:
    from ._file_utils import now_iso
    from .project_lifecycle import record_project_lifecycle
except ImportError:
    from _file_utils import now_iso  # type: ignore
    from memory_core.tools.project_lifecycle import record_project_lifecycle

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CWD 发现
# ---------------------------------------------------------------------------


def _payload_cwd(payload: dict[str, Any]) -> Path | None:
    """从 payload 提取 cwd。"""
    value = payload.get("cwd")
    if isinstance(value, str) and value:
        return Path(value).expanduser()
    return None


def _environment_cwd() -> Path | None:
    """从环境变量 PWD 获取 cwd。"""
    env_pwd = os.environ.get("PWD")
    return Path(env_pwd).expanduser() if env_pwd else None


def _original_cwd() -> Path | None:
    """从 MEMORY_HOOK_ORIGINAL_CWD 获取原始 cwd。"""
    value = os.environ.get("MEMORY_HOOK_ORIGINAL_CWD")
    return Path(value).expanduser() if value else None


def _path_within_repo(path: Path) -> bool:
    """检查路径是否在仓库内。"""
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _discover_cwd(payload: dict[str, Any]) -> Path:
    """发现当前工作目录。"""
    provided_cwd = _payload_cwd(payload)
    original_cwd = _original_cwd()
    if os.environ.get("MEMORY_HOOK_PREFER_EXTERNAL_CWD") and original_cwd:
        return original_cwd
    if provided_cwd and _path_within_repo(provided_cwd):
        return provided_cwd
    env_cwd = _environment_cwd()
    if env_cwd and _path_within_repo(env_cwd):
        return env_cwd
    if env_cwd:
        return env_cwd
    if provided_cwd:
        return provided_cwd
    return REPO_ROOT


# ---------------------------------------------------------------------------
# Payload 解析与参数
# ---------------------------------------------------------------------------


def _read_payload(raw_payload: str) -> dict[str, Any]:
    """读取并解析 payload。"""
    if not raw_payload.strip():
        return {}
    try:
        loaded = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        _logger.warning("payload JSON parse failed: %s", exc)
        return {}
    return loaded if isinstance(loaded, dict) else {"payload": loaded}


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Workbot memory hook gateway.")
    parser.add_argument("--host", required=True, choices=("factory",))
    parser.add_argument("--event", required=True, choices=(
        "session-start", "prompt-submit", "stop", "notification",
        "pre-tool-use", "post-tool-use", "subagent-stop",
        "pre-compact", "session-end",
    ))
    parser.add_argument("--no-delegate", action="store_true", help="Generate gateway artifacts only.")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Delegate 执行
# ---------------------------------------------------------------------------


def _execute_delegate_via_facade(
    host: str,
    event: str,
    raw_payload: str,
    payload: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    """IF-5: Execute delegate via Facade."""
    delegate = _get_host_delegate(host)
    return delegate.execute(event, raw_payload, payload)


def _require_env(name: str) -> str:
    """Require an environment variable; raise RuntimeError if missing."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing required env: {name}")
    return value


def _canonicalize_cmux_refs(workspace_ref: str, surface_ref: str) -> tuple[str, str]:
    """Canonicalize cmux workspace/surface refs via cmux identify."""
    proc = subprocess.run(
        ["cmux", "identify", "--workspace", workspace_ref, "--surface", surface_ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return workspace_ref, surface_ref
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return workspace_ref, surface_ref
    caller = payload.get("caller")
    if not isinstance(caller, dict):
        return workspace_ref, surface_ref
    return (
        str(caller.get("workspace_ref") or workspace_ref),
        str(caller.get("surface_ref") or surface_ref),
    )


def _delegate_codex(event: str, raw_payload: str) -> subprocess.CompletedProcess[str]:
    """Codex delegate 执行。"""
    return _execute_delegate_via_facade("codex", event, raw_payload, {})


def _delegate_claude(
    event: str, raw_payload: str, payload: dict[str, Any]
) -> subprocess.CompletedProcess[str]:
    """Claude delegate 执行。"""
    return _execute_delegate_via_facade("claude", event, raw_payload, payload)


# ---------------------------------------------------------------------------
# Noop 与降级
# ---------------------------------------------------------------------------


def _should_noop_for_external_context(payload: dict[str, Any]) -> bool:
    """检查是否应跳过外部上下文。"""
    if _FORCE_HOOK or os.environ.get("MEMORY_HOOK_FORCE") or os.environ.get("WORKBOT_FORCE_HOOK"):
        return False
    env_cwd = _environment_cwd()
    provided_cwd = _payload_cwd(payload)
    original_cwd = _original_cwd()
    env_in_repo = bool(env_cwd and _path_within_repo(env_cwd))
    payload_in_repo = bool(provided_cwd and _path_within_repo(provided_cwd))
    original_in_repo = bool(original_cwd and _path_within_repo(original_cwd))
    return not env_in_repo and not payload_in_repo and not original_in_repo


def _delegate_noop_response(host: str) -> int:
    """M2: delegate-owned bypass instead of gateway host-dispatch."""
    delegate = _get_host_delegate(host)
    result = delegate.noop_response()
    if result.stdout:
        sys.stdout.write(result.stdout)
    return result.returncode


def _build_degraded_package_with_error(
    host: str,
    event: str,
    cwd: Path,
    error: str,
    error_type: str = "delegate_preflight_failed",
) -> dict[str, Any]:
    """M3: Build a degraded context-package with error info."""
    return {
        "package_kind": "degraded-context",
        "mode": "degraded",
        "status": "degraded",
        "host": host,
        "event": event,
        "project_root": str(cwd),
        "cwd": str(cwd),
        "error": {
            "type": error_type,
            "message": error,
        },
        "validation_errors": [error],
    }


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------


def _build_factory_hook_output(package: dict[str, Any], event: str) -> str:
    """Build Factory JSON Output format from context-package."""
    if event not in ("session-start", "prompt-submit"):
        if package.get("status") == "ok":
            return '{"suppressOutput": true}'
        return "{}"

    hook_event_name = {
        "session-start": "SessionStart",
        "prompt-submit": "UserPromptSubmit",
    }[event]

    context_lines = ["## Memory Context", ""]

    allowed_reads = package.get("allowed_reads", [])
    if allowed_reads:
        context_lines.append("### Allowed Reads")
        for path in allowed_reads:
            context_lines.append(f"- {path}")
        context_lines.append("")

    allowed_writes = package.get("allowed_writes", {})
    if allowed_writes:
        context_lines.append("### Allowed Writes")
        for key, value in allowed_writes.items():
            if isinstance(value, dict):
                context_lines.append(f"- {key}:")
                for sub_key, sub_val in value.items():
                    context_lines.append(f"  - {sub_key}: {sub_val}")
            else:
                context_lines.append(f"- {key}: {value}")
        context_lines.append("")

    validation_errors = package.get("validation_errors", [])
    if validation_errors:
        context_lines.append("### Validation Warnings")
        for error in validation_errors:
            context_lines.append(f"- {error}")
        context_lines.append("")

    additional_context = "\n".join(context_lines)

    output = {
        "hookSpecificOutput": {
            "hookEventName": hook_event_name,
            "additionalContext": additional_context,
        },
        "suppressOutput": True,
    }

    return json.dumps(output, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Delegate 主执行与生命周期
# ---------------------------------------------------------------------------


def _execute_delegate(
    args: argparse.Namespace,
    raw_payload: str,
    payload: dict[str, Any],
    cwd: Path,
    package: dict[str, Any] | None = None,
) -> int:
    """Execute the host-specific delegate and return an exit code."""
    try:
        if args.host == "codex":
            proc = _delegate_codex(args.event, raw_payload)
        elif args.host == "claude":
            proc = _delegate_claude(args.event, raw_payload, payload)
        else:
            proc = None
    except RuntimeError as exc:
        append_error_log(
            "memory-hook-gateway",
            "delegate preflight failed",
            {"host": args.host, "event": args.event, "error": str(exc), "cwd": str(cwd)},
        )
        degraded_package = _build_degraded_package_with_error(
            args.host, args.event, cwd, str(exc), error_type="delegate_preflight_failed"
        )
        sys.stdout.write(json.dumps(degraded_package, ensure_ascii=False) + "\n")
        return 0

    if proc is not None:
        if proc.returncode != 0:
            append_error_log(
                "memory-hook-gateway",
                "delegate command failed",
                {
                    "host": args.host,
                    "event": args.event,
                    "returncode": proc.returncode,
                    "stderr": proc.stderr,
                    "stdout": proc.stdout,
                    "artifact_latest": None,
                },
            )

        if proc.stdout:
            sys.stdout.write(proc.stdout)
        else:
            noop = _get_host_delegate(args.host).noop_response()
            if noop.stdout:
                sys.stdout.write(noop.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return proc.returncode
    else:
        if package is not None:
            sys.stdout.write(_build_factory_hook_output(package, args.event) + "\n")
        return 0


def _record_project_lifecycle_event(
    *,
    host: str,
    event: str,
    payload: dict[str, Any],
    cwd: Path,
) -> dict[str, Any] | None:
    """记录项目生命周期事件。"""
    if os.environ.get("MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE") != "1":
        return None
    try:
        return record_project_lifecycle(
            lifecycle_root=PROJECT_LIFECYCLE_ROOT,
            cwd=cwd,
            host=host,
            event=event,
            payload=payload,
            now_iso_fn=now_iso,
        )
    except Exception as exc:
        append_error_log(
            "memory-hook-gateway",
            "project lifecycle record failed",
            {"host": host, "event": event, "cwd": str(cwd), "error": str(exc)},
        )
        return None


def _emit_fast_path_metrics(args: argparse.Namespace, start_time: float) -> None:
    """Emit minimal metrics for fast-path events (no context package).

    Writes directly to metrics file without building a full package.
    Non-blocking: exceptions are caught and logged.
    """
    try:
        from .memory_hook_metrics import _resolve_metrics_path, append_metrics_record
        duration_ms = max(1, int((time.time() - start_time) * 1000))
        record = {
            "timestamp": now_iso(),
            "host": str(args.host),
            "event": str(args.event),
            "status": "fast_path",
            "context_package_size_bytes": 0,
            "validation_error_count": 0,
            "missing_paths_count": 0,
            "degraded": False,
            "core_provider": "",
            "package_kind": "",
            "duration_ms": duration_ms,
            "fast_path": True,
        }
        path = _resolve_metrics_path(ARTIFACT_ROOT)
        append_metrics_record(path, record)
    except Exception as exc:
        _logger.debug("fast-path metrics emit skipped: %s", exc)


def _record_event_log_minimal(args: argparse.Namespace, start_time: float) -> None:
    """Write minimal event log entry for fast-path events.

    Appends a single JSON line to EVENT_LOG without building full context.
    Non-blocking: exceptions are caught and logged.
    """
    try:
        duration_ms = max(1, int((time.time() - start_time) * 1000))
        record = {
            "timestamp": now_iso(),
            "event": str(args.event),
            "host": str(args.host),
            "status": "ok",
            "duration_ms": duration_ms,
            "fast_path": True,
        }
        EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with EVENT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        _logger.debug("fast-path event log skipped: %s", exc)
