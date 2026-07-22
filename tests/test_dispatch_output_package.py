"""Tests for fix-dispatch-output: Factory host emits full context-package.

Validates VAL-TRANSPORT-001 through VAL-TRANSPORT-008:
- _execute_delegate accepts package parameter
- _dispatch_output forwards package to _execute_delegate
- Factory host (proc=None) outputs json.dumps(package) instead of {}
- PreToolUse/source-repo/degraded/--no-delegate paths unchanged
"""

import argparse
import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def gw():
    """Import gateway module."""
    from memory_core.tools import memory_hook_gateway as gw_mod
    return gw_mod


# ===========================================================================
# VAL-TRANSPORT-007: _execute_delegate signature accepts package parameter
# ===========================================================================

class TestExecuteDelegateSignature:
    """_execute_delegate must accept package as a parameter."""

    def test_execute_delegate_accepts_package(self, gw):
        """_execute_delegate signature includes package parameter."""
        import inspect
        sig = inspect.signature(gw._execute_delegate)
        assert "package" in sig.parameters, (
            "_execute_delegate must accept 'package' parameter"
        )


# ===========================================================================
# VAL-TRANSPORT-001: Factory host session-start emits non-empty context-package
# ===========================================================================

class TestFactoryHostOutputsPackage:
    """Factory host (proc=None) outputs Factory JSON Output format."""

    def test_factory_host_outputs_full_package(self, gw, tmp_path, capsys):
        """Factory host session-start outputs Factory JSON Output with allowed_reads."""
        args = argparse.Namespace(host="factory", event="session-start")
        package = {
            "package_kind": "context-package",
            "allowed_reads": ["/home/user/.memory/global-kb/operations"],
            "system_context": {"project": "test"},
        }

        # Mock _get_host_delegate - not used for factory (proc=None path)
        mock_delegate = MagicMock()
        gw._get_host_delegate = lambda h: mock_delegate  # type: ignore[attr-defined]

        exit_code = gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        # Factory JSON Output format
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Allowed Reads" in ctx
        assert "/home/user/.memory/global-kb/operations" in ctx

    def test_factory_host_not_empty_json(self, gw, tmp_path, capsys):
        """Output is not {} for Factory host when package has content."""
        args = argparse.Namespace(host="factory", event="prompt-submit")
        package = {
            "package_kind": "context-package",
            "system_context": {"key": "value"},
            "allowed_reads": ["/a", "/b"],
        }

        mock_delegate = MagicMock()
        gw._get_host_delegate = lambda h: mock_delegate  # type: ignore[attr-defined]

        gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output != {}
        assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"

    def test_factory_host_allowed_reads_nonempty(self, gw, tmp_path, capsys):
        """Factory host session-start outputs non-empty allowed_reads in additionalContext."""
        args = argparse.Namespace(host="factory", event="session-start")
        package = {
            "package_kind": "context-package",
            "allowed_reads": [
                "/home/.memory/global-kb/operations",
                "/home/.memory/global-kb/engineering",
                "/home/.memory/global-kb/infra",
            ],
        }

        mock_delegate = MagicMock()
        gw._get_host_delegate = lambda h: mock_delegate  # type: ignore[attr-defined]

        gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "global-kb/infra" in ctx


# ===========================================================================
# VAL-TRANSPORT-003: PreToolUse guard path NOT affected
# ===========================================================================

class TestPreToolUseUnaffected:
    """PreToolUse events return via _handle_pretooluse_guard, never reaching _execute_delegate."""

    def test_pretooluse_guard_returns_before_execute_delegate(self, gw):
        """_handle_pretooluse_guard is called before _execute_delegate in main()."""
        import inspect
        source = inspect.getsource(gw.main)
        # _handle_pretooluse_guard must appear before _dispatch_output/_execute_delegate
        guard_pos = source.find("_handle_pretooluse_guard")
        dispatch_pos = source.find("_dispatch_output")
        assert guard_pos != -1, "_handle_pretooluse_guard must be in main()"
        assert dispatch_pos != -1, "_dispatch_output must be in main()"
        assert guard_pos < dispatch_pos, (
            "_handle_pretooluse_guard must be called before _dispatch_output"
        )


