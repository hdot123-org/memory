"""Tests for _build_factory_hook_output: Factory JSON Output format.

Validates VAL-OUTPUT-001 through VAL-OUTPUT-009, VAL-NOREGRESS-001..004,
VAL-GATE-001..004.
"""

import json

import pytest


@pytest.fixture()
def gw():
    """Import gateway module."""
    from memory_core.tools import memory_hook_gateway as gw_mod
    return gw_mod


def _sample_package(**overrides):
    """Build a realistic context-package for testing."""
    pkg = {
        "package_kind": "context-package",
        "host": "factory",
        "event": "session-start",
        "status": "ok",
        "missing_paths": [],
        "validation_errors": [],
        "allowed_reads": [
            "/project/memory/kb/INDEX.md",
            "/project/memory/docs/INDEX.md",
            "/home/.memory/global-kb/INDEX.md",
        ],
        "allowed_writes": {
            "decision": "/project/memory/kb/decisions",
            "lesson": "/project/memory/kb/lessons",
            "docs": "/project/memory/docs",
        },
        "system_context": {
            "registration_commit_gate": {"phase": "declared-not-enforced"},
            "policy_pack": {"schema_version": "m3-policy-pack-v1"},
            "project_lifecycle": {"status": "active"},
            "truth_basis_errors": ["some error"],
            "core_provider": "legacy",
        },
        "artifact_refs": {
            "snapshot": "/artifacts/snapshot.json",
            "latest": "/artifacts/latest.json",
        },
        "evidence_refs": ["/project/memory/kb/global/memory-system.md"],
    }
    pkg.update(overrides)
    return pkg


# ===========================================================================
# VAL-OUTPUT-001: session-start outputs Factory JSON Output format
# ===========================================================================

class TestSessionStartOutputFormat:
    """session-start must output hookSpecificOutput with SessionStart."""

    def test_session_start_has_hook_specific_output(self, gw):
        """Output contains hookSpecificOutput with hookEventName='SessionStart'."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_session_start_additional_context_nonempty(self, gw):
        """additionalContext is non-empty string."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert isinstance(ctx, str)
        assert len(ctx) > 0


# ===========================================================================
# VAL-OUTPUT-002: prompt-submit outputs Factory JSON Output format
# ===========================================================================

