"""
Regression guard for webhook dispatch commands.

Background (2026-08-16):
Historically, trigger-droid.sh / trigger-ci-droid.sh dispatched droid via
`droid exec --mission --auto high ...`. Because the dispatch is wrapped by
`with_timeout 3600`, SIGTERM at the 3600s mark killed the orchestrator
mid-init, leaving mission state.json frozen in running/planning and
accumulating zombies under ~/.factory/missions/.

Fix: drop `--mission` from all non-comment dispatch invocations so the
dispatcher becomes a plain session (no mission state machine to freeze).
Comment lines are allowed to mention `--mission` for historical context.

This test asserts the invariant I1 from the mission architecture doc:
    Managed trigger scripts' non-comment lines must not contain `--mission`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
WEBHOOK_DIR = REPO_ROOT / "webhook-scripts"

MANAGED_DISPATCH_SCRIPTS = [
    "trigger-droid.sh",
    "trigger-ci-droid.sh",
]


def _non_comment_lines(script_path: Path) -> list[tuple[int, str]]:
    """Return (line_number, line_text) for non-comment, non-blank lines.

    A line is treated as a comment if its stripped content starts with `#`.
    Blank lines (after stripping) are ignored.
    """
    text = script_path.read_text(encoding="utf-8").splitlines()
    out: list[tuple[int, str]] = []
    for idx, raw in enumerate(text, start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        out.append((idx, raw))
    return out


@pytest.mark.parametrize("script_name", MANAGED_DISPATCH_SCRIPTS)
def test_dispatch_scripts_do_not_use_mission_flag(script_name: str) -> None:
    """Non-comment lines in managed dispatch scripts must not contain `--mission`."""
    script_path = WEBHOOK_DIR / script_name
    assert script_path.is_file(), f"managed script missing: {script_path}"

    offenders = [
        (lineno, line)
        for lineno, line in _non_comment_lines(script_path)
        if "--mission" in line
    ]
    assert offenders == [], (
        f"{script_name} still contains `--mission` on non-comment line(s); "
        f"offenders: {[(n, ln.strip()) for n, ln in offenders]}"
    )


def test_manifest_includes_trigger_ci_droid() -> None:
    """MANIFEST.sh MANAGED_FILES must list trigger-ci-droid.sh for sync coverage."""
    manifest_path = WEBHOOK_DIR / "MANIFEST.sh"
    assert manifest_path.is_file(), "MANIFEST.sh missing"
    text = manifest_path.read_text(encoding="utf-8")

    # Must appear as a quoted array entry (avoid substring false positives).
    assert '"trigger-ci-droid.sh"' in text, (
        "MANIFEST.sh MANAGED_FILES must include trigger-ci-droid.sh"
    )


def test_comment_lines_may_reference_mission() -> None:
    """Comments may retain historical `--mission` references (informational)."""
    # Sanity: this test is positive — we do not forbid `--mission` in comments.
    # Verify by constructing an example that has --mission only in a comment line.
    example = "# historical note: previously dispatched via droid exec --mission\n"
    example += "droid exec --auto high --tag foo 'prompt'\n"
    lines = example.splitlines()
    non_comment = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    assert all("--mission" not in ln for ln in non_comment)
    # comment line is allowed to mention it
    comment_lines = [ln for ln in lines if ln.strip().startswith("#")]
    assert any("--mission" in ln for ln in comment_lines)
