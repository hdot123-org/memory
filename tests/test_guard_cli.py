"""Tests for scripts/guard_cli.py — shared CLI skeleton for repo guards (INFRA-559).

``check_boundary.py`` and ``check_doc_classification.py`` delegate their
``main()`` structure to ``run_cli``; these tests pin the shared contract:

- ``--json`` prints ``{"findings": [...], "count": N}`` and exits 0/1
- default mode prints the label summary line and per-finding blocks
- exit code is 1 iff findings exist
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from guard_cli import run_cli


def _run(argv: list[str], findings: list[dict[str, str]], label: str = "test guard") -> tuple[int, str]:
    """Invoke run_cli with a fixed findings list under a fake argv; capture stdout."""
    import io
    from contextlib import redirect_stdout

    old_argv = sys.argv
    sys.argv = ["guard", *argv]
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            code = run_cli(
                label=label,
                description="test guard",
                collect_findings=lambda: findings,
                format_finding=lambda f: f"  [{f['kind']}] {f['path']}",
            )
    finally:
        sys.argv = old_argv
    return code, out.getvalue()


class TestRunCliClean:
    def test_clean_default_exits_zero(self) -> None:
        code, out = _run([], findings=[])
        assert code == 0
        assert "test guard: clean (0 findings)" in out

    def test_clean_json_exits_zero(self) -> None:
        code, out = _run(["--json"], findings=[])
        assert code == 0
        payload = json.loads(out)
        assert payload == {"findings": [], "count": 0}


class TestRunCliFindings:
    SAMPLE = [
        {"kind": "runtime-leak", "path": "core/leak.py", "line": "3", "matched": "x", "rule": "r1"},
        {"kind": "runtime-leak", "path": "core/leak2.py", "line": "4", "matched": "y", "rule": "r2"},
    ]

    def test_findings_default_exits_one(self) -> None:
        code, out = _run([], findings=self.SAMPLE)
        assert code == 1
        assert "test guard: 2 finding(s)" in out
        # Per-finding formatter output is rendered
        assert "[runtime-leak] core/leak.py" in out
        assert "[runtime-leak] core/leak2.py" in out

    def test_findings_json_exits_one(self) -> None:
        code, out = _run(["--json"], findings=self.SAMPLE)
        assert code == 1
        payload = json.loads(out)
        assert payload["count"] == 2
        assert payload["findings"] == self.SAMPLE
        # ensure_ascii=False keeps CJK rule text readable
        assert "ensure_ascii" not in out


class TestGuardIntegration:
    """Both consumer guards must keep the 0/1 exit contract via run_cli."""

    def test_boundary_guard_clean_via_subprocess(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_boundary.py"), "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["count"] == 0

    def test_doc_classification_guard_clean_via_subprocess(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_doc_classification.py"), "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["count"] == 0