class TestPromptSubmitOutputFormat:
    """prompt-submit must output hookSpecificOutput with UserPromptSubmit."""

    def test_prompt_submit_has_hook_specific_output(self, gw):
        """Output contains hookSpecificOutput with hookEventName='UserPromptSubmit'."""
        package = _sample_package(event="prompt-submit")
        result = json.loads(gw._build_factory_hook_output(package, "prompt-submit"))
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"

    def test_prompt_submit_additional_context_nonempty(self, gw):
        """additionalContext is non-empty string."""
        package = _sample_package(event="prompt-submit")
        result = json.loads(gw._build_factory_hook_output(package, "prompt-submit"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert isinstance(ctx, str)
        assert len(ctx) > 0


# ===========================================================================
# VAL-OUTPUT-003: additionalContext contains allowed_reads
# ===========================================================================

class TestAdditionalContextAllowedReads:
    """additionalContext must contain Allowed Reads section."""

    def test_contains_allowed_reads_section(self, gw):
        """additionalContext contains 'Allowed Reads' heading."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "Allowed Reads" in ctx

    def test_contains_read_paths(self, gw):
        """additionalContext contains at least one read path."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "memory/kb/INDEX.md" in ctx


# ===========================================================================
# VAL-OUTPUT-004: additionalContext contains allowed_writes
# ===========================================================================

class TestAdditionalContextAllowedWrites:
    """additionalContext must contain Allowed Writes section."""

    def test_contains_allowed_writes_section(self, gw):
        """additionalContext contains 'Allowed Writes' heading."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "Allowed Writes" in ctx

    def test_contains_write_paths(self, gw):
        """additionalContext contains write target paths."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "decisions" in ctx


# ===========================================================================
# VAL-OUTPUT-004b: dict-valued allowed_writes (e.g. kb_policy) render as nested sub-items
# ===========================================================================

class TestAdditionalContextDictWrites:
    """Dict-valued writes must render as nested sub-items, not dict repr."""

    def test_dict_value_renders_as_subitems(self, gw):
        """kb_policy dict renders each key as an indented sub-item."""
        aw = {
            "fact": "/project/memory/log/2026-07-22.md",
            "kb_policy": {
                "mode": "read-first-CRUD",
                "overwrite_allowed": False,
                "conflict_strategy": "preserve-and-escalate",
            },
        }
        package = _sample_package(**{"allowed_writes": aw})
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        # Dict repr must NOT leak into output
        assert "{'mode':" not in ctx
        # Each sub-key appears as its own line
        assert "mode: read-first-CRUD" in ctx
        assert "overwrite_allowed: False" in ctx
        assert "conflict_strategy: preserve-and-escalate" in ctx

    def test_string_value_still_renders_inline(self, gw):
        """Non-dict (string) values still render inline as before."""
        aw = {"decision": "/project/memory/kb/decisions"}
        package = _sample_package(**{"allowed_writes": aw})
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "- decision: /project/memory/kb/decisions" in ctx


# ===========================================================================
# VAL-OUTPUT-005: additionalContext omits internal metadata
# ===========================================================================

class TestAdditionalContextOmitsMetadata:
    """additionalContext must NOT contain internal metadata fields."""

    def test_omits_registration_commit_gate(self, gw):
        """additionalContext does not contain registration_commit_gate."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "registration_commit_gate" not in ctx

    def test_omits_policy_pack(self, gw):
        """additionalContext does not contain policy_pack."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "policy_pack" not in ctx

    def test_omits_project_lifecycle(self, gw):
        """additionalContext does not contain project_lifecycle."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "project_lifecycle" not in ctx

    def test_omits_artifact_refs(self, gw):
        """additionalContext does not contain artifact_refs."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "artifact_refs" not in ctx

    def test_omits_truth_basis_errors(self, gw):
        """additionalContext does not contain truth_basis_errors."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "truth_basis_errors" not in ctx


# ===========================================================================
# VAL-OUTPUT-006: suppressOutput is true
# ===========================================================================

class TestSuppressOutput:
    """Output must contain suppressOutput: true."""

    def test_suppress_output_true(self, gw):
        """suppressOutput is true in output JSON."""
        package = _sample_package()
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        assert result.get("suppressOutput") is True


# ===========================================================================
# VAL-OUTPUT-007: non-injection events output empty JSON
# ===========================================================================

class TestNonInjectionEventsEmpty:
    """Non-injection events must output {}."""

    @pytest.mark.parametrize("event", [
        "stop", "notification", "pre-compact", "session-end",
        "post-tool-use", "subagent-stop",
    ])
    def test_non_injection_events_output_empty(self, gw, event):
        """Non-injection events output {}."""
        package = _sample_package(event=event)
        result = json.loads(gw._build_factory_hook_output(package, event))
        assert result == {}


# ===========================================================================
# VAL-OUTPUT-008: validation_errors included only when non-empty
# ===========================================================================

class TestValidationErrorsConditional:
    """Validation Warnings section appears only when validation_errors is non-empty."""

    def test_empty_errors_omits_validation_warnings(self, gw):
        """Empty validation_errors omits Validation Warnings section."""
        package = _sample_package(validation_errors=[])
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "Validation Warnings" not in ctx

    def test_nonempty_errors_includes_validation_warnings(self, gw):
        """Non-empty validation_errors includes Validation Warnings section."""
        package = _sample_package(validation_errors=["missing canonical path"])
        result = json.loads(gw._build_factory_hook_output(package, "session-start"))
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "Validation Warnings" in ctx
        assert "missing canonical path" in ctx


# ===========================================================================
# VAL-OUTPUT-009: output size significantly smaller than full package
# ===========================================================================

class TestOutputSizeSmaller:
    """Output must be < 50% of full package size."""

    def test_output_size_under_50_percent(self, gw):
        """Factory hook output is significantly smaller than full package."""
        package = _sample_package()
        factory_output = gw._build_factory_hook_output(package, "session-start")
        full_package_json = json.dumps(package, ensure_ascii=False)
        assert len(factory_output) < len(full_package_json) * 0.5


# ===========================================================================
# VAL-NOREGRESS-001: PreToolUse guard unaffected
# ===========================================================================

class TestPreToolUseUnaffected:
    """PreToolUse events still return via _handle_pretooluse_guard."""

    def test_pretooluse_guard_called_before_execute_delegate(self, gw):
        """_handle_pretooluse_guard is called before _execute_delegate in main()."""
        import inspect
        source = inspect.getsource(gw.main)
        guard_pos = source.find("_handle_pretooluse_guard")
        dispatch_pos = source.find("_dispatch_output")
        assert guard_pos != -1
        assert dispatch_pos != -1
        assert guard_pos < dispatch_pos


# ===========================================================================
# VAL-NOREGRESS-003: --no-delegate mode still outputs full package
# ===========================================================================

class TestNoDelegateUnaffected:
    """--no-delegate branch still outputs complete package JSON."""

    def test_no_delegate_outputs_full_package(self, gw, tmp_path, capsys):
        """--no-delegate stdout is full context-package JSON."""
        import argparse
        args = argparse.Namespace(host="factory", event="session-start", no_delegate=True)
        package = _sample_package()

        gw._dispatch_output(args, package, "{}", {}, tmp_path, 0)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output == package
        assert "allowed_reads" in output


# ===========================================================================
# Integration: _execute_delegate uses _build_factory_hook_output for Factory
# ===========================================================================

class TestExecuteDelegateIntegration:
    """_execute_delegate Factory branch uses _build_factory_hook_output."""

    def test_factory_session_start_uses_hook_output(self, gw, tmp_path, capsys, monkeypatch):
        """Factory host session-start outputs Factory JSON Output format."""
        import argparse
        from unittest.mock import MagicMock
        args = argparse.Namespace(host="factory", event="session-start")
        package = _sample_package()

        mock_delegate = MagicMock()
        monkeypatch.setattr(gw, "_get_host_delegate", lambda h: mock_delegate)

        gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert output.get("suppressOutput") is True

    def test_factory_stop_outputs_empty(self, gw, tmp_path, capsys, monkeypatch):
        """Factory host stop event outputs {}."""
        import argparse
        from unittest.mock import MagicMock
        args = argparse.Namespace(host="factory", event="stop")
        package = _sample_package(event="stop")

        mock_delegate = MagicMock()
        monkeypatch.setattr(gw, "_get_host_delegate", lambda h: mock_delegate)

        gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output == {}

    def test_factory_prompt_submit_uses_hook_output(self, gw, tmp_path, capsys, monkeypatch):
        """Factory host prompt-submit outputs Factory JSON Output format."""
        import argparse
        from unittest.mock import MagicMock
        args = argparse.Namespace(host="factory", event="prompt-submit")
        package = _sample_package(event="prompt-submit")

        mock_delegate = MagicMock()
        monkeypatch.setattr(gw, "_get_host_delegate", lambda h: mock_delegate)

        gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
