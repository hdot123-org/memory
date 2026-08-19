"""INFRA-403: Reverse drift watch production hardening regression tests.

The D1 implementation (#780 / VAL-DRF-002/003) was a production no-op and
lacked the protection gates that auto_close_resolved has. These tests pin the
fixes:

1. P0 shape fix: get_open_issues() returns compact dicts (rule_id/location/
   number/state) — the classifier previously parsed issue["body"] only, which
   is absent in production, so every orphan was skipped (silent no-op).
2. P0 closed-state pollution: closed-in-window dedup entries (state="closed")
   must not be classified as orphans.
3. P1 GAP-C1: categories whose audit tool failed this tick → BLOCKED, not close.
4. P1 INFRA-216: self-audit category → BLOCKED (flapping-loop protection).
5. P1 comment spam: BLOCKED audit comment is idempotent (sentinel-guarded).
6. P1 double-processing: issues already closed (e.g. by auto_close_resolved in
   the same tick) are skipped, not re-closed or commented.
7. P2 P0-A: partial-output protection skips the whole watch.
8. P2 VAL-DRF-004: budget exhaustion skips the whole watch.
"""
import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import Finding
from evolution_utils import (
    REVERSE_DRIFT_SENTINEL,
    OrphanIssueClassification,
    classify_orphan_issues,
    execute_orphan_classifications,
    reverse_drift_watch,
)


def _gh_ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def _compact_issue(number: int, rule_id: str, location: str,
                   state: str = "open", body: str = "", category: str | None = None) -> dict:
    """Mirror the compact dict shape produced by get_open_issues() in production."""
    issue = {"rule_id": rule_id, "location": location, "number": number, "state": state, "body": body}
    if category is not None:
        issue["category"] = category
    return issue


def _body_issue(number: int, rule_id: str, location: str,
                linear_linkback: str = "", category: str | None = None) -> dict:
    """Issue dict carrying only a body (legacy shape, no pre-parsed fields)."""
    body = f"**Rule ID**: {rule_id}\n**Location**: {location}"
    if category:
        body += f"\n**Category**: {category}"
    if linear_linkback:
        body += f"\n<!-- linear-linkback {linear_linkback} -->"
    return {"number": number, "body": body}


# ---------------------------------------------------------------------------
# P0 shape fix: compact dicts (no body) must be classifiable via pre-parsed keys
# ---------------------------------------------------------------------------

def test_compact_issue_without_body_is_classified():
    """Production shape from get_open_issues() (no body field) must work.

    Red evidence: before INFRA-403, classify_orphan_issues parsed only
    issue["body"]; compact dicts have body="" → _parse_issue_fields returned
    (None, None) → every orphan skipped → the whole watch was a no-op.
    """
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _compact_issue(101, "R1", "present.py"),  # not orphan
        _compact_issue(102, "R2", "gone.py", body="", category="code_quality"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=False), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        report = classify_orphan_issues(findings, open_issues)

    assert len(report) == 1, "Compact orphan issue must be classified (was a no-op)"
    assert report[0].issue_number == 102
    assert report[0].classification == "BLOCKED_NO_EVIDENCE"
    assert report[0].reason == "no_evidence_of_resolution"


