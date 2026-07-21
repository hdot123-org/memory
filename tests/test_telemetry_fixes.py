"""Tests for telemetry fixes - VAL-EVENT-001, VAL-EVENT-002, VAL-PRETOOL-001, VAL-PRETOOL-002.

Verifies:
- session_end_logger.py writes 'session-end' (kebab-case) not 'session_ended' (snake_case)
- No snake_case event names remain in memory_core/tools/ source code
- pre-tool-use branch calls emit_metrics() before returning
- pre-tool-use metrics record has event, host, status, duration_ms fields
"""

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

    def test_session_end_event_uses_kebab_case(self, tmp_path):
        """Verify session_end_logger writes 'session-end' not 'session_ended' at runtime.

        This is a behavioral test that calls _write_session_metrics() directly
        and verifies the actual metrics record produced has event='session-end'.
        """
        from memory_core.tools import session_end_logger

        # Capture the metrics record passed to append_metrics_record
        captured_records = []

        def capture_append_metrics(path, record):
            captured_records.append(record)
            return True

        # Mock info dict that _extract_session_info_streaming would return
        mock_info = {
            "duration_seconds": 1,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tool_calls": 3,
        }

        # Call _write_session_metrics() directly with the extracted function
        with patch.object(session_end_logger, "_resolve_metrics_path", return_value=tmp_path / "metrics.jsonl"), \
             patch.object(session_end_logger, "append_metrics_record", side_effect=capture_append_metrics):

            session_end_logger._write_session_metrics(tmp_path, mock_info)

        # Verify append_metrics_record was called
        assert len(captured_records) > 0, "append_metrics_record should have been called"

        # VAL-TEST-001: Verify the event field is 'session-end' (kebab-case)
        record = captured_records[0]
        assert record["event"] == "session-end", (
            f"Event field should be 'session-end' (kebab-case), got '{record['event']}'"
        )

        # Verify other expected fields are present
        assert "duration_seconds" in record
        assert "input_tokens" in record
        assert "output_tokens" in record
        assert "total_tool_calls" in record
        assert "duration_ms" in record
        assert "timestamp" in record


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


