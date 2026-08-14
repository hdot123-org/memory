"""Regression test for silent exception swallow fix in pretooluse_guard.py (INFRA-261).

``_fail_closed_with_raw_check`` used bare ``except Exception: pass`` to swallow a
best-effort partial-JSON parse with zero observability.

Fix: the except clause now binds the exception and logs it via ``_logger.debug(...)``,
preserving the original behavior (the parse result was never consumed; the
``is_protected`` decision is unaffected).

Static code-inspection test following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "pretooluse_guard.py"


class TestFailClosedWithRawCheckSilentSwallow:
    """``_fail_closed_with_raw_check`` JSON-parse failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_fail_closed_with_raw_check")
        assert "except Exception as exc:" in body, (
            "_fail_closed_with_raw_check except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_fail_closed_with_raw_check")
        assert "JSON parse best-effort failed" in body and "_logger.debug" in body

    def test_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_fail_closed_with_raw_check")
        assert "except Exception:\n            pass" not in body, (
            "_fail_closed_with_raw_check must not regress to bare `except Exception: pass`"
        )
