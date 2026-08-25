"""Round-4 guard hardening tests (scrutiny round-3 findings).

R4-1: ruff fast-path regression — non-write ruff branch does `return False`
    before redirect target check. Commands like
    `ruff check <owned> > <owned>/out.txt` family (>>, 2>, 2>>, &>, > backups/)
    should block but allow in HEAD.

R4-2: sort write detection only matches exact token — combined short flags
    like `-ro`/`-nro`/`-uo` and space-separated `--output` escape.

Unification: 8 duplicated redirect regex blocks consolidated into a single
    `_check_redirect_targets` helper (architecture fact #10: regex fork is
    the root cause factory for the ruff regression).
"""

from __future__ import annotations

import pytest

from memory_core.tools._guard_classify import (
    _check_redirect_targets,
    _segment_has_write_intent,
)
from tests.guard_helpers import run_guard

# ---------------------------------------------------------------------------
# Cross-product matrix: command × operator × target
# ---------------------------------------------------------------------------

REDIRECT_OPS = [">", ">>", "2>", "2>>", "&>"]
PROTECTED_TARGET = "memory/kb/out.txt"
BACKUPS_TARGET = "backups/y.sql"
SAFE_TARGET = "/tmp/out.txt"

# R4-1: ruff cross-product — readonly ruff × redirect operators × targets
RUFF_REDIRECT_MATRIX = [
    # (operator, target, expected_write_intent)
    # Protected domain targets → should block (write intent True)
    (">", PROTECTED_TARGET, True),
    (">>", PROTECTED_TARGET, True),
    ("2>", PROTECTED_TARGET, True),
    ("2>>", PROTECTED_TARGET, True),
    ("&>", PROTECTED_TARGET, True),
    # Backups targets (file-type blacklist) → should block
    (">", BACKUPS_TARGET, True),
    (">>", BACKUPS_TARGET, True),
    ("2>", BACKUPS_TARGET, True),
    ("2>>", BACKUPS_TARGET, True),
    ("&>", BACKUPS_TARGET, True),
    # Safe targets → should allow (write intent False)
    (">", SAFE_TARGET, False),
    (">>", SAFE_TARGET, False),
    ("2>", SAFE_TARGET, False),
    ("2>>", SAFE_TARGET, False),
    ("&>", SAFE_TARGET, False),
]


@pytest.mark.parametrize("op,target,expected", RUFF_REDIRECT_MATRIX)
def test_ruff_redirect_cross_product(op: str, target: str, expected: bool) -> None:
    """R4-1: ruff readonly × redirect operator × target cross-product.

    Non-write ruff commands must still check redirect targets.
    """
    segment = f"ruff check memory_core/ {op} {target}"
    assert _segment_has_write_intent(segment) is expected, (
        f"ruff with '{op} {target}' should have write_intent={expected}"
    )


# R4-2: sort write detection cross-product
SORT_FLAG_VARIANTS = [
    # (flag_token, expected_write_intent) — flag targets protected domain
    ("-o", True),  # exact short flag (already worked)
    ("-ro", True),  # combined short flag with o (R4-2 fix)
    ("-nro", True),  # combined short flag with o (R4-2 fix)
    ("-uo", True),  # combined short flag with o (R4-2 fix)
    ("-nruo", True),  # combined short flag with o (R4-2 fix)
    ("--output=memory/kb/out.txt", True),  # = form (already worked)
    ("--output", True),  # space-separated form (R4-2 fix)
]


@pytest.mark.parametrize("flag,expected", SORT_FLAG_VARIANTS)
def test_sort_write_flag_variants(flag: str, expected: bool) -> None:
    """R4-2: sort write detection must handle all flag forms.

    Combined short flags (-ro, -nro, -uo) and space-separated --output
    must be detected as write operations.
    """
    if flag == "--output":
        segment = f"sort --output {PROTECTED_TARGET} data.csv"
    else:
        segment = f"sort {flag} {PROTECTED_TARGET} data.csv"
    assert _segment_has_write_intent(segment) is expected, f"sort with '{flag}' should have write_intent={expected}"


# Sort readonly controls — no -o must remain allow
SORT_READONLY_CONTROLS = [
    "sort data.csv",
    "sort -r data.csv",
    "sort -n data.csv",
    "sort -t ',' -k 2 data.csv",
    "sort -u data.csv",
    "sort -rn data.csv",
    "sort -t ',' memory/kb/data.csv > /tmp/out",  # safe redirect target
]


@pytest.mark.parametrize("cmd", SORT_READONLY_CONTROLS)
def test_sort_readonly_controls(cmd: str) -> None:
    """Sort without -o/--output must remain readonly (no false positives)."""
    assert _segment_has_write_intent(cmd) is False, f"'{cmd}' should be readonly"


# Ruff readonly controls — pure ruff check without redirect must allow
RUFF_READONLY_CONTROLS = [
    "ruff check memory_core/",
    "ruff check .",
    "ruff check src/",
]