# ===========================================================================
# VAL-TRANSPORT-005: Degraded/error path NOT affected
# ===========================================================================

class TestDegradedPathUnaffected:
    """When delegate preflight raises RuntimeError, degraded package is emitted."""

    def test_degraded_package_on_preflight_error(self, gw, tmp_path, capsys, monkeypatch):
        """RuntimeError in delegate preflight emits degraded package directly."""
        args = argparse.Namespace(host="codex", event="session-start")

        def failing_delegate(event, raw_payload):
            raise RuntimeError("preflight failed")

        monkeypatch.setattr(gw, "_delegate_codex", failing_delegate)

        package = {"package_kind": "context-package", "allowed_reads": []}
        exit_code = gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output.get("status") == "degraded" or "error" in output
        assert exit_code == 0


# ===========================================================================
# VAL-TRANSPORT-006: --no-delegate mode still outputs complete package
# ===========================================================================

class TestNoDelegateUnaffected:
    """--no-delegate branch already outputs full package. Must remain unchanged."""

    def test_no_delegate_outputs_full_package(self, gw, tmp_path, capsys):
        """--no-delegate branch outputs json.dumps(package) directly."""
        args = argparse.Namespace(host="factory", event="session-start", no_delegate=True)
        package = {
            "package_kind": "context-package",
            "allowed_reads": ["/a", "/b"],
            "system_context": {"key": "value"},
        }

        gw._dispatch_output(args, package, "{}", {}, tmp_path, 0)

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output == package
        assert "allowed_reads" in output


# ===========================================================================
# VAL-TRANSPORT-007: _dispatch_output forwards package to _execute_delegate
# ===========================================================================

class TestDispatchOutputForwardsPackage:
    """_dispatch_output must pass package to _execute_delegate."""

    def test_dispatch_output_forwards_package(self, gw, tmp_path, capsys, monkeypatch):
        """_dispatch_output passes package to _execute_delegate."""
        args = argparse.Namespace(host="factory", event="session-start", no_delegate=False)
        package = {
            "package_kind": "context-package",
            "allowed_reads": ["/test"],
        }

        captured_package = {}

        original_execute = gw._execute_delegate

        def spy_execute(a, raw, payload, cwd, package=None):
            captured_package.update(package or {})
            # Call the real function
            return original_execute(a, raw, payload, cwd, package=package)

        monkeypatch.setattr(gw, "_execute_delegate", spy_execute)

        gw._dispatch_output(args, package, "{}", {}, tmp_path, 0)

        assert captured_package == package


# ===========================================================================
# VAL-TRANSPORT-008: Real delegate subprocess branch NOT affected
# ===========================================================================

class TestRealDelegateUnaffected:
    """When proc is not None (codex/claude delegate), behavior is unchanged."""

    def test_codex_delegate_stdout_forwarded(self, gw, tmp_path, capsys, monkeypatch):
        """codex delegate stdout is forwarded as before."""
        args = argparse.Namespace(host="codex", event="session-start")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"delegate": "result"}\n'
        mock_proc.stderr = ""

        monkeypatch.setattr(gw, "_delegate_codex", lambda event, raw: mock_proc)

        package = {"package_kind": "context-package"}
        exit_code = gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        assert '{"delegate": "result"}' in captured.out
        assert exit_code == 0

    def test_claude_delegate_stdout_forwarded(self, gw, tmp_path, capsys, monkeypatch):
        """claude delegate stdout is forwarded as before."""
        args = argparse.Namespace(host="claude", event="session-start")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"claude": "response"}\n'
        mock_proc.stderr = ""

        monkeypatch.setattr(
            gw, "_delegate_claude", lambda event, raw, payload: mock_proc
        )

        package = {"package_kind": "context-package"}
        exit_code = gw._execute_delegate(args, "{}", {}, tmp_path, package=package)

        captured = capsys.readouterr()
        assert '{"claude": "response"}' in captured.out
        assert exit_code == 0
