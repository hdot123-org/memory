"""Regression tests for silent exception swallow fix in telemetry_bridge.py (INFRA-258 / PR #593).

Bug: In `_post_batch_with_retries`, the HTTP error body reading block used a bare
``except Exception: pass``, silently swallowing failures to read HTTP error response
bodies with zero observability.

Fix: The except clause now binds the exception (``except Exception as exc:``) and
logs it via ``logger.debug(...)``, providing observability while maintaining
graceful degradation (the method continues to process the error).

These are code-inspection tests (NOT runtime tests) following the pattern in
``tests/test_ownership_silent_swallow.py`` and ``tests/test_code_hygiene_audit_silent_swallow.py``:
read the source, slice the relevant scope, and assert the observability call is present.
The except block lives in an HTTP error handling path that is hard to trigger
reliably in tests, so static inspection is the appropriate guard.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TELEMETRY_BRIDGE_PATH = REPO_ROOT / "memory_core" / "tools" / "telemetry_bridge.py"


def _method_body(content: str, name: str) -> str:
    """Slice a method's source from its ``def`` to the next method boundary.

    ``_post_batch_with_retries`` is a method of ``TelemetryBridge``; methods
    inside the class are indented at 4 spaces, so we look for ``\\n    def ``
    (newline + 4 spaces + def) to find the next method boundary.
    """
    start = content.index(f"def {name}")
    # Look for next method at same indentation level (4 spaces inside class)
    next_def = content.find("\n    def ", start + 1)
    if next_def == -1:
        # If no next method found at 4-space indent, look for end of class
        # (newline at column 0 followed by non-indent)
        next_def = len(content)
    return content[start:next_def]


def _except_positions(body: str) -> list[int]:
    """Return character offsets of every ``except Exception`` clause in body.

    Matches the binding form (``except Exception as exc:``).
    """
    positions = []
    needle = "except Exception"
    idx = 0
    while True:
        pos = body.find(needle, idx)
        if pos == -1:
            break
        positions.append(pos)
        idx = pos + len(needle)
    return positions


class TestPostBatchWithRetriesSilentSwallow:
    """Regression guard: ``_post_batch_with_retries`` HTTP error body reading logs at debug (PR #593).

    Before PR #593 the HTTP error body reading except was ``except Exception: pass``,
    hiding read/decode failures with zero observability. The fix binds the
    exception and logs it via logger.debug.
    """

    def test_except_block_binds_exception(self):
        """The HTTP error body reading except clause must bind the exception (``except Exception as exc:``)."""
        content = TELEMETRY_BRIDGE_PATH.read_text()
        method_body = _method_body(content, "_post_batch_with_retries")
        positions = _except_positions(method_body)
        assert positions, "_post_batch_with_retries must have an except Exception clause"
        # Find the except block for HTTP error body reading (look for "read HTTP error body" message)
        assert "read HTTP error body" in method_body, (
            "_post_batch_with_retries must contain the HTTP error body reading section"
        )
        # The except clause header is short; grab the clause line.
        except_clause = method_body[positions[0] : positions[0] + 60]
        assert "as exc" in except_clause, (
            "_post_batch_with_retries HTTP error body reading except must bind the exception as `exc` "
            "so it can be included in the log message — a bare `except Exception: pass` "
            "silently swallows HTTP error body read failures"
        )

    def test_except_block_logs_with_logger_debug(self):
        """The except block must call logger.debug with the exception message."""
        content = TELEMETRY_BRIDGE_PATH.read_text()
        method_body = _method_body(content, "_post_batch_with_retries")
        positions = _except_positions(method_body)
        assert positions, "_post_batch_with_retries must have an except Exception clause"
        except_block = method_body[positions[0] : positions[0] + 300]
        assert "logger.debug" in except_block, (
            "_post_batch_with_retries HTTP error body reading except block must call logger.debug — "
            "bare pass silently swallows HTTP error body read failures"
        )
        assert "failed to read HTTP error body" in except_block, (
            "logger.debug must include descriptive message about HTTP error body read failure"
        )

    def test_no_bare_pass_in_method_scope(self):
        """The method must not contain a bare ``except Exception: pass`` swallow."""
        content = TELEMETRY_BRIDGE_PATH.read_text()
        # _post_batch_with_retries's except is at 8-space indent (method body); a bare
        # pass regression would render as a 12-space-indented pass.
        assert "except Exception:\n            pass" not in content, (
            "telemetry_bridge.py must not regress to a bare "
            "`except Exception: pass` in _post_batch_with_retries (silent swallow)"
        )


class TestNoSilentSwallowAnywhere:
    """Whole-file guard: no bare ``except Exception: pass`` swallow remains in telemetry_bridge.py.

    Covers both indentation levels present in the module:
      - 4-space except (8-space pass): module-level try blocks
      - 8-space except (12-space pass): class methods such as ``_post_batch_with_retries``
    """

    def test_no_bare_silent_swallow_pattern(self):
        """No bare ``except Exception:`` followed only by ``pass`` at any nesting."""
        content = TELEMETRY_BRIDGE_PATH.read_text()
        assert "except Exception:\n        pass" not in content, (
            "telemetry_bridge.py must not contain a 4-space-indented bare "
            "`except Exception: pass` (silent swallow)"
        )
        assert "except Exception:\n            pass" not in content, (
            "telemetry_bridge.py must not contain an 8-space-indented bare "
            "`except Exception: pass` (silent swallow)"
        )