class TestSourceRepoDegradedStatus:
    """VAL-DEGRADED-001, VAL-DEGRADED-002: Source-repo gets status='ok' with 0 validation errors.

    Bug 3: When source-repo runs in develop mode, it falls through to build_context_package()
    which runs full consumer validation. Source-repo doesn't have consumer-project structure,
    causing ~35 false validation errors → status='degraded'.

    Fix: build_context_package() must detect source-repo early and skip consumer validation,
    returning status='ok' with validation_error_count=0.
    """

    def test_source_repo_develop_mode_gets_status_ok(self):
        """Verify source-repo in develop mode gets status='ok', not 'degraded'.

        When is_memory_core_source_repo(cwd) returns True, build_context_package()
        should skip consumer-project validation layers (project_map, truth_basis,
        contract checks) that produce false errors. Should return status='ok'
        with validation_error_count=0.
        """
        from memory_core.tools import memory_hook_gateway

        # Mock cwd to be the source-repo
        mock_cwd = Path("/Users/busiji/memory")

        # Mock all dependencies to simulate source-repo scenario
        with patch.object(
            memory_hook_gateway,
            "is_memory_core_source_repo",
            return_value=True,
        ), patch.object(
            memory_hook_gateway,
            "_discover_cwd",
            return_value=mock_cwd,
        ), patch.object(
            memory_hook_gateway,
            "determine_project_scope",
            return_value="source-repo",
        ), patch.object(
            memory_hook_gateway,
            "_record_project_lifecycle_event",
            return_value=None,
        ), patch.object(
            memory_hook_gateway,
            "_get_gateway_business_policy",
        ), patch.object(
            memory_hook_gateway,
            "CoreConfig",
        ), patch.object(
            memory_hook_gateway,
            "_resolve_core_builder",
        ) as mock_resolve_core_builder:
            # Mock business policy to return empty/default values
            mock_policy_instance = MagicMock()
            mock_policy_instance.get_required_canonical.return_value = []
            mock_policy_instance.get_project_canonical.return_value = {}
            mock_policy_instance.get_project_runtime_root.return_value = {}
            mock_policy_instance.get_global_canonical.return_value = []

            # Mock the core builder to simulate validation errors
            # (this is what currently happens - it runs full validation)
            def mock_builder_with_errors(config):
                return {
                    "status": "degraded",
                    "validation_errors": [f"error-{i}" for i in range(35)],
                    "missing_paths": ["memory/kb/global/", "memory/project-map/"],
                    "host": config.host,
                    "event": config.event,
                    "system_context": {},
                }

            mock_resolve_core_builder.return_value = ("legacy", mock_builder_with_errors, [])

            # Call build_context_package - this should detect source-repo
            # and skip validation, returning status='ok'
            result = memory_hook_gateway.build_context_package(
                "factory", "session-start", {}
            )

        # VAL-DEGRADED-001: status must be 'ok', not 'degraded'
        assert result.get("status") == "ok", (
            f"Source-repo should get status='ok', got '{result.get('status')}'"
        )

        # VAL-DEGRADED-002: validation_error_count must be 0 or near-zero (≤2)
        validation_errors = result.get("validation_errors", [])
        error_count = len(validation_errors) if isinstance(validation_errors, list) else 0
        assert error_count <= 2, (
            f"Source-repo should have ≤2 validation errors, got {error_count}: {validation_errors}"
        )

    def test_source_repo_readonly_mode_gets_status_ok(self):
        """Verify source-repo in readonly mode gets status='ok'.

        When mode is 'readonly', main() should use _build_readonly_source_repo_package
        which already returns status='ok'. This test verifies that path works.
        """
        from memory_core.tools import memory_hook_gateway

        mock_cwd = Path("/Users/busiji/memory")

        with patch.object(
            memory_hook_gateway,
            "is_memory_core_source_repo",
            return_value=True,
        ), patch.object(
            memory_hook_gateway,
            "get_source_repo_mode",
            return_value="readonly",
        ), patch.object(
            memory_hook_gateway,
            "_discover_cwd",
            return_value=mock_cwd,
        ), patch.object(
            memory_hook_gateway,
            "_build_readonly_source_repo_package",
        ) as mock_readonly_builder, patch.object(
            memory_hook_gateway,
            "_parse_args",
            return_value=MagicMock(host="factory", event="session-start"),
        ), patch("sys.stdin", io.StringIO("{}")):
            # Mock the readonly package builder
            mock_readonly_builder.return_value = {
                "status": "ok",
                "package_kind": "source-repo-rules",
                "mode": "read-only",
                "validation_errors": [],
            }

            result_code = memory_hook_gateway.main()

        # Should return 0 (success)
        assert result_code == 0, f"Expected return code 0, got {result_code}"

        # Verify _build_readonly_source_repo_package was called
        mock_readonly_builder.assert_called_once()

    def test_non_source_repo_still_gets_full_validation(self):
        """Verify non-source-repo projects still get full validation (no regression).

        When is_memory_core_source_repo returns False, the gateway should run
        full consumer-project validation as normal.
        """
        from memory_core.tools import memory_hook_gateway

        mock_cwd = Path("/tmp/test-consumer-project")

        # Mock the core builder to return a normal package
        def mock_normal_package(config):
            return {
                "status": "ok",
                "validation_errors": [],
                "missing_paths": [],
                "host": "factory",
                "event": "session-start",
                "system_context": {},
            }

        # Capture the package returned
        with patch.object(
            memory_hook_gateway,
            "is_memory_core_source_repo",
            return_value=False,  # NOT source-repo
        ), patch.object(
            memory_hook_gateway,
            "_discover_cwd",
            return_value=mock_cwd,
        ), patch.object(
            memory_hook_gateway,
            "determine_project_scope",
            return_value="consumer-project",
        ), patch.object(
            memory_hook_gateway,
            "_record_project_lifecycle_event",
            return_value=None,
        ), patch.object(
            memory_hook_gateway,
            "CoreConfig",
        ), patch.object(
            memory_hook_gateway,
            "_resolve_core_builder",
            return_value=("legacy", mock_normal_package, []),
        ):
            result = memory_hook_gateway.build_context_package(
                "factory", "session-start", {}
            )

        # Non-source-repo should still get normal validation flow
        # (in this test, the mock returns 'ok' with no errors, which is fine)
        assert "status" in result
        assert "validation_errors" in result

        # Verify source_repo_skip_validation is NOT set (no regression)
        system_context = result.get("system_context", {})
        assert not system_context.get("source_repo_skip_validation"), (
            "Non-source-repo should not have source_repo_skip_validation flag"
        )
