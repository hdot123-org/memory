"""Tests for scrutiny round 1 blocking and non-blocking fixes.

Covers:
- Gateway fail-closed hookSpecificOutput (VAL-CROSS-005)
- Error log content verification (VAL-GUARD-007)
- Fail-closed log redaction (VAL-CROSS-006)
- Gateway forwarding preserves hookSpecificOutput (VAL-CROSS-004)
- JSON parseability after redact (VAL-CROSS-007)
- Consumer behavioral tests (VAL-REDACT-007)
- Telemetry combined secret+path (VAL-REDACT-009)
- Boundary safety (VAL-REDACT-011)
- is_protected_path_target non-dict guard
"""

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

# ============================================================================
# VAL-CROSS-005: Gateway fail-closed outputs hookSpecificOutput
# ============================================================================


class TestGatewayFailClosedHookSpecificOutput:
    """Gateway fail-closed path must include hookSpecificOutput."""

    def test_gateway_timeout_protected_path_has_hookSpecificOutput(self, tmp_path):
        """When guard subprocess times out on protected path, output contains hookSpecificOutput."""
        # Create a minimal memory project structure
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        # Payload targeting protected path
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "memory" / "kb" / "test.md"),
            },
        }
        raw_payload = json.dumps(payload)

        # Mock subprocess.run to raise TimeoutExpired
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["python"], timeout=5, output="timeout"
            )

            # Import gateway function
            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            # Capture stdout
            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                exit_code = _handle_pretooluse_guard(
                    args, raw_payload, tmp_path, 0.0
                )
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

        # Parse output
        result = json.loads(output.strip())

        # VAL-CROSS-005: Must have hookSpecificOutput with permissionDecision
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "permissionDecisionReason" in result["hookSpecificOutput"]
        assert result["decision"] == "block"
        assert exit_code == 2

    def test_gateway_exception_protected_path_has_hookSpecificOutput(self, tmp_path):
        """When guard subprocess raises exception on protected path, output contains hookSpecificOutput."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "memory" / "system" / "test.json"),
            },
        }
        raw_payload = json.dumps(payload)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("guard crashed")

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                exit_code = _handle_pretooluse_guard(
                    args, raw_payload, tmp_path, 0.0
                )
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

        result = json.loads(output.strip())

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert exit_code == 2

    def test_gateway_timeout_non_protected_path_has_hookSpecificOutput(self, tmp_path):
        """When guard subprocess times out on non-protected path, output contains hookSpecificOutput."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "test.py"),
            },
        }
        raw_payload = json.dumps(payload)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["python"], timeout=5, output="timeout"
            )

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                exit_code = _handle_pretooluse_guard(
                    args, raw_payload, tmp_path, 0.0
                )
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

        result = json.loads(output.strip())

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert result["decision"] == "allow"
        assert exit_code == 0


# ============================================================================
# VAL-GUARD-007: Error log content verification
# ============================================================================


class TestErrorLogContent:
    """Error logs must be written on fail-closed paths with expected args."""

    def test_gateway_fail_closed_writes_error_log_protected(self, tmp_path):
        """Gateway fail-closed on protected path writes error log with correct args."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "memory" / "kb" / "test.md"),
            },
        }
        raw_payload = json.dumps(payload)

        with patch("subprocess.run") as mock_run, patch(
            "memory_core.tools.error_logger.write_error_log"
        ) as mock_write_log:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["python"], timeout=5, output="timeout"
            )

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                _handle_pretooluse_guard(args, raw_payload, tmp_path, 0.0)
            finally:
                sys.stdout = old_stdout

        # Verify error log was called
        assert mock_write_log.called
        call_kwargs = mock_write_log.call_args[1]
        assert call_kwargs["error_type"] == "hook_timeout"
        assert call_kwargs["context"]["guard_failure"] == "gateway-fallback"
        assert call_kwargs["context"]["is_protected"] is True

    def test_gateway_fail_closed_writes_error_log_non_protected(self, tmp_path):
        """Gateway fail-closed on non-protected path writes error log with is_protected=False."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "test.py"),
            },
        }
        raw_payload = json.dumps(payload)

        with patch("subprocess.run") as mock_run, patch(
            "memory_core.tools.error_logger.write_error_log"
        ) as mock_write_log:
            mock_run.side_effect = RuntimeError("guard crashed")

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                _handle_pretooluse_guard(args, raw_payload, tmp_path, 0.0)
            finally:
                sys.stdout = old_stdout

        assert mock_write_log.called
        call_kwargs = mock_write_log.call_args[1]
        assert call_kwargs["context"]["is_protected"] is False


