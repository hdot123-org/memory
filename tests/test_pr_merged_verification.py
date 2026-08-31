"""Tests for PR-Merged Verification (VAL-CLOSE-001 to VAL-CLOSE-024).

Tests evolution_utils._verify_fix_merged_via_linear() and its integration
with evolution_utils.auto_close_resolved().
"""

import json
import os
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch


def _eu():
    """Lazy import of engine evolution_utils (VAL-M1-104: no engine import at module top)."""
    import infra_core.engine.evolution_utils as eu

    return eu


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _linear_response(data: dict) -> bytes:
    """Build a Linear API response body."""
    return json.dumps(data).encode("utf-8")


def _mock_urlopen(response_data: dict):
    """Create a mock urlopen context manager that returns the given data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = _linear_response(response_data)
    return mock_resp


def _linear_issue_response(linear_id: str, attachments: list[dict] = None, state_type: str = "completed") -> dict:
    """Build a Linear API response with issue, state, and attachments."""
    return {
        "data": {
            "issue": {
                "id": linear_id,
                "state": {
                    "id": "state-1",
                    "name": "Done",
                    "type": state_type,
                },
                "attachments": {"nodes": attachments or []},
            }
        }
    }


def _github_attachment(pr_number: int, attachment_type: str = "github") -> dict:
    """Build a GitHub PR attachment dict."""
    return {
        "id": f"att-{pr_number}",
        "url": f"https://github.com/owner/repo/pull/{pr_number}",
        "sourceType": attachment_type,
        "metadata": {},
    }


def _mock_gh_pr_merged(pr_number: int):
    """Mock subprocess result for a merged PR."""
    return MagicMock(returncode=0, stdout=json.dumps({"mergedAt": "2024-01-15T10:00:00Z"}), stderr="")


def _mock_gh_pr_unmerged(pr_number: int):
    """Mock subprocess result for an unmerged PR."""
    return MagicMock(returncode=0, stdout=json.dumps({"mergedAt": None}), stderr="")


def _mock_gh_pr_failed(pr_number: int):
    """Mock subprocess result for a failed gh pr view."""
    return MagicMock(returncode=1, stdout="", stderr="PR not found")


def _issue_body_with_linkback(rule_id: str, location: str, linear_id: str, category: str = None) -> str:
    """Build an issue body with linear-linkback comment."""
    parts = [
        f"**Rule ID**: {rule_id}",
        f"**Location**: {location}",
    ]
    if category:
        parts.insert(1, f"**Category**: {category}")
    parts.append(f"<!-- linear-linkback {linear_id} -->")
    return "\n".join(parts)


def _issue_body_without_linkback(rule_id: str, location: str, category: str = None) -> str:
    """Build an issue body without linear-linkback comment."""
    parts = [
        f"**Rule ID**: {rule_id}",
        f"**Location**: {location}",
    ]
    if category:
        parts.insert(1, f"**Category**: {category}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# VAL-CLOSE-021: Linkback extraction from well-formed HTML comment
# ---------------------------------------------------------------------------


class TestVALCLOSE021:
    """Well-formed linkback extraction."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_extracts_correct_infra_id(self, mock_urlopen):
        """VAL-CLOSE-021: INFRA-123 extracted from <!-- linear-linkback INFRA-123 -->."""
        issue_body = _issue_body_with_linkback("RULE_001", "file.py", "INFRA-123")

        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen({"data": {"issue": None}}))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        _eu()._verify_fix_merged_via_linear(issue_body)

        # Verify the Linear API was called with INFRA-123
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["variables"]["id"] == "INFRA-123"


# ---------------------------------------------------------------------------
# VAL-CLOSE-022: Malformed linkback comments
# ---------------------------------------------------------------------------


class TestVALCLOSE022:
    """Malformed linkback treated as no valid ID -> backward compat close."""

    def test_no_number_part(self):
        """VAL-CLOSE-022: <!-- linear-linkback INFRA- --> has marker, no extractable ID -> fail-closed."""
        issue_body = "Some text\n<!-- linear-linkback INFRA- -->\nMore text"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # P0-1: marker present but no ID -> fail-closed

    def test_non_numeric_id(self):
        """VAL-CLOSE-022: <!-- linear-linkback INFRA-abc --> has marker, no extractable ID -> fail-closed."""
        issue_body = "<!-- linear-linkback INFRA-abc -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # P0-1: marker present but no ID -> fail-closed

    def test_extra_whitespace_variations(self):
        """VAL-CLOSE-022: Extra whitespace but valid INFRA-42 still extracted."""
        issue_body = "<!--  linear-linkback  INFRA-42  -->"
        # Without API key + linkback present -> fail-closed (returns False)
        with patch.dict(os.environ, {}, clear=True):
            result = _eu()._verify_fix_merged_via_linear(issue_body)
            assert result is False  # fail-closed due to missing key


# ---------------------------------------------------------------------------
# VAL-CLOSE-023: Multiple linkback comments - deterministic selection
# ---------------------------------------------------------------------------