def test_body_only_issue_still_classified_via_fallback_parsing():
    """Legacy shape (body only, no pre-parsed keys) keeps working via fallback."""
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _body_issue(103, "R3", "legacy.py", linear_linkback="INFRA-1"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        report = classify_orphan_issues(findings, open_issues)

    assert len(report) == 1
    assert report[0].classification == "CLOSE_READY"
    assert report[0].reason == "merged_pr_verified"


# ---------------------------------------------------------------------------
# P0 closed-in-window dedup entries must not be treated as orphans
# ---------------------------------------------------------------------------

def test_closed_in_window_entries_skipped():
    """get_open_issues() includes closed-in-window entries for dedup only.

    Red evidence: before INFRA-403, such entries (state="closed") were
    classified as orphans → audit comments posted on CLOSED issues and even
    CLOSE_READY close attempts on already-closed issues.
    """
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _compact_issue(104, "R1", "present.py"),
        _compact_issue(105, "R4", "closed-recently.py", state="closed"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear') as mock_verify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        report = classify_orphan_issues(findings, open_issues)

    assert report == [], "Closed-in-window entries must not be classified as orphans"
    mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# P1 GAP-C1: failed-tool categories are blocked, not closed
# ---------------------------------------------------------------------------

def test_failed_category_tool_blocks_close():
    """GAP-C1 alignment: a crashed tool emits no findings; absence ≠ resolution."""
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _compact_issue(106, "R5", "gone.py", category="daily_audit"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear') as mock_verify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        report = classify_orphan_issues(findings, open_issues, failed_categories={"daily_audit"})

    assert len(report) == 1
    assert report[0].classification == "BLOCKED_NO_EVIDENCE"
    assert report[0].reason == "category_tool_failed:daily_audit"
    # Verification must not even run — protection is decided before evidence check
    mock_verify.assert_not_called()


def test_failed_category_parsed_from_body():
    """Same GAP-C1 protection when category is only in the body (legacy shape)."""
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _body_issue(107, "R6", "gone.py", category="daily_audit"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True) as mock_verify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        report = classify_orphan_issues(findings, open_issues, failed_categories={"daily_audit"})

    assert len(report) == 1
    assert report[0].classification == "BLOCKED_NO_EVIDENCE"
    assert "category_tool_failed" in report[0].reason
    mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# P1 INFRA-216: self-audit category is blocked, not closed
# ---------------------------------------------------------------------------

def test_self_audit_category_blocked():
    """INFRA-216 alignment: self-audit issues are transient health signals.

    Auto-closing them triggers the Gate A flapping loop (#648-class incident).
    """
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _compact_issue(108, "R7", "heartbeat.py", category="evolution_self_audit"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear') as mock_verify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        report = classify_orphan_issues(findings, open_issues)

    assert len(report) == 1
    assert report[0].classification == "BLOCKED_NO_EVIDENCE"
    assert report[0].reason == "self_audit_protected"
    mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# P1 comment idempotency: BLOCKED audit comments carry a sentinel
# ---------------------------------------------------------------------------

def test_blocked_comment_contains_sentinel():
    """The BLOCKED audit comment must embed the idempotency sentinel."""
    classification = OrphanIssueClassification(
        issue_number=109,
        rule_id="R8",
        location="blocked.py",
        classification="BLOCKED_NO_EVIDENCE",
        reason="no_evidence_of_resolution",
        timestamp="2026-08-19T00:00:00+00:00",
        action_taken="retained_with_reason",
    )

    with patch('evolution_utils.subprocess.run') as mock_run:
        # 1st call: state check (OPEN), 2nd: comment scan (empty), 3rd: post comment
        mock_run.side_effect = [
            _gh_ok(json.dumps({"state": "OPEN"})),
            _gh_ok(""),  # no existing comments
            _gh_ok(),    # comment posted
        ]
        result = execute_orphan_classifications([classification])

    assert result["retained"] == 1
    posted_body = mock_run.call_args_list[2].args[0][-1]
    assert REVERSE_DRIFT_SENTINEL in posted_body, \
        "BLOCKED audit comment must embed sentinel for idempotency"


def test_blocked_comment_not_repeated_when_sentinel_present():
    """Sentinel already present → skip re-commenting (no per-tick spam)."""
    classification = OrphanIssueClassification(
        issue_number=110,
        rule_id="R9",
        location="blocked2.py",
        classification="BLOCKED_NO_EVIDENCE",
        reason="no_evidence_of_resolution",
        timestamp="2026-08-19T00:00:00+00:00",
        action_taken="retained_with_reason",
    )

    with patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _gh_ok(json.dumps({"state": "OPEN"})),
            _gh_ok(f"{REVERSE_DRIFT_SENTINEL}\nprevious audit comment"),  # sentinel found
        ]
        result = execute_orphan_classifications([classification])

    assert result["retained"] == 0, "Must not re-comment when sentinel present"
    comment_calls = [
        c for c in mock_run.call_args_list
        if len(c.args[0]) > 2 and c.args[0][2] == "comment"
    ]
    assert len(comment_calls) == 0, "No comment call when sentinel already present"


# ---------------------------------------------------------------------------
# P1 double-processing: issues already closed are skipped
# ---------------------------------------------------------------------------

def test_execute_skips_already_closed_issue():
    """Issue closed earlier in the same tick (by auto_close_resolved) → skip.

    Red evidence: before INFRA-403, CLOSE_READY orphans closed by
    auto_close_resolved moments earlier were closed AGAIN by the reverse
    watch, and BLOCKED orphans received audit comments on closed issues.
    """
    close_ready = OrphanIssueClassification(
        issue_number=111, rule_id="RA", location="a.py",
        classification="CLOSE_READY", reason="merged_pr_verified",
        timestamp="2026-08-19T00:00:00+00:00", action_taken="close_attempt",
    )
    blocked = OrphanIssueClassification(
        issue_number=112, rule_id="RB", location="b.py",
        classification="BLOCKED_NO_EVIDENCE", reason="no_evidence_of_resolution",
        timestamp="2026-08-19T00:00:00+00:00", action_taken="retained_with_reason",
    )

    with patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _gh_ok(json.dumps({"state": "CLOSED"})),  # 111 already closed
            _gh_ok(json.dumps({"state": "CLOSED"})),  # 112 already closed
        ]
        result = execute_orphan_classifications([close_ready, blocked])

    assert result == {"closed": 0, "retained": 0, "deferred": 0}
    action_calls = [
        c for c in mock_run.call_args_list
        if len(c.args[0]) > 2 and c.args[0][2] in ("close", "comment")
    ]
    assert len(action_calls) == 0, "No close/comment on already-closed issues"


def test_execute_skips_issue_with_unknown_state():
    """State check fails (network/gh error) → fail-closed skip, no action."""
    classification = OrphanIssueClassification(
        issue_number=113, rule_id="RC", location="c.py",
        classification="CLOSE_READY", reason="merged_pr_verified",
        timestamp="2026-08-19T00:00:00+00:00", action_taken="close_attempt",
    )

    with patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="gh down")
        result = execute_orphan_classifications([classification])

    assert result == {"closed": 0, "retained": 0, "deferred": 0}


def test_execute_unknown_state_exception_skips():
    """Exception during state check → skip (fail-closed)."""
    classification = OrphanIssueClassification(
        issue_number=114, rule_id="RD", location="d.py",
        classification="BLOCKED_NO_EVIDENCE", reason="no_evidence_of_resolution",
        timestamp="2026-08-19T00:00:00+00:00", action_taken="retained_with_reason",
    )

    with patch('evolution_utils.subprocess.run', side_effect=OSError("boom")):
        result = execute_orphan_classifications([classification])

    assert result == {"closed": 0, "retained": 0, "deferred": 0}


# ---------------------------------------------------------------------------
# P2 P0-A: partial-output protection on the integrated entry point
# ---------------------------------------------------------------------------

def test_partial_output_skips_reverse_watch(tmp_path):
    """Findings far below baseline median (crashed adapter) → skip entirely."""
    history = tmp_path / "history.json"
    snapshots = {
        "snapshots": [
            {"findings": [{"rule_id": f"R{i}", "location": f"f{i}.py"} for i in range(50)]}
            for _ in range(5)
        ]
    }
    history.write_text(json.dumps(snapshots))

    findings = [Finding("R1", "warning", "cat", "d", "only.py", "e")]  # 1 vs median 50
    open_issues = [_compact_issue(115, "RX", "gone.py")]

    with patch('evolution_utils.classify_orphan_issues') as mock_classify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        result = reverse_drift_watch(findings, open_issues, history)

    assert result == {"closed": 0, "retained": 0, "deferred": 0}
    mock_classify.assert_not_called()


# ---------------------------------------------------------------------------
# P2 VAL-DRF-004: budget guard on the integrated entry point
# ---------------------------------------------------------------------------

def test_budget_exhausted_skips_reverse_watch(tmp_path):
    """Tick budget exhausted → skip reverse watch (mirror forward watch)."""
    history = tmp_path / "history.json"

    fake_tracker = MagicMock()
    fake_tracker.is_any_budget_exceeded.return_value = True
    fake_tracker.is_duration_exceeded.return_value = False
    fake_tracker.is_api_exceeded.return_value = True

    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [_compact_issue(116, "RY", "gone.py")]

    with patch('evolution_utils.classify_orphan_issues') as mock_classify, \
         patch('evolution_scanner.get_tick_tracker', return_value=fake_tracker), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()
        result = reverse_drift_watch(findings, open_issues, history)

    assert result == {"closed": 0, "retained": 0, "deferred": 0}
    mock_classify.assert_not_called()


def test_budget_tracker_unavailable_proceeds(tmp_path):
    """Budget tracker import fails (direct invocation) → proceed normally."""
    history = tmp_path / "history.json"  # no history file → no partial-output skip

    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [_compact_issue(117, "RZ", "gone.py", category="code_quality")]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=False), \
         patch('evolution_utils.subprocess.run') as mock_run, \
         patch.dict(sys.modules, {"evolution_scanner": None}):
        # State check + comment scan + comment post all succeed
        mock_run.side_effect = [
            _gh_ok(json.dumps({"state": "OPEN"})),
            _gh_ok(""),
            _gh_ok(),
        ]
        result = reverse_drift_watch(findings, open_issues, history)

    assert result["retained"] == 1