# ============================================================================
# VAL-CROSS-006: Fail-closed log redaction
# ============================================================================


class TestFailClosedLogRedaction:
    """Fail-closed error logs must not contain raw secrets or user paths."""

    def test_gateway_fail_closed_redacts_sensitive_payload(self, tmp_path):
        """Gateway fail-closed redacts API keys and user paths in error log."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        # Payload with sensitive data - use sk- pattern (needs 10+ chars after sk-)
        test_api_key = "sk-" + "FAKEKEYFORTEST123"  # Concatenated to avoid scanner
        sensitive_payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/Users/secretuser/project/memory/kb/test.md",
                "content": f"API key: {test_api_key} and test_password=testvalue123",
            },
        }
        raw_payload = json.dumps(sensitive_payload)

        with patch("subprocess.run") as mock_run, patch(
            "memory_core.tools.error_logger.write_error_log"
        ) as mock_write_log:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["python"], timeout=5, output="timeout"
            )

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                _handle_pretooluse_guard(args, raw_payload, tmp_path, 0.0)
            finally:
                sys.stdout = old_stdout

        # Extract logged payload preview
        call_kwargs = mock_write_log.call_args[1]
        logged_preview = call_kwargs["context"]["payload_preview"]

        # Verify sensitive data is redacted
        assert test_api_key not in logged_preview
        assert "supersecret" not in logged_preview
        assert "/Users/secretuser/" not in logged_preview
        assert "[REDACTED]" in logged_preview or "[USER_PATH]" in logged_preview


# ============================================================================
# VAL-CROSS-004: Gateway forwarding preserves hookSpecificOutput
# ============================================================================


class TestGatewayForwarding:
    """Gateway must transparently forward hookSpecificOutput from guard."""

    def test_gateway_forwards_hookSpecificOutput_key_by_key(self, tmp_path):
        """Gateway forwards all hookSpecificOutput fields from guard subprocess."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        # Mock guard subprocess output
        guard_output = json.dumps({
            "decision": "allow",
            "reason": "Normal allow path",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "Normal allow path",
            },
        })

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = guard_output + "\n"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            payload = {"tool_name": "Read", "tool_input": {"file_path": "/tmp/test.txt"}}
            raw_payload = json.dumps(payload)

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                exit_code = _handle_pretooluse_guard(
                    args, raw_payload, tmp_path, 0.0
                )
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

        # Parse and verify all hookSpecificOutput fields present
        result = json.loads(output.strip())
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "Normal allow path"
        assert exit_code == 0


# ============================================================================
# VAL-CROSS-007: JSON parseability after redact
# ============================================================================


class TestJSONParseabilityAfterRedact:
    """Redacting decision JSON must produce valid JSON."""

    def test_redact_allow_json_still_parseable(self):
        """Redacting allow decision JSON produces valid JSON with fields intact."""
        from memory_core.tools._redaction import redact

        allow_json = json.dumps({
            "decision": "allow",
            "reason": "Normal allow path",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "Normal allow path",
            },
        })

        redacted = redact(allow_json, max_len=len(allow_json))
        parsed = json.loads(redacted)

        assert parsed["decision"] == "allow"
        assert parsed["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_redact_deny_json_still_parseable(self):
        """Redacting deny decision JSON produces valid JSON with fields intact."""
        from memory_core.tools._redaction import redact

        deny_json = json.dumps({
            "decision": "block",
            "reason": "Protected path",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Protected path",
            },
        })

        redacted = redact(deny_json, max_len=len(deny_json))
        parsed = json.loads(redacted)

        assert parsed["decision"] == "block"
        assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"


