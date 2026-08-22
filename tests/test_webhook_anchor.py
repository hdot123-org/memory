"""Tests for anchor-based mirror location (VAL-ANC-001 to VAL-ANC-005).

Tests the extract_linkback_anchor() function from evolution_utils.py
and the extract_anchor.py CLI wrapper.

Window semantics (INFRA-357): extraction is scoped to the FIRST
comment BLOCK (blank-line separated) containing the linear-linkback
marker, not the marker line alone.

Architecture reference: docs/architecture/issue-flow.md §9.4/§10.3（镜像定位锚点）
"""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from evolution_utils import extract_linkback_anchor


class TestExtractLinkbackAnchor:
    """Unit tests for extract_linkback_anchor() function."""

    def test_tier1_html_comment_format(self):
        """Tier1: <!-- linear-linkback INFRA-333 -->"""
        comments = "<!-- linear-linkback INFRA-333 -->"
        assert extract_linkback_anchor(comments) == "INFRA-333"

    def test_tier1_with_whitespace(self):
        """Tier1: handles whitespace variations"""
        comments = "<!--linear-linkback   INFRA-456  -->"
        assert extract_linkback_anchor(comments) == "INFRA-456"

    def test_tier2a_href_format(self):
        """Tier2a: linear.app URL in linkback comment"""
        comments = "linear-linkback https://linear.app/team/issue/INFRA-789"
        assert extract_linkback_anchor(comments) == "INFRA-789"

    def test_tier2b_anchor_tag_format(self):
        """Tier2b: anchor tag in linkback comment"""
        comments = 'linear-linkback <a href="https://linear.app/team/issue/INFRA-123">INFRA-123</a>'
        assert extract_linkback_anchor(comments) == "INFRA-123"

    def test_no_linkback_marker(self):
        """No linear-linkback marker → None"""
        comments = "This is a regular comment with INFRA-999"
        assert extract_linkback_anchor(comments) is None

    def test_marker_but_no_extractable_id(self):
        """Marker present but extraction fails → None (fail-closed)"""
        comments = "linear-linkback but no ID here"
        assert extract_linkback_anchor(comments) is None

    def test_multiple_comments_first_wins(self):
        """Multiple linkback comment blocks → first block wins.

        Intent change (INFRA-357): comments are now comment BLOCKS
        (blank-line separated), not single lines; each marker-bearing
        block is its own window.
        """
        comments = """<!-- linear-linkback INFRA-111 -->

Some other text

<!-- linear-linkback INFRA-222 -->"""
        assert extract_linkback_anchor(comments) == "INFRA-111"

    def test_first_match_in_first_linkback_comment(self):
        """First INFRA-xxx in first linkback comment block (issue-flow.md §9.4).

        Intent change (INFRA-357): the window is the marker-bearing
        comment BLOCK; ids mentioned in other blocks are never harvested.
        """
        # Simulate gh --jq output: comment blocks separated by blank lines
        comments = """Regular comment mentioning INFRA-999

<!-- linear-linkback INFRA-333 -->

Another comment with INFRA-456"""
        # Should extract INFRA-333 from the linkback comment block, not INFRA-999
        assert extract_linkback_anchor(comments) == "INFRA-333"

    def test_empty_input(self):
        """Empty input → None"""
        assert extract_linkback_anchor("") is None
        assert extract_linkback_anchor(None) is None

    def test_prevents_body_reference_collision(self):
        """Prevents #724 incident: body contains INFRA reference but no linkback"""
        # Simulate notification issue body that mentions INFRA-333
        comments = """Branch cleanup notification
Deleted branches: refactor/INFRA-333-dedup-test-block
No linear-linkback marker present"""
        # Should return None (no linkback marker)
        assert extract_linkback_anchor(comments) is None


class TestExtractAnchorCLI:
    """Integration tests for extract_anchor.py CLI wrapper."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary git repo with mock gh CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            scripts_dir = repo_path / "scripts"
            scripts_dir.mkdir()

            # Copy extract_anchor.py and evolution_utils.py
            src_scripts = Path(__file__).parent.parent / "scripts"
            for script_name in ["extract_anchor.py", "evolution_utils.py", "evolution_adapters.py", "anchor_gate.py"]:
                src = src_scripts / script_name
                dst = scripts_dir / script_name
                dst.write_text(src.read_text())
                dst.chmod(0o755)

            yield repo_path

    def test_cli_issue_with_anchor(self, temp_repo):
        """CLI: extract anchor from issue with linkback comment"""
        # Create stub gh CLI (must be named "gh" for the script to call it)
        stub_gh = temp_repo / "gh"
        stub_gh.write_text("""#!/bin/bash
