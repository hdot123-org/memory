"""Schema guard tests for suppress.json expires field governance.

Fulfills VAL-SUPPRESS-001/002/003:
- VAL-SUPPRESS-001: Missing expires triggers deprecation warning (with rule_id/location) AND entry still suppresses (backward compat)
- VAL-SUPPRESS-002: CI schema guard: bad structure → hard fail; missing expires → warn only; real file passes
- VAL-SUPPRESS-003: Existing semantics preserved (covered by tests/test_suppression_expiry.py)
"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import Finding, _matches_suppression, apply_suppressions, load_suppressions


def test_missing_expires_triggers_deprecation_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """VAL-SUPPRESS-001a: load_suppressions prints one-time deprecation warning for entry missing expires."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Entry without expires field
    legacy_entry = {
        "rule_id": "LEGACY_RULE_001",
        "location": "legacy/file.py",
        # No 'expires' key
    }
    suppress_path.write_text(
        json.dumps({"suppressed": [legacy_entry]}), encoding="utf-8"
    )

    # Load suppressions
    suppressions = load_suppressions(tmp_path)

    # Entry should still be loaded (backward compat)
    assert len(suppressions) == 1
    assert suppressions[0]["rule_id"] == "LEGACY_RULE_001"

    # Deprecation warning should be printed
    captured = capsys.readouterr()
    # Warning should mention the rule_id and location
    assert "LEGACY_RULE_001" in captured.err or "LEGACY_RULE_001" in captured.out, \
        "Deprecation warning should mention rule_id"
    assert "legacy/file.py" in captured.err or "legacy/file.py" in captured.out, \
        "Deprecation warning should mention location"
    # Warning should indicate deprecation
    assert "deprecat" in (captured.err + captured.out).lower(), \
        "Warning should indicate deprecation"


def test_missing_expires_entry_still_suppresses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """VAL-SUPPRESS-001b: Entry without expires still suppresses matching finding (backward compat)."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Entry without expires field
    legacy_entry = {
        "rule_id": "LEGACY_RULE_002",
        "location": "legacy/file2.py",
    }
    suppress_path.write_text(
        json.dumps({"suppressed": [legacy_entry]}), encoding="utf-8"
    )

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    # Create matching finding
    finding = Finding(
        rule_id="LEGACY_RULE_002",
        severity="warning",
        category="test",
        description="Test finding",
        location="legacy/file2.py",
        evidence="Test evidence",
    )

    # Entry should still suppress (backward compat)
    assert _matches_suppression(finding, suppressions[0]), \
        "Entry without expires should still suppress matching finding"


def test_missing_expires_warning_is_one_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deprecation warning for missing expires is emitted once during load, not per-finding."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    legacy_entry = {
        "rule_id": "LEGACY_RULE_003",
        "location": "legacy/file3.py",
    }
    suppress_path.write_text(
        json.dumps({"suppressed": [legacy_entry]}), encoding="utf-8"
    )

    suppressions = load_suppressions(tmp_path)
    # Clear captured output from load
    capsys.readouterr()

    # Create multiple findings that match the entry
    findings = [
        Finding(
            rule_id="LEGACY_RULE_003",
            severity="warning",
            category="test",
            description=f"Test finding {i}",
            location="legacy/file3.py",
            evidence=f"Evidence {i}",
        )
        for i in range(5)
    ]

    # Apply suppressions to all findings
    for finding in findings:
        _matches_suppression(finding, suppressions[0])

    # Verify no additional warnings were printed during matching
    captured = capsys.readouterr()
    assert "LEGACY_RULE_003" not in (captured.err + captured.out), \
        "No additional deprecation warnings should be emitted during matching"


# ---------------------------------------------------------------------------
# VAL-SUPPRESS-002: CI schema guard tests
# ---------------------------------------------------------------------------


def test_schema_guard_suppressed_must_be_list(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002a: suppress.json with 'suppressed' as non-list fails validation."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Invalid: 'suppressed' is a string, not a list
    invalid_data = {"suppressed": "not a list"}
    suppress_path.write_text(json.dumps(invalid_data), encoding="utf-8")

    # load_suppressions should handle gracefully (returns empty list)
    suppressions = load_suppressions(tmp_path)
    assert suppressions == [], "Non-list 'suppressed' should be treated as empty"


def test_schema_guard_entry_must_be_dict(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002b: suppress.json with non-dict entries fails validation."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Invalid: entry is a string, not a dict
    invalid_data = {"suppressed": ["not a dict"]}
    suppress_path.write_text(json.dumps(invalid_data), encoding="utf-8")

    # load_suppressions should skip non-dict entries (schema guard)
    suppressions = load_suppressions(tmp_path)
    # Non-dict entries are skipped, so result is empty
    assert suppressions == [], "Non-dict entries should be skipped"


def test_schema_guard_expires_must_be_iso_date(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002c: suppress.json with non-ISO expires fails validation."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Invalid: expires is not ISO date format
    invalid_entry = {
        "rule_id": "BAD_DATE",
        "location": "test.py",
        "expires": "not-a-valid-date",
    }
    suppress_path.write_text(
        json.dumps({"suppressed": [invalid_entry]}), encoding="utf-8"
    )

    # load_suppressions should handle gracefully (entry still loaded, but marked as expired)
    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    # Entry with malformed expires should fail open (not suppress)
    finding = Finding(
        rule_id="BAD_DATE",
        severity="warning",
        category="test",
        description="Test",
        location="test.py",
        evidence="test",
    )
    assert not _matches_suppression(finding, suppressions[0]), \
        "Malformed expires should fail open"


def test_schema_guard_missing_expires_warns_but_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """VAL-SUPPRESS-002d: Missing expires field triggers warning but does not fail validation."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Valid but deprecated: missing expires field
    legacy_entry = {
        "rule_id": "LEGACY",
        "location": "legacy.py",
    }
    suppress_path.write_text(
        json.dumps({"suppressed": [legacy_entry]}), encoding="utf-8"
    )

    # Should load successfully (with warning)
    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 1

    # Warning should be printed
    captured = capsys.readouterr()
    assert "LEGACY" in (captured.err + captured.out), \
        "Missing expires should trigger deprecation warning"


