"""Regression tests for the conftest.py silent-swallow fix (INFRA-531, rebuilt from INFRA-487).

Bug: the autouse teardown fixture ``_reset_gateway_adapter_config`` ended with
``except Exception: pass`` — a bare swallow with zero observability (SILENT_SWALLOW,
evolution finding, INFRA-487/#939). In minimal test environments where the gateway
import fails, the reset was skipped silently.

Fix: the except clause now binds the exception and emits a DEBUG record (with
traceback via ``exc_info=True``) while preserving the graceful-degradation
semantics: teardown still completes without raising.

Coverage follows the established INFRA-242 dual pattern:
  - Code-inspection tests: read conftest source, slice the teardown helper
    body, assert the observability call replaced the bare pass.
  - Runtime tests: call the real teardown helper with a failing
    ``reload_adapter`` and assert the debug record via caplog.
"""

import logging
from pathlib import Path

import pytest

from tests.silent_swallow_helpers import (
    bare_except_positions as _bare_except_positions,
)
from tests.silent_swallow_helpers import (
    except_positions as _except_positions,
)
from tests.silent_swallow_helpers import (
    function_body as _function_body,
)

CONFTEST_PATH = Path(__file__).resolve().parent.parent / "conftest.py"


def _read_conftest() -> str:
    return CONFTEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Code-inspection tests (static source checks, INFRA-242 pattern)
# ---------------------------------------------------------------------------


class TestConftestGatewayResetSilentSwallow:
    """Regression guard: the teardown helper's except block logs at debug (INFRA-531)."""

    def test_fixture_delegates_to_helper(self):
        """The autouse fixture must run the reset via the helper."""
        content = _read_conftest()
        func_body = _function_body(content, "_reset_gateway_adapter_config")
        assert "_do_reset_gateway_adapter_config()" in func_body, (
            "_reset_gateway_adapter_config must delegate its teardown to "
            "_do_reset_gateway_adapter_config (pytest 8 forbids calling "
            "fixtures directly, so the logic must live in a plain function)"
        )

    def test_fixture_except_block_no_bare_pass(self):
        """Neither the fixture nor the helper may contain a bare except swallow."""
        content = _read_conftest()
        for name in ("_reset_gateway_adapter_config", "_do_reset_gateway_adapter_config"):
            func_body = _function_body(content, name)
            assert not _bare_except_positions(func_body), (
                f"{name} must not contain a bare `except Exception:` clause — "
                "the degraded teardown path needs an audit trail "
                "(SILENT_SWALLOW, INFRA-531)"
            )

    def test_helper_except_block_binds_exception(self):
        """The helper's except clause must bind the exception for the log record."""
        content = _read_conftest()
        func_body = _function_body(content, "_do_reset_gateway_adapter_config")
        positions = _except_positions(func_body)
        assert len(positions) >= 1, "_do_reset_gateway_adapter_config must have an except Exception block"
        except_header = func_body[positions[0] : positions[0] + 60]
        assert "as exc" in except_header, (
            "except clause must bind the exception (`as exc`) so the log record carries the failure reason"
        )

    def test_helper_except_block_logs_debug_with_exc_info(self):
        """The helper's except block must call logging at DEBUG with exc_info=True."""
        content = _read_conftest()
        func_body = _function_body(content, "_do_reset_gateway_adapter_config")
        positions = _except_positions(func_body)
        assert positions, "_do_reset_gateway_adapter_config must have an except Exception block"
        except_block = func_body[positions[0] : positions[0] + 700]
        assert "logging.getLogger" in except_block, (
            "except block must emit a logging record — bare pass silently "
            "swallows the degraded gateway reset (SILENT_SWALLOW, INFRA-531)"
        )
        assert ".debug(" in except_block, "the record must be at DEBUG level (teardown degradation, not an error)"
        assert "exc_info=True" in except_block, "logging call must include exc_info=True so the traceback is captured"


# ---------------------------------------------------------------------------
# Runtime tests (drive the real teardown helper, INFRA-242 pattern)
# ---------------------------------------------------------------------------


def test_runtime_teardown_failure_logs_debug_and_degrades(caplog):
    """Import/config failure during teardown logs DEBUG and never raises.

    Patches the gateway module's ``reload_adapter`` to raise, then calls the
    real teardown helper: it must complete without raising and emit a DEBUG
    record mentioning the skip (with traceback attached).
    """
    pytest.importorskip("memory_core.tools.memory_hook_gateway")
    conftest = pytest.importorskip("conftest")

    from memory_core.tools import memory_hook_gateway as gw

    with (
        pytest.MonkeyPatch.context() as mp,
        caplog.at_level(logging.DEBUG, logger="conftest"),
    ):

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom: config reload failed")

        mp.setattr(gw, "reload_adapter", _boom)
        conftest._do_reset_gateway_adapter_config()  # must not raise

    debug_records = [
        r for r in caplog.records if r.levelno == logging.DEBUG and "gateway adapter reset skipped" in r.getMessage()
    ]
    assert debug_records, (
        "expected a DEBUG record for the degraded gateway reset "
        f"(INFRA-531), got: {[r.getMessage() for r in caplog.records]}"
    )
    assert any(r.exc_info for r in debug_records), "the DEBUG record must carry exc_info (traceback)"


def test_runtime_teardown_success_is_silent(caplog):
    """Happy path: a successful reset emits no skip record at DEBUG level."""
    pytest.importorskip("memory_core.tools.memory_hook_gateway")
    conftest = pytest.importorskip("conftest")

    with caplog.at_level(logging.DEBUG, logger="conftest"):
        conftest._do_reset_gateway_adapter_config()  # must not raise

    skip_records = [r for r in caplog.records if "gateway adapter reset skipped" in r.getMessage()]
    assert not skip_records, "successful reset must not emit a skip record"
