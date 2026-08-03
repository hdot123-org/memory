#!/usr/bin/env python3.12
"""PreToolUse guard for memory-core ownership protection.

Reads stdin JSON payload, classifies the target path, and outputs
{"decision":"block"/"allow","reason":"..."} JSON to stdout.

Exit codes:
- 0: allow
- 2: block
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Any

from memory_core.tools._guard_classify import _get_project_root_for_task, classify_tool_use  # noqa: F401
from memory_core.tools._guard_patterns import (  # noqa: F401
    FORBIDDEN_DIRS,
    FORBIDDEN_SUFFIXES,
    PROTECTED_PATH_MARKERS,
    is_protected_path_target,
)
from memory_core.tools.memory_hook_metrics import _resolve_metrics_path, append_metrics_record

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore


def _load_project_root() -> Path | None:
    """Determine project root from environment."""
    # Try FACTORY_PROJECT_DIR first
    factory_dir = os.environ.get("FACTORY_PROJECT_DIR")
    if factory_dir:
        return Path(factory_dir).expanduser().resolve()

    # Try MEMORY_HOOK_ORIGINAL_CWD
    original_cwd = os.environ.get("MEMORY_HOOK_ORIGINAL_CWD")
    if original_cwd:
        return Path(original_cwd).expanduser().resolve()

    # Fallback to current working directory
    try:
        return Path.cwd().resolve()
    except Exception:
        return None


_now_iso = now_iso


_logger = logging.getLogger(__name__)


def _fail_closed_with_raw_check(raw_input: str, reason: str) -> tuple[int, dict[str, Any]]:
    """Fail-closed handler for when JSON parsing fails.

    Attempts to extract protected path markers from raw input string.
    """
    is_protected = False
    payload: dict[str, Any] = {}

    # Try to find protected markers in raw input
    if raw_input:
        for marker in PROTECTED_PATH_MARKERS:
            if marker in raw_input:
                is_protected = True
                break
        # Try to parse partial JSON for logging
        try:
            payload = json.loads(raw_input[:2000]) if raw_input else {}
        except Exception:
            # Could not parse, but we already checked markers
            pass

    if is_protected:
        decision = "block"
        permission_decision = "deny"
        reason_text = f"guard failure on protected path: {reason}"
        exit_code = 2
    else:
        decision = "allow"
        permission_decision = "allow"
        reason_text = f"guard failure, non-protected or undetermined path: {reason}"
        exit_code = 0

    result = {
        "decision": decision,
        "reason": reason_text,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission_decision,
            "permissionDecisionReason": reason_text,
        },
    }

    # Write error log (non-blocking)
    try:
        project_root = _load_project_root()
        if project_root is not None:
            from memory_core.tools.error_logger import write_error_log
            from memory_core.tools._redaction import redact

            redacted_raw = redact(raw_input[:500]) if raw_input else ""
            write_error_log(
                project_root=str(project_root),
                error_type="json_parse_error",
                context={
                    "guard_failure": "fail-closed",
                    "is_protected": is_protected,
                    "raw_input_preview": redacted_raw,
                },
                error_msg=reason,
            )
    except Exception as exc:
        _logger.debug("error log write failed in _fail_closed_with_raw_check: %s", exc)

    return exit_code, result


def _fail_closed_log_and_output(
    payload: dict[str, Any],
    reason: str,
    project_root: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Context-aware fail-closed: deny protected paths, allow others.

    Called when the guard encounters an internal failure (JSON parse error,
    stdin read exception, project root detection failure).

    Args:
        payload: Partial or empty payload (may not have been parsed successfully).
        reason: Human-readable failure reason.
        project_root: Project root if known, None otherwise.

    Returns:
        Tuple of (exit_code, result_dict).
        exit_code: 2 for deny (protected path), 0 for allow (non-protected/undetermined).
        result_dict: Decision JSON to print.
    """
    # Try to determine if the target path is protected
    is_protected = False
    if payload:
        try:
            is_protected = is_protected_path_target(payload)
        except Exception as exc:
            _logger.warning("is_protected_path_target check failed: %s", exc)

    # Decide: deny if protected, allow otherwise
    if is_protected:
        decision = "block"
        permission_decision = "deny"
        reason_text = f"guard failure on protected path: {reason}"
        exit_code = 2
    else:
        decision = "allow"
        permission_decision = "allow"
        reason_text = f"guard failure, non-protected or undetermined path: {reason}"
        exit_code = 0

    result = {
        "decision": decision,
        "reason": reason_text,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission_decision,
            "permissionDecisionReason": reason_text,
        },
    }

    # Write error log (non-blocking)
    try:
        if project_root is not None:
            from memory_core.tools.error_logger import write_error_log

            # Redact payload before logging
            from memory_core.tools._redaction import redact

            redacted_payload = redact(json.dumps(payload)[:500])
            write_error_log(
                project_root=str(project_root),
                error_type="json_parse_error",
                context={
                    "guard_failure": "fail-closed",
                    "is_protected": is_protected,
                    "payload_preview": redacted_payload,
                },
                error_msg=reason,
            )
    except Exception as exc:
        _logger.debug("error log write failed: %s", exc)

    return exit_code, result


