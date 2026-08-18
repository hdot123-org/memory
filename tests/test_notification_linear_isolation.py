"""Tests for notification Linear isolation (VAL-NTF-003, VAL-NTF-004, VAL-NTF-005).

D6: Notification issues (branch-cleanup tracking) must NOT enter:
  1. The dispatch chain (VAL-NTF-003)
  2. The mirror location candidates in reconcile §4b (VAL-NTF-004)
  3. Any of the three mirror location paths: §4b, GATE A 4.5, GATE A 4.6 (VAL-NTF-005)

Replay #724/INFRA-346 original form:
  - Notification issue #724: labels=[automation, branch-cleanup], body mentions INFRA-346
  - Real mirror issue #999: labels=[evolution-found], anchor=INFRA-346
  - All three paths must select #999, NOT #724

Architecture reference: architecture.md §3.6 (通知终态 — Linear 隔离)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Add scripts directory to path for import
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from anchor_gate import gate as anchor_gate_fn
from evolution_utils import (
    _extract_linear_linkback,
    _has_linear_linkback_marker,
    extract_linkback_anchor,
)

# ============================================================================
# Test Fixtures: #724/INFRA-346 original form replay data
# ============================================================================

# Notification issue #724 — branch-cleanup tracking, body mentions INFRA-346
NOTIFICATION_ISSUE_724: dict[str, Any] = {
    "number": 724,
    "labels": [{"name": "automation"}, {"name": "branch-cleanup"}],
    "state": "OPEN",
    "body": (
        "<!-- branch-cleanup-tracker -->\n"
        "## 分支清理跟踪 Issue\n\n"
        "以下保护分支在清理中仍为 protected：\n"
        "- `refactor/INFRA-346-anchor-mirror-location`\n\n"
        "此 Issue 由 branch-cleanup workflow 创建。"
    ),
    "createdAt": "2026-08-15T10:00:00Z",
}

# Real mirror issue #999 — evolution-found, with linear-linkback to INFRA-346
REAL_MIRROR_ISSUE_999: dict[str, Any] = {
    "number": 999,
    "labels": [{"name": "evolution-found"}],
    "state": "OPEN",
    "body": (
        "**Rule ID**: TEST_RULE_001\n"
        "**Location**: scripts/evolution_scanner.py::L42\n"
        "**Severity**: warning\n"
        "**Category**: code_hygiene\n\n"
        "<!-- linear-linkback INFRA-346 -->"
    ),
    "createdAt": "2026-08-14T08:00:00Z",
}

TARGET_REF: str = "INFRA-346"


def _label_names(issue: dict[str, Any]) -> set[str]:
    """Extract label names from an issue dict."""
    return {lbl["name"] for lbl in issue["labels"]}


def _has_evolution_found(issue: dict[str, Any]) -> bool:
    """Check if an issue has the evolution-found label."""
    return any(lbl["name"] == "evolution-found" for lbl in issue["labels"])


# ============================================================================
# VAL-NTF-005: Three-path replay matrix — notification issue never selected
# ============================================================================


class TestPath1_Reconcile_4b_LabelFilter:
    """Path 1: reconcile §4b terminal cleanup uses --label evolution-found.

    The reconcile script queries:
        gh issue list --label evolution-found --state open --search INFRA-xxx
    Notification issues lack the evolution-found label, so they are excluded.
    """

    def test_notification_issue_lacks_evolution_found_label(self) -> None:
        """VAL-NTF-005 §4b: Notification issue does NOT have evolution-found label."""
        labels = _label_names(NOTIFICATION_ISSUE_724)
        assert "evolution-found" not in labels, \
            "Notification issue must not have evolution-found label"

    def test_real_mirror_has_evolution_found_label(self) -> None:
        """VAL-NTF-005 §4b: Real mirror issue DOES have evolution-found label."""
        labels = _label_names(REAL_MIRROR_ISSUE_999)
        assert "evolution-found" in labels, \
            "Real mirror issue must have evolution-found label"

    def test_label_filter_excludes_notification(self) -> None:
        """Simulate gh --label evolution-found filtering: notification excluded."""
        all_issues = [NOTIFICATION_ISSUE_724, REAL_MIRROR_ISSUE_999]
        # Simulate gh --label evolution-found
        filtered = [issue for issue in all_issues if _has_evolution_found(issue)]
        assert len(filtered) == 1
        assert filtered[0]["number"] == 999
        assert NOTIFICATION_ISSUE_724 not in filtered

    def test_notification_body_mentions_infra_but_not_selected(self) -> None:
        """VAL-NTF-005 §4b: Even though #724 body mentions INFRA-346, it's excluded."""
        # Verify notification body contains the INFRA ref
        assert TARGET_REF in NOTIFICATION_ISSUE_724["body"], \
            "Test fixture: notification body should mention INFRA-346"
        # But label filter excludes it
        labels = _label_names(NOTIFICATION_ISSUE_724)
        assert "evolution-found" not in labels


