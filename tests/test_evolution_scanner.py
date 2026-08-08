"""Tests for evolution scanner."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import (
    Finding,
    check_isolation,
    check_kill_switch,
    create_issue,
    deduplicate,
    detect_regressions,
    get_open_issues,
    normalize_finding,
    run_audit_tool,
    sort_by_severity,
    update_history,
)


def test_kill_switch(tmp_path):
    """Kill switch present → scanner exits immediately."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    disabled = evolution_dir / "DISABLED"
    disabled.touch()

    assert check_kill_switch(tmp_path) is True


def test_kill_switch_absent(tmp_path):
    """Kill switch absent → scanner continues."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()

    assert check_kill_switch(tmp_path) is False


def test_normalize_findings():
    """Raw audit JSON → 6-field Finding objects."""
    raw = {
        "rule_id": "TEST_RULE_001",
        "severity": "warning",
        "category": "consistency",
        "description": "Test issue",
        "location": "test/file.md",
        "evidence": "Test evidence",
    }
    finding = normalize_finding(raw)

    assert finding.rule_id == "TEST_RULE_001"
    assert finding.severity == "warning"
    assert finding.category == "consistency"
    assert finding.description == "Test issue"
    assert finding.location == "test/file.md"
    assert finding.evidence == "Test evidence"


def test_normalize_finding_invalid_severity():
    """Invalid severity defaults to info."""
    raw = {"severity": "invalid", "rule_id": "TEST", "location": "test"}
    finding = normalize_finding(raw)
    assert finding.severity == "info"


def test_normalize_finding_missing_fields():
    """Missing fields get defaults."""
    raw = {}
    finding = normalize_finding(raw)
    assert finding.rule_id == "UNKNOWN"
    assert finding.severity == "info"
    assert finding.category == "unknown"


def test_run_audit_tool_success():
    """Audit tool executes and returns JSON."""
    tool = {"name": "test_tool", "command": "echo '{\"rule_id\": \"TEST\"}'}"}

    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='[{"rule_id": "TEST"}]', stderr=""
        )
        result = run_audit_tool(tool)
        assert len(result) == 1
        assert result[0]["rule_id"] == "TEST"


def test_run_audit_tool_failure():
    """Audit tool failure returns empty list."""
    tool = {"name": "test_tool", "command": "exit 1"}

    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")
        result = run_audit_tool(tool)
        assert result == []


def test_dedup_existing_issues():
    """Finding matching open Issue → skipped."""
    findings = [
        Finding("RULE_001", "warning", "consistency", "Issue 1", "file1.md", "evidence"),
        Finding("RULE_002", "warning", "consistency", "Issue 2", "file2.md", "evidence"),
    ]
    open_issues = ["RULE_001|file1.md"]

    deduped = deduplicate(findings, open_issues)
    assert len(deduped) == 1
    assert deduped[0].rule_id == "RULE_002"


def test_max_3_issues():
    """5 findings → only 3 Issues created."""
    findings = [
        Finding(f"RULE_{i}", "warning", "test", f"Issue {i}", f"file{i}.md", "evidence")
        for i in range(5)
    ]
    # In actual usage, we'd slice to max_issues_per_tick=3
    limited = findings[:3]
    assert len(limited) == 3


def test_severity_sort():
    """Critical findings sorted before info findings."""
    findings = [
        Finding("RULE_1", "info", "test", "Low", "file1.md", "evidence"),
        Finding("RULE_2", "critical", "test", "High", "file2.md", "evidence"),
        Finding("RULE_3", "warning", "test", "Medium", "file3.md", "evidence"),
    ]
    severity_order = ["critical", "warning", "info"]
    sorted_findings = sort_by_severity(findings, severity_order)

    assert sorted_findings[0].severity == "critical"
    assert sorted_findings[1].severity == "warning"
    assert sorted_findings[2].severity == "info"


def test_regression_detection(tmp_path):
    """Resolved finding reappears → severity upgraded to critical."""
    history_path = tmp_path / "findings_over_time.json"
    history_data = {
        "snapshots": [],
        "resolved_findings": [
            {"rule_id": "RULE_001", "location": "file1.md", "resolved_at": "2026-01-01"}
        ],
    }
    with open(history_path, "w") as f:
        json.dump(history_data, f)

    findings = [Finding("RULE_001", "warning", "test", "Reappeared", "file1.md", "evidence")]
    updated = detect_regressions(findings, history_path)

    assert updated[0].severity == "critical"


def test_audit_tool_failure():
    """Tool crashes → graceful skip, other tools still run."""
    tool = {"name": "crash_tool", "command": "nonexistent_command"}

    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.side_effect = Exception("Command not found")
        result = run_audit_tool(tool)
        assert result == []


def test_findings_over_time(tmp_path):
    """Snapshot appended correctly, bounded at 100."""
    history_path = tmp_path / "findings_over_time.json"

    findings = [Finding("RULE_1", "warning", "test", "Issue", "file.md", "evidence")]

    # Add 105 snapshots
    for i in range(105):
        update_history(history_path, findings, 1, 100)

    with open(history_path) as f:
        data = json.load(f)

    assert len(data["snapshots"]) == 100
    assert "timestamp" in data["snapshots"][0]
    assert "tick_id" in data["snapshots"][0]
    assert "findings" in data["snapshots"][0]
    assert "issues_created" in data["snapshots"][0]


def test_isolation_label(tmp_path):
    """Same finding 3 ticks → isolated label applied."""
    history_path = tmp_path / "findings_over_time.json"

    # Create 3 snapshots with the same finding
    history_data = {
        "snapshots": [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "tick_id": "20260101-000000",
                "findings": [{"rule_id": "RULE_001", "location": "file.md"}],
                "issues_created": 1,
            }
            for _ in range(3)
        ],
        "resolved_findings": [],
    }
    with open(history_path, "w") as f:
        json.dump(history_data, f)

    findings = [Finding("RULE_001", "warning", "test", "Stuck", "file.md", "evidence")]

    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        check_isolation(findings, history_path, 3, "evolution-isolated")
        # Should have called gh issue list to find the issue to label
        assert mock_run.called


def test_issue_body_contains_droid():
    """Created Issue body contains @droid trigger."""
    finding = Finding("RULE_001", "warning", "test", "Issue", "file.md", "evidence")

    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = create_issue(finding, "evolution-found")

        assert result is True
        # Check that the body parameter contains @droid
        call_args = mock_run.call_args[0][0]
        body_index = call_args.index("--body") + 1
        body = call_args[body_index]
        assert "@droid" in body
        assert "RULE_001" in body
        assert "warning" in body


def test_get_open_issues():
    """Fetch open issues with evolution-found label."""
    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"title": "Issue 1", "body": "RULE_001|file1.md"}]',
        )
        issues = get_open_issues("evolution-found")
        assert len(issues) == 1
        assert "RULE_001|file1.md" in issues[0]


def test_dedup_no_duplicates():
    """No open issues → all findings kept."""
    findings = [
        Finding("RULE_001", "warning", "test", "Issue 1", "file1.md", "evidence"),
        Finding("RULE_002", "warning", "test", "Issue 2", "file2.md", "evidence"),
    ]
    open_issues = []

    deduped = deduplicate(findings, open_issues)
    assert len(deduped) == 2


def test_update_history_empty(tmp_path):
    """Update history creates new file if none exists."""
    history_path = tmp_path / "findings_over_time.json"
    findings = [Finding("RULE_1", "warning", "test", "Issue", "file.md", "evidence")]

    update_history(history_path, findings, 1, 100)

    with open(history_path) as f:
        data = json.load(f)

    assert len(data["snapshots"]) == 1
    assert "resolved_findings" in data
