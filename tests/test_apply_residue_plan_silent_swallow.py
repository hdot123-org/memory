"""Regression tests for silent exception swallow fix in apply_residue_plan.py (INFRA-242).

Bug: Two `except Exception: pass` clauses in apply_residue_plan.py silently
swallowed ownership-classification / forbidden-path-scan failures with zero
observability:
  1. _is_forbidden_path — ownership classification failure (~L164)
  2. _validate_plan — dynamic forbidden-path scan failure (~L229)

Fix: Each except clause now calls logger.debug(..., exc_info=True) while still
preserving the graceful-degradation behavior (fall through to legacy check /
legacy patterns). Control flow and return values are unchanged.

The fix is covered two ways:
  - Code-inspection tests (mirroring the INFRA-241 pattern in
    tests/test_ownership_silent_swallow.py): read the source, slice the
    relevant scope, and assert the observability call is present.
  - Runtime tests: patch load_memory_ownership to raise, then assert the
    graceful-degradation result still holds AND logger.debug is invoked with
    exc_info=True.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from memory_core.tools.apply_residue_plan import _is_forbidden_path, _validate_plan
from tests.silent_swallow_helpers import (
    bare_except_positions as _except_positions,
)
from tests.silent_swallow_helpers import (
    top_level_function_body as _function_body,
)

MODULE = "memory_core.tools.apply_residue_plan"
LOGGER_NAME = MODULE
MODULE_PATH = Path(__file__).parent.parent / "memory_core" / "tools" / "apply_residue_plan.py"


# ---------------------------------------------------------------------------
# Code-inspection tests
# ---------------------------------------------------------------------------

class TestIsForbiddenPathSilentSwallow:
    """Regression guard: _is_forbidden_path except block logs at debug (INFRA-242)."""

    def test_is_forbidden_path_except_logs_with_exc_info(self):
        """The ownership-classification except block must call logger.debug(exc_info=True)."""
        content = MODULE_PATH.read_text()
        func_body = _function_body(content, "_is_forbidden_path")
        positions = _except_positions(func_body)
        assert len(positions) >= 1, (
            "_is_forbidden_path must have an except Exception block"
        )
        except_block = func_body[positions[0]:positions[0] + 300]
        assert "logger.debug" in except_block, (
            "_is_forbidden_path except block must call logger.debug — "
            "bare pass silently swallows ownership classification failures"
        )
        assert "exc_info=True" in except_block, (
            "logger.debug must include exc_info=True so the traceback is captured"
        )

    def test_no_bare_pass_in_function_scope(self):
        """The function must not contain a bare `except Exception: pass` swallow."""
        content = MODULE_PATH.read_text()
        # _is_forbidden_path's except is at 8-space indent, so a bare pass
        # regression would render as 12-space-indented pass.
        assert "except Exception:\n            pass" not in content


class TestValidatePlanSilentSwallow:
    """Regression guard: _validate_plan except block logs at debug (INFRA-242)."""

    def test_validate_plan_except_logs_with_exc_info(self):
        """The forbidden-path-scan except block must call logger.debug(exc_info=True)."""
        content = MODULE_PATH.read_text()
        func_body = _function_body(content, "_validate_plan")
        positions = _except_positions(func_body)
        assert len(positions) >= 1, (
            "_validate_plan must have an except Exception block"
        )
        except_block = func_body[positions[0]:positions[0] + 300]
        assert "logger.debug" in except_block, (
            "_validate_plan except block must call logger.debug — "
            "bare pass silently swallows forbidden-path scan failures"
        )
        assert "exc_info=True" in except_block, (
            "logger.debug must include exc_info=True so the traceback is captured"
        )

    def test_no_bare_exception_pass_in_scan_scope(self):
        """The outer forbidden-path-scan except must not be a bare pass swallow.

        Note: the inner `except (ValueError, OSError): pass` is intentional
        (specific exception types) and is NOT a bare-Exception swallow, so we
        only guard against `except Exception: pass`.
        """
        content = MODULE_PATH.read_text()
        # _validate_plan's outer except is at 8-space indent.
        assert "except Exception:\n            pass" not in content


# ---------------------------------------------------------------------------
# Runtime tests (patch load_memory_ownership to raise)
# ---------------------------------------------------------------------------

def _run_under_ownership_failure(
    call: Callable[[], object],
    expected_fragment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Shared runtime helper: patch load_memory_ownership to raise, run ``call``
    at DEBUG level, and assert the graceful-degradation debug log was captured.

    Used by both runtime test classes so their caplog assertions stay identical
    (INFRA-287: deduplicate the duplicated test_caplog_captures_debug blocks).
    """
    with mock.patch(f"{MODULE}.load_memory_ownership", side_effect=RuntimeError("boom")):
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            call()

    assert any(
        expected_fragment in record.message
        and "legacy" in record.message
        and record.levelno == logging.DEBUG
        for record in caplog.records
    ), [r.message for r in caplog.records]