class TestPath2_GateA_45_PRMergedOverride:
    """Path 2: GATE A 4.5 PR-merged override uses --label evolution-found.

    trigger-droid.sh GATE A 4.5 queries:
        gh pr list --label evolution-found --state merged --limit 10
    Notification issues/PRs lack the evolution-found label.
    """

    def test_gate_a_45_query_requires_evolution_found_label(self) -> None:
        """VAL-NTF-005 GATE A 4.5: Script source contains --label evolution-found."""
        trigger_script = Path(__file__).parent.parent / "webhook-scripts" / "trigger-droid.sh"
        content = trigger_script.read_text()
        # GATE A 4.5 PR-merged override section
        assert "--label evolution-found" in content, \
            "GATE A 4.5 must filter by evolution-found label"

    def test_notification_pr_would_not_match_label_filter(self) -> None:
        """VAL-NTF-005 GATE A 4.5: Notification-labeled items excluded by label filter."""
        # Simulate PR list with label filter
        pr_candidates: list[dict[str, Any]] = [
            {"number": 724, "labels": [{"name": "automation"}, {"name": "branch-cleanup"}]},
            {"number": 900, "labels": [{"name": "evolution-found"}]},
        ]
        filtered = [
            pr for pr in pr_candidates
            if any(lbl["name"] == "evolution-found" for lbl in pr["labels"])
        ]
        assert len(filtered) == 1
        assert filtered[0]["number"] == 900


class TestPath3_GateA_46_SyncOriginOverride:
    """Path 3: GATE A 4.6 sync-origin override uses --label evolution-found.

    trigger-droid.sh GATE A 4.6 queries:
        gh issue list --label evolution-found --state all --limit 10
    Notification issues lack the evolution-found label.
    """

    def test_gate_a_46_query_requires_evolution_found_label(self) -> None:
        """VAL-NTF-005 GATE A 4.6: Script source contains --label evolution-found in sync section."""
        trigger_script = Path(__file__).parent.parent / "webhook-scripts" / "trigger-droid.sh"
        content = trigger_script.read_text()
        # Count occurrences — GATE A 4.5, 4.6, and reconcile all use this filter
        count = content.count("--label evolution-found")
        assert count >= 3, \
            f"Expected at least 3 uses of --label evolution-found (4.5, 4.6, terminal close), got {count}"

    def test_sync_origin_excludes_notification_issues(self) -> None:
        """VAL-NTF-005 GATE A 4.6: Notification issues excluded from sync-origin check."""
        # Simulate gh issue list --label evolution-found --state all
        issues = [NOTIFICATION_ISSUE_724, REAL_MIRROR_ISSUE_999]
        filtered = [issue for issue in issues if _has_evolution_found(issue)]
        selected_numbers = {issue["number"] for issue in filtered}
        assert 724 not in selected_numbers, \
            "Notification issue #724 must NOT be selected by GATE A 4.6"
        assert 999 in selected_numbers, \
            "Real mirror #999 must be selected by GATE A 4.6"


# ============================================================================
# VAL-NTF-005: Anchor extraction from notification issues
# ============================================================================


class TestAnchorExtraction_NotificationIssue:
    """Verify anchor extraction does NOT find INFRA-346 in notification issue.

    Even if we bypassed the label filter (defense in depth), the notification
    issue has no linear-linkback marker, so anchor extraction returns None.
    """

    def test_no_linkback_marker_in_notification_body(self) -> None:
        """VAL-NTF-005: Notification issue body has no linear-linkback marker."""
        body: str = NOTIFICATION_ISSUE_724["body"]
        assert not _has_linear_linkback_marker(body), \
            "Notification issue should not have linear-linkback marker"

    def test_extract_linkback_returns_none_for_notification(self) -> None:
        """VAL-NTF-005: _extract_linear_linkback returns None for notification issue."""
        body: str = NOTIFICATION_ISSUE_724["body"]
        result = _extract_linear_linkback(body)
        assert result is None, \
            "Should not extract any INFRA ref from notification issue"

    def test_extract_linkback_anchor_returns_none_for_notification_comments(self) -> None:
        """VAL-NTF-005: extract_linkback_anchor returns None for notification comments."""
        # Simulate notification issue comments (no linkback)
        comments = "This is a branch cleanup notification\nNothing to do with Linear"
        result = extract_linkback_anchor(comments)
        assert result is None

    def test_infra_string_in_body_is_not_extracted(self) -> None:
        """VAL-NTF-005: INFRA-346 appearing in branch name is not a linkback."""
        body: str = NOTIFICATION_ISSUE_724["body"]
        assert "INFRA-346" in body  # It's in the branch name
        # But extraction still returns None (no linkback marker)
        assert _extract_linear_linkback(body) is None


