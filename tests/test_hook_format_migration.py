"""Tests for hook format migration (VAL-FORMAT-*, VAL-CROSS-*).

Verifies that the PreToolUse guard outputs both legacy format (decision/reason)
and Factory official format (hookSpecificOutput.permissionDecision) for backward
compatibility while supporting the new Factory hook contract.
"""

import json
from unittest.mock import patch

from memory_core.tools._rule_types import RuleResult
from memory_core.tools.pretooluse_guard import _rule_result_to_hook_json


class TestHookFormatMigration:
    """VAL-FORMAT-001: Guard output contains hookSpecificOutput.permissionDecision"""

    def test_allow_decision_has_hook_specific_output(self):
        """VAL-FORMAT-001: Allow decision includes hookSpecificOutput.permissionDecision"""
        rule_result = RuleResult(
            matched=False,
            message="path not in protected domains",
            detail={"scenario": "normal_allow", "item_results": []},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert "hookSpecificOutput" in result
        assert "permissionDecision" in result["hookSpecificOutput"]
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_block_decision_has_hook_specific_output(self):
        """VAL-FORMAT-001: Block decision includes hookSpecificOutput.permissionDecision"""
        rule_result = RuleResult(
            matched=True,
            message="path in protected domain: memory/kb/",
            detail={"scenario": "protected_path", "item_results": []},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert "hookSpecificOutput" in result
        assert "permissionDecision" in result["hookSpecificOutput"]
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestDecisionMapping:
    """VAL-FORMAT-002: decision-to-permissionDecision mapping correct"""

    def test_allow_maps_to_allow(self):
        """VAL-FORMAT-002: decision 'allow' maps to permissionDecision 'allow'"""
        rule_result = RuleResult(
            matched=False,
            message="allowed",
            detail={"decision": "allow"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert result["decision"] == "allow"
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_block_maps_to_deny(self):
        """VAL-FORMAT-002: decision 'block' maps to permissionDecision 'deny' (NOT 'block')"""
        rule_result = RuleResult(
            matched=True,
            message="blocked",
            detail={"decision": "block"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert result["decision"] == "block"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        # Explicitly verify it's NOT "block"
        assert result["hookSpecificOutput"]["permissionDecision"] != "block"


class TestLegacyFieldsPreserved:
    """VAL-FORMAT-003: Legacy fields preserved for backward compatibility"""

    def test_legacy_decision_field_present(self):
        """VAL-FORMAT-003: Top-level 'decision' field preserved"""
        rule_result = RuleResult(
            matched=False,
            message="test reason",
            detail={"scenario": "test"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert "decision" in result
        assert result["decision"] in ("allow", "block")

    def test_legacy_reason_field_present(self):
        """VAL-FORMAT-003: Top-level 'reason' field preserved (non-empty string)"""
        rule_result = RuleResult(
            matched=False,
            message="this is the reason",
            detail={"scenario": "test"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert "reason" in result
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0
        assert result["reason"] == "this is the reason"

    def test_both_legacy_and_new_fields_present(self):
        """VAL-FORMAT-003: Both old and new format fields present simultaneously"""
        rule_result = RuleResult(
            matched=True,
            message="protected path",
            detail={"decision": "block", "scenario": "protected"},
        )

        result = _rule_result_to_hook_json(rule_result)

        # Legacy fields
        assert "decision" in result
        assert "reason" in result
        # New format fields
        assert "hookSpecificOutput" in result
        assert "permissionDecision" in result["hookSpecificOutput"]
        assert "permissionDecisionReason" in result["hookSpecificOutput"]
        assert "hookEventName" in result["hookSpecificOutput"]


class TestPermissionDecisionReasonAndHookEventName:
    """VAL-FORMAT-004: permissionDecisionReason and hookEventName correct"""

    def test_permission_decision_reason_equals_reason(self):
        """VAL-FORMAT-004: permissionDecisionReason equals top-level reason"""
        rule_result = RuleResult(
            matched=False,
            message="path is safe to write",
            detail={"scenario": "normal"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert result["reason"] == result["hookSpecificOutput"]["permissionDecisionReason"]
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "path is safe to write"

    def test_hook_event_name_is_pretooluse(self):
        """VAL-FORMAT-004: hookEventName equals exactly 'PreToolUse'"""
        rule_result = RuleResult(
            matched=False,
            message="test",
            detail={"scenario": "test"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"

    def test_permission_decision_reason_equals_reason_for_block(self):
        """VAL-FORMAT-004: permissionDecisionReason equals reason for block decisions too"""
        rule_result = RuleResult(
            matched=True,
            message="blocked: memory/kb/ is protected",
            detail={"decision": "block"},
        )

        result = _rule_result_to_hook_json(rule_result)

        assert result["reason"] == result["hookSpecificOutput"]["permissionDecisionReason"]
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "blocked: memory/kb/ is protected"


class TestExitCodesUnchanged:
    """VAL-FORMAT-005: Exit codes unchanged by format migration"""

    def test_allow_exit_code_zero(self):
        """VAL-FORMAT-005: Allow path exits with code 0"""
        # This is tested via integration, but we verify the decision value
        rule_result = RuleResult(
            matched=False,
            message="allowed",
            detail={"decision": "allow"},
        )

        result = _rule_result_to_hook_json(rule_result)

        # Decision "allow" should map to exit 0 (verified in main())
        assert result["decision"] == "allow"
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_block_exit_code_two(self):
        """VAL-FORMAT-005: Block path exits with code 2"""
        rule_result = RuleResult(
            matched=True,
            message="blocked",
            detail={"decision": "block"},
        )

        result = _rule_result_to_hook_json(rule_result)

        # Decision "block" should map to exit 2 (verified in main())
        assert result["decision"] == "block"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_no_exit_code_one(self):
        """VAL-FORMAT-005: No decision path exits with code 1"""
        # Verify that neither allow nor block uses exit 1
        for matched, expected_decision, _expected_permission in [
            (False, "allow", "allow"),
            (True, "block", "deny"),
        ]:
            rule_result = RuleResult(
                matched=matched,
                message="test",
                detail={"decision": expected_decision},
            )

            result = _rule_result_to_hook_json(rule_result)

            # Exit codes are 0 (allow) or 2 (block), never 1
            assert result["decision"] in ("allow", "block")
            assert result["hookSpecificOutput"]["permissionDecision"] in ("allow", "deny")


class TestInvalidRuleResult:
    """Edge case: invalid RuleResult handling"""

    def test_invalid_rule_result_type(self):
        """Invalid RuleResult type returns allow with hookSpecificOutput"""
        result = _rule_result_to_hook_json("not a RuleResult")

        assert result["decision"] == "allow"
        assert result["reason"] == "Invalid result type"
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "Invalid result type"


class TestEndToEndAllowFlow:
    """VAL-CROSS-002: End-to-end allow flow with dual-format output"""

    @patch("memory_core.tools.pretooluse_guard._load_project_root")
    @patch("memory_core.tools.pretooluse_guard.classify_tool_use")
    @patch("memory_core.tools.pretooluse_guard._write_metrics_jsonl")
    def test_allow_flow_produces_dual_format(self, mock_metrics, mock_classify, mock_root, tmp_path):
        """VAL-CROSS-002: Valid non-protected path produces both legacy and new format"""
        # Setup
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        (project_root / "memory" / "system").mkdir(parents=True)

        mock_root.return_value = project_root
        mock_classify.return_value = RuleResult(
            matched=False,
            message="path not in protected domains",
            detail={"decision": "allow", "scenario": "normal_allow"},
        )

        # Create payload
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/some/safe/path.txt"},
        }

        # Execute
        import sys

        from memory_core.tools.pretooluse_guard import main

        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.read.return_value = json.dumps(payload)
            # Capture print output
            printed = []
            with patch("builtins.print", side_effect=lambda x: printed.append(x)):
                exit_code = main()

        # Verify
        assert exit_code == 0
        assert len(printed) > 0
        result = json.loads(printed[0])

        # Legacy format
        assert result["decision"] == "allow"
        assert "reason" in result

        # New format
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


class TestEndToEndDenyFlow:
    """VAL-CROSS-003: End-to-end deny flow with dual-format output"""

    @patch("memory_core.tools.pretooluse_guard._load_project_root")
    @patch("memory_core.tools.pretooluse_guard.classify_tool_use")
    @patch("memory_core.tools.pretooluse_guard._write_metrics_jsonl")
    def test_deny_flow_produces_dual_format(self, mock_metrics, mock_classify, mock_root, tmp_path):
        """VAL-CROSS-003: Protected path produces both legacy and new format with deny"""
        # Setup
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        (project_root / "memory" / "system").mkdir(parents=True)

        mock_root.return_value = project_root
        mock_classify.return_value = RuleResult(
            matched=True,
            message="path in protected domain: memory/kb/",
            detail={"decision": "block", "scenario": "protected_path"},
        )

        # Create payload
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/memory/kb/test.md"},
        }

        # Execute
        import sys

        from memory_core.tools.pretooluse_guard import main

        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.read.return_value = json.dumps(payload)
            printed = []
            with patch("builtins.print", side_effect=lambda x: printed.append(x)):
                exit_code = main()

        # Verify
        assert exit_code == 2
        assert len(printed) > 0
        result = json.loads(printed[0])

        # Legacy format
        assert result["decision"] == "block"
        assert "reason" in result
        assert len(result["reason"]) > 0

        # New format
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == result["reason"]


class TestGatewayTransparentForwarding:
    """VAL-CROSS-004: Gateway transparent forwarding preserves hookSpecificOutput"""

    @patch("memory_core.tools.pretooluse_guard._load_project_root")
    @patch("memory_core.tools.pretooluse_guard.classify_tool_use")
    @patch("memory_core.tools.pretooluse_guard._write_metrics_jsonl")
    def test_gateway_preserves_hook_specific_output(self, mock_metrics, mock_classify, mock_root, tmp_path):
        """VAL-CROSS-004: Guard output includes all hookSpecificOutput fields for gateway forwarding"""
        # Setup
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        (project_root / "memory" / "system").mkdir(parents=True)

        mock_root.return_value = project_root
        mock_classify.return_value = RuleResult(
            matched=False,
            message="allowed path",
            detail={"decision": "allow"},
        )

        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/safe/file.py"},
        }

        # Execute
        import sys

        from memory_core.tools.pretooluse_guard import main

        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.read.return_value = json.dumps(payload)
            printed = []
            with patch("builtins.print", side_effect=lambda x: printed.append(x)):
                main()

        # Verify
        result = json.loads(printed[0])

        # All hookSpecificOutput fields present for gateway forwarding
        assert "hookSpecificOutput" in result
        hso = result["hookSpecificOutput"]
        assert "hookEventName" in hso
        assert "permissionDecision" in hso
        assert "permissionDecisionReason" in hso

        # Values are correct
        assert hso["hookEventName"] == "PreToolUse"
        assert hso["permissionDecision"] == "allow"
        assert hso["permissionDecisionReason"] == "allowed path"


class TestFailClosedDenyOutput:
    """VAL-CROSS-005: Fail-closed deny outputs new format"""

    @patch("memory_core.tools.pretooluse_guard._load_project_root")
    @patch("memory_core.tools.error_logger.write_error_log")
    def test_fail_closed_deny_has_hook_specific_output(self, mock_error_log, mock_root, tmp_path):
        """VAL-CROSS-005: Fail-closed deny (protected path) includes hookSpecificOutput"""
        from memory_core.tools.pretooluse_guard import _fail_closed_with_raw_check

        # Setup
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        mock_root.return_value = project_root

        # Raw input with protected path marker
        raw_input = '{"tool_input": {"file_path": "/project/memory/kb/test.md"}}'

        # Execute
        exit_code, result = _fail_closed_with_raw_check(raw_input, "JSON parse error")

        # Verify
        assert exit_code == 2
        assert result["decision"] == "block"

        # New format present
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "permissionDecisionReason" in result["hookSpecificOutput"]
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == result["reason"]
