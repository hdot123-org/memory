"""Tests for telemetry fixes - VAL-EVENT-001, VAL-EVENT-002, VAL-PRETOOL-001, VAL-PRETOOL-002.

Verifies:
- session_end_logger.py writes 'session-end' (kebab-case) not 'session_ended' (snake_case)
- No snake_case event names remain in memory_core/tools/ source code
- pre-tool-use branch calls emit_metrics() before returning
- pre-tool-use metrics record has event, host, status, duration_ms fields
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


class TestSessionEndEventNaming:
    """VAL-EVENT-001: Session-end event uses kebab-case."""

    def test_session_end_event_uses_kebab_case(self):
        """Verify session_end_logger writes 'session-end' not 'session_ended'.

        Reads the source file directly to confirm the event name literal,
        avoiding fragile mocking of main()'s complex control flow.
        """
        from pathlib import Path

        from memory_core.tools import session_end_logger

        source_file = Path(session_end_logger.__file__)
        source_text = source_file.read_text(encoding="utf-8")

        assert '"event": "session-end"' in source_text, (
            "session_end_logger should use 'session-end' (kebab-case)"
        )
        assert '"event": "session_ended"' not in source_text, (
            "session_end_logger should NOT use 'session_ended' (snake_case)"
        )


class TestNoSnakeCaseEventNames:
    """VAL-EVENT-002: No snake_case event names in codebase."""

    def test_no_snake_case_event_names_in_source(self):
        """Grep-verify no snake_case event names exist in memory_core/tools/.

        Searches for patterns like:
        - "event": "session_ended"
        - "event": "session_started"
        - "event": "pre_tool_use"
        """
        tools_dir = repo_root / "memory_core" / "tools"

        snake_case_patterns = [
            '"event": "session_ended"',
            '"event": "session_started"',
            '"event": "pre_tool_use"',
            '"event":"session_ended"',
            '"event":"session_started"',
            '"event":"pre_tool_use"',
        ]

        violations = []

        for py_file in tools_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for pattern in snake_case_patterns:
                if pattern in content:
                    violations.append(f"{py_file.name}: found {pattern}")

        assert len(violations) == 0, (
            "Found snake_case event names in source code:\n"
            + "\n".join(violations)
            + "\nAll event names should use kebab-case (e.g., 'session-end')"
        )


class TestPreToolUseEmitMetrics:
    """VAL-PRETOOL-001 and VAL-PRETOOL-002: Pre-tool-use emits metrics before returning."""

    def test_pretooluse_calls_emit_metrics_on_success(self):
        """Verify emit_metrics is called when pre-tool-use branch returns proc.returncode.

        This test simulates a pre-tool-use event where the guard script succeeds,
        and verifies emit_metrics is called with event='pre-tool-use' and correct fields.
        """
        from memory_core.tools import memory_hook_gateway

        # Mock emit_metrics to capture calls
        emit_calls = []

        def capture_emit(artifact_root, host, event, package, duration_ms=0):
            emit_calls.append({
                "artifact_root": artifact_root,
                "host": host,
                "event": event,
                "package": package,
                "duration_ms": duration_ms,
            })
            return Path("/tmp/test_metrics.jsonl")

        # Create a mock process result
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"decision": "allow", "reason": "guard passed"})
        mock_proc.stderr = ""

        # Mock subprocess.run to return our mock process
        # Patch emit_metrics at the module level where it's defined
        with patch("subprocess.run", return_value=mock_proc), \
             patch("memory_core.tools.memory_hook_metrics.emit_metrics", side_effect=capture_emit), \
             patch.object(memory_hook_gateway, "is_memory_core_source_repo", return_value=False), \
             patch.object(memory_hook_gateway, "is_denied_project_root", return_value=False), \
             patch.object(memory_hook_gateway, "_should_noop_for_external_context", return_value=False), \
             patch.object(memory_hook_gateway, "_discover_cwd", return_value=Path("/tmp/test-project")), \
             patch.object(memory_hook_gateway, "_parse_args", return_value=MagicMock(
                 host="factory",
                 event="pre-tool-use",
             )), \
             patch("sys.stdin", io.StringIO("{}")):

            # Run main() - it should return the guard's returncode
            result = memory_hook_gateway.main()

            # Verify the function returned the guard's returncode
            assert result == 0, f"Expected return code 0, got {result}"

            # Verify emit_metrics was called
            assert len(emit_calls) > 0, "emit_metrics should have been called in pre-tool-use branch"

            # Verify the event field is 'pre-tool-use'
            call = emit_calls[0]
            assert call["event"] == "pre-tool-use", (
                f"Event field should be 'pre-tool-use', got '{call['event']}'"
            )

            # Verify host field is present
            assert call["host"] == "factory", f"Expected host='factory', got '{call['host']}'"

            # Verify package is a dict (minimal structure)
            assert isinstance(call["package"], dict), "Package should be a dict"

            # Verify duration_ms is present and non-negative
            assert isinstance(call["duration_ms"], int), "duration_ms should be an integer"
            assert call["duration_ms"] >= 0, "duration_ms should be non-negative"

    def test_pretooluse_calls_emit_metrics_on_fallback(self):
        """Verify emit_metrics is called when pre-tool-use branch falls back to return 0.

        This test simulates a pre-tool-use event where the guard script is unavailable,
        and verifies emit_metrics is still called before the fallback return.
        """
        from memory_core.tools import memory_hook_gateway

        emit_calls = []

        def capture_emit(artifact_root, host, event, package, duration_ms=0):
            emit_calls.append({
                "artifact_root": artifact_root,
                "host": host,
                "event": event,
                "package": package,
                "duration_ms": duration_ms,
            })
            return Path("/tmp/test_metrics.jsonl")

        # Mock subprocess.run to raise an exception (guard unavailable)
        with patch("subprocess.run", side_effect=FileNotFoundError("guard script not found")), \
             patch("memory_core.tools.memory_hook_metrics.emit_metrics", side_effect=capture_emit), \
             patch.object(memory_hook_gateway, "append_error_log"), \
             patch.object(memory_hook_gateway, "is_memory_core_source_repo", return_value=False), \
             patch.object(memory_hook_gateway, "is_denied_project_root", return_value=False), \
             patch.object(memory_hook_gateway, "_should_noop_for_external_context", return_value=False), \
             patch.object(memory_hook_gateway, "_discover_cwd", return_value=Path("/tmp/test-project")), \
             patch.object(memory_hook_gateway, "_parse_args", return_value=MagicMock(
                 host="factory",
                 event="pre-tool-use",
             )), \
             patch("sys.stdin", io.StringIO("{}")):

            # Run main() - it should return 0 (fallback)
            result = memory_hook_gateway.main()

            # Verify the function returned 0 (fallback)
            assert result == 0, f"Expected return code 0 (fallback), got {result}"

            # Verify emit_metrics was called even in fallback path
            assert len(emit_calls) > 0, (
                "emit_metrics should have been called in pre-tool-use fallback path"
            )

            # Verify the event field is 'pre-tool-use'
            call = emit_calls[0]
            assert call["event"] == "pre-tool-use", (
                f"Event field should be 'pre-tool-use', got '{call['event']}'"
            )

    def test_pretooluse_metrics_record_has_required_fields(self):
        """VAL-PRETOOL-002: Verify metrics record contains event, host, status, duration_ms.

        This test verifies the metrics record structure for pre-tool-use events
        matches the expected schema with all required fields.
        """
        from memory_core.tools import memory_hook_gateway
        from memory_core.tools.memory_hook_metrics import collect_metrics

        captured_records = []

        def capture_collect_metrics(host, event, package, now_iso=None, duration_ms=0):
            # Call the real collect_metrics to get the actual record structure
            record = collect_metrics(host, event, package, now_iso, duration_ms)
            captured_records.append(record)
            return record

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"decision": "allow", "reason": "test"})
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc), \
             patch("memory_core.tools.memory_hook_metrics.collect_metrics", side_effect=capture_collect_metrics), \
             patch("memory_core.tools.memory_hook_metrics.append_metrics_record", return_value=True), \
             patch.object(memory_hook_gateway, "is_memory_core_source_repo", return_value=False), \
             patch.object(memory_hook_gateway, "is_denied_project_root", return_value=False), \
             patch.object(memory_hook_gateway, "_should_noop_for_external_context", return_value=False), \
             patch.object(memory_hook_gateway, "_discover_cwd", return_value=Path("/tmp/test-project")), \
             patch.object(memory_hook_gateway, "_parse_args", return_value=MagicMock(
                 host="factory",
                 event="pre-tool-use",
             )), \
             patch("sys.stdin", io.StringIO("{}")):

            memory_hook_gateway.main()

        # Verify collect_metrics was called
        assert len(captured_records) > 0, "collect_metrics should have been called"

        # Verify the record has all required fields
        record = captured_records[0]
        required_fields = ["event", "host", "status", "duration_ms"]
        for field in required_fields:
            assert field in record, f"Metrics record missing required field: {field}"

        # Verify field values
        assert record["event"] == "pre-tool-use"
        assert record["host"] == "factory"
        assert "status" in record  # status field exists
        assert "duration_ms" in record  # duration_ms field exists
