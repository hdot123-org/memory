"""Regression tests for silent exception swallow fix in error_logger.py (INFRA-260).

Bug: In `_try_sign_file`, the signing failure block used a bare
``except Exception: pass``, silently swallowing signing failures with zero
observability.

Fix (INFRA-260/PR #596 upgraded): The except clause now binds the exception
(``except Exception as exc:``) and logs it via ``logger.warning(...)``, with
a stderr fallback when logging itself fails. The function still does not
re-raise, preserving graceful degradation. Matches the pattern established
in daily_summary_generator.py::_try_sign_file (INFRA-244/PR #575).

These are code-inspection tests (NOT runtime tests) following the pattern in
``tests/test_telemetry_bridge_silent_swallow.py`` and
``tests/test_session_end_logger_silent_swallow.py``:
read the source, slice the relevant function, and assert the observability
call is present. The except block lives in a signing path that is hard to
trigger reliably in tests, so static inspection is the appropriate guard.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
ERROR_LOGGER_PATH = REPO_ROOT / "memory_core" / "tools" / "error_logger.py"


class TestTrySignFileSilentSwallow:
    """Regression guard: ``_try_sign_file`` signing failure must log at warning (INFRA-260).

    Before the fix the signing except was ``except Exception: pass``,
    hiding signing failures with zero observability. The fix binds the
    exception and logs it via logger.warning with stderr fallback, matching
    the pattern in daily_summary_generator.py::_try_sign_file (PR #575).
    """

    def test_except_block_binds_exception(self):
        """The signing except clause must bind the exception (``except Exception as exc:``)."""
        content = ERROR_LOGGER_PATH.read_text()
        body = _func_body(content, "_try_sign_file")
        assert "except Exception as exc:" in body, (
            "_try_sign_file except must bind the exception as `exc` "
            "so it can be included in the log message — a bare `except Exception: pass` "
            "silently swallows signing failures"
        )

    def test_except_block_logs_with_logger_warning(self):
        """The except block must call logger.warning with the exception message."""
        content = ERROR_LOGGER_PATH.read_text()
        body = _func_body(content, "_try_sign_file")
        assert "logger.warning" in body, (
            "_try_sign_file except block must call logger.warning — "
            "bare pass silently swallows signing failures"
        )
        assert "sign_project_incremental failed" in body, (
            "logger.warning must include descriptive message about signing failure"
        )

    def test_except_block_has_stderr_fallback(self):
        """The except block must have a stderr fallback when logging itself fails."""
        content = ERROR_LOGGER_PATH.read_text()
        body = _func_body(content, "_try_sign_file")
        assert "sys.stderr" in body, (
            "_try_sign_file except block must have a stderr fallback for when "
            "logging itself fails"
        )

    def test_no_bare_pass(self):
        """The function must not contain a bare ``except Exception: pass`` swallow."""
        content = ERROR_LOGGER_PATH.read_text()
        body = _func_body(content, "_try_sign_file")
        assert "except Exception:\n        pass" not in body, (
            "_try_sign_file must not regress to bare `except Exception: pass`"
        )

    def test_function_does_not_reraise(self):
        """The function must not re-raise the exception (graceful degradation preserved)."""
        content = ERROR_LOGGER_PATH.read_text()
        body = _func_body(content, "_try_sign_file")
        assert "raise" not in body, (
            "_try_sign_file must not re-raise — signing failure must not block main flow"
        )
