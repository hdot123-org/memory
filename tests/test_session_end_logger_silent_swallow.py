"""Regression tests for silent exception swallow fixes in session_end_logger.py.

Covers two SILENT_SWALLOW fixes:

- INFRA-261: ``_write_session_metrics`` used bare ``except Exception: pass`` to swallow
  metrics-write failures with zero observability. Fix: the except clause now binds the
  exception and logs it via ``logger.debug(...)``, preserving the graceful-degradation
  behavior (function returns None; metrics not written; calling hook continues).

- INFRA-1042 (Issue #1255): ``_resolve_project_root`` used bare ``except Exception: pass``
  to swallow gateway root-resolution failures. Fix: the except clause now logs the
  fallback reason and full traceback via ``logger.debug(..., exc_info=True)``, preserving
  the fallback behavior (returns ``payload_cwd.expanduser().resolve()``).
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


class TestResolveProjectRootSilentSwallow:
    """``_resolve_project_root`` gateway-resolution failure must log at debug (INFRA-1042)."""

    def test_gateway_failure_falls_back_to_payload_cwd(self, monkeypatch, tmp_path):
        """Fallback behavior unchanged: gateway failure returns resolved payload cwd."""
        from memory_core.tools import session_end_logger

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated gateway failure")

        monkeypatch.setattr(session_end_logger, "_gateway_resolve_root", _boom)

        result = session_end_logger._resolve_project_root(tmp_path, {})

        assert result == tmp_path.expanduser().resolve()

    def test_gateway_failure_logs_debug_record(self, monkeypatch, tmp_path, caplog):
        """The previously-swallowed gateway failure must now emit a debug log record."""
        from memory_core.tools import session_end_logger

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated gateway failure")

        monkeypatch.setattr(session_end_logger, "_gateway_resolve_root", _boom)

        with caplog.at_level("DEBUG", logger="memory_core.tools.session_end_logger"):
            session_end_logger._resolve_project_root(tmp_path, {})

        debug_records = [
            r for r in caplog.records if r.levelname == "DEBUG" and "gateway root resolution failed" in r.message
        ]
        assert debug_records, "expected a DEBUG log record for the swallowed gateway failure"
        assert any("falling back to payload_cwd" in r.message for r in debug_records)
        assert any(r.exc_info is not None for r in debug_records)

    def test_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_resolve_project_root")
        assert "except Exception:\n        pass" not in body, (
            "_resolve_project_root must not regress to bare `except Exception: pass`"
        )
