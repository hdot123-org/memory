"""Regression tests for silent exception swallow fix in code_hygiene_audit.py (INFRA-243 / PR #573).

Bug: SwallowVisitor._extract_evidence (~L166) used a bare
``except Exception: pass``, silently swallowing evidence-extraction failures
(file read / BOM strip / utf-8 decode errors) with zero observability. This was
especially ironic because code_hygiene_audit.py is itself the tool that detects
the SILENT_SWALLOW rule.

Fix: The except clause now binds the exception (``except Exception as e:``) and
emits a stderr warning via ``print(..., file=sys.stderr)``, matching the
observability pattern used throughout the ``audit_file`` function in the same
module. Control flow is unchanged — it still returns the fallback evidence
string ``"except clause with silent swallow"`` (graceful degradation preserved).

These are code-inspection tests (NOT runtime tests) following the pattern in
``tests/test_ownership_silent_swallow.py`` and the ``TestOsExitRegression``
class in ``tests/test_sigint_handling.py``: read the source, slice the relevant
scope, and assert the observability call is present. The except block lives in
a fallback path (file read / decode errors) that is hard to trigger reliably
and portably, so static inspection is the appropriate guard.
"""

from pathlib import Path

from tests.silent_swallow_helpers import except_positions as _except_positions

REPO_ROOT = Path(__file__).parent.parent
AUDIT_PATH = REPO_ROOT / "memory_core" / "tools" / "code_hygiene_audit.py"


def _method_body(content: str, name: str) -> str:
    """Slice a method's source from its ``def`` to the next ``def`` boundary.

    ``_extract_evidence`` is the last method of ``SwallowVisitor``; the next
    ``\\ndef `` at column 0 is the top-level ``should_skip_file`` function, so
    the search correctly stops outside the class. The helper relies on a
    column-0 ``def`` being preceded by a bare newline while a nested def is
    preceded by newline+indentation, so the slice never stops inside the target
    method.
    """
    start = content.index(f"def {name}")
    next_def = content.index("\ndef ", start + 1)
    return content[start:next_def]


class TestExtractEvidenceSilentSwallow:
    """Regression guard: ``_extract_evidence`` except block logs to stderr (PR #573).

    Before PR #573 the evidence-extraction except was ``except Exception: pass``,
    hiding read/decode failures with zero observability. The fix preserves
    graceful degradation (return the fallback evidence string) but binds the
    exception and emits a stderr warning.
    """

    def test_except_block_binds_exception(self):
        """The except clause must bind the exception (``except Exception as e:``)."""
        content = AUDIT_PATH.read_text()
        method_body = _method_body(content, "_extract_evidence")
        positions = _except_positions(method_body)
        assert positions, "_extract_evidence must have an except Exception clause"
        # The except clause header is short; grab the clause line.
        except_clause = method_body[positions[0] : positions[0] + 60]
        assert "as e" in except_clause, (
            "_extract_evidence except must bind the exception as `e` so it can be "
            "included in the warning message — a bare `except Exception: pass` "
            "silently swallows evidence extraction failures"
        )

    def test_except_block_logs_to_stderr(self):
        """The except block must emit a stderr warning (``print(..., file=sys.stderr)``)."""
        content = AUDIT_PATH.read_text()
        method_body = _method_body(content, "_extract_evidence")
        positions = _except_positions(method_body)
        assert positions, "_extract_evidence must have an except Exception clause"
        except_block = method_body[positions[0] : positions[0] + 300]
        assert "sys.stderr" in except_block, (
            "_extract_evidence except block must write to sys.stderr — "
            "bare pass silently swallows evidence extraction failures. The fix "
            "uses print(..., file=sys.stderr) matching the audit_file pattern."
        )
        assert "Warning" in except_block, (
            "_extract_evidence warning message must include 'Warning' so the "
            "failure is observable in stderr output"
        )

    def test_no_bare_pass_in_method_scope(self):
        """The method must not contain a bare ``except Exception: pass`` swallow."""
        content = AUDIT_PATH.read_text()
        # _extract_evidence's except is at 8-space indent (method body); a bare
        # pass regression would render as a 12-space-indented pass.
        assert "except Exception:\n            pass" not in content, (
            "code_hygiene_audit.py must not regress to a bare "
            "`except Exception: pass` in _extract_evidence (silent swallow)"
        )