def _write_metrics_jsonl(project_root: Path, record: dict[str, Any]) -> None:
    """Write a metrics record to metrics.jsonl using append_metrics_record."""
    try:
        metrics_path = _resolve_metrics_path(project_root / "memory" / "artifacts" / "memory-hook")
        append_metrics_record(metrics_path, record)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("metrics write failed: %s", exc)


def _rule_result_to_hook_json(rule_result: Any) -> dict[str, Any]:
    """Convert RuleResult to hook JSON dict format with dual-format output.

    The hook system expects a specific JSON format with 'decision', 'reason', 'scenario', etc.
    This function converts the internal RuleResult back to that format.

    Output includes BOTH legacy format (decision/reason) AND Factory official format
    (hookSpecificOutput.permissionDecision) for backward compatibility.

    Args:
        rule_result: RuleResult from classify_tool_use

    Returns:
        Dict in dual hook JSON format:
        {
            "decision": "allow"/"block",
            "reason": "...",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow"/"deny",
                "permissionDecisionReason": "..."
            },
            ...other fields from rule_result.detail
        }
    """
    from memory_core.tools._rule_types import RuleResult

    if not isinstance(rule_result, RuleResult):
        # Shouldn't happen, but handle gracefully
        reason = "Invalid result type"
        return {
            "decision": "allow",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": reason,
            },
        }

    # Start with the detail dict which contains decision, scenario, item_results, injected_prompt
    result_dict = dict(rule_result.detail)

    # Ensure decision is present (should be in detail)
    if "decision" not in result_dict:
        result_dict["decision"] = "block" if rule_result.matched else "allow"

    # Add reason from message
    result_dict["reason"] = rule_result.message

    # Add Factory official format (hookSpecificOutput) for forward compatibility
    # Map "block" → "deny", "allow" → "allow"
    permission_decision = "deny" if result_dict["decision"] == "block" else "allow"
    result_dict["hookSpecificOutput"] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": permission_decision,
        "permissionDecisionReason": result_dict["reason"],
    }

    return result_dict


def main() -> int:
    """Main entry point for PreToolUse guard."""
    start_time = time.time()

    # MEMORY_HOOK_FORCE does NOT bypass PreToolUse guard
    # This is intentional - PreToolUse is a hard guard

    # Read JSON payload from stdin
    try:
        raw_stdin = sys.stdin.read()
        payload = json.loads(raw_stdin)
    except json.JSONDecodeError as e:
        # Fail-closed: check raw stdin for protected path markers
        exit_code, result = _fail_closed_with_raw_check(raw_stdin, f"Invalid JSON input: {e}")
        print(json.dumps(result))
        return exit_code
    except Exception as e:
        # Fail-closed: stdin read failed, no payload to check
        exit_code, result = _fail_closed_with_raw_check("", f"Error reading input: {e}")
        print(json.dumps(result))
        return exit_code

    # Normalize payload: Factory hooks wrap tool params in tool_input
    # Standalone tests pass fields at top level
    if "tool_input" in payload:
        tool_input = payload.get("tool_input", {})
        for k, v in tool_input.items():
            payload.setdefault(k, v)

    # Get project root
    project_root = _load_project_root()
    if project_root is None:
        # Fail-closed: check payload for protected path
        exit_code, result = _fail_closed_log_and_output(
            payload,
            "Cannot determine project root",
            project_root=None
        )
        print(json.dumps(result))
        return exit_code

    # Check if memory/system exists (if not, this isn't a memory-managed project)
    if not (project_root / "memory" / "system").exists():
        print(json.dumps({
            "decision": "allow",
            "reason": "Not a memory-managed project (no memory/system directory)"
        }))
        return 0

    # Classify the tool use
    rule_result = classify_tool_use(payload, project_root)
    result = _rule_result_to_hook_json(rule_result)

    # Write metrics to local JSONL (replaces PostHog telemetry)
    try:
        duration_ms = int((time.time() - start_time) * 1000)
        metrics_record = {
            "event": "tool_used",
            "tool_name": payload.get("tool_name", "unknown"),
            "decision": result.get("decision", "unknown"),
            "reason": result.get("reason", ""),
            "duration_ms": duration_ms,
            "timestamp": _now_iso(),
        }
        _write_metrics_jsonl(project_root, metrics_record)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("metrics write failed in main: %s", exc)

    # Output JSON result
    print(json.dumps(result))

    # Exit code: 0 = allow, 2 = block
    if result["decision"] == "block":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
