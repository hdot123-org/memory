#!/usr/bin/env python3.12
"""Gateway 处理器模块：事件处理函数与主入口。

职责：
- 各类事件的 handler 函数（session-start、prompt-submit 等）
- main() 主入口函数
- 顶层异常处理 _gateway_excepthook

依赖层级：位于拆分链的顶层，依赖 _gateway_config、_gateway_artifacts、
_gateway_telemetry、_gateway_policy、_gateway_dispatch。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_core.constants import SUPPORTED_HOSTS

from ._gateway_artifacts import (
    _build_readonly_source_repo_package,
    _inject_health_alert,
    _launch_async_health_check,
    _update_state_dynamic_fields,
    append_error_log,
)
from ._gateway_config import (
    ARTIFACT_ROOT,
    CONTEXT_ROOT,
    ERROR_LOG,
    _integrity_verify,
    get_source_repo_mode,
    is_denied_project_root,
    is_memory_core_source_repo,
)
from ._gateway_dispatch import (
    _delegate_noop_response,
    _discover_cwd,
    _emit_fast_path_metrics,
    _execute_delegate,
    _parse_args,
    _read_payload,
    _record_event_log_minimal,
    _record_project_lifecycle_event,
    _should_noop_for_external_context,
)
from ._gateway_policy import (
    build_context_package,
    determine_project_scope,
)
from ._gateway_telemetry import (
    _log_prompt_submit,
    _maybe_sync_telemetry,
)
from ._guard_patterns import is_protected_path_target
from .memory_hook_impls import ArtifactWriter

_logger = logging.getLogger(__name__)

# 非注入事件列表
NON_INJECTION_EVENTS = (
    "stop",
    "post-tool-use",
    "subagent-stop",
    "pre-compact",
    "session-end",
    "notification",
)


class HookTimeoutError(Exception):
    """Hook 执行超时异常。"""

    pass


# ---------------------------------------------------------------------------
# 通用辅助函数
# ---------------------------------------------------------------------------


def _emit_pretooluse_metrics(host: str, event: str, status: str, start_time: float) -> None:
    """Emit metrics for pre-tool-use events before returning."""
    try:
        from .memory_hook_metrics import emit_metrics

        duration_ms = max(1, int((time.time() - start_time) * 1000))
        minimal_package = {"status": status}
        emit_metrics(ARTIFACT_ROOT, host, event, minimal_package, duration_ms=duration_ms)
    except Exception as exc:
        _logger.debug("pre-tool-use metrics emit skipped: %s", exc)


# ---------------------------------------------------------------------------
# 事件处理函数
# ---------------------------------------------------------------------------


def _handle_source_repo_check(cwd: Path, host: str, event: str) -> int | None:
    """Handle source repo readonly mode. Returns exit code if handled, None to continue."""
    if is_memory_core_source_repo(cwd):
        mode = get_source_repo_mode(cwd)
        if mode != "develop":
            readonly_package = _build_readonly_source_repo_package(cwd, host, event)
            sys.stdout.write(json.dumps(readonly_package, ensure_ascii=False) + "\n")
            return 0
    return None


def _handle_pretooluse_guard(args: argparse.Namespace, raw_payload: str, cwd: Path, start_time: float) -> int | None:
    """Handle pre-tool-use event: intercept write operations via guard script.

    Returns exit code if handled, None to continue to normal flow.
    """
    if args.event != "pre-tool-use":
        return None

    # Use -m module mode so absolute imports work (REF-001: guard uses
    # 'from memory_core.tools._guard_classify import ...' which requires
    # __package__ to be set; script mode sets __package__=None).
    exc_type = "unknown"
    try:
        guard_env = {**os.environ, "MEMORY_HOOK_ORIGINAL_CWD": str(cwd)}
        proc = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input=raw_payload,
            text=True,
            capture_output=True,
            timeout=5,
            env=guard_env,
        )
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        status = "ok" if proc.returncode == 0 else "error"
        _emit_pretooluse_metrics(args.host, args.event, status, start_time)
        return proc.returncode
    except subprocess.TimeoutExpired:
        exc_type = "TimeoutExpired"
        append_error_log("pretooluse-guard", "guard timed out after 5s", {"cwd": str(cwd)})
    except Exception as exc:
        exc_type = type(exc).__name__
        append_error_log("pretooluse-guard", "guard execution failed", {"error": str(exc)})

    # Fail-closed: context-aware fallback instead of blanket allow
    # Parse raw_payload to check if target path is protected
    payload_dict: dict[str, Any] = {}
    try:
        payload_dict = json.loads(raw_payload) if raw_payload else {}
    except (json.JSONDecodeError, ValueError) as exc:
        _logger.warning("Failed to parse pre-tool-use payload for guard: %s", exc)
        print(f"Warning: failed to parse pre-tool-use payload: {exc}", file=sys.stderr)

    # Guard against non-dict JSON payloads (e.g., JSON array or scalar)
    is_protected = False
    if isinstance(payload_dict, dict):
        is_protected = is_protected_path_target(payload_dict)

    # Write error log with redacted context
    try:
        from memory_core.tools._redaction import redact as _redact
        from memory_core.tools.error_logger import write_error_log as _write_err

        redacted_raw = _redact(raw_payload[:500]) if raw_payload else ""

        _write_err(
            project_root=str(cwd),
            error_type="hook_timeout",
            context={
                "guard_failure": "gateway-fallback",
                "is_protected": is_protected,
                "payload_preview": redacted_raw,
            },
            error_msg=f"guard subprocess failed on {'protected' if is_protected else 'non-protected'} path (exception: {exc_type})",
        )
    except Exception as exc:
        _logger.debug("memory_hook_gateway._handle_pretooluse_guard: error logging failed: %s", exc)

    if is_protected:
        # Fail-closed: deny protected paths
        reason_text = "guard unavailable, blocking protected path by default"
        result = {
            "decision": "block",
            "reason": reason_text,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason_text,
            },
        }
        print(json.dumps(result))
        _emit_pretooluse_metrics(args.host, args.event, "error", start_time)
        return 2
    else:
        # Fail-open: allow non-protected or undetermined paths
        reason_text = "guard unavailable, allowing non-protected path by default"
        result = {
            "decision": "allow",
            "reason": reason_text,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": reason_text,
            },
        }
        print(json.dumps(result))
        _emit_pretooluse_metrics(args.host, args.event, "ok", start_time)
        return 0


def _handle_session_start_setup(cwd: Path) -> None:
    """Handle session-start side effects: health check, state update, telemetry sync, version probe."""
    _launch_async_health_check(cwd)
    project_scope = determine_project_scope(cwd)
    _update_state_dynamic_fields(cwd, project_scope)
    try:
        _maybe_sync_telemetry(ARTIFACT_ROOT)
    except Exception as exc:
        _logger.debug("telemetry sync skipped: %s", exc)

    # M1: Auto-version-follow probe
    # Detect version mismatch and auto-sync consumer projects
    # M3 (INFRA-576): version_sync 已迁移到 infra-core，本地副本已删除
    try:
        from infra_core.engine.version_sync import (
            probe_version_and_sync,
            set_resign_hook,
        )

        from memory_core.constants import CURRENT_MEMORY_VERSION

        # Inject memory-core's resign wrapper
        def _memory_core_resign_wrapper(project_path: Path, changed_paths: list[str]) -> dict[str, Any]:
            """Wrap memory-core's load_key + sign_project_incremental."""
            try:
                from memory_core.tools.memory_hook_integrity_keys import load_key
                from memory_core.tools.memory_hook_integrity_manifest import (
                    sign_project_incremental,
                )

                key = load_key()
                if key is None:
                    return {"resigned": False, "reason": "no signing key"}
                sign_project_incremental(project_path, key, changed_paths=changed_paths)
                return {"resigned": True, "paths": changed_paths}
            except Exception as exc:
                return {"resigned": False, "reason": str(exc)}

        set_resign_hook(_memory_core_resign_wrapper)

        # Pass current_version parameter (infra-core does not hardcode it)
        probe_version_and_sync(cwd, CURRENT_MEMORY_VERSION)
    except Exception as exc:
        # Fail-safe: any exception must not block hook main chain
        _logger.debug("version probe skipped: %s", exc)


