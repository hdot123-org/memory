"""Tests for P2 info-level noise suppression proposal (VAL-SUP-001, VAL-SUP-002).

Tests that persistent info-level findings in the history trigger suppress.json
proposal output to stdout, and that non-persistent findings do not.
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import check_persistent_info_findings


def _make_history(num_snapshots: int, findings_per_snapshot: list[list[dict]]) -> dict:
    """Helper to create a history dict with N snapshots containing given findings.

    Args:
        num_snapshots: Number of snapshots to create
        findings_per_snapshot: List of finding-LISTS. Each element is a list of
                               findings (as dicts) for that snapshot.
                               If len < num_snapshots, all remaining snapshots
                               get the same findings as the last entry.
                               If len == 1, all snapshots get the same findings.
    """
    snapshots = []
    for i in range(num_snapshots):
        if i < len(findings_per_snapshot):
            findings = findings_per_snapshot[i]
        else:
            findings = findings_per_snapshot[-1] if findings_per_snapshot else []
        snapshots.append({
            "timestamp": f"2026-08-{15 + i:02d}T00:00:00+00:00",
            "tick_id": f"2026081{i}-000000",
            "findings": findings,
            "issues_created": 0,
        })
    return {"snapshots": snapshots, "resolved_findings": []}


def test_suppression_suggestion_001_persistent_info_finding_emits_snippet(tmp_path):
    """VAL-SUP-001: info finding present in >=10 consecutive snapshots emits suppress proposal.

    When a CODE_HYGIENE_DUPLICATE_BLOCK finding with severity=info appears in
    10+ consecutive snapshots, the function should output a JSON proposal to
    stdout containing rule_id, location, and expires (= UTC today + 90 days).
    """
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # Create a persistent info-level finding that appears in all 12 snapshots
    persistent_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    history_data = _make_history(12, [[persistent_finding]])
    history_path.write_text(json.dumps(history_data))

    # Capture stdout
    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # Should have returned 1 proposal
    assert len(proposals) == 1

    proposal = proposals[0]
    assert proposal["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"
    assert proposal["location"] == "foo.py::L10-bar.py::L20"
    assert "expires" in proposal

    # Verify expires is exactly 90 days from today (UTC)
    from datetime import timedelta
    expected_expires = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    assert proposal["expires"] == expected_expires

    # Verify stdout contains the proposal
    stdout_text = captured.getvalue()
    assert "suppress.json proposal" in stdout_text
    assert "CODE_HYGIENE_DUPLICATE_BLOCK" in stdout_text
    assert expected_expires in stdout_text


def test_suppression_suggestion_002_fewer_than_10_snapshots_no_proposal(tmp_path):
    """VAL-SUP-002: info finding present in <10 consecutive snapshots emits NO proposal.

    When a finding appears in fewer than 10 consecutive snapshots, no suppress
    proposal should be emitted.
    """
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # Create a finding that appears in only 5 snapshots (below threshold)
    transient_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    history_data = _make_history(5, [[transient_finding]])
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # Should have returned 0 proposals
    assert len(proposals) == 0

    # Verify stdout does NOT contain a proposal
    stdout_text = captured.getvalue()
    assert "suppress.json proposal" not in stdout_text


def test_suppression_suggestion_does_not_write_suppress_file(tmp_path):
    """VAL-SUP-001: Persistent info finding emits proposal but NEVER writes suppress.json.

    The function must only print to stdout, never modify .evolution/suppress.json.
    """
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # Create .evolution/suppress.json with initial content
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"
    initial_content = {"suppressed": []}
    suppress_path.write_text(json.dumps(initial_content))

    # Get initial mtime
    initial_mtime = suppress_path.stat().st_mtime

    # Create a persistent info finding
    persistent_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    history_data = _make_history(10, [[persistent_finding]])
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # Should have emitted a proposal
    assert len(proposals) == 1

    # Verify suppress.json was NOT modified
    assert suppress_path.exists()
    assert suppress_path.read_text() == json.dumps(initial_content)
    final_mtime = suppress_path.stat().st_mtime
    assert final_mtime == initial_mtime, "suppress.json mtime changed — function must not write to disk"


def test_suppression_suggestion_skips_already_suppressed(tmp_path):
    """If a finding is already in suppress.json, no duplicate proposal is emitted."""
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # Create .evolution/suppress.json with the finding already suppressed
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"
    suppress_content = {
        "suppressed": [
            {
                "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
                "location": "foo.py::L10-bar.py::L20",
                "expires": "2026-12-31",
            }
        ]
    }
    suppress_path.write_text(json.dumps(suppress_content))

    # Create a persistent info finding that matches the suppressed entry
    persistent_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    history_data = _make_history(10, [[persistent_finding]])
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # Should have returned 0 proposals (already suppressed)
    assert len(proposals) == 0

    # Verify stdout does NOT contain a proposal
    stdout_text = captured.getvalue()
    assert "suppress.json proposal" not in stdout_text


def test_suppression_suggestion_only_info_severity(tmp_path):
    """Only info-severity findings trigger proposals; warning/critical are skipped."""
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # Create persistent findings with different severities
    warning_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "warning",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    critical_finding = {
        "rule_id": "SOME_OTHER_RULE",
        "severity": "critical",
        "category": "consistency",
        "description": "Critical issue",
        "location": "baz.py::L30",
        "evidence": "missing",
    }
    history_data = _make_history(10, [[warning_finding, critical_finding]])
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # Should have returned 0 proposals (no info-severity findings)
    assert len(proposals) == 0


def test_suppression_suggestion_multiple_persistent_findings(tmp_path):
    """Multiple persistent info findings each get their own proposal."""
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # Create two persistent info findings
    finding1 = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block 1",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    finding2 = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block 2",
        "location": "baz.py::L30-qux.py::L40",
        "evidence": "similarity=0.88",
    }
    history_data = _make_history(10, [[finding1, finding2]])
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # Should have returned 2 proposals
    assert len(proposals) == 2

    locations = {p["location"] for p in proposals}
    assert "foo.py::L10-bar.py::L20" in locations
    assert "baz.py::L30-qux.py::L40" in locations

    # All should have the same expires
    from datetime import timedelta
    expected_expires = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    assert all(p["expires"] == expected_expires for p in proposals)


def test_suppression_suggestion_no_history_file(tmp_path):
    """Missing history file returns empty proposals without error."""
    history_path = tmp_path / "nonexistent.json"
    repo_root = tmp_path

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    assert len(proposals) == 0


def test_suppression_suggestion_empty_history(tmp_path):
    """Empty history (no snapshots) returns empty proposals."""
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    history_data = {"snapshots": [], "resolved_findings": []}
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    assert len(proposals) == 0


def test_suppression_suggestion_003_intermittent_finding_no_proposal(tmp_path):
    """VAL-SUP-002 补强：≥10 快照内间歇出现（非全连续）不触发提案。

    即使总快照数 ≥10，若 finding 未在所有快照中出现（count < threshold），
    则不应触发提案。
    """
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # 创建 15 个快照，但 finding 只在其中 8 个出现（间歇，非连续）
    persistent_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }

    snapshots = []
    for i in range(15):
        # finding 出现在快照 0-7（共 8 个），不在 8-14
        if i < 8:
            snapshots.append({
                "timestamp": f"2026-08-{15 + i:02d}T00:00:00+00:00",
                "tick_id": f"2026081{i}-000000",
                "findings": [persistent_finding],
                "issues_created": 0,
            })
        else:
            snapshots.append({
                "timestamp": f"2026-08-{15 + i:02d}T00:00:00+00:00",
                "tick_id": f"2026081{i}-000000",
                "findings": [],
                "issues_created": 0,
            })

    history_data = {"snapshots": snapshots, "resolved_findings": []}
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # 不应触发提案（只在 8/15 快照出现，未达 threshold=10）
    assert len(proposals) == 0
    stdout_text = captured.getvalue()
    assert "suppress.json proposal" not in stdout_text


def test_suppression_suggestion_004_expired_suppress_allows_reproposal(tmp_path):
    """VAL-SUP-003：过期 suppress 条目不再永久静默同 finding 的再提案。

    当 suppress.json 中的条目已过期（expires < today），即使 finding 曾匹配该条目，
    仍应重新输出提案。
    """
    history_path = tmp_path / "findings_over_time.json"
    repo_root = tmp_path

    # 创建 .evolution/suppress.json，含一个已过期的条目
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    from datetime import timedelta
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    suppress_content = {
        "suppressed": [
            {
                "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
                "location": "foo.py::L10-bar.py::L20",
                "expires": yesterday,  # 已过期
            }
        ]
    }
    suppress_path.write_text(json.dumps(suppress_content))

    # 创建持续 info finding（在 10 个快照中全部出现）
    persistent_finding = {
        "rule_id": "CODE_HYGIENE_DUPLICATE_BLOCK",
        "severity": "info",
        "category": "code_hygiene",
        "description": "Duplicate block",
        "location": "foo.py::L10-bar.py::L20",
        "evidence": "similarity=0.95",
    }
    history_data = _make_history(10, [[persistent_finding]])
    history_path.write_text(json.dumps(history_data))

    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        proposals = check_persistent_info_findings(history_path, repo_root)

    # 应触发提案（suppress 已过期，不再抑制）
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"
    assert proposal["location"] == "foo.py::L10-bar.py::L20"
    assert "expires" in proposal

    stdout_text = captured.getvalue()
    assert "suppress.json proposal" in stdout_text
    assert "CODE_HYGIENE_DUPLICATE_BLOCK" in stdout_text