class TestIsForbiddenPathRuntimeLogsAndDegrades:
    """When ownership classification fails, _is_forbidden_path logs and degrades."""

    def test_logs_and_falls_through_to_legacy(self, tmp_path: Path):
        """A failure must emit a debug log and still return the legacy result."""
        with mock.patch(f"{MODULE}.load_memory_ownership", side_effect=RuntimeError("boom")) as \
                mocked_load, mock.patch(f"{MODULE}.logger") as mocked_logger:
            # AGENTS.md is caught by the legacy fallback.
            result = _is_forbidden_path("AGENTS.md", target=tmp_path)

        assert mocked_load.called
        # Graceful degradation: legacy check still flags AGENTS.md.
        assert result is True
        # Observability: logger.debug called with exc_info.
        assert mocked_logger.debug.called
        _, kwargs = mocked_logger.debug.call_args
        assert kwargs.get("exc_info") is True

    def test_logs_and_returns_false_for_non_forbidden(self, tmp_path: Path):
        """A non-forbidden path must return False (legacy) while still logging."""
        with mock.patch(f"{MODULE}.load_memory_ownership", side_effect=RuntimeError("boom")), \
                mock.patch(f"{MODULE}.logger") as mocked_logger:
            # README.md is NOT forbidden by the legacy check.
            result = _is_forbidden_path("README.md", target=tmp_path)

        assert result is False
        assert mocked_logger.debug.called
        _, kwargs = mocked_logger.debug.call_args
        assert kwargs.get("exc_info") is True

    def test_is_forbidden_path_caplog_captures_debug(self, tmp_path: Path, caplog):
        """The debug log must be visible via caplog at DEBUG level."""
        _run_under_ownership_failure(
            call=lambda: _is_forbidden_path("AGENTS.md", target=tmp_path),
            expected_fragment="_is_forbidden_path",
            caplog=caplog,
        )


class TestValidatePlanRuntimeLogsAndDegrades:
    """When the forbidden-path scan fails, _validate_plan logs and degrades."""

    def test_logs_and_plan_still_valid(self, tmp_path: Path):
        """A scan failure must emit a debug log and not mark a valid plan invalid."""
        plan = {
            "target": str(tmp_path),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "medium",
            "requires_human_confirmation": False,
        }
        with mock.patch(f"{MODULE}.load_memory_ownership", side_effect=RuntimeError("boom")) as \
                mocked_load, mock.patch(f"{MODULE}.logger") as mocked_logger:
            is_valid, errors = _validate_plan(plan, target=tmp_path)

        assert mocked_load.called
        # Graceful degradation: plan is still valid (no forbidden-path error).
        assert is_valid is True
        assert not any("forbidden" in e.lower() for e in errors)
        # Observability: logger.debug called with exc_info.
        assert mocked_logger.debug.called
        _, kwargs = mocked_logger.debug.call_args
        assert kwargs.get("exc_info") is True

    def test_validate_plan_caplog_captures_debug(self, tmp_path: Path, caplog):
        """The debug log must be visible via caplog at DEBUG level."""
        plan = {
            "target": str(tmp_path),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "medium",
            "requires_human_confirmation": False,
        }
        _run_under_ownership_failure(
            call=lambda: _validate_plan(plan, target=tmp_path),
            expected_fragment="_validate_plan",
            caplog=caplog,
        )