def _handle_prompt_submit_logging(cwd: Path, payload: dict[str, Any]) -> None:
    """Handle prompt-submit real-time logging."""
    try:
        _log_prompt_submit(cwd, payload)
    except Exception as exc:
        _logger.warning("_log_prompt_submit failed: %s", exc)


def _handle_integrity_check(cwd: Path, package: dict[str, Any], host: str, event: str) -> None:
    """Verify project integrity on session-start. May set package status to 'blocked'."""
    integrity_result = _integrity_verify(cwd)
    if not integrity_result or integrity_result.get("ok", True):
        return
    if integrity_result.get("skipped_reason") == "key_not_found":
        _logger.info("Integrity protection skipped: key not found")
        return
    append_error_log(
        "memory-hook-integrity",
        "project integrity check failed",
        {"host": host, "event": event, "cwd": str(cwd), "integrity": integrity_result},
    )
    package["status"] = "blocked"
    package.setdefault("validation_errors", [])
    if isinstance(package.get("validation_errors"), list):
        package["validation_errors"].append("integrity-check-failed")
        for err in integrity_result.get("errors", []):
            detail = err.get("detail", str(err))
            package["validation_errors"].append(f"integrity-error: {detail}")


# ---------------------------------------------------------------------------
# 工件写入与指标
# ---------------------------------------------------------------------------


