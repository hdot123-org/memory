"""Tests for anchor-based mirror location (VAL-ANC-001 to VAL-ANC-005).

Tests the extract_linkback_anchor() function from evolution_utils.py
and the extract_anchor.py CLI wrapper.

Architecture reference: §3.1 镜像锚点
"""
import os
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
        """Multiple linkback comments → first one wins"""
        comments = """<!-- linear-linkback INFRA-111 -->
Some other text
<!-- linear-linkback INFRA-222 -->"""
        assert extract_linkback_anchor(comments) == "INFRA-111"

    def test_first_match_in_first_linkback_comment(self):
        """First INFRA-xxx in first linkback comment (architecture §3.1)"""
        # Simulate gh --jq output: each comment on separate line
        comments = """Regular comment mentioning INFRA-999
<!-- linear-linkback INFRA-333 -->
Another comment with INFRA-456"""
        # Should extract INFRA-333 from the linkback comment, not INFRA-999
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
            for script_name in ["extract_anchor.py", "evolution_utils.py", "evolution_adapters.py"]:
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
            ["python3", "scripts/extract_anchor.py", "issue", "123", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10
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
            ["python3", "scripts/extract_anchor.py", "issue", "456", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10
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
            ["python3", "scripts/extract_anchor.py", "pr", "789", "test/repo"],
            cwd=temp_repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0
        assert "INFRA-789" in result.stdout

    def test_cli_invalid_args(self, temp_repo):
        """CLI: invalid arguments → exit 1"""
        result = subprocess.run(
            ["python3", "scripts/extract_anchor.py", "invalid"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 1
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