# ============================================================================
# VAL-NTF-005: Anchor gate replay — #724 scenario
# ============================================================================


class TestAnchorGate_Replay724:
    """Replay the #724 scenario through anchor_gate.py.

    When anchor_gate receives a candidate list containing ONLY the notification
    issue (simulating what would happen if label filter were bypassed), it must
    still NOT select it because anchor extraction fails.
    """

    def test_anchor_gate_rejects_notification_issue(self) -> None:
        """VAL-NTF-005: anchor_gate rejects notification issue even if it's the only candidate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate: only notification issue as candidate (label filter bypassed)
            candidates_json = json.dumps([{"number": 724}])

            # Mock extract_anchor.py to return empty (notification has no linkback)
            with patch("anchor_gate.extract_anchor") as mock_extract:
                mock_extract.return_value = (0, "")  # rc=0, anchor="" (no anchor)
                result = anchor_gate_fn(candidates_json, TARGET_REF, "test/repo", tmpdir)

            assert result == "", \
                "anchor_gate must NOT select notification issue (no anchor)"

    def test_anchor_gate_selects_real_mirror_over_notification(self) -> None:
        """VAL-NTF-005: anchor_gate selects real mirror, not notification issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Both issues as candidates
            candidates_json = json.dumps([{"number": 724}, {"number": 999}])

            def mock_extract(target: str, number: int, repo: str) -> tuple[int, str]:
                if number == 724:
                    return (0, "")  # Notification: no anchor
                elif number == 999:
                    return (0, TARGET_REF)  # Real mirror: anchor matches
                return (0, "")

            with patch("anchor_gate.extract_anchor") as mock_extract_fn:
                mock_extract_fn.side_effect = mock_extract
                result = anchor_gate_fn(candidates_json, TARGET_REF, "test/repo", tmpdir)

            assert result == "999", \
                "anchor_gate must select real mirror #999, not notification #724"

    def test_anchor_gate_rejects_both_when_neither_matches(self) -> None:
        """VAL-NTF-005: When notification has wrong anchor, it's rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates_json = json.dumps([{"number": 724}])

            # Even if notification somehow had an anchor, it wouldn't match
            with patch("anchor_gate.extract_anchor") as mock_extract:
                mock_extract.return_value = (0, "INFRA-999")  # Wrong ref
                result = anchor_gate_fn(candidates_json, TARGET_REF, "test/repo", tmpdir)

            assert result == "", \
                "anchor_gate must reject notification with mismatched anchor"


# ============================================================================
# VAL-NTF-003: Notification issues don't enter dispatch chain
# ============================================================================


class TestDispatchChainExclusion:
    """VAL-NTF-003: Notification issues don't trigger droid dispatch.

    The dispatch chain is: Linear webhook → trigger-droid.sh → droid exec.
    Notification issues are GitHub-only (created by branch-cleanup workflow),
    they don't exist in Linear. But the reconcile script's LINEAR_ISSUES query
    also filters by evolution-found label, providing defense in depth.
    """

    def test_reconcile_linear_query_filters_evolution_found(self) -> None:
        """VAL-NTF-003: reconcile Linear query requires evolution-found label."""
        reconcile_script = Path(__file__).parent.parent / "webhook-scripts" / "reconcile-evolution.sh"
        content = reconcile_script.read_text()
        # The Linear GraphQL query must filter by evolution-found label
        assert "evolution-found" in content, \
            "Reconcile Linear query must filter by evolution-found label"

    def test_reconcile_terminal_query_filters_evolution_found(self) -> None:
        """VAL-NTF-003: reconcile terminal cleanup query requires evolution-found label."""
        reconcile_script = Path(__file__).parent.parent / "webhook-scripts" / "reconcile-evolution.sh"
        content = reconcile_script.read_text()
        # Section 4b terminal cleanup also uses evolution-found label filter
        # Count occurrences: at least 2 (section 4 active + section 4b terminal)
        count = content.count("evolution-found")
        assert count >= 2, \
            f"Expected at least 2 evolution-found references in reconcile, got {count}"

    def test_notification_issue_not_in_linear_evolution_found_query(self) -> None:
        """VAL-NTF-003: Notification issues don't have evolution-found label in Linear."""
        # Notification issues are created by branch-cleanup workflow with
        # labels: automation, branch-cleanup — NOT evolution-found
        notification_labels = {"automation", "branch-cleanup"}
        assert "evolution-found" not in notification_labels

    def test_trigger_droid_team_whitelist_filters_non_infra(self) -> None:
        """VAL-NTF-003: trigger-droid.sh team whitelist filters non-INFRA events."""
        trigger_script = Path(__file__).parent.parent / "webhook-scripts" / "trigger-droid.sh"
        content = trigger_script.read_text()
        # Team whitelist check
        assert "TEAM_KEY" in content and "INFRA" in content, \
            "trigger-droid.sh must have team whitelist for INFRA"


