"""Regression test for silent exception swallow fix in memory_hook_integrity_manifest.py (INFRA-261).

``_discover_canonical_files`` used bare ``except Exception: pass`` to swallow
ownership-loading failures with zero observability.

Fix: the except clause now binds the exception and logs it via ``_logger.debug(...)``,
preserving the graceful-degradation behavior (falls through to canonical patterns).

Static code-inspection test following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

from tests.silent_swallow_helpers import function_body as _func_body

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "memory_hook_integrity_manifest.py"


class TestDiscoverCanonicalFilesSilentSwallow:
    """``_discover_canonical_files`` ownership-loading failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_discover_canonical_files")
        assert "except Exception as exc:" in body, "_discover_canonical_files except must bind the exception as `exc`"

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_discover_canonical_files")
        assert "ownership loading failed" in body and "_logger.debug" in body

    def test_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_discover_canonical_files")
        assert "except Exception:\n            pass" not in body, (
            "_discover_canonical_files must not regress to bare `except Exception: pass`"
        )