@pytest.mark.parametrize("cmd", RUFF_READONLY_CONTROLS)
def test_ruff_readonly_controls(cmd: str) -> None:
    """Pure ruff check without redirect must remain readonly."""
    assert _segment_has_write_intent(cmd) is False, f"'{cmd}' should be readonly"


# ---------------------------------------------------------------------------
# _check_redirect_targets unified helper tests
# ---------------------------------------------------------------------------


def test_check_redirect_targets_owned_target() -> None:
    """_check_redirect_targets detects owned path targets."""
    assert _check_redirect_targets("echo hi > memory/kb/out.txt") is True
    assert _check_redirect_targets("cat src/a.py >> memory/system/data.json") is True
    assert _check_redirect_targets("echo x 2> memory/docs/err.log") is True
    assert _check_redirect_targets("echo x &> memory/kb/combined.txt") is True


def test_check_redirect_targets_backups_target() -> None:
    """_check_redirect_targets detects file-type blacklist targets."""
    assert _check_redirect_targets("echo hi > backups/y.sql") is True
    assert _check_redirect_targets("cat a.txt >> backups/data.bak") is True
    assert _check_redirect_targets("echo x 2> backups/err.dump") is True


def test_check_redirect_targets_safe_target() -> None:
    """_check_redirect_targets returns False for safe targets."""
    assert _check_redirect_targets("echo hi > /tmp/out.txt") is False
    assert _check_redirect_targets("echo x >> /tmp/log") is False
    assert _check_redirect_targets("cat src/a.py > /dev/null") is False


def test_check_redirect_targets_no_redirect() -> None:
    """_check_redirect_targets returns False when no redirect present."""
    assert _check_redirect_targets("echo hello") is False
    assert _check_redirect_targets("grep pattern src/") is False


def test_check_redirect_targets_fd_duplication() -> None:
    """>&N fd duplication (2>&1) is not a redirect to owned."""
    assert _check_redirect_targets("grep pattern src/ 2>&1") is False
    assert _check_redirect_targets("cat file 2>&1 > /tmp/out") is False


def test_check_redirect_targets_multi_redirect() -> None:
    """Multiple redirects in one segment — any owned target triggers True."""
    assert _check_redirect_targets("echo x 1>/tmp/a 2>memory/kb/err.log") is True
    assert _check_redirect_targets("echo x >/tmp/a 2>/tmp/b") is False


# ---------------------------------------------------------------------------
# Subprocess-level integration tests (round-3 regression matrix)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_project(tmp_path):
    """Create a fake project with memory/system/ for guard subprocess."""
    (tmp_path / "memory" / "system").mkdir(parents=True)
    (tmp_path / "memory" / "kb").mkdir(parents=True)
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "app.py").write_text("# app\n")
    return tmp_path


# R4-1 subprocess: ruff redirect family must block
RUFF_SUBPROCESS_BLOCK = [
    f"ruff check memory_core/ > {PROTECTED_TARGET}",
    f"ruff check memory_core/ >> {PROTECTED_TARGET}",
    f"ruff check memory_core/ 2> {PROTECTED_TARGET}",
    f"ruff check memory_core/ 2>> {PROTECTED_TARGET}",
    f"ruff check memory_core/ &> {PROTECTED_TARGET}",
    f"ruff check memory_core/ > {BACKUPS_TARGET}",
    "ruff check memory_core/ > backups/out.txt",
]


@pytest.mark.parametrize("cmd", RUFF_SUBPROCESS_BLOCK)
def test_ruff_redirect_subprocess_block(fake_project, cmd: str) -> None:
    """R4-1 subprocess: ruff redirect to protected/blacklist must block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


# R4-2 subprocess: sort combined flags / --output space form must block
SORT_SUBPROCESS_BLOCK = [
    f"sort -ro {PROTECTED_TARGET} data.csv",
    f"sort -nro {PROTECTED_TARGET} data.csv",
    f"sort -uo {PROTECTED_TARGET} data.csv",
    f"sort --output {PROTECTED_TARGET} data.csv",
]


@pytest.mark.parametrize("cmd", SORT_SUBPROCESS_BLOCK)
def test_sort_combined_flags_subprocess_block(fake_project, cmd: str) -> None:
    """R4-2 subprocess: sort combined flags / space --output must block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


# Subprocess readonly controls
RUFF_SUBPROCESS_ALLOW = [
    "ruff check memory_core/",
    "ruff check .",
    "ruff check memory_core/ > /tmp/out.txt",
    "ruff check memory_core/ >> /tmp/out.txt",
]