class TestVALCLOSE023:
    """Multiple linkback comments - first match wins."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_first_linkback_selected(self, mock_urlopen):
        """VAL-CLOSE-023: Multiple linkbacks -> first match selected deterministically."""
        issue_body = (
            "**Rule ID**: RULE_001\n"
            "**Location**: file.py\n"
            "<!-- linear-linkback INFRA-100 -->\n"
            "Some content\n"
            "<!-- linear-linkback INFRA-200 -->\n"
        )

        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen({"data": {"issue": None}}))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        _eu()._verify_fix_merged_via_linear(issue_body)

        # Should be called exactly once with INFRA-100 (first match)
        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["variables"]["id"] == "INFRA-100"


# ---------------------------------------------------------------------------
# VAL-CLOSE-024: Truncated HTML comment
# ---------------------------------------------------------------------------


class TestVALCLOSE024:
    """Truncated HTML comment treated as no valid ID."""

    def test_truncated_without_closing(self):
        """VAL-CLOSE-024: <!-- linear-linkback INFRA-123 (no closing -->) has marker, no extractable ID -> fail-closed."""
        issue_body = "text\n<!-- linear-linkback INFRA-123\nmore text"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # P0-1: marker present but no ID -> fail-closed


# ---------------------------------------------------------------------------
# VAL-CLOSE-005: No linkback -> backward compat close
# ---------------------------------------------------------------------------


class TestVALCLOSE005:
    """No INFRA-xxx linkback -> backward compat close (no verification)."""

    def test_no_linkback_returns_true(self):
        """VAL-CLOSE-005: No linear-linkback comment -> returns True (backward compat)."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is True

    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_no_linkback_no_linear_api_call(self, mock_urlopen):
        """VAL-CLOSE-005: No linkback -> urlopen NOT called."""
        issue_body = "Just some regular issue body"
        result = _eu()._verify_fix_merged_via_linear(issue_body)

        assert result is True
        assert not mock_urlopen.called


# ---------------------------------------------------------------------------
# VAL-CLOSE-020: LINEAR_API_KEY missing -> fail-closed for Linear-linked issues
# ---------------------------------------------------------------------------


class TestVALCLOSE020:
    """LINEAR_API_KEY missing -> fail-closed for linked issues (prevents churn).

    When a Linear linkback IS present but the API key is missing, we must NOT
    close — the Linear native GitHub integration would reopen the issue,
    causing infinite close/reopen churn. This is the core fix for the
    #454/#456/#457 churn loop.
    """

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_with_linkback_returns_false(self):
        """VAL-CLOSE-020: LINEAR_API_KEY not set + linkback present -> returns False (fail-closed)."""
        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed — prevent Linear reopen churn

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_without_linkback_returns_true(self):
        """VAL-CLOSE-020: LINEAR_API_KEY not set + no linkback -> returns True (environmental)."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is True  # backward compat for environmental findings


# ---------------------------------------------------------------------------
# VAL-CLOSE-004: Linear API error -> fail-closed (VAL-FAILOPEN-003, VAL-FAILOPEN-004)
# ---------------------------------------------------------------------------


class TestVALCLOSE004:
    """Linear API error/unreachable -> fail-closed (prevents unverified close)."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_urlerror_fail_closed(self, mock_urlopen):
        """VAL-CLOSE-004/VAL-FAILOPEN-003: URLError -> fail-closed, returns False."""
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
        issue_body = "<!-- linear-linkback INFRA-123 -->"

        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_timeout_fail_closed(self, mock_urlopen):
        """VAL-CLOSE-004/VAL-FAILOPEN-004: Timeout -> fail-closed, returns False."""
        mock_urlopen.side_effect = TimeoutError("timed out")
        issue_body = "<!-- linear-linkback INFRA-123 -->"

        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed


# ---------------------------------------------------------------------------
# VAL-CLOSE-013: Linear GraphQL errors field -> fail-closed (VAL-FAILOPEN-001)
# ---------------------------------------------------------------------------


class TestVALCLOSE013:
    """Linear GraphQL errors field -> fail-closed (prevents unverified close)."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_graphql_errors_field(self, mock_urlopen):
        """VAL-CLOSE-013/VAL-FAILOPEN-001: Response has 'errors' field -> fail-closed, returns False."""
        mock_urlopen.return_value.__enter__ = MagicMock(
            return_value=_mock_urlopen({"errors": [{"message": "Something went wrong"}]})
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed


# ---------------------------------------------------------------------------
# VAL-CLOSE-014: Linear issue null -> fail-closed (VAL-FAILOPEN-002)
# ---------------------------------------------------------------------------


class TestVALCLOSE014:
    """Linear issue null (deleted) -> fail-closed (prevents unverified close)."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_issue_null(self, mock_urlopen):
        """VAL-CLOSE-014/VAL-FAILOPEN-002: data.issue is null -> fail-closed, returns False."""
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen({"data": {"issue": None}}))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed


# ---------------------------------------------------------------------------
# VAL-CLOSE-002: No PR in Linear -> NOT closed
# ---------------------------------------------------------------------------


