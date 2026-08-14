"""Tests for suppress.json expires lifecycle mechanism (VAL-SUPPRESS-001/002/003)."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import Finding, _matches_suppression, load_suppressions


def test_expired_suppression_does_not_suppress(tmp_path: Path) -> None:
    """VAL-SUPPRESS-001: Entry with past expires date does NOT suppress matching finding."""
    # Create suppress.json with expired entry
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Use a date clearly in the past (2026-08-01, assuming current date is after)
    expired_entry = {
        "rule_id": "TEST_RULE_001",
        "location": "test/file.md",
        "expires": "2026-08-01",
    }
    suppress_path.write_text(json.dumps({"suppressed": [expired_entry]}), encoding="utf-8")

    # Load suppressions
    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    # Create matching finding
    finding = Finding(
        rule_id="TEST_RULE_001",
        severity="warning",
        category="test",
        description="Test finding",
        location="test/file.md",
        evidence="Test evidence",
    )

    # Expired entry should NOT suppress the finding
    assert not _matches_suppression(finding, suppressions[0]), \
        "Expired suppression entry should not suppress matching finding"


def test_future_suppression_still_suppresses(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002: Entry with future expires date suppresses matching finding."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Use a date far in the future
    future_entry = {
        "rule_id": "TEST_RULE_002",
        "location": "test/file2.md",
        "expires": "2030-12-31",
    }
    suppress_path.write_text(json.dumps({"suppressed": [future_entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    finding = Finding(
        rule_id="TEST_RULE_002",
        severity="warning",
        category="test",
        description="Test finding",
        location="test/file2.md",
        evidence="Test evidence",
    )

    # Future entry should suppress the finding
    assert _matches_suppression(finding, suppressions[0]), \
        "Future suppression entry should suppress matching finding"


def test_today_suppression_still_suppresses(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002: Entry with today's date as expires suppresses matching finding."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Use today's date
    today_str = date.today().isoformat()
    today_entry = {
        "rule_id": "TEST_RULE_003",
        "location": "test/file3.md",
        "expires": today_str,
    }
    suppress_path.write_text(json.dumps({"suppressed": [today_entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    finding = Finding(
        rule_id="TEST_RULE_003",
        severity="warning",
        category="test",
        description="Test finding",
        location="test/file3.md",
        evidence="Test evidence",
    )

    # Today's date should suppress the finding
    assert _matches_suppression(finding, suppressions[0]), \
        "Today's date suppression entry should suppress matching finding"


def test_no_expires_field_permanent_suppression(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002: Entry without expires field suppresses permanently (backward compat)."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Entry without expires field (legacy format)
    legacy_entry = {
        "rule_id": "TEST_RULE_004",
        "location": "test/file4.md",
    }
    suppress_path.write_text(json.dumps({"suppressed": [legacy_entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    finding = Finding(
        rule_id="TEST_RULE_004",
        severity="warning",
        category="test",
        description="Test finding",
        location="test/file4.md",
        evidence="Test evidence",
    )

    # Legacy entry (no expires) should suppress the finding
    assert _matches_suppression(finding, suppressions[0]), \
        "Legacy suppression entry (no expires) should suppress matching finding"


def test_malformed_expires_fails_open(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """VAL-SUPPRESS-003: Malformed expires value fails open (no suppress + stderr warning)."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Entry with malformed expires
    malformed_entry = {
        "rule_id": "TEST_RULE_005",
        "location": "test/file5.md",
        "expires": "not-a-valid-date",
    }
    suppress_path.write_text(json.dumps({"suppressed": [malformed_entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    finding = Finding(
        rule_id="TEST_RULE_005",
        severity="warning",
        category="test",
        description="Test finding",
        location="test/file5.md",
        evidence="Test evidence",
    )

    # Malformed entry should NOT suppress (fail-open)
    assert not _matches_suppression(finding, suppressions[0]), \
        "Malformed expires should fail open and not suppress"

    # Verify warning was printed to stderr
    captured = capsys.readouterr()
    assert "not-a-valid-date" in captured.err or "malformed" in captured.err.lower(), \
        "Warning about malformed expires should be printed to stderr"


def test_wildcard_suppression_with_expires(tmp_path: Path) -> None:
    """Wildcard rule_id/location still works with expires field."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Wildcard entry with future expires
    wildcard_entry = {
        "rule_id": "*",
        "location": "*",
        "expires": "2030-12-31",
    }
    suppress_path.write_text(json.dumps({"suppressed": [wildcard_entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    finding = Finding(
        rule_id="ANY_RULE",
        severity="warning",
        category="test",
        description="Test finding",
        location="any/file.md",
        evidence="Test evidence",
    )

    # Wildcard with future expires should suppress
    assert _matches_suppression(finding, suppressions[0]), \
        "Wildcard suppression with future expires should suppress"


def test_wildcard_suppression_expired(tmp_path: Path) -> None:
    """Wildcard suppression with past expires does not suppress."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Wildcard entry with expired date
    wildcard_entry = {
        "rule_id": "*",
        "location": "*",
        "expires": "2020-01-01",
    }
    suppress_path.write_text(json.dumps({"suppressed": [wildcard_entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    finding = Finding(
        rule_id="ANY_RULE",
        severity="warning",
        category="test",
        description="Test finding",
        location="any/file.md",
        evidence="Test evidence",
    )

    # Wildcard with past expires should NOT suppress
    assert not _matches_suppression(finding, suppressions[0]), \
        "Wildcard suppression with past expires should not suppress"


def test_non_matching_finding_not_suppressed(tmp_path: Path) -> None:
    """Finding that doesn't match rule_id/location is not suppressed."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    entry = {
        "rule_id": "SPECIFIC_RULE",
        "location": "specific/file.md",
        "expires": "2030-12-31",
    }
    suppress_path.write_text(json.dumps({"suppressed": [entry]}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)

    # Finding with different rule_id
    finding_different_rule = Finding(
        rule_id="DIFFERENT_RULE",
        severity="warning",
        category="test",
        description="Test finding",
        location="specific/file.md",
        evidence="Test evidence",
    )

    assert not _matches_suppression(finding_different_rule, suppressions[0]), \
        "Finding with different rule_id should not be suppressed"

    # Finding with different location
    finding_different_location = Finding(
        rule_id="SPECIFIC_RULE",
        severity="warning",
        category="test",
        description="Test finding",
        location="different/file.md",
        evidence="Test evidence",
    )

    assert not _matches_suppression(finding_different_location, suppressions[0]), \
        "Finding with different location should not be suppressed"
