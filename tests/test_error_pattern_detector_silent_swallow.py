"""Regression tests for silent exception swallow fixes in error_pattern_detector.py (INFRA-261).

Two findings in ``run_pipeline`` and ``main`` used bare ``except Exception: pass``
to swallow failures of the inner ``write_error_log()`` call with zero observability.

Fix: each except clause now binds the exception (``except Exception as exc:``) and
logs it via ``logger.debug(...)``, providing observability while preserving the
original graceful-degradation behavior (continue / exit).

Static code-inspection tests following the established pattern in
``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "error_pattern_detector.py"


class TestRunPipelineSilentSwallow:
    """``run_pipeline`` inner write_error_log failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "run_pipeline")
        assert "except Exception as exc:" in body, (
            "run_pipeline write_error_log except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "run_pipeline")
        assert "write_error_log failed" in body and "logger.debug" in body, (
            "run_pipeline except block must call logger.debug with a descriptive message"
        )


class TestMainSilentSwallow:
    """``main`` inner write_error_log failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "main")
        assert "except Exception as exc:" in body, "main write_error_log except must bind the exception as `exc`"

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "main")
        assert "write_error_log failed" in body and "logger.debug" in body, (
            "main except block must call logger.debug with a descriptive message"
        )


class TestNoBareSilentSwallow:
    """No bare ``except Exception: pass`` swallow remains in error_pattern_detector.py."""

    def test_no_bare_pass(self):
        content = SOURCE_PATH.read_text()
        assert "except Exception:\n                pass" not in content, (
            "error_pattern_detector.py must not regress to bare `except Exception: pass`"
        )
        assert "except Exception:\n                    pass" not in content, (
            "error_pattern_detector.py must not regress to bare `except Exception: pass`"
        )