class TestVALCLOSE002:
    """No PR in Linear -> Issue NOT closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_empty_attachments(self, mock_urlopen):
        """VAL-CLOSE-002: Empty attachments -> returns False (NOT closed)."""
        mock_urlopen.return_value.__enter__ = MagicMock(
            return_value=_mock_urlopen(_linear_issue_response("INFRA-123", []))
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_no_gh_pr_view_called(self, mock_urlopen):
        """VAL-CLOSE-002: No PR -> gh pr view NOT called."""
        mock_urlopen.return_value.__enter__ = MagicMock(
            return_value=_mock_urlopen(_linear_issue_response("INFRA-123", []))
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        with patch("infra_core.engine.evolution_utils.subprocess.run") as mock_subprocess:
            _eu()._verify_fix_merged_via_linear(issue_body)
            # No subprocess calls for gh pr view
            assert not mock_subprocess.called


# ---------------------------------------------------------------------------
# VAL-CLOSE-010: INFRA-xxx extracted but no attachments -> NOT closed
# ---------------------------------------------------------------------------


class TestVALCLOSE010:
    """INFRA-xxx extracted but no attachments -> NOT closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_no_attachments_of_any_type(self, mock_urlopen):
        """VAL-CLOSE-010: Linear issue exists but attachments empty -> returns False."""
        mock_urlopen.return_value.__enter__ = MagicMock(
            return_value=_mock_urlopen(_linear_issue_response("INFRA-456", []))
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-456 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False


# ---------------------------------------------------------------------------
# VAL-CLOSE-016: Non-github attachments ignored
# ---------------------------------------------------------------------------


class TestVALCLOSE016:
    """Non-github attachments ignored -> treated as no associated PR."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_only_url_attachments(self, mock_urlopen):
        """VAL-CLOSE-016: Only non-github attachments -> returns False."""
        mock_urlopen.return_value.__enter__ = MagicMock(
            return_value=_mock_urlopen(
                _linear_issue_response(
                    "INFRA-789",
                    [
                        _github_attachment(1, attachment_type="url"),
                    ],
                )
            )
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        # Fix the attachment type
        response = _linear_issue_response(
            "INFRA-789", [{"id": "att-1", "url": "https://example.com/doc.pdf", "sourceType": "url", "metadata": {}}]
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))

        issue_body = "<!-- linear-linkback INFRA-789 -->"
        with patch("infra_core.engine.evolution_utils.subprocess.run") as mock_subprocess:
            result = _eu()._verify_fix_merged_via_linear(issue_body)
            assert result is False
            # No gh pr view call
            assert not mock_subprocess.called


# ---------------------------------------------------------------------------
# VAL-CLOSE-003: PR exists but not merged -> NOT closed
# ---------------------------------------------------------------------------


class TestVALCLOSE003:
    """PR exists but not merged -> Issue NOT closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_unmerged_pr(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-003: PR exists, mergedAt null -> returns False."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(100)])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_unmerged(100)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False


# ---------------------------------------------------------------------------
# VAL-CLOSE-015: PR number correctly extracted from attachment URL
# ---------------------------------------------------------------------------


class TestVALCLOSE015:
    """PR number correctly extracted from GitHub attachment URL."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_pr_number_extracted_from_url(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-015: gh pr view receives PR number 523, not the full URL."""
        response = _linear_issue_response(
            "INFRA-123",
            [
                {
                    "id": "att-523",
                    "url": "https://github.com/hdot123-org/memory/pull/523",
                    "sourceType": "github",
                    "metadata": {},
                }
            ],
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_merged(523)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        _eu()._verify_fix_merged_via_linear(issue_body)

        # Verify gh pr view received "523", not the URL
        assert mock_subprocess.called
        call_args = mock_subprocess.call_args[0][0]
        assert "523" in call_args
        assert "https://github.com/hdot123-org/memory/pull/523" not in call_args


# ---------------------------------------------------------------------------
# VAL-CLOSE-025: Cross-repo PR - repo extracted from URL for gh pr view --repo
# ---------------------------------------------------------------------------


class TestVALCLOSE025:
    """Cross-repo PR verification: --repo flag passed to gh pr view."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_cross_repo_pr_passes_repo_flag(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-025: Cross-repo PR -> gh pr view includes --repo owner/name."""
        response = _linear_issue_response(
            "INFRA-123",
            [
                {
                    "id": "att-42",
                    "url": "https://github.com/hdot123-org/infra-core/pull/42",
                    "sourceType": "github",
                    "metadata": {},
                }
            ],
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_merged(42)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)

        # gh pr view called with --repo hdot123-org/infra-core（跨仓 fixture：
        # 原用 shared-workflows 仓，M6 退役后换 infra-core，语义不变——URL 仓
        # 与默认仓不同即验证 --repo 提取）
        assert mock_subprocess.called
        call_args = mock_subprocess.call_args[0][0]
        assert "42" in call_args
        assert "--repo" in call_args
        repo_idx = call_args.index("--repo")
        assert call_args[repo_idx + 1] == "hdot123-org/infra-core"
        assert result is True

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_cross_repo_pr_unmerged_returns_false(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-025: Cross-repo PR not merged -> returns False (no fail-open)."""
        response = _linear_issue_response(
            "INFRA-123",
            [
                {
                    "id": "att-42",
                    "url": "https://github.com/hdot123-org/infra-core/pull/42",
                    "sourceType": "github",
                    "metadata": {},
                }
            ],
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_unmerged(42)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_same_repo_pr_also_passes_repo_flag(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-025: Same-repo PR -> --repo still passed (explicit context)."""
        response = _linear_issue_response(
            "INFRA-123",
            [
                {
                    "id": "att-523",
                    "url": "https://github.com/hdot123-org/memory/pull/523",
                    "sourceType": "github",
                    "metadata": {},
                }
            ],
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_merged(523)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        _eu()._verify_fix_merged_via_linear(issue_body)

        assert mock_subprocess.called
        call_args = mock_subprocess.call_args[0][0]
        assert "--repo" in call_args
        repo_idx = call_args.index("--repo")
        assert call_args[repo_idx + 1] == "hdot123-org/memory"


# ---------------------------------------------------------------------------
# VAL-CLOSE-001: Happy path - merged PR -> closed
# ---------------------------------------------------------------------------


class TestVALCLOSE001:
    """Happy path - absent 2+ ticks + merged PR -> Issue closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_merged_pr_returns_true(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-001: Merged PR verified -> returns True."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(523)])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_merged(523)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is True

        # INFRA-372: query must not reference removed `attachmentType` field
        # (Linear GraphQL validation 400 permanently fail-closes the trust
        # chain). The discriminator is `sourceType`.
        req = mock_urlopen.call_args[0][0]
        sent_query = json.loads(req.data.decode())["query"]
        assert "attachmentType" not in sent_query
        assert "sourceType" in sent_query


# ---------------------------------------------------------------------------
# VAL-CLOSE-008: Multiple PRs - one merged -> Issue closed
# ---------------------------------------------------------------------------


class TestVALCLOSE008:
    """Multiple PRs - one merged -> Issue closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_one_merged_among_multiple(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-008: Multiple PRs, one merged -> returns True."""
        response = _linear_issue_response(
            "INFRA-123",
            [
                _github_attachment(100),
                _github_attachment(200),
            ],
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        # First PR unmerged, second PR merged (short-circuit)
        mock_subprocess.side_effect = [
            _mock_gh_pr_unmerged(100),
            _mock_gh_pr_merged(200),
        ]

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is True
        assert mock_subprocess.call_count == 2


# ---------------------------------------------------------------------------
# VAL-CLOSE-009: Multiple PRs all unmerged -> NOT closed
# ---------------------------------------------------------------------------


class TestVALCLOSE009:
    """Multiple PRs all unmerged -> Issue NOT closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_all_unmerged(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-009: All PRs unmerged -> returns False."""
        response = _linear_issue_response(
            "INFRA-123",
            [
                _github_attachment(100),
                _github_attachment(200),
            ],
        )
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.side_effect = [
            _mock_gh_pr_unmerged(100),
            _mock_gh_pr_unmerged(200),
        ]

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False
        assert mock_subprocess.call_count == 2


# ---------------------------------------------------------------------------
# VAL-CLOSE-018: gh pr view failure -> fail-closed (block close)
# ---------------------------------------------------------------------------


class TestVALCLOSE018:
    """gh pr view failure -> fail-closed (block close)."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_gh_pr_view_nonzero(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-018: gh pr view returns non-zero -> fail-closed (block close)."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(100)])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_failed(100)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_gh_pr_view_exception(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-018: gh pr view throws exception -> fail-closed (block close)."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(100)])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.side_effect = OSError("gh not found")

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # fail-closed


# ---------------------------------------------------------------------------
# VAL-CLOSE-006: Grace period checked before PR-Merged verification
# ---------------------------------------------------------------------------


class TestVALCLOSE006:
    """Grace period still applies - absent only 1 tick -> NOT closed, no verification."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_absent_1_tick_no_verification(self, mock_subprocess):
        """VAL-CLOSE-006: 1 absence < GRACE_PERIOD_TICKS -> no Linear API, no close."""
        findings = []  # RULE_001 absent from current scan
        mock_issues = [{"number": 101, "body": _issue_body_with_linkback("RULE_001", "file.py", "INFRA-123")}]
        mock_subprocess.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues), stderr="")

        history_data = {
            "snapshots": [
                {"findings": [{"rule_id": "RULE_001", "location": "file.py"}]},
                {"findings": []},  # only 1 absence
            ],
            "resolved_findings": [],
        }

        with (
            patch("infra_core.engine.evolution_utils.load_history", return_value=history_data),
            patch("infra_core.engine.evolution_utils._verify_fix_merged_via_linear") as mock_verify,
        ):
            _eu().auto_close_resolved(findings, "evolution-found", history_path=Path("/tmp/test_history.json"))

            # _verify_fix_merged_via_linear should NOT be called
            assert not mock_verify.called

            # No close call
            close_calls = [c for c in mock_subprocess.call_args_list if len(c[0]) > 2 and c[0][0][2] == "close"]
            assert len(close_calls) == 0


# ---------------------------------------------------------------------------
# VAL-CLOSE-007: GAP-C1 checked before PR-Merged verification
# ---------------------------------------------------------------------------


class TestVALCLOSE007:
    """GAP-C1 still applies - failed category -> NOT closed, no verification."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_failed_category_no_verification(self, mock_subprocess):
        """VAL-CLOSE-007: Category in failed_categories -> no Linear API, no close."""
        findings = []  # RULE_001 absent
        mock_issues = [
            {
                "number": 101,
                "body": _issue_body_with_linkback("RULE_001", "file.py", "INFRA-123", category="daily_audit"),
            }
        ]
        mock_subprocess.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues), stderr="")

        history_data = {
            "snapshots": [
                {"findings": [{"rule_id": "RULE_001", "location": "file.py"}]},
                {"findings": []},
                {"findings": []},  # 2 absences (grace period met)
            ],
            "resolved_findings": [],
        }

        with (
            patch("infra_core.engine.evolution_utils.load_history", return_value=history_data),
            patch("infra_core.engine.evolution_utils._verify_fix_merged_via_linear") as mock_verify,
        ):
            _eu().auto_close_resolved(
                findings,
                "evolution-found",
                failed_categories={"daily_audit"},
                history_path=Path("/tmp/test_history.json"),
            )

            # _verify_fix_merged_via_linear should NOT be called
            assert not mock_verify.called

            # No close call
            close_calls = [c for c in mock_subprocess.call_args_list if len(c[0]) > 2 and c[0][0][2] == "close"]
            assert len(close_calls) == 0


# ---------------------------------------------------------------------------
# VAL-CLOSE-011: Verification ordering - grace period first
# ---------------------------------------------------------------------------


class TestVALCLOSE011:
    """Verification ordering - grace period checked before PR-Merged verification."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_1_absence_no_linear_call(self, mock_subprocess):
        """VAL-CLOSE-011: With 1 absent tick, urlopen NOT called."""
        findings = []
        mock_issues = [{"number": 101, "body": _issue_body_with_linkback("RULE_001", "file.py", "INFRA-123")}]
        mock_subprocess.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues), stderr="")

        history_data = {
            "snapshots": [
                {"findings": [{"rule_id": "RULE_001", "location": "file.py"}]},
                {"findings": []},  # only 1 absence
            ],
            "resolved_findings": [],
        }

        with (
            patch("infra_core.engine.evolution_utils.load_history", return_value=history_data),
            patch("infra_core.engine.evolution_utils.urllib.request.urlopen") as mock_urlopen,
        ):
            _eu().auto_close_resolved(findings, "evolution-found", history_path=Path("/tmp/test_history.json"))
            assert not mock_urlopen.called


# ---------------------------------------------------------------------------
# VAL-CLOSE-012: Verification ordering - GAP-C1 first
# ---------------------------------------------------------------------------


class TestVALCLOSE012:
    """Verification ordering - GAP-C1 checked before PR-Merged verification."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_failed_category_no_linear_call(self, mock_subprocess):
        """VAL-CLOSE-012: With failed category + 2 ticks, urlopen NOT called."""
        findings = []
        mock_issues = [
            {
                "number": 101,
                "body": _issue_body_with_linkback("RULE_001", "file.py", "INFRA-123", category="daily_audit"),
            }
        ]
        mock_subprocess.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues), stderr="")

        history_data = {
            "snapshots": [
                {"findings": [{"rule_id": "RULE_001", "location": "file.py"}]},
                {"findings": []},
                {"findings": []},  # 2 absences
            ],
            "resolved_findings": [],
        }

        with (
            patch("infra_core.engine.evolution_utils.load_history", return_value=history_data),
            patch("infra_core.engine.evolution_utils.urllib.request.urlopen") as mock_urlopen,
        ):
            _eu().auto_close_resolved(
                findings,
                "evolution-found",
                failed_categories={"daily_audit"},
                history_path=Path("/tmp/test_history.json"),
            )
            assert not mock_urlopen.called


# ---------------------------------------------------------------------------
# VAL-CLOSE-017: Multiple stale issues with mixed PR states
# ---------------------------------------------------------------------------


class TestVALCLOSE017:
    """Multiple stale issues with mixed PR states - only merged-PR and backward-compat closed."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_mixed_pr_states(self, mock_urlopen, mock_subprocess):
        """VAL-CLOSE-017: Merged PR + no linkback + unmerged PR -> correct close decisions."""
        mock_issues = [
            {"number": 101, "body": _issue_body_with_linkback("RULE_001", "file1.py", "INFRA-100")},
            {"number": 102, "body": _issue_body_without_linkback("RULE_002", "file2.py")},
            {"number": 103, "body": _issue_body_with_linkback("RULE_003", "file3.py", "INFRA-300")},
        ]

        history_data = {
            "snapshots": [
                {
                    "findings": [
                        {"rule_id": "RULE_001", "location": "file1.py"},
                        {"rule_id": "RULE_002", "location": "file2.py"},
                        {"rule_id": "RULE_003", "location": "file3.py"},
                    ]
                },
                {"findings": []},
                {"findings": []},
                {"findings": []},
            ],
            "resolved_findings": [],
        }

        # Setup Linear API mocks
        def urlopen_side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "data": {
                        "issue": {
                            "id": "test",
                            "state": {"id": "s1", "name": "Done", "type": "completed"},
                            "attachments": {
                                "nodes": [
                                    {
                                        "id": "att",
                                        "url": "https://github.com/o/r/pull/99",
                                        "sourceType": "github",
                                        "metadata": {},
                                    }
                                ]
                            },
                        }
                    }
                }
            ).encode()
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=mock_resp)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        mock_urlopen.side_effect = urlopen_side_effect

        # Setup subprocess mocks - order matters!
        # Issues #101 and #103 have linkback in body → comment fetch SKIPPED
        # Issue #102 has no linkback → comment fetch happens
        # 1. gh issue list
        # 2. gh pr view 99 (for #101) - merged -> verify returns True
        # 3. gh issue close 101
        # 4. comment fetch for #102 (no linkback in body)
        # 5. gh issue close 102
        # 6. gh pr view 99 (for #103) - unmerged -> verify returns False
        mock_subprocess.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(mock_issues), stderr=""),  # gh issue list
            MagicMock(returncode=0, stdout=json.dumps({"mergedAt": "2024-01-01"}), stderr=""),  # gh pr view 99 for #101
            MagicMock(returncode=0, stdout="", stderr=""),  # gh issue close 101
            MagicMock(returncode=0, stdout="", stderr=""),  # comment fetch for #102
            MagicMock(returncode=0, stdout="", stderr=""),  # gh issue close 102
            MagicMock(returncode=0, stdout=json.dumps({"mergedAt": None}), stderr=""),  # gh pr view 99 for #103
        ]

        with patch("infra_core.engine.evolution_utils.load_history", return_value=history_data):
            _eu().auto_close_resolved([], "evolution-found", history_path=Path("/tmp/test_history.json"))

        # Find close calls
        close_calls = [
            c for c in mock_subprocess.call_args_list if len(c[0][0]) > 3 and c[0][0][0:3] == ["gh", "issue", "close"]
        ]

        closed_numbers = [c[0][0][3] for c in close_calls]
        assert "101" in closed_numbers  # merged PR -> closed
        assert "102" in closed_numbers  # no linkback -> closed (backward compat)
        assert "103" not in closed_numbers  # unmerged PR -> NOT closed


# ---------------------------------------------------------------------------
# VAL-CLOSE-019: Close comment format preserved
# ---------------------------------------------------------------------------


class TestVALCLOSE019:
    """Close comment format preserved - contains rule_id and location."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_close_comment_contains_rule_and_location(self, mock_urlopen, mock_subprocess):
        """VAL-CLOSE-019: Close comment contains rule_id, location, and existing text."""
        mock_issues = [{"number": 101, "body": _issue_body_with_linkback("RULE_001", "test/file.py", "INFRA-123")}]

        history_data = {
            "snapshots": [
                {"findings": [{"rule_id": "RULE_001", "location": "test/file.py"}]},
                {"findings": []},
                {"findings": []},
                {"findings": []},
            ],
            "resolved_findings": [],
        }

        # Setup Linear API mock
        response = _linear_issue_response("INFRA-123", [_github_attachment(523)])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        # Setup subprocess mocks
        # Issue #101 has linkback in body → comment fetch SKIPPED
        # 1. gh issue list
        # 2. gh pr view (merged)
        # 3. gh issue close
        mock_subprocess.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(mock_issues), stderr=""),  # gh issue list
            MagicMock(returncode=0, stdout=json.dumps({"mergedAt": "2024-01-01"}), stderr=""),  # gh pr view
            MagicMock(returncode=0, stdout="", stderr=""),  # gh issue close
        ]

        with patch("infra_core.engine.evolution_utils.load_history", return_value=history_data):
            _eu().auto_close_resolved([], "evolution-found", history_path=Path("/tmp/test_history.json"))

        # Find the close call
        close_calls = [
            c for c in mock_subprocess.call_args_list if len(c[0][0]) > 3 and c[0][0][0:3] == ["gh", "issue", "close"]
        ]
        assert len(close_calls) == 1

        call_args = close_calls[0][0][0]
        comment_idx = call_args.index("--comment")
        comment_text = call_args[comment_idx + 1]

        assert "RULE_001" in comment_text
        assert "test/file.py" in comment_text
        assert "最近一次扫描" in comment_text


