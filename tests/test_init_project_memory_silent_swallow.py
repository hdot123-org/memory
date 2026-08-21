"""Regression tests for silent exception swallow fixes in init_project_memory.py (INFRA-261).

``_detect_from_package_json`` and ``_detect_from_pyproject`` used bare
``except Exception: pass`` to swallow file-parsing failures with zero observability.

Fix: each except clause now binds the exception and logs it via ``logger.debug(...)``,
preserving the original graceful-degradation behavior (project_info left unchanged).

Static code-inspection tests following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "init_project_memory.py"

# init_project_memory.py was split into submodules (feat/m3-init-project-memory-split).
# The detector functions now live in _init_autofill.py; the facade still re-exports
# them. Inspect the union of the facade and all split submodules so the INFRA-261
# regression guard keeps covering the moved functions.
TOOLS_DIR = REPO_ROOT / "memory_core" / "tools"


def _combined_source() -> str:
    """Concatenate facade + all _init_* submodules for static inspection."""
    parts = [SOURCE_PATH.read_text()]
    parts.extend(p.read_text() for p in sorted(TOOLS_DIR.glob("_init_*.py")))
    return "\n".join(parts)


class TestDetectFromPackageJsonSilentSwallow:
    """``_detect_from_package_json`` parsing failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(_combined_source(), "_detect_from_package_json")
        assert "except Exception as exc:" in body, (
            "_detect_from_package_json except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(_combined_source(), "_detect_from_package_json")
        assert "package.json parsing failed" in body and "logger.debug" in body


class TestDetectFromPyprojectSilentSwallow:
    """``_detect_from_pyproject`` parsing failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(_combined_source(), "_detect_from_pyproject")
        assert "except Exception as exc:" in body, (
            "_detect_from_pyproject except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(_combined_source(), "_detect_from_pyproject")
        assert "pyproject parsing failed" in body and "logger.debug" in body


class TestNoBareSilentSwallow:
    """No bare ``except Exception: pass`` swallow remains for the two detector functions."""

    def test_no_bare_pass(self):
        content = _combined_source()
        assert "except Exception:\n        pass" not in content, (
            "init_project_memory.py must not regress to bare `except Exception: pass`"
        )
