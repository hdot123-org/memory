"""Regression tests for silent exception swallow fixes in memory_hook_gateway.py (INFRA-261).

``_gateway_excepthook`` and ``_handle_pretooluse_guard`` used bare
``except Exception: pass`` to swallow best-effort logging/metrics failures.

Fix: each except clause now binds the exception and logs it via ``_logger.debug(...)``,
preserving the original graceful-degradation behavior.

Static code-inspection tests following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "memory_hook_gateway.py"


class TestGatewayExcepthookSilentSwallow:
    """``_gateway_excepthook`` metrics-write failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_gateway_excepthook")
        assert "except Exception as exc:" in body, (
            "_gateway_excepthook except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_gateway_excepthook")
        assert "metrics write failed" in body and "_logger.debug" in body


class TestHandlePretooluseGuardSilentSwallow:
    """``_handle_pretooluse_guard`` error-logging failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_handle_pretooluse_guard")
        assert "except Exception as exc:" in body, (
            "_handle_pretooluse_guard except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_handle_pretooluse_guard")
        assert "error logging failed" in body and "_logger.debug" in body


class TestNoBareSilentSwallow:
    """No bare ``except Exception: pass`` swallow remains in the two guard functions."""

    def test_excepthook_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_gateway_excepthook")
        assert "except Exception:\n        pass" not in body, (
            "_gateway_excepthook must not regress to bare `except Exception: pass`"
        )

    def test_pretooluse_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_handle_pretooluse_guard")
        assert "except Exception:\n        pass" not in body, (
            "_handle_pretooluse_guard must not regress to bare `except Exception: pass`"
        )