# ---------------------------------------------------------------------------
# VAL-CLOSE-026: Linkback found in comments (not body) — Linear integration writes it there
# ---------------------------------------------------------------------------


class TestVALCLOSE026:
    """Linear linkback found in issue comments (not body)."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_linkback_in_comments_detected(self, mock_urlopen, mock_subprocess):
        """VAL-CLOSE-026: Linkback in comments -> Linear API queried with correct ID."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"

        # Mock gh issue view to return comments with linkback
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            if "view" in cmd and "comments" in cmd:
                return MagicMock(returncode=0, stdout="Some comment\n<!-- linear-linkback INFRA-500 -->", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.side_effect = subprocess_side_effect

        response = _linear_issue_response("INFRA-500", [_github_attachment(300)])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        _eu()._verify_fix_merged_via_linear(issue_body, issue_number=42)

        # Should have queried Linear API (linkback found in comments)
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["variables"]["id"] == "INFRA-500"

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_no_issue_number_no_comment_search(self, mock_urlopen, mock_subprocess):
        """VAL-CLOSE-026: Without issue_number, comments NOT searched (backward compat)."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"

        # gh issue view should NOT be called for comments
        result = _eu()._verify_fix_merged_via_linear(issue_body)  # no issue_number

        assert result is True  # no linkback in body, no comment search
        assert not mock_urlopen.called

    # ---------------------------------------------------------------------------
    # VAL-CLOSE-027: Linear issue NOT in terminal state -> block close
    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_linkback_in_body_skips_comment_fetch(self, mock_urlopen, mock_subprocess):
        """VAL-CLOSE-026: Linkback in body → comment fetch NOT called (optimization)."""
        issue_body = "**Rule ID**: RULE_001\n<!-- linear-linkback INFRA-400 -->"

        response = _linear_issue_response("INFRA-400", [])
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        _eu()._verify_fix_merged_via_linear(issue_body, issue_number=42)

        # No PR attachments → returns False, but the important check is:
        # gh issue view (comment fetch) should NOT have been called at all
        comment_fetch_calls = [
            c for c in mock_subprocess.call_args_list if c[0] and "view" in c[0][0] and "comments" in c[0][0]
        ]
        assert len(comment_fetch_calls) == 0


# ---------------------------------------------------------------------------


class TestVALCLOSE027:
    """Linear issue in non-terminal state -> block close (churn prevention).

    This is the core gate that prevents the close/reopen churn loop.
    When Linear issue is "In Progress" or "In Review", closing the GitHub
    issue causes the Linear native GitHub integration to reopen it.
    """

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_non_terminal_state_blocks_close(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-027: Linear state 'started' (In Progress) -> returns False."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(523)], state_type="started")  # Non-terminal!
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_merged(523)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # Non-terminal state blocks close

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_canceled_state_allows_close(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-027: Linear state 'canceled' -> returns True (terminal)."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(523)], state_type="canceled")
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        mock_subprocess.return_value = _mock_gh_pr_merged(523)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is True  # Canceled is terminal

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_non_terminal_no_pr_check(self, mock_subprocess, mock_urlopen):
        """VAL-CLOSE-027: Non-terminal state -> PR merge NOT checked (short-circuit)."""
        response = _linear_issue_response("INFRA-123", [_github_attachment(523)], state_type="started")  # Non-terminal!
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        _eu()._verify_fix_merged_via_linear(issue_body)

        # gh pr view should NOT be called (short-circuited by state check)
        assert not mock_subprocess.called


# ---------------------------------------------------------------------------
# VAL-FAILOPEN-005: Comment fetch failure -> fail-closed
# ---------------------------------------------------------------------------


class TestVALFAILOPEN005:
    """Comment fetch failure (non-zero return code) -> fail-closed (VAL-FAILOPEN-005)."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_comment_fetch_nonzero_returns_false(self, mock_subprocess):
        """VAL-FAILOPEN-005: Comment fetch returns non-zero -> returns False."""
        mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="gh: issue not found")
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"
        # No linkback in body, so it tries to fetch comments
        result = _eu()._verify_fix_merged_via_linear(issue_body, issue_number=123)
        assert result is False  # fail-closed


