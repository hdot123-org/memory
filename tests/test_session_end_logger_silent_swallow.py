"""Regression test for silent exception swallow fix in session_end_logger.py (INFRA-261).

``_write_session_metrics`` used bare ``except Exception: pass`` to swallow metrics-write
failures with zero observability.

Fix: the except clause now binds the exception and logs it via ``logger.debug(...)``,
preserving the graceful-degradation behavior (function returns None; metrics not written;
calling hook continues).

Static code-inspection test following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "session_end_logger.py"


class TestWriteSessionMetricsSilentSwallow:
    """``_write_session_metrics`` metrics-write failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_write_session_metrics")
        assert "except Exception as exc:" in body, "_write_session_metrics except must bind the exception as `exc`"

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_write_session_metrics")
        assert "metrics write failed" in body and "logger.debug" in body

    def test_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_write_session_metrics")
        assert "except Exception:\n        pass" not in body, (
            "_write_session_metrics must not regress to bare `except Exception: pass`"
        )
