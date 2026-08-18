"""Tests for notification TTL auto-close (VAL-NTF-002, VAL-CROSS-204).

Notification issues (label: automation,branch-cleanup) are auto-closed by
the pipeline after NOTIFICATION_TTL_DAYS (7 days). Non-notification issues
are not affected.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_utils import NOTIFICATION_TTL_DAYS, close_expired_notifications


class TestNotificationTTLConstant:
    """VAL-NTF-002: TTL constant exists and is 7 days."""

    def test_ttl_constant_is_7_days(self):
        """NOTIFICATION_TTL_DAYS is defined as 7."""
        assert NOTIFICATION_TTL_DAYS == 7


class TestCloseExpiredNotifications:
    """TTL expired → close; TTL not expired → don't close; non-notification → skip."""

    def test_ttl_expired_closes_notification_issue(self):
        """VAL-NTF-002: Notification issue older than TTL is closed."""
        # Issue created 10 days ago (past 7-day TTL)
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_issues = [
            {
                "number": 700,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": old_date,
                "body": "Branch cleanup tracking issue",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            # First call: list issues, subsequent calls: comment and close
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=json.dumps(mock_issues)),
                MagicMock(returncode=0, stdout=""),  # comment
                MagicMock(returncode=0, stdout=""),  # close
            ]
            close_expired_notifications()

            # Verify close was called by checking call arguments
            assert mock_run.call_count == 3, "Should make 3 calls: list, comment, close"

            # Check the third call was a close
            close_call_args = mock_run.call_args_list[2][0][0]
            assert "issue" in close_call_args and "close" in close_call_args, \
                "Third call should be issue close"

            # Check the second call was a comment
            comment_call_args = mock_run.call_args_list[1][0][0]
            assert "issue" in comment_call_args and "comment" in comment_call_args, \
                "Second call should be issue comment"

    def test_ttl_not_expired_does_not_close(self):
        """VAL-NTF-002: Notification issue within TTL is NOT closed."""
        # Issue created 3 days ago (within 7-day TTL)
        recent_date = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        mock_issues = [
            {
                "number": 701,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": recent_date,
                "body": "Branch cleanup tracking issue",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues))
            close_expired_notifications()

            # Verify close was NOT called
            calls = mock_run.call_args_list
            close_calls = [c for c in calls if "issue close" in str(c)]
            assert len(close_calls) == 0, "Notification issue within TTL should NOT be closed"

    def test_non_notification_issues_not_affected(self):
        """VAL-NTF-002: Non-notification issues are never closed by TTL logic."""
        # Old issue without notification labels
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        mock_issues = [
            {
                "number": 650,
                "labels": [{"name": "evolution-found"}],
                "createdAt": old_date,
                "body": "**Rule ID**: TEST_RULE\n**Location**: test.py",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues))
            close_expired_notifications()

            # Verify close was NOT called (not a notification issue)
            calls = mock_run.call_args_list
            close_calls = [c for c in calls if "issue close" in str(c)]
            assert len(close_calls) == 0, "Non-notification issues should not be closed by TTL"

    def test_mixed_issues_only_close_expired_notifications(self):
        """TTL logic only closes expired notification issues, leaves others alone."""
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=10)).isoformat()
        recent_date = (now - timedelta(days=3)).isoformat()

        # Simulate gh response after filtering by labels (only notification issues)
        mock_notification_issues = [
            {
                "number": 700,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": old_date,  # Expired notification
                "body": "Branch cleanup tracking",
            },
            {
                "number": 701,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": recent_date,  # Active notification
                "body": "Branch cleanup tracking",
            },
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            # First call: list issues (filtered by gh to only notification issues)
            # Then comment+close for #700 only
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=json.dumps(mock_notification_issues)),
                MagicMock(returncode=0, stdout=""),  # comment #700
                MagicMock(returncode=0, stdout=""),  # close #700
            ]
            result = close_expired_notifications()

            # Should close exactly 1 issue (#700)
            assert result == 1, "Should close exactly 1 expired notification issue"

            # Verify 3 calls were made (list, comment, close)
            assert mock_run.call_count == 3, "Should make 3 calls for 1 expired issue"

    def test_close_comment_contains_ttl_marker(self):
        """VAL-CROSS-204: Close comment contains TTL marker for traceability."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_issues = [
            {
                "number": 700,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": old_date,
                "body": "Branch cleanup tracking",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=json.dumps(mock_issues)),
                MagicMock(returncode=0, stdout=""),  # comment
                MagicMock(returncode=0, stdout=""),  # close
            ]
            close_expired_notifications()

            # Check the comment call contains TTL information
            assert mock_run.call_count == 3, "Should make 3 calls: list, comment, close"
            comment_call_args = mock_run.call_args_list[1][0][0]
            assert "issue" in comment_call_args and "comment" in comment_call_args, \
                "Second call should be issue comment"
            # Check comment body contains TTL marker
            comment_body = " ".join(str(arg) for arg in comment_call_args)
            assert "TTL" in comment_body or "7d" in comment_body, \
                "Close comment should reference TTL for traceability"

    def test_no_notification_issues_no_action(self):
        """No notification issues → no close calls."""
        mock_issues = [
            {
                "number": 650,
                "labels": [{"name": "evolution-found"}],
                "createdAt": "2026-01-01T00:00:00Z",
                "body": "**Rule ID**: TEST\n**Location**: test.py",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues))
            close_expired_notifications()

            calls = mock_run.call_args_list
            close_calls = [c for c in calls if "issue close" in str(c)]
            comment_calls = [c for c in calls if "issue comment" in str(c)]
            assert len(close_calls) == 0
            assert len(comment_calls) == 0

    def test_empty_issue_list_no_error(self):
        """Empty issue list → no error, no calls."""
        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[]")
            close_expired_notifications()

            # Should not crash
            assert mock_run.called

    def test_already_closed_issue_not_in_query(self):
        """Query only fetches OPEN issues (already-closed not affected)."""
        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[]")
            close_expired_notifications()

            # Verify the query includes state:open
            call_args = mock_run.call_args[0][0]
            call_str = " ".join(str(arg) for arg in call_args)
            assert "--state open" in call_str or "state=open" in call_str, \
                "Should only query open issues"

    def test_boundary_exact_ttl_days(self):
        """Issue exactly at TTL boundary (7 days) is closed."""
        # Exactly 7 days old
        boundary_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        mock_issues = [
            {
                "number": 700,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": boundary_date,
                "body": "Branch cleanup tracking",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=json.dumps(mock_issues)),
                MagicMock(returncode=0, stdout=""),  # comment
                MagicMock(returncode=0, stdout=""),  # close
            ]
            result = close_expired_notifications()

            # At exactly TTL boundary, should close
            assert result == 1, "Issue at exact TTL boundary should be closed"
            assert mock_run.call_count == 3, "Should make 3 calls for 1 expired issue"

    def test_one_day_before_ttl_not_closed(self):
        """Issue one day before TTL (6 days old) is NOT closed."""
        # 6 days old (one day before TTL)
        recent_date = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
        mock_issues = [
            {
                "number": 700,
                "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
                "createdAt": recent_date,
                "body": "Branch cleanup tracking",
            }
        ]

        with patch("evolution_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues))
            result = close_expired_notifications()

            # Should not close any issues
            assert result == 0, "Issue one day before TTL should NOT be closed"
            assert mock_run.call_count == 1, "Should only make list call, no close"
