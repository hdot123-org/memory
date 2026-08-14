"""Regression test for silent exception swallow fix in promote_global_kb.py (INFRA-261).

``_interactive_mode`` used bare ``except Exception: pass`` to swallow failures when
reading the first line of a pending candidate file for display, with zero observability.

Fix: the except clause now binds the exception and logs it via ``logger.debug(...)``,
preserving the graceful-degradation behavior (candidate name still printed; loop continues).

Static code-inspection test following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "promote_global_kb.py"


class TestInteractiveModeSilentSwallow:
    """``_interactive_mode`` candidate-file read failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_interactive_mode")
        assert "except Exception as exc:" in body, (
            "_interactive_mode except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_interactive_mode")
        assert "reading candidate file failed" in body and "logger.debug" in body

    def test_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_interactive_mode")
        assert "except Exception:\n            pass" not in body, (
            "_interactive_mode must not regress to bare `except Exception: pass`"
        )