def _validate_suppress_json_raw(suppress_path: Path) -> None:
    """Raw structural validation — bypasses load_suppressions' graceful degradation.

    Raises AssertionError (or calls pytest.fail) on structural violations.
    Shared by real-file guard and negative-path tests (VAL-SUPPRESS-002).
    """
    with suppress_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict), f"suppress.json root must be a dict, got {type(data).__name__}"
    assert "suppressed" in data, "suppress.json must contain 'suppressed' key"
    assert isinstance(data["suppressed"], list), (
        f"'suppressed' must be a list, got {type(data['suppressed']).__name__}"
    )

    for idx, entry in enumerate(data["suppressed"]):
        assert isinstance(entry, dict), (
            f"suppressed[{idx}] must be a dict, got {type(entry).__name__}: {entry!r}"
        )
        # P3 polish: check required keys exist (rule_id, location)
        assert "rule_id" in entry, (
            f"suppressed[{idx}] must contain 'rule_id' key: {entry!r}"
        )
        assert "location" in entry, (
            f"suppressed[{idx}] must contain 'location' key: {entry!r}"
        )
        # If expires is present, it must be valid ISO date
        if "expires" in entry and entry["expires"] is not None:
            try:
                date.fromisoformat(str(entry["expires"]))
            except ValueError:
                pytest.fail(f"Entry has invalid expires format: {entry['expires']}")


def test_schema_guard_real_suppress_json_passes() -> None:
    """VAL-SUPPRESS-002e: Real .evolution/suppress.json passes raw schema validation.

    Unlike the load_suppressions() path (which silently degrades structural
    violations), this test reads the raw JSON and asserts hard structure,
    so a corrupted suppress.json would fail CI.
    """
    repo_root = Path(__file__).parent.parent
    suppress_path = repo_root / ".evolution" / "suppress.json"

    # P3 polish: hard failure if file missing (prevents silent skip masking coverage)
    assert suppress_path.exists(), ".evolution/suppress.json must exist in repository"

    # Raw structural validation (not through load_suppressions)
    _validate_suppress_json_raw(suppress_path)

    # Also verify load_suppressions still works (backward compat)
    suppressions = load_suppressions(repo_root)
    assert isinstance(suppressions, list), "Suppressions should be a list"