# Stub gh that returns mock comments
echo '<!-- linear-linkback INFRA-333 -->'
exit 0
""")
        stub_gh.chmod(0o755)

        # Run extract_anchor.py with stub gh in PATH
        env = os.environ.copy()
        env["PATH"] = f"{temp_repo}:{env.get('PATH', '')}"

        result = subprocess.run(
            [sys.executable, "scripts/extract_anchor.py", "issue", "123", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "INFRA-333" in result.stdout

    def test_cli_issue_no_anchor(self, temp_repo):
        """CLI: no linkback → empty output"""
        stub_gh = temp_repo / "gh"
        stub_gh.write_text("""#!/bin/bash
echo 'Regular comment without linkback'
exit 0
""")
        stub_gh.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{temp_repo}:{env.get('PATH', '')}"

        result = subprocess.run(
            [sys.executable, "scripts/extract_anchor.py", "issue", "456", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_cli_pr_type(self, temp_repo):
        """CLI: works with pr type"""
        stub_gh = temp_repo / "gh"
        stub_gh.write_text("""#!/bin/bash
echo '<!-- linear-linkback INFRA-789 -->'
exit 0
""")
        stub_gh.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{temp_repo}:{env.get('PATH', '')}"

        result = subprocess.run(
            [sys.executable, "scripts/extract_anchor.py", "pr", "789", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "INFRA-789" in result.stdout

    def test_cli_invalid_args(self, temp_repo):
        """CLI: invalid arguments → exit 1"""
        result = subprocess.run(
            [sys.executable, "scripts/extract_anchor.py", "invalid"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "Usage" in result.stderr

    def test_cli_ci_gateway_multiline_format(self, temp_repo):
        """CLI: ci-gateway multi-line comment body → extracts INFRA-357."""
        stub_gh = temp_repo / "gh"
        stub_gh.write_text(
            "#!/bin/bash\n"
            "echo '_此 comment 由 ci-gateway skill 自动生成。_'\n"
            "echo '<!-- linear-linkback -->'\n"
            "echo '<p><a href=\"https://linear.app/jtoom/issue/INFRA-357\">INFRA-357</a></p>'\n"
            "exit 0\n"
        )
        stub_gh.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{temp_repo}:{env.get('PATH', '')}"

        result = subprocess.run(
            [sys.executable, "scripts/extract_anchor.py", "issue", "357", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "INFRA-357"


# ============================================================================
# INFRA-357: comment-block window semantics (ci-gateway multi-line format)
# ============================================================================


class TestCommentBlockWindow:
    """INFRA-357: extraction window = marker-bearing comment BLOCK.

    Production linkback comments (verified across 25 live objects, 100%)
    use the ci-gateway multi-line format: bare marker line with the href
    on the NEXT line. Line-scoped extraction returned None for all of them.
    """

    def test_ci_gateway_multiline_format(self):
        """Real ci-gateway multi-line linkback → extracts INFRA-357.

        The bare marker line carries no id; the href lives on the next
        line of the SAME comment block.
        """
        comments = (
            "_此 comment 由 ci-gateway skill 自动生成。_\n"
            "<!-- linear-linkback -->\n"
            '<p><a href="https://linear.app/jtoom/issue/INFRA-357">INFRA-357</a></p>'
        )
        assert extract_linkback_anchor(comments) == "INFRA-357"

    def test_later_comment_href_ignored_when_marker_block_has_id(self):
        """First-marker-block rule: later comment's unrelated href ignored.

        The marker block carries its own id; a later block mentioning an
        unrelated Linear href must not win or interfere.
        """
        comments = (
            "<!-- linear-linkback -->\n"
            '<p><a href="https://linear.app/jtoom/issue/INFRA-357">INFRA-357</a></p>\n'
            "\n"
            "Related discussion: see https://linear.app/jtoom/issue/INFRA-999 for context"
        )
        assert extract_linkback_anchor(comments) == "INFRA-357"

    def test_later_comment_href_ignored_when_marker_block_has_no_id(self):
        """Fail-closed: bare marker block + later href-only block → None.

        The later comment's href belongs to a DIFFERENT comment block and
        must not be harvested into the marker block's window (#724 safety).
        """
        comments = (
            "_此 comment 由 ci-gateway skill 自动生成。_\n"
            "<!-- linear-linkback -->\n"
            "\n"
            "Related discussion: https://linear.app/jtoom/issue/INFRA-999"
        )
        assert extract_linkback_anchor(comments) is None

    def test_724_notification_without_marker_is_none(self):
        """#724 protection: notification content WITHOUT marker → None.

        Even notification text that contains a Linear-looking href yields
        None when no linear-linkback marker exists anywhere.
        """
        comments = (
            "Branch cleanup notification\n"
            "Deleted branches: refactor/INFRA-333-dedup-test-block\n"
            "Tracking: https://linear.app/jtoom/issue/INFRA-333"
        )
        assert extract_linkback_anchor(comments) is None

    def test_marker_block_multiline_no_id_anywhere(self):
        """Marker present, no id anywhere in the block → None (fail-closed)."""
        comments = "_此 comment 由 ci-gateway skill 自动生成。_\n<!-- linear-linkback -->\n（无链接）"
        assert extract_linkback_anchor(comments) is None


# ============================================================================
# INFRA-357: anchor gate for compensation-layer close (trigger-droid.sh L1166)
# ============================================================================


class TestAnchorGate:
    """INFRA-357: compensation-layer close guard (scripts/anchor_gate.py).

    The guard enforces label + anchor dual gating for the last remaining
    full-text-located close path in trigger-droid.sh: a candidate issue is
    closed ONLY when its linear-linkback anchor == the tracked Linear ref.
    Everything else is fail-closed (skip close + drift record).
    """

    @pytest.fixture
    def gate_repo(self):
        """Temp scripts dir (extract_anchor + deps + anchor_gate) with stub gh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            scripts_dir = repo_path / "scripts"
            scripts_dir.mkdir()
            logs_dir = repo_path / "logs"
            logs_dir.mkdir()

            src_scripts = Path(__file__).parent.parent / "scripts"
            for script_name in [
                "extract_anchor.py",
                "evolution_utils.py",
                "evolution_adapters.py",
                "anchor_gate.py",
            ]:
                dst = scripts_dir / script_name
                dst.write_text((src_scripts / script_name).read_text())
                dst.chmod(0o755)

            yield repo_path, logs_dir

    def _write_stub_gh(self, repo_path: Path, cases: dict) -> None:
        """Stub gh: `gh issue view <N> ...` returns per-issue comment body.

        cases: {issue_number: (body, exit_code)}; multi-line bodies are
        echoed line by line to mimic raw gh --jq output.
        """
        lines = ["#!/bin/bash", "# args: issue view <N> --repo ..."]
        for num, (body, rc) in sorted(cases.items()):
            lines.append(f'if [ "$3" = "{num}" ]; then')
            for line in body.split("\n"):
                lines.append(f"  printf '%s\\n' {shlex.quote(line)}")
            if rc != 0:
                lines.append("  echo 'gh error' >&2")
            lines.append(f"  exit {rc}")
            lines.append("fi")
        lines.append("echo 'unexpected gh call: $*' >&2")
        lines.append("exit 1")
        stub = repo_path / "gh"
        stub.write_text("\n".join(lines) + "\n")
        stub.chmod(0o755)

    def _run_gate(self, repo_path: Path, logs_dir: Path, candidates_json: str, target_ref: str = "INFRA-357"):
        env = os.environ.copy()
        env["PATH"] = f"{repo_path}:{env.get('PATH', '')}"
        return subprocess.run(
            [sys.executable, "scripts/anchor_gate.py", target_ref, "test/repo", str(logs_dir)],
            cwd=repo_path,
            env=env,
            input=candidates_json,
            capture_output=True,
            text=True,
            timeout=30,
        )

    @staticmethod
    def _read_log(logs_dir: Path, name: str) -> str:
        log_file = logs_dir / name
        return log_file.read_text() if log_file.exists() else ""

    def test_gate_anchor_match_returns_number(self, gate_repo):
        """Anchor == target_ref → prints issue number (close allowed)."""
        repo_path, logs_dir = gate_repo
        self._write_stub_gh(
            repo_path,
            {
                101: ("<!-- linear-linkback INFRA-357 -->", 0),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 101}]')
        assert result.returncode == 0
        assert result.stdout.strip() == "101"
        assert self._read_log(logs_dir, "anchor-drift.log") == ""

    def test_gate_missing_anchor_skips_close_with_drift(self, gate_repo):
        """No anchor in candidate → empty output + drift record (fail-closed)."""
        repo_path, logs_dir = gate_repo
        self._write_stub_gh(
            repo_path,
            {
                102: ("Branch cleanup notification, mentions INFRA-357 only in text", 0),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 102}]')
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        drift = self._read_log(logs_dir, "anchor-drift.log")
        assert "DRIFT: INFRA-357 GitHub Issue #102 missing anchor" in drift

    def test_gate_anchor_mismatch_skips_close_with_drift(self, gate_repo):
        """Anchor != target_ref → empty output + mismatch drift (fail-closed)."""
        repo_path, logs_dir = gate_repo
        self._write_stub_gh(
            repo_path,
            {
                103: ("<!-- linear-linkback INFRA-999 -->", 0),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 103}]')
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        drift = self._read_log(logs_dir, "anchor-drift.log")
        assert "DRIFT: INFRA-357 GitHub Issue #103 anchor mismatch (got INFRA-999)" in drift

    def test_gate_extract_failure_skips_close_with_trails(self, gate_repo):
        """gh failure (extract_anchor exit 1) → skip + drift + anchor-extract.log."""
        repo_path, logs_dir = gate_repo
        self._write_stub_gh(
            repo_path,
            {
                104: ("unused", 1),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 104}]')
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        drift = self._read_log(logs_dir, "anchor-drift.log")
        assert "DRIFT: INFRA-357 GitHub Issue #104 anchor extract failed (rc=1)" in drift
        extract_log = self._read_log(logs_dir, "anchor-extract.log")
        assert "anchor-extract issue#104 rc=1" in extract_log

    def test_gate_drift_log_unwritable_warns_on_stderr(self, gate_repo):
        """INFRA-359: drift log write failure must not be swallowed silently.

        anchor-drift.log path occupied by a directory -> open("a") raises.
        Gate must stay fail-closed (rc 0, empty stdout) AND warn on stderr.
        """
        repo_path, logs_dir = gate_repo
        (logs_dir / "anchor-drift.log").mkdir()  # unwritable target
        self._write_stub_gh(
            repo_path,
            {
                107: ("Branch cleanup notification, no anchor here", 0),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 107}]')
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert "drift log write failed" in result.stderr
        assert "#107" in result.stderr

    def test_gate_extract_log_unwritable_warns_on_stderr(self, gate_repo):
        """INFRA-359: extract log write failure must not be swallowed silently.

        anchor-extract.log path occupied by a directory -> open("a") raises.
        Gate must stay fail-closed (rc 0, empty stdout) AND warn on stderr.
        """
        repo_path, logs_dir = gate_repo
        (logs_dir / "anchor-extract.log").mkdir()  # unwritable target
        self._write_stub_gh(
            repo_path,
            {
                108: ("unused", 1),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 108}]')
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert "extract log write failed" in result.stderr
        # drift log itself remains writable and still records the skip
        drift = self._read_log(logs_dir, "anchor-drift.log")
        assert "DRIFT: INFRA-357 GitHub Issue #108 anchor extract failed (rc=1)" in drift

    def test_gate_multiple_candidates_first_match_wins(self, gate_repo):
        """Mismatched candidate drift-recorded; matched candidate returned."""
        repo_path, logs_dir = gate_repo
        self._write_stub_gh(
            repo_path,
            {
                105: ("<!-- linear-linkback INFRA-999 -->", 0),
                106: ("<!-- linear-linkback INFRA-357 -->", 0),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 105}, {"number": 106}]')
        assert result.returncode == 0
        assert result.stdout.strip() == "106"
        drift = self._read_log(logs_dir, "anchor-drift.log")
        assert "DRIFT: INFRA-357 GitHub Issue #105 anchor mismatch (got INFRA-999)" in drift
        assert "#106" not in drift

    def test_gate_ci_gateway_multiline_candidate_matches(self, gate_repo):
        """Full chain: real ci-gateway multi-line comment → gate opens."""
        repo_path, logs_dir = gate_repo
        self._write_stub_gh(
            repo_path,
            {
                357: (
                    "_此 comment 由 ci-gateway skill 自动生成。_\n"
                    "<!-- linear-linkback -->\n"
                    '<p><a href="https://linear.app/jtoom/issue/INFRA-357">INFRA-357</a></p>',
                    0,
                ),
            },
        )
        result = self._run_gate(repo_path, logs_dir, '[{"number": 357}]')
        assert result.returncode == 0
        assert result.stdout.strip() == "357"
        assert self._read_log(logs_dir, "anchor-drift.log") == ""

    def test_gate_empty_and_invalid_candidates_json(self, gate_repo):
        """Empty list / invalid JSON → empty output, exit 0 (fail-closed)."""
        repo_path, logs_dir = gate_repo
        for payload in ("", "[]", "not-json", "null"):
            result = self._run_gate(repo_path, logs_dir, payload)
            assert result.returncode == 0, f"payload={payload!r} rc={result.returncode}"
            assert result.stdout.strip() == "", f"payload={payload!r} stdout={result.stdout!r}"

    def test_gate_invalid_usage_exits_2(self, gate_repo):
        """Wrong argc → exit 2 with usage on stderr."""
        repo_path, logs_dir = gate_repo
        result = subprocess.run(
            [sys.executable, "scripts/anchor_gate.py", "INFRA-357"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        assert "Usage" in result.stderr


# ============================================================================
# VAL-ANC assertions (validation-contract.md)
# ============================================================================


class TestVALANCAssertions:
    """Tests for VAL-ANC-001 to VAL-ANC-005 assertions."""

    def test_val_anc_001_anchor_extraction(self):
        """VAL-ANC-001: extract anchor from linkback comment"""
        comments = "<!-- linear-linkback INFRA-333 -->"
        anchor = extract_linkback_anchor(comments)
        assert anchor == "INFRA-333"

    def test_val_anc_002_label_dual_gate(self):
        """VAL-ANC-002: label filter prevents notification issue closure"""
        # Notification issue without evolution-found label should not be closed
        # This is tested by the shell script integration (reconcile §4b)
        # Here we just verify the anchor extraction works correctly
        comments = "Branch cleanup notification"
        anchor = extract_linkback_anchor(comments)
        assert anchor is None  # No anchor → won't pass anchor check

    def test_val_anc_003_three_forms(self):
        """VAL-ANC-003: three anchor forms (consistent/inconsistent/missing)"""
        # Form 1: consistent anchor (should pass)
        comments1 = "<!-- linear-linkback INFRA-333 -->"
        assert extract_linkback_anchor(comments1) == "INFRA-333"

        # Form 2: inconsistent anchor (should fail)
        comments2 = "<!-- linear-linkback INFRA-999 -->"
        assert extract_linkback_anchor(comments2) == "INFRA-999"
        # Caller checks: "INFRA-999" != "INFRA-333" → fail-closed

        # Form 3: missing anchor (should fail-closed)
        comments3 = "Regular comment"
        assert extract_linkback_anchor(comments3) is None

    def test_val_anc_004_724_incident_prevention(self):
        """VAL-ANC-004: prevent #724 incident (notification issue closure)"""
        # #724 incident: notification issue body contains INFRA reference
        # but no linkback comment → should not be closed
        comments = """Branch cleanup notification
Deleted branches: refactor/INFRA-333-dedup-test-block
Notification issue, not a real finding"""
        anchor = extract_linkback_anchor(comments)
        assert anchor is None  # No linkback → won't close

    def test_val_anc_005_anchor_consistency_check(self):
        """VAL-ANC-005: anchor consistency validation"""
        # Extract anchor and verify it matches target ref
        comments = "<!-- linear-linkback INFRA-333 -->"
        anchor = extract_linkback_anchor(comments)

        # Consistency check: anchor == target_ref
        target_ref = "INFRA-333"
        assert anchor == target_ref  # Consistent → pass

        # Inconsistent case
        target_ref_wrong = "INFRA-999"
        assert anchor != target_ref_wrong  # Inconsistent → fail-closed