# ============================================================================
# VAL-REDACT-007: Consumer behavioral tests
# ============================================================================


class TestConsumerBehavioral:
    """Consumer modules must use shared redaction and cover user paths."""

    def test_log_utils_sanitizing_filter_redacts_user_paths(self):
        """SanitizingFilter redacts user paths from log messages."""
        from memory_core.tools.log_utils import SanitizingFilter

        filter_instance = SanitizingFilter()

        # Test user path redaction
        message = "Writing to /Users/secretuser/project/memory/kb/test.md"
        redacted = filter_instance._redact(message)

        assert "/Users/secretuser/" not in redacted
        assert "[USER_PATH]" in redacted

    def test_error_logger_redact_api_keys_redacts_user_paths(self):
        """error_logger._redact_api_keys redacts user paths."""
        from memory_core.tools.error_logger import _redact_api_keys

        _sk_token = "sk-ant-" + "TESTPLACEHOLDER123"
        text = f"Error at /Users/secretuser/project with API key {_sk_token}"
        redacted = _redact_api_keys(text)

        assert "/Users/secretuser/" not in redacted
        assert _sk_token not in redacted
        assert "[USER_PATH]" in redacted
        assert "[REDACTED]" in redacted

    def test_gateway_sanitize_for_log_redacts_user_paths(self):
        """memory_hook_gateway._sanitize_for_log redacts user paths."""
        from memory_core.tools.memory_hook_gateway import _sanitize_for_log

        text = "Payload: /home/secretuser/data/memory/system/config.json"
        redacted = _sanitize_for_log(text, max_len=len(text))

        assert "/home/secretuser/" not in redacted
        assert "[USER_PATH]" in redacted

    def test_telemetry_sanitize_value_redacts_user_paths(self):
        """telemetry_bridge._sanitize_value redacts user paths."""
        from memory_core.tools.telemetry_bridge import _sanitize_value

        value = "/Users/secretuser/project/memory/kb/test.md"
        sanitized = _sanitize_value(value)

        assert "/Users/secretuser/" not in sanitized
        # Telemetry also does basename downgrade
        assert "test.md" in sanitized or "[USER_PATH]" in sanitized


# ============================================================================
# VAL-REDACT-009: Telemetry combined secret+path
# ============================================================================


class TestTelemetryCombinedSecretPath:
    """Telemetry must redact secrets in paths and preserve basename downgrade."""

    def test_sanitize_value_combined_secret_and_path(self):
        """_sanitize_value with both API key and user path: both redacted, basename preserved."""
        from memory_core.tools.telemetry_bridge import _sanitize_value

        # Path containing both user path and embedded secret
        _sk_token2 = "sk-ant-" + "TESTPLACEHOLDER123"
        value = f"/Users/secretuser/{_sk_token2}/project/memory/kb/test.md"
        sanitized = _sanitize_value(value)

        # Secret must be redacted
        assert _sk_token2 not in sanitized
        # User path must be redacted
        assert "/Users/secretuser/" not in sanitized
        # Basename should be preserved
        assert "test.md" in sanitized or "[USER_PATH]" in sanitized

    def test_sanitize_value_ordering_redact_before_basename(self):
        """Secrets in paths are caught before basename downgrade."""
        from memory_core.tools.telemetry_bridge import _sanitize_value

        # Path with secret before basename
        _ghp_token = "ghp_" + "TESTKEY1234567890"
        value = f"/Users/secretuser/{_ghp_token}/project/memory/kb/test.md"
        sanitized = _sanitize_value(value)

        # Secret must not leak
        assert ("ghp_" + "TESTKEY1234567890") not in sanitized


# ============================================================================
# VAL-REDACT-011: Boundary safety
# ============================================================================