def _write_artifacts_and_emit_metrics(
    args: argparse.Namespace, writer: Any, package: dict[str, Any], cwd: Path, start_time: float
) -> bool:
    """Write artifacts, re-sign manifest, and emit metrics. Returns write_ok status."""

    write_ok = writer.write(args.host, args.event, package)
    if not write_ok:
        append_error_log(
            "memory-hook-gateway",
            "artifact write failed",
            {"host": args.host, "event": args.event, "error": writer.last_error},
        )
        print(f"[memory-hook-gateway] artifact write failed: {writer.last_error}", file=sys.stderr)
    if write_ok:
        from ._gateway_config import _integrity_sign

        _integrity_sign(cwd)
    try:
        from .memory_hook_metrics import emit_metrics

        duration_ms = max(1, int((time.time() - start_time) * 1000))
        emit_metrics(ARTIFACT_ROOT, args.host, args.event, package, duration_ms=duration_ms)
    except Exception as exc:
        _logger.debug("metrics emit skipped: %s", exc)
    return bool(write_ok)


def _compute_exit_code(args: argparse.Namespace, package: dict[str, Any]) -> int:
    """Determine exit code based on package status."""
    if package["status"] != "ok":
        append_error_log(
            "memory-hook-gateway",
            "missing canonical prerequisites or project-map validation failed",
            {
                "host": args.host,
                "event": args.event,
                "missing_paths": package["missing_paths"],
                "validation_errors": package.get("validation_errors", []),
            },
        )
        print(
            "[memory-hook-gateway] degraded: "
            f"missing canonical paths: {', '.join(package['missing_paths']) or 'none'}; "
            f"project-map errors: {', '.join(package.get('validation_errors', [])) or 'none'}",
            file=sys.stderr,
        )
        return 1
    return 0


