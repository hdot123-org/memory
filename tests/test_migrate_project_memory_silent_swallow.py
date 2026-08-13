"""Regression test for silent exception swallow fix in migrate_project_memory.py (INFRA-261).

``_check_evidence_refs`` used bare ``except Exception: pass`` to swallow post-migration
evidence-ref validation failures with zero observability.

Fix: the except clause now binds the exception and logs it via ``logger.debug(...)``,
preserving the graceful-degradation behavior (result dict returned unchanged).

Static code-inspection test following ``tests/test_telemetry_bridge_silent_swallow.py``.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCE_PATH = REPO_ROOT / "memory_core" / "tools" / "migrate_project_memory.py"


def _func_body(content: str, name: str) -> str:
    """Slice a top-level function's source from its ``def`` to the next top-level def/class."""
    start = content.index(f"def {name}")
    next_def = content.find("\ndef ", start + 1)
    next_class = content.find("\nclass ", start + 1)
    candidates = [p for p in (next_def, next_class) if p != -1]
    end = min(candidates) if candidates else len(content)
    return content[start:end]


class TestCheckEvidenceRefsSilentSwallow:
    """``_check_evidence_refs`` validation failure must log at debug (INFRA-261)."""

    def test_except_binds_exception(self):
        body = _func_body(SOURCE_PATH.read_text(), "_check_evidence_refs")
        assert "except Exception as exc:" in body, (
            "_check_evidence_refs except must bind the exception as `exc`"
        )

    def test_except_logs_debug(self):
        body = _func_body(SOURCE_PATH.read_text(), "_check_evidence_refs")
        assert "validation failed" in body and "logger.debug" in body

    def test_no_bare_pass(self):
        body = _func_body(SOURCE_PATH.read_text(), "_check_evidence_refs")
        assert "except Exception:\n        pass" not in body, (
            "_check_evidence_refs must not regress to bare `except Exception: pass`"
        )
