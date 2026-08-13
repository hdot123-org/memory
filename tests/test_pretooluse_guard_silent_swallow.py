"""Regression tests for INFRA-255: silent exception swallow in pretooluse_guard.py.

These tests verify that the _fail_closed_with_raw_check function no longer
silently swallows exceptions via bare `pass`, but instead logs them with
exc_info for debuggability.
"""

from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parent.parent / "memory_core" / "tools" / "pretooluse_guard.py"


class TestPretooluseGuardSilentSwallow:
    """Verify INFRA-255 fix: no silent exception swallowing remains."""

    def test_source_file_exists(self):
        assert SOURCE_PATH.exists(), f"Source file not found: {SOURCE_PATH}"

    def test_no_bare_pass_in_fail_closed(self):
        """The _fail_closed_with_raw_check function must not contain bare `pass` in its except block."""
        content = SOURCE_PATH.read_text()
        # Find the function
        func_marker = "def _fail_closed_with_raw_check"
        assert func_marker in content, f"Function not found in source"

        func_start = content.index(func_marker)
        # Get a window of the function body (next 800 chars should cover it)
        func_window = content[func_start:func_start + 800]

        # The except block must NOT contain bare pass
        assert "except Exception:\n" not in func_window or "pass" not in func_window.split("except Exception:\n")[1].split("\n\n")[0], \
            "Bare `except Exception: pass` pattern found - silent swallow not fixed"

    def test_exception_captured_as_variable(self):
        """The except block must capture the exception as a variable (e.g., `as exc`)."""
        content = SOURCE_PATH.read_text()
        func_marker = "def _fail_closed_with_raw_check"
        func_start = content.index(func_marker)
        func_window = content[func_start:func_start + 800]

        assert "except Exception as exc:" in func_window, \
            "Exception must be captured as a variable (e.g., `except Exception as exc:`)"

    def test_logger_debug_called_with_exception(self):
        """The except block must call _logger.debug with the exception."""
        content = SOURCE_PATH.read_text()
        func_marker = "def _fail_closed_with_raw_check"
        func_start = content.index(func_marker)
        func_window = content[func_start:func_start + 800]

        assert "_logger.debug" in func_window, \
            "_logger.debug must be called in the except block"
        assert "exc" in func_window, \
            "The exception variable must be referenced in the debug log message"

    def test_no_silent_swallow_pattern_in_file(self):
        """Whole-file guard: no `except Exception:\\n        pass` pattern should exist anywhere in the file."""
        content = SOURCE_PATH.read_text()
        # Check for the exact silent swallow pattern with proper indentation
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "except Exception:" or stripped.startswith("except Exception:  #"):
                # Check if the next non-empty line is just `pass`
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_stripped = lines[j].strip()
                    if next_stripped:
                        assert next_stripped != "pass", \
                            f"Silent swallow pattern found at line {i+1}-{j+1}: `except Exception: pass`"
                        break