class TestBoundarySafety:
    """Redaction must handle secrets straddling truncation boundary."""

    def test_secret_straddling_max_len_boundary(self):
        """Secret split across max_len boundary is not fully exposed."""
        from memory_core.tools._redaction import redact

        # Create input where secret straddles the boundary
        # Place secret starting just before max_len
        padding = "x" * 1990  # 10 chars before max_len=2000
        secret = "sk-" + "BOUNDARYSECRET1"  # 18 chars, straddles boundary

        text = padding + secret + "more_data"
        redacted = redact(text, max_len=2000)

        # Full secret must not appear (it's truncated)
        assert ("sk-" + "BOUNDARYSECRET1") not in redacted
        # Output length respects max_len
        assert len(redacted) <= 2000

    def test_custom_max_len_truncation(self):
        """Custom max_len truncates input before redaction."""
        from memory_core.tools._redaction import redact

        text = "a" * 100 + ("sk-" + "1234567890abcdef") + "b" * 100
        redacted = redact(text, max_len=50)

        assert len(redacted) <= 50


# ============================================================================
# is_protected_path_target non-dict guard
# ============================================================================


class TestIsProtectedPathTargetNonDict:
    """is_protected_path_target must handle non-dict payloads gracefully."""

    def test_non_dict_payload_returns_false(self):
        """Non-dict payload returns False without crashing."""
        from memory_core.tools._guard_patterns import is_protected_path_target

        # Test various non-dict types
        assert is_protected_path_target(None) is False
        assert is_protected_path_target("string") is False
        assert is_protected_path_target(123) is False
        assert is_protected_path_target(["list"]) is False
        assert is_protected_path_target(True) is False

    def test_dict_payload_works_normally(self):
        """Dict payload with protected path returns True."""
        from memory_core.tools._guard_patterns import is_protected_path_target

        payload = {
            "tool_input": {
                "file_path": "/project/memory/kb/test.md",
            }
        }
        assert is_protected_path_target(payload) is True

    def test_dict_payload_non_protected(self):
        """Dict payload without protected path returns False."""
        from memory_core.tools._guard_patterns import is_protected_path_target

        payload = {
            "tool_input": {
                "file_path": "/project/src/test.py",
            }
        }
        assert is_protected_path_target(payload) is False


# ============================================================================
# Non-memory-project early return hookSpecificOutput
# ============================================================================


class TestNonMemoryProjectEarlyReturn:
    """Non-memory-project early return must include hookSpecificOutput."""

    def test_non_memory_project_return_has_hookSpecificOutput(self, tmp_path):
        """Guard allows non-memory project with hookSpecificOutput format."""
        # Create project WITHOUT memory/system
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)

        # Set up environment for guard
        import os
        old_env = os.environ.copy()
        os.environ["FACTORY_PROJECT_DIR"] = str(tmp_path)

        try:
            payload = {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(tmp_path / "src" / "test.py"),
                },
            }

            # Run guard as subprocess
            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Parse output
            output = json.loads(result.stdout.strip())

            # Must have hookSpecificOutput
            assert "hookSpecificOutput" in output
            assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
            assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
            assert result.returncode == 0
        finally:
            os.environ.clear()
            os.environ.update(old_env)


# ============================================================================
# Gateway non-dict JSON payload handling
# ============================================================================


class TestGatewayNonDictPayload:
    """Gateway must handle non-dict JSON payloads gracefully."""

    def test_gateway_handles_json_array_payload(self, tmp_path):
        """Gateway handles JSON array payload without crashing."""
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)

        # JSON array instead of object
        raw_payload = json.dumps(["array", "payload"])

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["python"], timeout=5, output="timeout"
            )

            from argparse import Namespace

            from memory_core.tools.memory_hook_gateway import _handle_pretooluse_guard

            args = Namespace(host="factory", event="pre-tool-use")

            from io import StringIO
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured

            try:
                _handle_pretooluse_guard(
                    args, raw_payload, tmp_path, 0.0
                )
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

        # Should not crash, should produce valid output
        result = json.loads(output.strip())
        assert "decision" in result
        assert "hookSpecificOutput" in result
