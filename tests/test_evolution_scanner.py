"""Tests for evolution scanner."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_adapters import (
    adapt_consistency_check,
    adapt_daily_audit,
    adapt_error_patterns,
)
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
    # Open issues now parsed as dicts with rule_id, location, number
    open_issues = [
        {"rule_id": "RULE_001", "location": "file1.md", "number": 42}
    ]

    deduped = deduplicate(findings, open_issues)
    assert len(deduped) == 1
    assert deduped[0].rule_id == "RULE_002"


def test_max_3_issues():
    """Scanner creates at most max_issues_per_tick issues."""
    findings = [
        Finding(f"RULE_{i}", "warning", "test", f"Issue {i}", f"file{i}.md", "evidence")
        for i in range(5)
    ]
    # Dedup: no open issues
    open_issues = []
    deduped = deduplicate(findings, open_issues)
    deduped = sort_by_severity(deduped, ["critical", "warning", "info"])

    # Simulate the main() loop with max_issues_per_tick=3
    max_issues = 3
    issues_created = 0
    with patch("evolution_scanner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        for finding in deduped[:max_issues]:
            if create_issue(finding, "evolution-found"):
                issues_created += 1

    assert issues_created == 3
    assert mock_run.call_count == 3
    # Verify each call was 'gh issue create' with correct labels
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert args[0] == "gh"
        assert args[1] == "issue"
        assert args[2] == "create"


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
    """Regression detection: update_history() computes resolved_findings by comparing snapshots."""
    history_path = tmp_path / "findings_over_time.json"

    # Tick 1: Two findings present
    findings_1 = [
        Finding("RULE_001", "warning", "test", "Issue 1", "file1.md", "evidence"),
        Finding("RULE_002", "warning", "test", "Issue 2", "file2.md", "evidence"),
    ]
    update_history(history_path, findings_1, 1, 100)

    # Tick 2: Only RULE_001 present, RULE_002 is gone (should be resolved)
    findings_2 = [
        Finding("RULE_001", "warning", "test", "Issue 1", "file1.md", "evidence"),
    ]
    update_history(history_path, findings_2, 1, 100)

    # Verify resolved_findings was populated
    with open(history_path) as f:
        data = json.load(f)

    assert len(data["resolved_findings"]) == 1
    assert data["resolved_findings"][0]["rule_id"] == "RULE_002"
    assert data["resolved_findings"][0]["location"] == "file2.md"
    assert "resolved_at" in data["resolved_findings"][0]

    # Tick 3: RULE_002 reappears - should be marked as critical regression
    findings_3 = [
        Finding("RULE_001", "warning", "test", "Issue 1", "file1.md", "evidence"),
        Finding("RULE_002", "warning", "test", "Reappeared", "file2.md", "evidence"),
    ]
    updated = detect_regressions(findings_3, history_path)

    # RULE_002 should be upgraded to critical
    rule_002_finding = next(f for f in updated if f.rule_id == "RULE_002")
    assert rule_002_finding.severity == "critical"


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
    """Same finding 3 ticks → gh issue edit --add-label called with correct issue number."""
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
        # Mock gh issue list to return matching issue
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"number": 42, "title": "[evolution] RULE_001", "body": "**Rule ID**: RULE_001\\n**Location**: file.md"}]',
        )

        check_isolation(findings, history_path, 3, "evolution-isolated", "evolution-found")

        # Verify gh issue edit was called with --add-label evolution-isolated
        edit_calls = [
            call for call in mock_run.call_args_list
            if len(call[0]) > 0 and len(call[0][0]) >= 4
            and call[0][0][1] == "issue" and call[0][0][2] == "edit"
        ]

        assert len(edit_calls) > 0, "gh issue edit was not called"
        edit_call = edit_calls[0]
        args = edit_call[0][0]
        assert args[0] == "gh"
        assert args[1] == "issue"
        assert args[2] == "edit"
        assert args[3] == "42"  # Issue number extracted from gh issue list
        assert "--add-label" in args
        assert "evolution-isolated" in args


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
            stdout='[{"title": "[evolution] RULE_001", "body": "**Rule ID**: RULE_001\\n**Location**: file1.md", "number": 42}]',
        )
        issues = get_open_issues("evolution-found")
        assert len(issues) == 1
        assert issues[0]["rule_id"] == "RULE_001"
        assert issues[0]["location"] == "file1.md"
        assert issues[0]["number"] == 42


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


# ============================================================================
# Exit Code and Adapter Tests (VAL-FIX-EXIT-001, VAL-FIX-ADAPT-*)
# ============================================================================


def test_exit_code_nonzero_with_findings():
    """VAL-FIX-EXIT-001: returncode=1 + valid stdout → findings returned."""
    # Real daily audit output with violations
    real_output = {
        "audit_date": "2026-08-08",
        "projects": {
            "memory": {
                "violations": [
                    {
                        "type": "hash_mismatch",
                        "severity": "critical",
                        "file": "memory/system/manifest.json",
                        "detail": "manifest.json 不存在：项目未签名",
                    }
                ]
            }
        },
        "infrastructure": {"servers": {}},
    }
    tool = {"name": "daily_kb_audit", "command": "memory-audit-daily --json"}

    with patch("evolution_scanner.subprocess.run") as mock_run:
        # Simulate tool returning exit code 1 (found violations) with valid JSON
        mock_run.return_value = MagicMock(
            returncode=1, stdout=json.dumps(real_output), stderr=""
        )
        result = run_audit_tool(tool)

        # Should return findings despite non-zero exit code
        assert len(result) > 0
        assert result[0]["rule_id"] == "HASH_MISMATCH"
        assert result[0]["severity"] == "critical"


def test_adapt_daily_audit():
    """VAL-FIX-ADAPT-001: Real daily audit JSON → Finding dicts."""
    # Real format captured from memory-audit-daily --json
    raw_output = {
        "audit_date": "2026-08-08",
        "projects": {
            "memory": {
                "path": "/Users/busiji/memory",
                "violations": [
                    {
                        "type": "hash_mismatch",
                        "severity": "critical",
                        "file": "memory/system/manifest.json",
                        "detail": "manifest.json 不存在：项目未签名（缺少完整性清单）",
                    }
                ],
                "note": "memory-core 源仓库：跳过 KB 未签名/残留/大文件检查",
            }
        },
        "infrastructure": {
            "servers": {
                "node-00": {
                    "host": "47.111.21.195",
                    "violations": [
                        {
                            "type": "container_down",
                            "severity": "critical",
                            "file": "node-00/openclaw",
                            "detail": "期望容器未运行：openclaw",
                        }
                    ],
                }
            }
        },
    }

    findings = adapt_daily_audit(raw_output)

    assert len(findings) == 2
    # First finding from projects
    assert findings[0]["rule_id"] == "HASH_MISMATCH"
    assert findings[0]["severity"] == "critical"
    assert findings[0]["category"] == "daily_audit"
    assert findings[0]["location"] == "memory/system/manifest.json"
    assert "manifest.json" in findings[0]["description"]
    # Second finding from infrastructure
    assert findings[1]["rule_id"] == "CONTAINER_DOWN"
    assert findings[1]["location"] == "node-00/openclaw"


def test_adapt_consistency_check():
    """VAL-FIX-ADAPT-002: Real consistency check JSON → Finding dicts."""
    # Real format captured from memory-consistency-check --json
    raw_output = {
        "errors": [
            "[init_validate_roundtrip] init_project_memory failed: ",
        ],
        "warnings": [
            "[docstring_host_mentions] /Users/busiji/memory/tests/test_hook_event.py: docstring mentions codex and claude but not factory",
        ],
        "checks": [
            {
                "name": "init_validate_roundtrip",
                "errors": ["init_project_memory failed: "],
                "warnings": [],
                "passed": False,
            }
        ],
    }

    findings = adapt_consistency_check(raw_output)

    assert len(findings) == 2
    # Error finding
    assert findings[0]["rule_id"] == "INIT_VALIDATE_ROUNDTRIP"
    assert findings[0]["severity"] == "warning"
    assert findings[0]["category"] == "consistency"
    assert "init_project_memory failed" in findings[0]["description"]
    # Warning finding
    assert findings[1]["rule_id"] == "DOCSTRING_HOST_MENTIONS"
    assert findings[1]["severity"] == "info"
    assert findings[1]["location"] == "/Users/busiji/memory/tests/test_hook_event.py"


def test_adapt_error_patterns():
    """VAL-FIX-ADAPT-003: Real registry.jsonl format → Finding dicts."""
    # Real format from memory/kb/patterns/registry.jsonl
    raw_lines = [
        {
            "fingerprint": "30a2abcbf1334863",
            "type": "llm_api_error",
            "script": "daily_summary_generator",
            "normalized_msg": "LLM API curl error:",
            "status": "detected",
            "first_seen": "2026-06-02T23:57:06.732633+08:00",
            "last_seen": "2026-06-02T23:57:06.732633+08:00",
            "distinct_days": ["2026-06-02"],
            "total_count": 1,
            "projects": ["/Users/busiji/memory"],
            "threshold_met": None,  # Not threshold yet
        },
        {
            "fingerprint": "81316c864847d7da",
            "type": "json_parse_error",
            "script": "pretooluse_guard",
            "normalized_msg": "Invalid JSON input: Expecting value",
            "status": "detected",
            "total_count": 2,
            "threshold_met": "days",  # Meets threshold
        },
        {
            "fingerprint": "843d8aabcfed4c0c",
            "type": "transcript_missing",
            "script": "session_end_logger",
            "normalized_msg": "transcript not found",
            "status": "detected",
            "total_count": 5,
            "threshold_met": "both",  # Meets both thresholds
        },
    ]

    findings = adapt_error_patterns(raw_lines)

    # Only entries with threshold_met should be converted
    assert len(findings) == 2
    # First threshold entry
    assert findings[0]["rule_id"] == "ERROR_PATTERN_JSON_PARSE_ERROR"
    assert findings[0]["severity"] == "warning"  # "days" threshold
    assert findings[0]["category"] == "error_pattern"
    assert findings[0]["location"] == "pretooluse_guard"
    assert "fingerprint=81316c864847d7da" in findings[0]["evidence"]
    # Second threshold entry (both)
    assert findings[1]["rule_id"] == "ERROR_PATTERN_TRANSCRIPT_MISSING"
    assert findings[1]["severity"] == "critical"  # "both" threshold


def test_config_has_json_flags():
    """VAL-FIX-ADAPT-004: Config commands include --json flags."""
    config_path = Path(__file__).parent.parent / ".evolution" / "config.yml"
    with open(config_path) as f:
        config_content = f.read()

    # Check that --json flags are present
    assert "memory-audit-daily --json" in config_content
    assert "memory-consistency-check --json" in config_content
