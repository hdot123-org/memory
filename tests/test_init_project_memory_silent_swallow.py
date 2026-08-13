"""Regression tests for silent exception swallow fixes in init_project_memory.py (INFRA-261).

``_detect_from_package_json`` and ``_detect_from_pyproject`` used bare
``except Exception: pass`` to swallow file-parsing failures with zero observability.

Fix: each except clause now binds the exception and logs it via ``logger.debug(...)``,
preserving the original graceful-degradation behavior (project_info left unchanged).

Static code-inspection tests following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "init_project_memory.py"


def _func_body(content: str, name: str) -> str:
    """Slice a top-level function's source from its ``def`` to the next top-level def/class."""
    start = content.index(f"def {name}")
    next_def = content.find("\ndef ", start + 1)
    next_class = content.find("\nclass ", start + 1)
    candidates = [p for p in (next_def, next_class) if p != -1]
    end = min(candidates) if candidates else len(content)
    return content[start:end]


class TestDetectFromPackageJsonSilentSwallow:
    """``_detect_from_package_json`` parsing failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_detect_from_package_json")
        assert "except Exception as exc:" in body, (
            "_detect_from_package_json except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_detect_from_package_json")
        assert "package.json parsing failed" in body and "logger.debug" in body


class TestDetectFromPyprojectSilentSwallow:
    """``_detect_from_pyproject`` parsing failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_detect_from_pyproject")
        assert "except Exception as exc:" in body, (
            "_detect_from_pyproject except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_detect_from_pyproject")
        assert "pyproject parsing failed" in body and "logger.debug" in body


class TestNoBareSilentSwallow:
    """No bare ``except Exception: pass`` swallow remains for the two detector functions."""

    def test_no_bare_pass(self):
        content = SOURCE_PATH.read_text()
        assert "except Exception:\n        pass" not in content, (
            "init_project_memory.py must not regress to bare `except Exception: pass`"
        )
