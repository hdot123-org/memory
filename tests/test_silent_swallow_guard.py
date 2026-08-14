"""Whole-file guards: no bare ``except Exception: pass`` swallow remains (INFRA-283).

Consolidates the ``TestNoSilentSwallowAnywhere`` classes that were previously
duplicated across the per-module silent-swallow test files
(ownership / apply_residue_plan / code_hygiene_audit / telemetry_bridge /
error_logger). The per-module copies were 84-94% AST-similar and repeatedly
triggered CODE_HYGIENE_DUPLICATE_BLOCK findings (e.g. INFRA-283), so the guard
is now a single parametrized check.

The guard uses a regex that matches ``except Exception:`` followed only by
``pass`` at ANY indentation level, strictly stronger than the previous
hard-coded 4-space/8-space patterns.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

# (module-relative path, historical guard note)
GUARDED_MODULES = [
    (
        "memory_core/ownership.py",
        "ownership.py (PR #569)",
    ),
    (
        "memory_core/tools/apply_residue_plan.py",
        "apply_residue_plan.py (INFRA-242)",
    ),
    (
        "memory_core/tools/code_hygiene_audit.py",
        "code_hygiene_audit.py (INFRA-243 / PR #573)",
    ),
    (
        "memory_core/tools/telemetry_bridge.py",
        "telemetry_bridge.py",
    ),
    (
        "memory_core/tools/error_logger.py",
        "error_logger.py",
    ),
]

# ``except Exception:`` followed (after optional comment/whitespace lines) only
# by a ``pass`` line, at any indentation depth. Blocks that log, bind the
# exception, return, or continue do not match.
_BARE_SWALLOW_RE = re.compile(
    r"except Exception:\s*(?:#[^\n]*\n\s*)*pass\b"
)


@pytest.mark.parametrize(
    "module_relpath,note",
    GUARDED_MODULES,
    ids=[m for m, _ in GUARDED_MODULES],
)
def test_no_bare_silent_swallow_pattern(module_relpath: str, note: str) -> None:
    """No bare ``except Exception:`` followed only by ``pass`` at any nesting level."""
    content = (REPO_ROOT / module_relpath).read_text()
    match = _BARE_SWALLOW_RE.search(content)
    assert match is None, (
        f"{module_relpath} must not contain a bare `except Exception: pass` "
        f"(silent swallow) at any indentation level — guard for {note}"
    )