def test_schema_guard_negative_suppressed_not_list(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002f: Raw guard FAILS when 'suppressed' is not a list.

    Proves the guard has hard-fail capability — same corruption through
    load_suppressions would silently return [], but the raw guard catches it.
    """
    suppress_path = tmp_path / "suppress.json"
    suppress_path.write_text(json.dumps({"suppressed": "not a list"}), encoding="utf-8")

    with pytest.raises(AssertionError, match="must be a list"):
        _validate_suppress_json_raw(suppress_path)


def test_schema_guard_negative_entry_not_dict(tmp_path: Path) -> None:
    """VAL-SUPPRESS-002g: Raw guard FAILS when an entry is not a dict.

    Proves the guard has hard-fail capability — same corruption through
    load_suppressions would silently skip the entry, but the raw guard catches it.
    """
    suppress_path = tmp_path / "suppress.json"
    suppress_path.write_text(
        json.dumps({"suppressed": ["not a dict"]}), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match="must be a dict"):
        _validate_suppress_json_raw(suppress_path)


@pytest.mark.parametrize(
    "bad_entry, match_pattern",
    [
        pytest.param(
            {"location": "file.py", "expires": "2030-01-01"},
            "must contain 'rule_id' key",
            id="missing-rule_id",
        ),
        pytest.param(
            {"rule_id": "R001", "expires": "2030-01-01"},
            "must contain 'location' key",
            id="missing-location",
        ),
    ],
)
def test_schema_guard_negative_entry_missing_required_keys(
    tmp_path: Path, bad_entry: dict, match_pattern: str
) -> None:
    """Negative proof: _validate_suppress_json_raw rejects entries missing rule_id or location.

    Proves the key-existence assertions (PR #688) are not vacuous —
    each missing-key case triggers a hard AssertionError.
    """
    suppress_path = tmp_path / "suppress.json"
    suppress_path.write_text(
        json.dumps({"suppressed": [bad_entry]}), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match=match_pattern):
        _validate_suppress_json_raw(suppress_path)


def test_schema_guard_negative_entry_non_iso_expires(tmp_path: Path) -> None:
    """Negative proof: _validate_suppress_json_raw rejects entries with non-ISO expires.

    The expires check uses pytest.fail (not AssertionError), so this is a
    separate test to keep the parametrize above clean and type-consistent.
    """
    bad_entry = {"rule_id": "R001", "location": "file.py", "expires": "not-a-date"}
    suppress_path = tmp_path / "suppress.json"
    suppress_path.write_text(
        json.dumps({"suppressed": [bad_entry]}), encoding="utf-8"
    )

    with pytest.raises(pytest.fail.Exception, match="invalid expires format"):
        _validate_suppress_json_raw(suppress_path)


# ---------------------------------------------------------------------------
# Integration test: apply_suppressions with mixed entries
# ---------------------------------------------------------------------------


def test_apply_suppressions_with_mixed_expires(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Integration test: apply_suppressions handles mix of entries with/without expires."""
    evolution_dir = tmp_path / ".evolution"
    evolution_dir.mkdir()
    suppress_path = evolution_dir / "suppress.json"

    # Mix of entries: with expires, without expires, malformed expires
    entries = [
        {
            "rule_id": "RULE_WITH_EXPIRES",
            "location": "file1.py",
            "expires": "2030-12-31",  # Future: should suppress
        },
        {
            "rule_id": "RULE_WITHOUT_EXPIRES",
            "location": "file2.py",
            # No expires: should suppress (with deprecation warning)
        },
        {
            "rule_id": "RULE_BAD_EXPIRES",
            "location": "file3.py",
            "expires": "invalid-date",  # Malformed: should fail open
        },
    ]
    suppress_path.write_text(json.dumps({"suppressed": entries}), encoding="utf-8")

    suppressions = load_suppressions(tmp_path)
    assert len(suppressions) == 3

    # Create findings
    findings = [
        Finding("RULE_WITH_EXPIRES", "warning", "test", "Test 1", "file1.py", "e1"),
        Finding("RULE_WITHOUT_EXPIRES", "warning", "test", "Test 2", "file2.py", "e2"),
        Finding("RULE_BAD_EXPIRES", "warning", "test", "Test 3", "file3.py", "e3"),
        Finding("RULE_NOT_SUPPRESSED", "warning", "test", "Test 4", "file4.py", "e4"),
    ]

    # Apply suppressions
    filtered = apply_suppressions(findings, suppressions)

    # RULE_WITH_EXPIRES (future) → suppressed
    # RULE_WITHOUT_EXPIRES → suppressed (backward compat)
    # RULE_BAD_EXPIRES → NOT suppressed (fail open)
    # RULE_NOT_SUPPRESSED → NOT suppressed
    assert len(filtered) == 2, f"Expected 2 findings after suppression, got {len(filtered)}"
    assert filtered[0].rule_id == "RULE_BAD_EXPIRES"
    assert filtered[1].rule_id == "RULE_NOT_SUPPRESSED"