def _dispatch_output(
    args: argparse.Namespace,
    package: dict[str, Any],
    raw_payload: str,
    payload: dict[str, Any],
    cwd: Path,
    exit_code: int,
) -> int:
    """Handle final output dispatch: no-delegate JSON or delegate execution."""
    if args.no_delegate:
        sys.stdout.write(json.dumps(package, ensure_ascii=False) + "\n")
        return exit_code
    return _execute_delegate(args, raw_payload, payload, cwd, package=package)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main() -> int:
    """Gateway 主入口函数。"""
    start_time = time.time()
    args = _parse_args()
    raw_payload = sys.stdin.read()
    payload = _read_payload(raw_payload)
    cwd = _discover_cwd(payload)

    # M3: Anti-pollution - source repo gets readonly context-package instead of noop
    source_result = _handle_source_repo_check(cwd, args.host, args.event)
    if source_result is not None:
        return source_result

    if is_denied_project_root(cwd):
        sys.stdout.write("{}\n")
        return 0

    if _should_noop_for_external_context(payload):
        return _delegate_noop_response(args.host)

    # ── PreToolUse guard: intercept write operations ──
    guard_result = _handle_pretooluse_guard(args, raw_payload, cwd, start_time)
    if guard_result is not None:
        return guard_result

    # Async: Launch health check in background for session-start
    if args.event == "session-start":
        _handle_session_start_setup(cwd)

    # F4: PromptSubmit real-time logging
    if args.event == "prompt-submit":
        _handle_prompt_submit_logging(cwd, payload)

    # Fast path for non-injection events: skip expensive build_context_package()
    # Only apply fast path for supported hosts; other hosts go through full path
    if args.event in NON_INJECTION_EVENTS and args.host in SUPPORTED_HOSTS:
        lifecycle_record = None
        try:
            lifecycle_record = _record_project_lifecycle_event(
                host=args.host,
                event=args.event,
                payload=payload,
                cwd=cwd,
            )
        except Exception as exc:
            _logger.debug("lifecycle recording failed for %s: %s", args.event, exc)

        try:
            _emit_fast_path_metrics(args, start_time)
        except Exception as exc:
            _logger.debug("fast-path metrics failed for %s: %s", args.event, exc)

        try:
            _record_event_log_minimal(args, start_time)
        except Exception as exc:
            _logger.debug("fast-path event log failed for %s: %s", args.event, exc)

        sys.stdout.write('{"suppressOutput": true}\n')
        return 0

    # Injection events: full path with lifecycle pre-recorded
    lifecycle_record = _record_project_lifecycle_event(
        host=args.host,
        event=args.event,
        payload=payload,
        cwd=cwd,
    )

    writer = ArtifactWriter(CONTEXT_ROOT, ERROR_LOG, datetime_module=datetime)
    package = build_context_package(args.host, args.event, payload, lifecycle_record=lifecycle_record)

    # Health Alert: Inject previous session's health report if available
    if args.event == "session-start":
        _inject_health_alert(cwd, package)

    # L2: Verify integrity on session-start (after package is built)
    if args.event == "session-start":
        _handle_integrity_check(cwd, package, args.host, args.event)

    _write_artifacts_and_emit_metrics(args, writer, package, cwd, start_time)

    exit_code = _compute_exit_code(args, package)
    return _dispatch_output(args, package, raw_payload, payload, cwd, exit_code)


# ---------------------------------------------------------------------------
# 顶层异常处理
# ---------------------------------------------------------------------------


def _gateway_excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
    """Top-level exception hook: capture unexpected gateway crashes to JSONL."""
    try:
        metrics_dir = ARTIFACT_ROOT
        metrics_dir.mkdir(parents=True, exist_ok=True)
        metrics_file = metrics_dir / "metrics.jsonl"
        # Calculate duration_ms if we have a start_time (from main())
        # Otherwise use 0 for unexpected crashes before main() starts
        duration_ms = 0
        if hasattr(sys, "_gateway_start_time"):
            duration_ms = int((time.time() - sys._gateway_start_time) * 1000)
        record = {
            "event": "hook_error",
            "error_type": exc_type.__name__,
            "error_message": str(exc_value)[:500],
            "hook_version": "memory-hook-gateway-v1",
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "status": "error",
        }
        with metrics_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        _logger.debug("memory_hook_gateway._gateway_excepthook: metrics write failed: %s", exc)
    # Call the default handler to preserve standard traceback behavior
    sys.__excepthook__(exc_type, exc_value, exc_tb)


# 安装顶层异常钩子
sys.excepthook = _gateway_excepthook


if __name__ == "__main__":
    raise SystemExit(main())