# ---------------------------------------------------------------------------
# VAL-FAILOPEN-006: Comment fetch exception -> fail-closed
# ---------------------------------------------------------------------------


class TestVALFAILOPEN006:
    """Comment fetch exception -> fail-closed (VAL-FAILOPEN-006)."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_comment_fetch_exception_returns_false(self, mock_subprocess):
        """VAL-FAILOPEN-006: Comment fetch raises exception -> returns False."""
        mock_subprocess.side_effect = Exception("subprocess failed")
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"
        # No linkback in body, so it tries to fetch comments
        result = _eu()._verify_fix_merged_via_linear(issue_body, issue_number=123)
        assert result is False  # fail-closed


# ---------------------------------------------------------------------------
# VAL-FAILOPEN-007: Warning logs for all fail-closed paths
# ---------------------------------------------------------------------------


class TestVALFAILOPEN007:
    """All fail-closed paths must emit warning-level logs (VAL-FAILOPEN-007)."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_graphql_errors_warning_log(self, mock_urlopen, caplog):
        """VAL-FAILOPEN-007: GraphQL errors -> warning log."""
        mock_urlopen.return_value.__enter__ = MagicMock(
            return_value=_mock_urlopen({"errors": [{"message": "API error"}]})
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        import logging

        with caplog.at_level(logging.WARNING):
            _eu()._verify_fix_merged_via_linear(issue_body)

        assert any("fail-closed" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_issue_null_warning_log(self, mock_urlopen, caplog):
        """VAL-FAILOPEN-007: Issue null -> warning log."""
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen({"data": {"issue": None}}))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        issue_body = "<!-- linear-linkback INFRA-123 -->"
        import logging

        with caplog.at_level(logging.WARNING):
            _eu()._verify_fix_merged_via_linear(issue_body)

        assert any("fail-closed" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_urlerror_warning_log(self, mock_urlopen, caplog):
        """VAL-FAILOPEN-007: URLError -> warning log."""
        mock_urlopen.side_effect = urllib.error.URLError("Network error")
        issue_body = "<!-- linear-linkback INFRA-123 -->"

        import logging

        with caplog.at_level(logging.WARNING):
            _eu()._verify_fix_merged_via_linear(issue_body)

        assert any("fail-closed" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_generic_exception_warning_log(self, mock_urlopen, caplog):
        """VAL-FAILOPEN-007: Generic exception -> warning log."""
        mock_urlopen.side_effect = RuntimeError("Unexpected error")
        issue_body = "<!-- linear-linkback INFRA-123 -->"

        import logging

        with caplog.at_level(logging.WARNING):
            _eu()._verify_fix_merged_via_linear(issue_body)

        assert any("fail-closed" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_comment_fetch_failure_warning_log(self, mock_subprocess, caplog):
        """VAL-FAILOPEN-007: Comment fetch failure -> warning log."""
        mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="gh: issue not found")
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"

        import logging

        with caplog.at_level(logging.WARNING):
            _eu()._verify_fix_merged_via_linear(issue_body, issue_number=123)

        assert any("fail-closed" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_comment_fetch_exception_warning_log(self, mock_subprocess, caplog):
        """VAL-FAILOPEN-007: Comment fetch exception -> warning log."""
        mock_subprocess.side_effect = Exception("subprocess failed")
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"

        import logging

        with caplog.at_level(logging.WARNING):
            _eu()._verify_fix_merged_via_linear(issue_body, issue_number=123)

        assert any("fail-closed" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)


# ---------------------------------------------------------------------------
# VAL-CROSS-022/023/024/026: Two-tier linkback extraction + fail-closed narrowing
# Regression fixtures from the #648 oscillation (25 false closures).
# ---------------------------------------------------------------------------

# Real accident text written by linear-code for #648 (anchor + href format).
# This is the exact format that caused 25 false closures because the old regex
# only matched the ID inside the HTML comment, but linear-code writes a bare
# marker plus an external anchor.
_REAL_ACCIDENT_LINKBACK_COMMENT = (
    '<!-- linear-linkback -->\n<p><a href="https://linear.app/jtoom/issue/INFRA-292">INFRA-292</a></p>'
)


class TestVALCROSS022:
    """VAL-CROSS-022: Anchor-format linkback extracted + Linear started -> block close."""

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_anchor_format_started_state_blocks_close(self, mock_subprocess):
        """Real accident format in comments + Linear started -> no gh issue close."""
        # Issue body has no linkback; comments have the real accident format
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"

        # Mock gh issue view comments -> real accident linkback
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            if cmd[0] == "gh" and "view" in cmd and "comments" in " ".join(cmd):
                return MagicMock(returncode=0, stdout=_REAL_ACCIDENT_LINKBACK_COMMENT, stderr="")
            # gh issue list
            return MagicMock(returncode=0, stdout="[]", stderr="")

        mock_subprocess.side_effect = subprocess_side_effect

        # Linear API returns "started" state (non-terminal)
        response = _linear_issue_response("INFRA-292", [_github_attachment(523)], state_type="started")
        with patch("infra_core.engine.evolution_utils.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            result = _eu()._verify_fix_merged_via_linear(issue_body, issue_number=42)

        # Non-terminal state must block close (core churn-prevention gate)
        assert result is False

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_anchor_format_id_extracted(self, mock_subprocess):
        """Two-tier extraction: anchor text format correctly extracts INFRA-292."""
        from infra_core.engine.evolution_utils import _extract_linear_linkback

        result = _extract_linear_linkback("", _REAL_ACCIDENT_LINKBACK_COMMENT)
        assert result == "INFRA-292"

    @patch("infra_core.engine.evolution_utils.subprocess.run")
    def test_href_format_id_extracted(self, mock_subprocess):
        """Two-tier extraction: href format correctly extracts INFRA-292."""
        from infra_core.engine.evolution_utils import _extract_linear_linkback

        # Must have linear-linkback marker to trigger tier 2
        href_with_marker = '<!-- linear-linkback -->\n<a href="https://linear.app/jtoom/issue/INFRA-292">link</a>'
        result = _extract_linear_linkback("", href_with_marker)
        assert result == "INFRA-292"


class TestVALCROSS023:
    """VAL-CROSS-023: Anchor-format linkback + completed state + merged PR -> allow close."""

    @patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"})
    @patch("infra_core.engine.evolution_utils.subprocess.run")
    @patch("infra_core.engine.evolution_utils.urllib.request.urlopen")
    def test_anchor_format_completed_merged_allows_close(self, mock_urlopen, mock_subprocess):
        """Real accident format + completed + merged PR -> returns True (allow close)."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"

        # Mock comment fetch returns real accident linkback
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            # gh issue view (comment fetch) — has "issue" subcommand
            if cmd[0] == "gh" and "issue" in cmd and "view" in cmd:
                return MagicMock(returncode=0, stdout=_REAL_ACCIDENT_LINKBACK_COMMENT, stderr="")
            # gh pr view (merged PR check) — has "pr" subcommand
            if cmd[0] == "gh" and "pr" in cmd:
                return _mock_gh_pr_merged(523)
            return MagicMock(returncode=0, stdout="[]", stderr="")

        mock_subprocess.side_effect = subprocess_side_effect

        # Linear API returns completed state with merged PR
        response = _linear_issue_response("INFRA-292", [_github_attachment(523)], state_type="completed")
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=_mock_urlopen(response))
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _eu()._verify_fix_merged_via_linear(issue_body, issue_number=42)
        assert result is True  # Terminal state + merged PR -> allow close


class TestVALCROSS024:
    """VAL-CROSS-024: No linear traces at all -> backward-compat allow close."""

    def test_no_linear_traces_allows_close(self):
        """Completely no linear-linkback marker or traces -> returns True (backward compat)."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py\n**Category**: code_hygiene"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is True  # Environmental finding, no Linear association

    def test_no_linear_traces_no_api_call(self):
        """No linear traces -> Linear API NOT called."""
        issue_body = "Just a regular issue body with no Linear references"
        with patch("infra_core.engine.evolution_utils.urllib.request.urlopen") as mock_urlopen:
            result = _eu()._verify_fix_merged_via_linear(issue_body)
            assert result is True
            assert not mock_urlopen.called


class TestVALCROSS026:
    """VAL-CROSS-026: Marker present but ID not extractable -> fail-closed (block close)."""

    def test_marker_without_id_fail_closed(self):
        """linear-linkback marker present but no extractable ID -> fail-closed."""
        # Bare marker with no ID anywhere (malformed linkback)
        issue_body = "**Rule ID**: RULE_001\n<!-- linear-linkback -->\nSome text with no INFRA-xxx ID"
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # P0-1: marker present -> fail-closed

    def test_marker_in_comments_without_id_fail_closed(self):
        """Marker in comments but no extractable ID -> fail-closed."""
        issue_body = "**Rule ID**: RULE_001\n**Location**: file.py"
        # Comments have marker but no extractable ID
        comments_text = "<!-- linear-linkback -->\nSome unrelated text"

        with patch("infra_core.engine.evolution_utils.subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(returncode=0, stdout=comments_text, stderr="")
            result = _eu()._verify_fix_merged_via_linear(issue_body, issue_number=42)
            assert result is False  # P0-1: marker in comments but no ID -> fail-closed

    def test_marker_with_broken_href_fail_closed(self):
        """Marker present + broken href (no valid INFRA-xxx) -> fail-closed."""
        issue_body = '<!-- linear-linkback -->\n<a href="https://linear.app/jtoom/issue/invalid">broken</a>'
        result = _eu()._verify_fix_merged_via_linear(issue_body)
        assert result is False  # Marker present, tier 2 fails -> fail-closed
