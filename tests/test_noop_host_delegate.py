"""Tests for NoopHostDelegate and resolve_host_delegate."""

from unittest.mock import patch

from memory_core.tools.memory_hook_impls import (
    ClaudeDelegate,
    CodexDelegate,
    NoopHostDelegate,
    resolve_host_delegate,
)

# ---------------------------------------------------------------------------
# NoopHostDelegate
# ---------------------------------------------------------------------------

class TestNoopHostDelegate:
    def test_can_handle_always_true(self):
        d = NoopHostDelegate()
        assert d.can_handle() is True

    def test_execute_returns_noop(self):
        d = NoopHostDelegate()
        result = d.execute("test-event", "{}", {})
        assert result.returncode == 0
        assert result.stdout == "{}\n"
        assert result.stderr == ""

    def test_noop_response_returns_noop(self):
        d = NoopHostDelegate()
        result = d.noop_response()
        assert result.returncode == 0
        assert result.stdout == "{}\n"
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# resolve_host_delegate — mode="noop"
# ---------------------------------------------------------------------------

class TestResolveNoopMode:
    def test_noop_mode_codex_host(self):
        d = resolve_host_delegate("codex", mode="noop")
        assert isinstance(d, NoopHostDelegate)

    def test_noop_mode_claude_host(self):
        d = resolve_host_delegate("claude", mode="noop")
        assert isinstance(d, NoopHostDelegate)


# ---------------------------------------------------------------------------
# resolve_host_delegate — mode="cmux"
# ---------------------------------------------------------------------------

class TestResolveCmuxMode:
    def test_cmux_mode_codex_host(self):
        d = resolve_host_delegate("codex", mode="cmux")
        assert isinstance(d, CodexDelegate)

    def test_cmux_mode_claude_host(self):
        d = resolve_host_delegate("claude", mode="cmux")
        assert isinstance(d, ClaudeDelegate)


# ---------------------------------------------------------------------------
# resolve_host_delegate — mode="auto" fallback
# ---------------------------------------------------------------------------

class TestResolveAutoMode:
    @patch("shutil.which", return_value=None)
    def test_auto_fallback_when_cmux_unavailable_codex(self, _mock_which):
        d = resolve_host_delegate("codex", mode="auto")
        assert isinstance(d, NoopHostDelegate)

    @patch("shutil.which", return_value=None)
    def test_auto_fallback_when_cmux_unavailable_claude(self, _mock_which):
        d = resolve_host_delegate("claude", mode="auto")
        assert isinstance(d, NoopHostDelegate)


# ---------------------------------------------------------------------------
# resolve_host_delegate — unknown host
# ---------------------------------------------------------------------------

class TestResolveUnknownHost:
    def test_unknown_host_returns_noop(self):
        d = resolve_host_delegate("unknown", mode="auto")
        assert isinstance(d, NoopHostDelegate)

    def test_unknown_host_noop_mode(self):
        d = resolve_host_delegate("other", mode="noop")
        assert isinstance(d, NoopHostDelegate)

    def test_unknown_host_cmux_mode(self):
        d = resolve_host_delegate("other", mode="cmux")
        assert isinstance(d, NoopHostDelegate)
