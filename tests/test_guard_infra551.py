"""INFRA-551 guard tests: sort output-flag target classification + redirect precision.

Findings fixed in this round (on top of PR #1026 / R4-1..R4-3):

False decisions (scrutiny r3/r4 residual):
- F-1: ``sort -o backups/y.sql data.csv`` allowed — sort output-flag targets
  were never extracted, so file-type blacklist never ran (only the coarse
  string heuristic on ``memory/``/``agents.md`` applied).
- F-2: ``ruff check . > audit/report.md`` / ``> review/x.md`` allowed — the
  unified redirect helper only knows string indicators, not the ownership
  classifier's audit/ and review/ domains.
- F-3: ``sort -o /tmp/out memory/kb/data.csv`` blocked — coarse string gate
  fires on the owned INPUT file even though the OUTPUT target is safe.

Design (architecture fact #10 anti-regression):
- One semantic parser ``_extract_sort_output_path`` shared by write-intent
  detection and legacy path extraction (no regex fork).
- Authoritative pre-pass: segments with precisely-extractable write targets
  are classified against the ownership policy BEFORE the coarse string gate;
  the coarse gate then skips readonly-vocabulary segments (owned strings
  there are usually inputs) but still guards write commands
  (defense-in-depth for extractor gaps like ``install -t``).
"""

from __future__ import annotations

import pytest

from memory_core.tools._guard_classify import (
    _extract_path_from_execute,
    _extract_sort_output_path,
    _segment_has_write_intent,
)
from memory_core.tools._guard_patterns import RE_SORT_OUTPUT
from tests.guard_helpers import run_guard

PROTECTED_TARGET = "memory/kb/out.txt"
BACKUPS_TARGET = "backups/y.sql"
SAFE_TARGET = "/tmp/out.txt"


@pytest.fixture
def fake_project(tmp_path):
    """Create a fake project with memory/ tree for guard subprocess."""
    (tmp_path / "memory" / "system").mkdir(parents=True)
    (tmp_path / "memory" / "kb").mkdir(parents=True)
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "app.py").write_text("# app\n")
    return tmp_path


# ---------------------------------------------------------------------------
# F-1: sort output-flag targets must reach blacklist + ownership classifiers
# ---------------------------------------------------------------------------

SORT_FLAG_BLACKLIST_BLOCK = [
    f"sort -o {BACKUPS_TARGET} data.csv",
    f"sort --output={BACKUPS_TARGET} data.csv",
    f"sort --output {BACKUPS_TARGET} data.csv",
    f"sort -ro {BACKUPS_TARGET} data.csv",
    "sort -o dump.sql data.csv",
    "sort --output=data.bak data.csv",
]


@pytest.mark.parametrize("cmd", SORT_FLAG_BLACKLIST_BLOCK)
def test_sort_flag_blacklist_block(fake_project, cmd: str) -> None:
    """F-1: sort output flags targeting blacklisted types must block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


SORT_FLAG_OWNED_DOMAIN_BLOCK = [
    f"sort -o {PROTECTED_TARGET} data.csv",
    f"sort --output={PROTECTED_TARGET} data.csv",
    f"sort --output {PROTECTED_TARGET} data.csv",
    f"sort -ro {PROTECTED_TARGET} data.csv",
    "sort -o audit/report.md data.csv",
    "sort -o review/findings.md data.csv",
    "sort --output=memory/docs/note.md data.csv",
]


@pytest.mark.parametrize("cmd", SORT_FLAG_OWNED_DOMAIN_BLOCK)
def test_sort_flag_owned_domain_block(fake_project, cmd: str) -> None:
    """F-1: sort output flags targeting owned domains (incl. audit/review) must block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


# ---------------------------------------------------------------------------
# F-2: redirect targets in classifier-owned domains (audit/, review/)
# ---------------------------------------------------------------------------

REDIRECT_OWNED_DOMAIN_BLOCK = [
    "ruff check . > audit/report.md",
    "ruff check . > review/x.md",
    "cat src/a.py >> audit/evidence.txt",
    "git log > review/history.txt",
    "echo x 2> audit/err.log",
    "grep pat src/ &> review/scan.txt",
]


@pytest.mark.parametrize("cmd", REDIRECT_OWNED_DOMAIN_BLOCK)
def test_redirect_classifier_owned_domain_block(fake_project, cmd: str) -> None:
    """F-2: redirects into classifier-owned domains (audit/review) must block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


# ---------------------------------------------------------------------------
# F-3: owned INPUT files with safe OUTPUT targets must allow
# ---------------------------------------------------------------------------

OWNED_INPUT_SAFE_OUTPUT_ALLOW = [
    f"sort -o {SAFE_TARGET} memory/kb/data.csv",
    f"sort --output {SAFE_TARGET} memory/kb/data.csv",
    f"sort --output={SAFE_TARGET} memory/kb/data.csv",
    "cat memory/kb/README.md > /tmp/out.txt",
    "grep pattern memory/kb/x.md > /tmp/matches.txt",
    "git log memory/kb/ > /tmp/history.txt",
]


@pytest.mark.parametrize("cmd", OWNED_INPUT_SAFE_OUTPUT_ALLOW)
def test_owned_input_safe_output_allow(fake_project, cmd: str) -> None:
    """F-3: owned paths as INPUT with safe OUTPUT targets must allow."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 0, f"Expected exit 0 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "allow", f"Expected allow for '{cmd}', got {output}"