def test_budget_tracker_unavailable_logs_swallow(tmp_path, caplog):
    """INFRA-413 (SILENT_SWALLOW): the tracker-unavailable fallback must be logged.

    Red evidence: the except clause previously used a bare ``pass`` with no
    logging — the exact pattern the code_hygiene_audit SILENT_SWALLOW rule
    flags. Graceful degradation must stay observable (DEBUG log), matching
    the error_logger pattern.
    """
    history = tmp_path / "history.json"  # no history file → no partial-output skip

    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [_compact_issue(120, "RS", "gone.py", category="code_quality")]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=False), \
         patch('evolution_utils.subprocess.run') as mock_run, \
         patch.dict(sys.modules, {"evolution_scanner": None}), \
         caplog.at_level(logging.DEBUG, logger="evolution_utils"):
        mock_run.side_effect = [
            _gh_ok(json.dumps({"state": "OPEN"})),
            _gh_ok(""),
            _gh_ok(),
        ]
        result = reverse_drift_watch(findings, open_issues, history)

    assert result["retained"] == 1, "proceed-unguarded behavior unchanged"
    debug_records = [
        r for r in caplog.records
        if r.levelname == "DEBUG" and "Budget tracker unavailable" in r.message
    ]
    assert debug_records, \
        "expected a DEBUG log record for the swallowed tracker exception (INFRA-413)"