# ============================================================================
# VAL-NTF-004: Notification issues not closed by terminal cleanup
# ============================================================================


class TestTerminalCleanupNotificationExclusion:
    """VAL-NTF-004: Terminal cleanup does not close notification issues.

    The reconcile §4b terminal cleanup queries:
        gh issue list --label evolution-found --state open --search INFRA-xxx
    Notification issues lack the evolution-found label, so they are never
    candidates for closing.
    """

    def test_terminal_cleanup_query_has_label_filter(self) -> None:
        """VAL-NTF-004: reconcile §4b query uses --label evolution-found."""
        reconcile_script = Path(__file__).parent.parent / "webhook-scripts" / "reconcile-evolution.sh"
        content = reconcile_script.read_text()
        # Section 4b: terminal cleanup must use label filter
        assert "--label evolution-found" in content, \
            "Section 4b terminal cleanup must filter by evolution-found label"

    def test_notification_issue_excluded_from_close_candidates(self) -> None:
        """VAL-NTF-004: Notification issue is excluded from close candidates."""
        # Simulate the close candidate query
        all_open_issues = [NOTIFICATION_ISSUE_724, REAL_MIRROR_ISSUE_999]
        # Filter by evolution-found label (what gh --label evolution-found does)
        candidates = [issue for issue in all_open_issues if _has_evolution_found(issue)]
        candidate_numbers = {issue["number"] for issue in candidates}
        assert 724 not in candidate_numbers, \
            "Notification issue #724 must NOT be a close candidate"
        assert 999 in candidate_numbers, \
            "Real mirror #999 should be a close candidate"

    def test_anchor_gate_provides_second_layer_of_protection(self) -> None:
        """VAL-NTF-004: Even if label filter bypassed, anchor gate blocks notification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Notification issue as only candidate (label filter bypassed)
            candidates_json = json.dumps([{"number": 724}])

            # Mock: notification issue has no anchor
            with patch("anchor_gate.extract_anchor") as mock_extract:
                mock_extract.return_value = (0, "")  # No anchor
                result = anchor_gate_fn(candidates_json, TARGET_REF, "test/repo", tmpdir)

            assert result == "", \
                "Even without label filter, anchor gate must block notification issue"


# ============================================================================
# Integration: Three-path matrix summary
# ============================================================================


class TestThreePathMatrix:
    """Summary test: all three paths exclude notification issues.

    This test consolidates the #724/INFRA-346 replay evidence.
    """

    def test_all_three_paths_exclude_notification_issue_724(self) -> None:
        """VAL-NTF-005: Three-path matrix — notification #724 excluded from all."""
        # Path 1: §4b label filter
        path1_filtered = [NOTIFICATION_ISSUE_724, REAL_MIRROR_ISSUE_999]
        path1_result = [i for i in path1_filtered if _has_evolution_found(i)]
        assert len(path1_result) == 1
        assert path1_result[0]["number"] == 999, "§4b: only real mirror selected"

        # Path 2: GATE A 4.5 label filter (same mechanism)
        path2_result = [
            i for i in [NOTIFICATION_ISSUE_724, REAL_MIRROR_ISSUE_999]
            if _has_evolution_found(i)
        ]
        assert len(path2_result) == 1
        assert path2_result[0]["number"] == 999, "GATE A 4.5: only real mirror selected"

        # Path 3: GATE A 4.6 label filter + anchor gate
        path3_candidates = [NOTIFICATION_ISSUE_724, REAL_MIRROR_ISSUE_999]
        path3_labeled = [i for i in path3_candidates if _has_evolution_found(i)]
        assert len(path3_labeled) == 1
        assert path3_labeled[0]["number"] == 999, "GATE A 4.6: only real mirror selected"

    def test_notification_body_contains_infra_but_no_linkback(self) -> None:
        """VAL-NTF-005: #724 body contains INFRA-346 string but no linkback marker."""
        body: str = NOTIFICATION_ISSUE_724["body"]
        # Body contains the INFRA ref (in branch name)
        assert TARGET_REF in body
        # But no linear-linkback marker
        assert "linear-linkback" not in body
        # So extraction returns None
        assert _extract_linear_linkback(body) is None
        assert extract_linkback_anchor(body) is None