# ---------------------------------------------------------------------------
# Semantic parser unit tests (single source of truth for sort output flags)
# ---------------------------------------------------------------------------


class TestExtractSortOutputPath:
    """_extract_sort_output_path handles all GNU sort output flag forms."""

    def _extract(self, segment: str) -> list[str]:
        match = RE_SORT_OUTPUT.match(segment)
        assert match is not None, f"RE_SORT_OUTPUT failed to match: {segment!r}"
        return _extract_sort_output_path(match)

    def test_exact_short_flag_space_form(self):
        assert self._extract("sort -o out.txt data.csv") == ["out.txt"]

    def test_combined_flag_space_form(self):
        assert self._extract("sort -ro out.txt data.csv") == ["out.txt"]
        assert self._extract("sort -nruo out.txt data.csv") == ["out.txt"]

    def test_attached_gnu_form(self):
        assert self._extract("sort -oout.txt data.csv") == ["out.txt"]
        assert self._extract("sort -roout.txt data.csv") == ["out.txt"]

    def test_long_flag_equals_form(self):
        assert self._extract("sort --output=out.txt data.csv") == ["out.txt"]

    def test_long_flag_space_form(self):
        assert self._extract("sort --output out.txt data.csv") == ["out.txt"]

    def test_no_output_flag_returns_empty(self):
        assert self._extract("sort -r data.csv") == []
        assert self._extract("sort -t , -k 2 data.csv") == []

    def test_value_carrying_flags_not_misdetect(self):
        """R4-3 guard: -T/-S/-k value forms must not be treated as -o targets."""
        assert self._extract("sort -T/tmp/work data.csv") == []
        assert self._extract("sort -S1Go data.csv") == []
        assert self._extract("sort -k1,1 data.csv") == []

    def test_dangling_flag_returns_empty(self):
        assert self._extract("sort -o") == []
        assert self._extract("sort --output") == []


# ---------------------------------------------------------------------------
# Write-intent ↔ extraction consistency (no regex fork drift)
# ---------------------------------------------------------------------------


class TestIntentExtractionConsistency:
    """Write-intent detection and target extraction must agree for sort."""

    SORT_FORMS = [
        "sort -o memory/kb/out.txt data.csv",
        "sort -ro memory/kb/out.txt data.csv",
        "sort --output=memory/kb/out.txt data.csv",
        "sort --output memory/kb/out.txt data.csv",
        "sort -oout.txt data.csv",
        "sort -roout.txt data.csv",
        "sort -r data.csv",
        "sort -T/tmp/work data.csv",
        "sort -k1,1 data.csv",
    ]

    @pytest.mark.parametrize("segment", SORT_FORMS)
    def test_intent_iff_extractable(self, segment: str) -> None:
        """_segment_has_write_intent True ⟺ semantic parser finds an output target."""
        match = RE_SORT_OUTPUT.match(segment)
        extracted = _extract_sort_output_path(match) if match else []
        assert _segment_has_write_intent(segment) is bool(extracted), (
            f"intent/extraction drift for {segment!r}: extracted={extracted}"
        )


# ---------------------------------------------------------------------------
# Defense-in-depth: coarse gate still guards write commands
# ---------------------------------------------------------------------------


COARSE_GATE_WRITE_COMMANDS_BLOCK = [
    "install -t memory/log app.conf",
    "install --target-directory=memory/log app.conf",
    "rsync -a src/ --target-directory=memory/docs/",
    "mv -t memory/system x",
]


@pytest.mark.parametrize("cmd", COARSE_GATE_WRITE_COMMANDS_BLOCK)
def test_coarse_gate_write_commands_block(fake_project, cmd: str) -> None:
    """INFRA-551: readonly-vocab skip must NOT weaken write-command gating."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


# ---------------------------------------------------------------------------
# Extraction dispatch: sort output flag participates in legacy pipeline
# ---------------------------------------------------------------------------


class TestSortExtractionDispatch:
    """_extract_path_from_execute returns sort output-flag targets."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("sort -o backups/y.sql data.csv", ["backups/y.sql"]),
            ("sort --output=memory/kb/out.txt data.csv", ["memory/kb/out.txt"]),
            ("sort -ro /tmp/out data.csv", ["/tmp/out"]),
            ("sort -r data.csv", []),
        ],
    )
    def test_extraction_dispatch(self, command: str, expected: list[str]) -> None:
        assert _extract_path_from_execute(command) == expected

    def test_redirect_takes_priority_for_sort_with_redirect(self):
        """sort with BOTH -o and > : both targets extracted by redirect findall."""
        paths = _extract_path_from_execute("sort -o /tmp/a data.csv > /tmp/b")
        assert "/tmp/a" in paths and "/tmp/b" in paths