# ---------------------------------------------------------------------------
# get_open_issues() passes body/category through (P0 shape fix, producer side)
# ---------------------------------------------------------------------------

def test_get_open_issues_passes_body_and_category():
    """Producer side of the P0 fix: compact dicts must carry body + category."""
    from evolution_scanner import get_open_issues

    open_data = json.dumps([
        {"title": "[evolution] RULE_P",
         "body": "**Rule ID**: RULE_P\n**Location**: p.py\n**Category**: code_quality",
         "number": 77}
    ])
    with patch('evolution_scanner.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _gh_ok(open_data),
            _gh_ok("[]"),
        ]
        issues = get_open_issues("evolution-found")

    assert len(issues) == 1
    issue = issues[0]
    assert issue["rule_id"] == "RULE_P"
    assert issue["location"] == "p.py"
    assert issue["number"] == 77
    assert issue["state"] == "open"
    assert "**Rule ID**: RULE_P" in issue["body"], "body must be passed through"
    assert issue["category"] == "code_quality", "category must be parsed and passed through"


def test_get_open_issues_closed_entry_carries_state_closed():
    """Closed-in-window entries still tagged state='closed' (INFRA-396 regression)."""
    from datetime import datetime, timedelta, timezone

    from evolution_scanner import get_open_issues

    closed_3d_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    closed_data = json.dumps([
        {"title": "[evolution] RULE_Q",
         "body": "**Rule ID**: RULE_Q\n**Location**: q.py",
         "number": 88, "closedAt": closed_3d_ago}
    ])
    with patch('evolution_scanner.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _gh_ok("[]"),
            _gh_ok(closed_data),
        ]
        issues = get_open_issues("evolution-found")

    assert len(issues) == 1
    assert issues[0]["state"] == "closed"
    assert issues[0]["rule_id"] == "RULE_Q"


# ---------------------------------------------------------------------------
# End-to-end: compact production shape flows through the whole pipeline
# ---------------------------------------------------------------------------

def test_end_to_end_compact_shape_closes_with_evidence():
    """Full pipeline with get_open_issues() output shape + merge evidence."""
    findings = [Finding("R1", "warning", "cat", "d", "present.py", "e")]
    open_issues = [
        _compact_issue(118, "R1", "present.py"),
        _compact_issue(119, "R10", "resolved.py", body="<!-- linear-linkback INFRA-9 -->",
                       category="code_quality"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _gh_ok(json.dumps({"state": "OPEN"})),  # state check 119
            _gh_ok(),                               # close 119
        ]
        result = reverse_drift_watch(findings, open_issues)

    assert result == {"closed": 1, "retained": 0, "deferred": 0}
    close_call = mock_run.call_args_list[1].args[0]
    assert close_call[0:3] == ["gh", "issue", "close"]
    assert "119" in close_call