@pytest.mark.parametrize("cmd", RUFF_SUBPROCESS_ALLOW)
def test_ruff_readonly_subprocess_allow(fake_project, cmd: str) -> None:
    """R4-1 subprocess: readonly ruff without owned redirect must allow."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 0, f"Expected exit 0 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "allow", f"Expected allow for '{cmd}', got {output}"


SORT_SUBPROCESS_ALLOW = [
    "sort data.csv",
    "sort -r data.csv",
    "sort -t ',' memory/kb/data.csv > /tmp/out",
]


@pytest.mark.parametrize("cmd", SORT_SUBPROCESS_ALLOW)
def test_sort_readonly_subprocess_allow(fake_project, cmd: str) -> None:
    """R4-2 subprocess: sort without -o must remain allow."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 0, f"Expected exit 0 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "allow", f"Expected allow for '{cmd}', got {output}"


# ---------------------------------------------------------------------------
# Round-3 regression matrix (must remain green after round-4 changes)
# ---------------------------------------------------------------------------

ROUND3_REGRESSION_BLOCK = [
    # Round-2 14 commands that must remain block
    "echo hi &> memory/kb/x",
    "cat src/a.py &> memory/kb/out.txt",
    "git log &> memory/kb/out.txt",
    "git stash push memory/kb/x",
    "git stash push -m wip memory/kb",
    "sed --in-place 's/a/b/' memory/kb/README.md",
    "sort -o memory/kb/out.txt data.csv",
    "sort --output=memory/kb/out.txt data.csv",
    "git show HEAD > backups/y.sql",
    "git diff > backups/x.bak",
    "git status > backups/s.sql",
    "sed -n '1p' input.txt > backups/y.sql",
    "ruff format memory/kb/",
    "ruff check --fix memory/kb/x.py",
    # Round-1 carry-overs
    "echo hi & rm -rf memory/kb",
    "cd memory && cd . && rm -f x.md",
    "echo $(rm -rf memory/kb)",
    "echo `rm -rf memory/kb`",
    "mv -t memory/system x",
    "echo x > backups/y.sql && echo done",
    "git add memory/kb/x",
    "git log > memory/kb/out.txt",
    "sort | tee memory/kb/out.txt",
    "grep pattern 2> memory/kb/err.txt",
    "cat >| memory/kb/overwritten.txt",
]


@pytest.mark.parametrize("cmd", ROUND3_REGRESSION_BLOCK)
def test_round3_regression_matrix_block(fake_project, cmd: str) -> None:
    """Round-3 regression matrix: all commands that must remain block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"


ROUND3_REGRESSION_ALLOW = [
    'rg "memory/kb" src/',
    "sed -n 1p memory/kb/README.md",
    "sort -t ',' memory/kb/data.csv > /tmp/out",
    "ruff check memory_core/",
    "ruff check > /tmp/lint.txt",
    "grep ... 2>&1 > /tmp/out",
    "cat memory/kb/README.md 2>&1",
    "grep pattern src/ 2>&1",
    "mypy memory_core/",
    "git status",
    "echo hi &> /tmp/out",
    "sort data.csv",
    "ruff check .",
]


@pytest.mark.parametrize("cmd", ROUND3_REGRESSION_ALLOW)
def test_round3_regression_matrix_allow(fake_project, cmd: str) -> None:
    """Round-3 regression matrix: all commands that must remain allow."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 0, f"Expected exit 0 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "allow", f"Expected allow for '{cmd}', got {output}"


# ---------------------------------------------------------------------------
# R4-3: sort value-carrying flag false positive fix
# ---------------------------------------------------------------------------

# Sort flags that carry values (with /, =, digits) should NOT be misdetected as -o write intent
SORT_VALUE_FLAG_ALLOW = [
    "sort -T/tmp/work memory/kb/data.csv",
    "sort -k1,1 -T/tmp/foo memory/kb/x.csv > /tmp/o",
    "sort -S1Go memory/kb/data.csv",
    "sort -T/tmp/work memory/kb/data.csv > /tmp/out",
    "sort -k2 memory/kb/data.csv",
    "sort --field-separator=, memory/kb/data.csv",
]


@pytest.mark.parametrize("cmd", SORT_VALUE_FLAG_ALLOW)
def test_r4_3_sort_value_carrying_flags_allow(fake_project, cmd: str) -> None:
    """R4-3 fix: sort with value-carrying flags must NOT false-positive on 'o' in flag value."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 0, f"Expected exit 0 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "allow", f"Expected allow for '{cmd}', got {output}"


# Sort combined flags ending with 'o' (pure alphabetic) must still block
SORT_COMBINED_O_BLOCK = [
    "sort -ro memory/kb/out.txt data.csv",
    "sort -nro memory/kb/out.txt data.csv",
    "sort -uo memory/kb/out.txt data.csv",
]


@pytest.mark.parametrize("cmd", SORT_COMBINED_O_BLOCK)
def test_r4_3_sort_combined_o_flags_block(fake_project, cmd: str) -> None:
    """R4-3: sort with pure alphabetic combined flags ending in 'o' must still block."""
    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"
