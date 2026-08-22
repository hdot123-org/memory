#!/usr/bin/env python3.12
"""Tests for error_pattern_detector.py fingerprint and grouping engine."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from memory_core.tools.error_pattern_detector import (
    PatternGroup,
    _is_test_artifact,
    build_parser,
    compute_fingerprint,
    evaluate_threshold,
    group_by_fingerprint,
    main,
    merge_patterns,
    normalize_error_msg,
    parse_error_file,
    read_registry,
    resolve_patterns,
    run_pipeline,
    scan_project,
    write_registry,
)

ERROR_LOG_DIR = Path(__file__).resolve().parent.parent / "memory" / "log"


def _load_real_errors() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not ERROR_LOG_DIR.exists():
        return entries
    for fpath in sorted(ERROR_LOG_DIR.glob("*-errors.jsonl")):
        with fpath.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


REAL_ERRORS = _load_real_errors()


class TestNormalizePaths:
    def test_absolute_path_replaced(self) -> None:
        msg = "failed to open /Users/busiji/memory/log/foo.jsonl for reading"
        result = normalize_error_msg(msg)
        assert "<PATH>" in result
        assert "/Users/busiji/memory/log/foo.jsonl" not in result

    def test_relative_path_replaced(self) -> None:
        msg = "cannot read memory/log/foo.jsonl"
        result = normalize_error_msg(msg)
        assert "<PATH>" in result

    def test_path_with_tilde(self) -> None:
        msg = "error in ~/projects/app/config.toml"
        result = normalize_error_msg(msg)
        assert "<PATH>" in result


class TestNormalizeTimestamps:
    def test_iso_with_fractional_and_offset(self) -> None:
        msg = "error at 2026-07-12T11:07:05.219585+08:00 occurred"
        result = normalize_error_msg(msg)
        assert "<TS>" in result

    def test_iso_without_fractional(self) -> None:
        msg = "at 2026-07-12 11:07:05 failed"
        result = normalize_error_msg(msg)
        assert "<TS>" in result

    def test_iso_with_z_suffix(self) -> None:
        msg = "timestamp 2026-07-12T11:07:05Z here"
        result = normalize_error_msg(msg)
        assert "<TS>" in result

    def test_iso_with_fractional_z(self) -> None:
        msg = "at 2026-07-12T11:07:05.123Z done"
        result = normalize_error_msg(msg)
        assert "<TS>" in result

    def test_iso_with_compact_offset(self) -> None:
        msg = "time 2026-07-12T11:07:05+0800 end"
        result = normalize_error_msg(msg)
        assert "<TS>" in result


class TestNormalizeUUIDs:
    def test_uuid_replaced(self) -> None:
        msg = "session 12345678-1234-1234-1234-1234567890ab failed"
        result = normalize_error_msg(msg)
        assert "<UUID>" in result


class TestNormalizeHex:
    def test_exactly_8_char_hex(self) -> None:
        msg = "session 1a2b3c4d ended"
        result = normalize_error_msg(msg)
        assert "<HEX>" in result

    def test_7_char_hex_not_matched(self) -> None:
        msg = "token abc1234 here"
        result = normalize_error_msg(msg)
        assert "abc1234" in result

    def test_9_char_hex_not_matched(self) -> None:
        msg = "token abc123456 here"
        result = normalize_error_msg(msg)
        assert "abc123456" in result


class TestNormalizeNumbers:
    def test_standalone_numbers(self) -> None:
        msg = "retried 3 times after 300 ms"
        result = normalize_error_msg(msg)
        assert result == "retried N times after N ms"


class TestNormalizeWhitespace:
    def test_multiple_spaces(self) -> None:
        msg = "error:    too    many   spaces"
        result = normalize_error_msg(msg)
        assert "  " not in result

    def test_tabs_and_newlines(self) -> None:
        msg = "error:\t\ttoo\n\nmany\t  spaces"
        result = normalize_error_msg(msg)
        assert "\t" not in result
        assert "\n" not in result


class TestNormalizeStrip:
    def test_strip(self) -> None:
        msg = "   error here   "
        result = normalize_error_msg(msg)
        assert result == "error here"


class TestNormalizeOrder:
    def test_path_digits_not_leaked(self) -> None:
        msg = "failed: /var/log/app2/2026/file.bin"
        result = normalize_error_msg(msg)
        assert "<PATH>" in result
        assert result == "failed: <PATH>"


class TestNormalizeCombined:
    def test_exact_golden(self) -> None:
        msg = (
            "2026-07-12T11:07:05+08:00 session 1a2b3c4d "
            "req 12345678-1234-1234-1234-1234567890ab "
            "in /Users/x/p/log.jsonl retried 3 times"
        )
        result = normalize_error_msg(msg)
        expected = "<TS> session <HEX> req <UUID> in <PATH> retried N times"
        assert result == expected


class TestNormalizeDeterminism:
    def test_in_process(self) -> None:
        msg = "error at 2026-07-12T11:07:05+08:00 in /Users/x/file.py"
        results = [normalize_error_msg(msg) for _ in range(100)]
        assert len(set(results)) == 1

    def test_cross_process(self) -> None:
        import subprocess
        import sys

        script = (
            "from memory_core.tools.error_pattern_detector import normalize_error_msg; "
            'print(normalize_error_msg("error at 2026-07-12T11:07:05+08:00 in /Users/x/file.py"))'
        )
        r1 = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        r2 = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert r1.stdout.strip() == r2.stdout.strip()


class TestNormalizeIdempotent:
    def test_idempotent_varied_inputs(self) -> None:
        inputs = [
            "error at 2026-07-12T11:07:05+08:00 in /Users/x/file.py",
            "session 1a2b3c4d crashed with code 42",
            "UUID 12345678-1234-1234-1234-1234567890ab failed",
            "already <PATH> normalized <TS> with <HEX> and <UUID>",
            "",
            "   spaces   everywhere   ",
        ]
        for msg in inputs:
            once = normalize_error_msg(msg)
            twice = normalize_error_msg(once)
            assert once == twice, f"Not idempotent for: {msg!r}"


class TestNormalizeEdgeCases:
    def test_empty_string(self) -> None:
        assert normalize_error_msg("") == ""

    def test_none_message(self) -> None:
        result = normalize_error_msg(None)  # type: ignore[arg-type]
        assert result == ""

    def test_long_message(self) -> None:
        long_msg = "error " + "/path/to/file.py " * 10000 + "failed 42 times"
        result = normalize_error_msg(long_msg)
        assert "<PATH>" in result
        assert "N" in result

    def test_unicode_message(self) -> None:
        msg = "错误：文件 /x/y.jsonl 不存在"
        result = normalize_error_msg(msg)
        assert "<PATH>" in result
        assert "错误" in result

    def test_unicode_fingerprint_stable(self) -> None:
        msg = "错误：文件 /x/y.jsonl 不存在"
        fp1 = compute_fingerprint("t", "s", normalize_error_msg(msg))
        fp2 = compute_fingerprint("t", "s", normalize_error_msg(msg))
        assert fp1 == fp2
        assert re.fullmatch(r"[0-9a-f]{16}", fp1)


class TestFingerprint:
    def test_16_char_hex(self) -> None:
        fp = compute_fingerprint("llm_api_error", "daily_summary_generator", "some msg")
        assert re.fullmatch(r"[0-9a-f]{16}", fp)

    def test_composition_golden_vector(self) -> None:
        expected = hashlib.sha256(b"t|s|m").hexdigest()[:16]
        assert compute_fingerprint("t", "s", "m") == expected

    def test_varies_with_type(self) -> None:
        fp1 = compute_fingerprint("type_a", "script", "msg")
        fp2 = compute_fingerprint("type_b", "script", "msg")
        assert fp1 != fp2

    def test_varies_with_script(self) -> None:
        fp1 = compute_fingerprint("type", "script_a", "msg")
        fp2 = compute_fingerprint("type", "script_b", "msg")
        assert fp1 != fp2

    def test_varies_with_msg(self) -> None:
        fp1 = compute_fingerprint("type", "script", "msg_a")
        fp2 = compute_fingerprint("type", "script", "msg_b")
        assert fp1 != fp2

    def test_empty_msg_fingerprint(self) -> None:
        fp = compute_fingerprint("t", "s", "")
        assert re.fullmatch(r"[0-9a-f]{16}", fp)


class TestGroupByFingerprint:
    @staticmethod
    def _make_entry(
        ts: str,
        msg: str,
        error_type: str = "llm_api_error",
        script: str = "daily_summary_generator",
        project: str = "/Users/busiji/memory",
    ) -> dict[str, Any]:
        return {"ts": ts, "type": error_type, "script": script, "project": project, "msg": msg}

    def test_entries_same_fingerprint_grouped(self) -> None:
        entries = [
            self._make_entry("2026-07-12T11:07:05+08:00", "curl error in /Users/a/b.py"),
            self._make_entry("2026-07-12T12:00:00+08:00", "curl error in /Users/c/d.py"),
            self._make_entry("2026-07-13T09:00:00+08:00", "curl error in /Users/e/f.py"),
            self._make_entry("2026-07-13T10:00:00+08:00", "curl error in /Users/g/h.py"),
            self._make_entry("2026-07-14T11:00:00+08:00", "curl error in /Users/i/j.py"),
        ]
        groups = group_by_fingerprint(entries)
        assert len(groups) == 1
        group = list(groups.values())[0]
        assert group.total_count == 5

    def test_first_seen_is_earliest(self) -> None:
        entries = [
            self._make_entry("2026-07-14T11:00:00+08:00", "curl error in /a/b.py"),
            self._make_entry("2026-07-12T09:00:00+08:00", "curl error in /c/d.py"),
            self._make_entry("2026-07-13T10:00:00+08:00", "curl error in /e/f.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.first_seen == "2026-07-12T09:00:00+08:00"

    def test_last_seen_is_latest(self) -> None:
        entries = [
            self._make_entry("2026-07-14T11:00:00+08:00", "curl error in /a/b.py"),
            self._make_entry("2026-07-12T09:00:00+08:00", "curl error in /c/d.py"),
            self._make_entry("2026-07-13T10:00:00+08:00", "curl error in /e/f.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.last_seen == "2026-07-14T11:00:00+08:00"

    def test_distinct_days(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "err in /a/b.py"),
            self._make_entry("2026-07-12T15:00:00+08:00", "err in /c/d.py"),
            self._make_entry("2026-07-13T10:00:00+08:00", "err in /e/f.py"),
            self._make_entry("2026-07-14T11:00:00+08:00", "err in /g/h.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.distinct_days == ["2026-07-12", "2026-07-13", "2026-07-14"]

    def test_distinct_days_sorted(self) -> None:
        entries = [
            self._make_entry("2026-07-14T11:00:00+08:00", "err in /g/h.py"),
            self._make_entry("2026-07-12T09:00:00+08:00", "err in /a/b.py"),
            self._make_entry("2026-07-13T10:00:00+08:00", "err in /e/f.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.distinct_days == sorted(group.distinct_days)

    def test_total_count(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "err in /x/a.py"),
            self._make_entry("2026-07-12T10:00:00+08:00", "err in /y/b.py"),
            self._make_entry("2026-07-12T11:00:00+08:00", "err in /z/c.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.total_count == 3

    def test_projects_sorted_unique(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "err in /x/a.py", project="/proj/b"),
            self._make_entry("2026-07-12T10:00:00+08:00", "err in /y/b.py", project="/proj/a"),
            self._make_entry("2026-07-12T11:00:00+08:00", "err in /z/c.py", project="/proj/b"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.projects == ["/proj/a", "/proj/b"]

    def test_sample_first_raw_msg(self) -> None:
        entries = [
            self._make_entry("2026-07-14T11:00:00+08:00", "raw error in /late/path.py"),
            self._make_entry("2026-07-12T09:00:00+08:00", "raw error in /early/path.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.sample_first["ts"] == "2026-07-12T09:00:00+08:00"
        assert group.sample_first["msg"] == "raw error in /early/path.py"

    def test_sample_last_raw_msg(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "raw error in /early/path.py"),
            self._make_entry("2026-07-14T11:00:00+08:00", "raw error in /late/path.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.sample_last["ts"] == "2026-07-14T11:00:00+08:00"
        assert group.sample_last["msg"] == "raw error in /late/path.py"

    def test_type_script_constant(self) -> None:
        entries = [
            self._make_entry(
                "2026-07-12T09:00:00+08:00", "err in /x/a.py", error_type="hook_timeout", script="session_end"
            ),
            self._make_entry(
                "2026-07-12T10:00:00+08:00", "err in /y/b.py", error_type="hook_timeout", script="session_end"
            ),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.type == "hook_timeout"
        assert group.script == "session_end"

    def test_normalized_msg_stored(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "error in /Users/x/file.py at line 42"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.normalized_msg == normalize_error_msg("error in /Users/x/file.py at line 42")

    def test_sample_tie_breaking(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "error in /x/a.py"),
            self._make_entry("2026-07-12T09:00:00+08:00", "error in /y/b.py"),
            self._make_entry("2026-07-12T09:00:00+08:00", "error in /z/c.py"),
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.sample_first["msg"] == "error in /x/a.py"
        assert group.sample_last["msg"] == "error in /z/c.py"

    def test_multiple_groups(self) -> None:
        entries = [
            self._make_entry("2026-07-12T09:00:00+08:00", "curl error in /x/a.py"),
            self._make_entry("2026-07-12T10:00:00+08:00", "openai API timeout 42 seconds"),
            self._make_entry("2026-07-12T11:00:00+08:00", "curl error in /y/b.py"),
        ]
        groups = group_by_fingerprint(entries)
        assert len(groups) == 2

    def test_status_always_detected(self) -> None:
        entries = [self._make_entry("2026-07-12T09:00:00+08:00", "err in /a.py")]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.status == "detected"

    def test_samples_preserve_raw_msg(self) -> None:
        raw_msg = "error in /Users/busiji/memory/log/test.py at 2026-07-12T11:07:05+08:00"
        entries = [self._make_entry("2026-07-12T09:00:00+08:00", raw_msg)]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.sample_first["msg"] == raw_msg
        assert "<PATH>" in group.normalized_msg


class TestEvaluateThreshold:
    @staticmethod
    def _make_group(distinct_days: list[str], total_count: int) -> PatternGroup:
        return PatternGroup(
            fingerprint="abc123",
            type="test",
            script="test",
            normalized_msg="test",
            status="detected",
            first_seen="2026-07-12T09:00:00+08:00",
            last_seen="2026-07-12T09:00:00+08:00",
            distinct_days=distinct_days,
            total_count=total_count,
            projects=["/test"],
            sample_first={"ts": "2026-07-12T09:00:00+08:00", "msg": "raw"},
            sample_last={"ts": "2026-07-12T09:00:00+08:00", "msg": "raw"},
        )

    def test_threshold_both(self) -> None:
        group = self._make_group(["2026-07-12", "2026-07-13"], 5)
        assert evaluate_threshold(group) == "both"

    def test_threshold_days_only(self) -> None:
        group = self._make_group(["2026-07-12", "2026-07-13"], 2)
        assert evaluate_threshold(group) == "days"

    def test_threshold_count_only(self) -> None:
        group = self._make_group(["2026-07-12"], 5)
        assert evaluate_threshold(group) == "count"

    def test_threshold_null(self) -> None:
        group = self._make_group(["2026-07-12"], 1)
        assert evaluate_threshold(group) is None


class TestDateExtraction:
    def test_same_date_different_offsets(self) -> None:
        entries: list[dict[str, Any]] = [
            {
                "ts": "2026-07-12T23:00:00+08:00",
                "type": "test",
                "script": "test",
                "project": "/test",
                "msg": "err in /a.py",
            },
            {
                "ts": "2026-07-12T15:00:00+00:00",
                "type": "test",
                "script": "test",
                "project": "/test",
                "msg": "err in /b.py",
            },
        ]
        groups = group_by_fingerprint(entries)
        group = list(groups.values())[0]
        assert group.distinct_days == ["2026-07-12"]


class TestRealDataIntegration:
    @pytest.mark.skipif(not REAL_ERRORS, reason="No real error data found")
    def test_real_data_curl_pattern(self) -> None:
        curl_entries = [e for e in REAL_ERRORS if e.get("msg", "").startswith("LLM API curl error: curl: option")]
        if not curl_entries:
            pytest.skip("No curl blank-arg entries")
        groups = group_by_fingerprint(curl_entries)
        assert len(groups) == 1
        group = list(groups.values())[0]
        assert group.total_count == len(curl_entries)

    @pytest.mark.skipif(not REAL_ERRORS, reason="No real error data found")
    def test_real_data_valid_fingerprints(self) -> None:
        groups = group_by_fingerprint(REAL_ERRORS)
        for fp, group in groups.items():
            assert re.fullmatch(r"[0-9a-f]{16}", fp)
            assert group.fingerprint == fp


# ============================================================================
# VAL-REGISTRY: Registry I/O Tests
# ============================================================================


class TestRegistryIO:
    """VAL-REGISTRY: Registry JSONL format and operations."""

    def test_write_registry_creates_jsonl(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-001: Registry file is valid JSONL."""
        registry_path = tmp_path / "registry.jsonl"
        entries = [
            {
                "fingerprint": "abc123def456",
                "type": "test_error",
                "script": "test_script",
                "normalized_msg": "test message",
                "status": "detected",
                "first_seen": "2026-07-12T11:07:05+08:00",
                "last_seen": "2026-07-12T11:07:05+08:00",
                "first_detected": "2026-08-01T00:00:00+08:00",
                "last_updated": "2026-08-01T00:00:00+08:00",
                "distinct_days": ["2026-07-12"],
                "total_count": 1,
                "projects": ["/test"],
                "threshold_met": None,
                "sample_first": {"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
                "sample_last": {"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            }
        ]
        write_registry(registry_path, entries)
        assert registry_path.exists()

        # Verify valid JSONL
        with registry_path.open() as f:
            for line in f:
                data = json.loads(line)
                assert isinstance(data, dict)

    def test_write_registry_all_required_fields(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-002: All required fields present on every line."""
        registry_path = tmp_path / "registry.jsonl"
        entries = [
            {
                "fingerprint": "abc123def456",
                "type": "test_error",
                "script": "test_script",
                "normalized_msg": "test message",
                "status": "detected",
                "first_seen": "2026-07-12T11:07:05+08:00",
                "last_seen": "2026-07-12T11:07:05+08:00",
                "first_detected": "2026-08-01T00:00:00+08:00",
                "last_updated": "2026-08-01T00:00:00+08:00",
                "distinct_days": ["2026-07-12"],
                "total_count": 1,
                "projects": ["/test"],
                "threshold_met": None,
                "sample_first": {"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
                "sample_last": {"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            }
        ]
        write_registry(registry_path, entries)

        required_fields = {
            "fingerprint",
            "type",
            "script",
            "normalized_msg",
            "status",
            "first_seen",
            "last_seen",
            "first_detected",
            "last_updated",
            "distinct_days",
            "total_count",
            "projects",
            "threshold_met",
            "sample_first",
            "sample_last",
        }

        with registry_path.open() as f:
            for line in f:
                data = json.loads(line)
                assert required_fields.issubset(data.keys())

    def test_merge_patterns_preserves_first_detected(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-003: Merge preserves existing first_detected."""
        # Create existing registry with old first_detected
        existing = {
            "abc123": {
                "fingerprint": "abc123",
                "first_detected": "2026-01-01T00:00:00+08:00",
                "last_updated": "2026-07-01T00:00:00+08:00",
            }
        }

        # Create new detected pattern
        group = PatternGroup(
            fingerprint="abc123",
            type="test_error",
            script="test_script",
            normalized_msg="test message",
            status="detected",
            first_seen="2026-07-12T11:07:05+08:00",
            last_seen="2026-07-12T11:07:05+08:00",
            distinct_days=["2026-07-12"],
            total_count=5,
            projects=["/test"],
            sample_first={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            sample_last={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        )

        detected = {"abc123": group}
        merged = merge_patterns(detected, existing)

        # first_detected should be preserved from existing
        assert merged[0]["first_detected"] == "2026-01-01T00:00:00+08:00"
        # last_updated should be current time (not the old value)
        assert merged[0]["last_updated"] != "2026-07-01T00:00:00+08:00"

    def test_merge_patterns_updates_last_updated(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-004: Merge updates last_updated to current run time."""
        existing = {
            "abc123": {
                "fingerprint": "abc123",
                "first_detected": "2026-01-01T00:00:00+08:00",
                "last_updated": "2026-07-01T00:00:00+08:00",
            }
        }

        group = PatternGroup(
            fingerprint="abc123",
            type="test_error",
            script="test_script",
            normalized_msg="test message",
            status="detected",
            first_seen="2026-07-12T11:07:05+08:00",
            last_seen="2026-07-12T11:07:05+08:00",
            distinct_days=["2026-07-12"],
            total_count=5,
            projects=["/test"],
            sample_first={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            sample_last={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        )

        detected = {"abc123": group}
        merged = merge_patterns(detected, existing)

        # last_updated should be updated to current time
        from datetime import datetime

        last_updated = datetime.fromisoformat(merged[0]["last_updated"])
        now = datetime.now().astimezone()
        diff = abs((now - last_updated).total_seconds())
        assert diff < 5  # Within 5 seconds

    def test_merge_patterns_recomputes_aggregates(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-005: Aggregated fields are recomputed from source on every run."""
        existing = {
            "abc123": {
                "fingerprint": "abc123",
                "total_count": 10,
                "distinct_days": ["2026-07-10", "2026-07-11"],
                "projects": ["/old"],
            }
        }

        # New data has different aggregates
        group = PatternGroup(
            fingerprint="abc123",
            type="test_error",
            script="test_script",
            normalized_msg="test message",
            status="detected",
            first_seen="2026-07-12T11:07:05+08:00",
            last_seen="2026-07-12T11:07:05+08:00",
            distinct_days=["2026-07-12"],
            total_count=5,
            projects=["/new"],
            sample_first={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            sample_last={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        )

        detected = {"abc123": group}
        merged = merge_patterns(detected, existing)

        # Aggregates should be recomputed from new data
        assert merged[0]["total_count"] == 5
        assert merged[0]["distinct_days"] == ["2026-07-12"]
        assert merged[0]["projects"] == ["/new"]

    def test_merge_patterns_preserves_resolved_status(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-006: Merge preserves resolved status from existing entry (INFRA-184).

        When an existing registry entry is marked status="resolved", merge_patterns
        must preserve that status (and resolved_at) instead of overwriting it back
        to "detected", so manual resolutions stay durable across runs.
        """
        existing = {
            "abc123": {
                "fingerprint": "abc123",
                "status": "resolved",
                "resolved_at": "2026-07-15T10:00:00+08:00",
                "first_detected": "2026-01-01T00:00:00+08:00",
            }
        }

        # New detection of the same pattern (status defaults to "detected")
        group = PatternGroup(
            fingerprint="abc123",
            type="test_error",
            script="test_script",
            normalized_msg="test message",
            status="detected",
            first_seen="2026-07-12T11:07:05+08:00",
            last_seen="2026-07-12T11:07:05+08:00",
            distinct_days=["2026-07-12"],
            total_count=5,
            projects=["/test"],
            sample_first={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            sample_last={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        )

        detected = {"abc123": group}
        merged = merge_patterns(detected, existing)

        # resolved status and resolved_at must be preserved, not overwritten
        assert merged[0]["status"] == "resolved"
        assert merged[0]["resolved_at"] == "2026-07-15T10:00:00+08:00"

    def test_merge_patterns_detected_status_when_no_existing(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-007: New patterns default to status=detected (INFRA-184)."""
        group = PatternGroup(
            fingerprint="new_fp",
            type="test_error",
            script="test_script",
            normalized_msg="test message",
            status="detected",
            first_seen="2026-07-12T11:07:05+08:00",
            last_seen="2026-07-12T11:07:05+08:00",
            distinct_days=["2026-07-12"],
            total_count=5,
            projects=["/test"],
            sample_first={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            sample_last={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        )

        detected = {"new_fp": group}
        merged = merge_patterns(detected, existing={})

        # No existing entry → default detected status, no resolved_at
        assert merged[0]["status"] == "detected"
        assert "resolved_at" not in merged[0]

    def test_read_registry_skips_malformed_lines(self, tmp_path: Path, capsys: Any) -> None:
        """VAL-RESILIENCE-002: Malformed JSONL lines are skipped."""
        registry_path = tmp_path / "registry.jsonl"

        # Write registry with one good line and one malformed line
        with registry_path.open("w") as f:
            f.write('{"fingerprint": "abc123", "type": "test"}\n')
            f.write('{"not valid json\n')  # Malformed
            f.write('{"fingerprint": "def456", "type": "test"}\n')

        result = read_registry(registry_path)

        # Should read 2 valid entries
        assert len(result) == 2
        assert "abc123" in result
        assert "def456" in result

        # Should log warning to stderr
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()

    def test_write_registry_empty_list(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-014: Empty detection result yields empty registry."""
        registry_path = tmp_path / "registry.jsonl"
        write_registry(registry_path, [])

        assert registry_path.exists()
        with registry_path.open() as f:
            content = f.read()
        assert content == ""

    def test_write_registry_overwrites_existing(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-009: Registry write is a full rewrite, not append."""
        registry_path = tmp_path / "registry.jsonl"

        # Write initial registry
        initial = [{"fingerprint": "old123", "data": "old"}]
        write_registry(registry_path, initial)

        # Write new registry (should overwrite, not append)
        new = [{"fingerprint": "new456", "data": "new"}]
        write_registry(registry_path, new)

        # Read back and verify only new data exists
        result = read_registry(registry_path)
        assert len(result) == 1
        assert "new456" in result
        assert "old123" not in result

    def test_registry_line_count_matches_fingerprints(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-015: Registry line count equals number of distinct fingerprints."""
        registry_path = tmp_path / "registry.jsonl"
        entries = [
            {"fingerprint": "abc123", "type": "test"},
            {"fingerprint": "def456", "type": "test"},
            {"fingerprint": "ghi789", "type": "test"},
        ]
        write_registry(registry_path, entries)

        with registry_path.open() as f:
            lines = [line for line in f if line.strip()]

        assert len(lines) == 3

    def test_registry_no_duplicate_fingerprints(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-010: Each fingerprint appears at most once."""
        registry_path = tmp_path / "registry.jsonl"
        entries = [
            {"fingerprint": "abc123", "type": "test"},
            {"fingerprint": "def456", "type": "test"},
            {"fingerprint": "abc123", "type": "test"},  # Duplicate
        ]
        write_registry(registry_path, entries)

        result = read_registry(registry_path)
        # read_registry uses dict, so duplicates are naturally handled
        assert len(result) == 2  # Only 2 unique fingerprints


# ============================================================================
# VAL-CLI: CLI Interface Tests
# ============================================================================


class TestCLI:
    """VAL-CLI: CLI argument parsing and behavior."""

    def test_help_flag(self) -> None:
        """VAL-CLI-006: Help message exists."""
        parser = build_parser()
        # Should not raise
        help_text = parser.format_help()
        assert "error_pattern_detector" in help_text or "usage:" in help_text.lower()

    def test_project_flag(self) -> None:
        """VAL-CLI-001: --project PATH scans a single project."""
        parser = build_parser()
        args = parser.parse_args(["--project", "/test/path"])
        assert args.project == "/test/path"
        assert args.all_projects is False

    def test_all_projects_flag(self) -> None:
        """VAL-CLI-002: --all-projects scans every project."""
        parser = build_parser()
        args = parser.parse_args(["--all-projects"])
        assert args.all_projects is True
        assert args.project is None

    def test_dry_run_flag(self) -> None:
        """VAL-CLI-003: --dry-run detects but doesn't write."""
        parser = build_parser()
        args = parser.parse_args(["--project", "/test", "--dry-run"])
        assert args.dry_run is True

    def test_verbose_flag(self) -> None:
        """VAL-CLI-004: --verbose prints detailed output."""
        parser = build_parser()
        args = parser.parse_args(["--project", "/test", "--verbose"])
        assert args.verbose is True

    def test_mutually_exclusive_flags(self) -> None:
        """VAL-CLI-009: --project and --all-projects are mutually exclusive."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--project", "/test", "--all-projects"])

    def test_default_mode_no_flags(self) -> None:
        """VAL-CLI-005: Default mode auto-detects from cwd."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.project is None
        assert args.all_projects is False
        # Should use auto-detect from cwd


# ============================================================================
# VAL-RESILIENCE: Error Handling Tests
# ============================================================================


class TestResilience:
    """VAL-RESILIENCE: Error handling and resilience."""

    def test_missing_error_log_files(self, tmp_path: Path) -> None:
        """VAL-RESILIENCE-001: Missing error log files are skipped silently."""
        # Empty project with no error logs
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "memory").mkdir()
        (project_root / "memory" / "log").mkdir()

        entries = scan_project(project_root)
        assert entries == []  # No entries, no crash

    def test_malformed_jsonl_continues_processing(self, tmp_path: Path) -> None:
        """VAL-RESILIENCE-002: Malformed lines are skipped, processing continues."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "good 1"}\n'
            )
            f.write('{"not valid json\n')  # Malformed
            f.write(
                '{"ts": "2026-08-01T11:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "good 2"}\n'
            )

        entries = parse_error_file(error_file)
        assert len(entries) == 2  # Skipped malformed, kept 2 good entries

    def test_empty_input_produces_empty_registry(self, tmp_path: Path) -> None:
        """VAL-RESILIENCE-005: Empty input produces empty registry."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "memory" / "log").mkdir(parents=True)

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False)

        assert registry_path.exists()
        with registry_path.open() as f:
            assert f.read() == ""

    def test_blank_lines_tolerated(self, tmp_path: Path) -> None:
        """VAL-RESILIENCE-011: Trailing newline/blank lines tolerated."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "test"}\n'
            )
            f.write("\n")  # Blank line
            f.write(
                '{"ts": "2026-08-01T11:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "test2"}\n'
            )
            f.write("\n")  # Trailing newline

        entries = parse_error_file(error_file)
        assert len(entries) == 2  # Blank lines ignored

    def test_missing_patterns_directory_created(self, tmp_path: Path) -> None:
        """VAL-RESILIENCE-003: Missing patterns directory is auto-created."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "memory" / "log").mkdir(parents=True)

        # Patterns directory doesn't exist yet
        patterns_dir = project_root / "memory" / "kb" / "patterns"
        assert not patterns_dir.exists()

        registry_path = patterns_dir / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False)

        # Directory should be created
        assert patterns_dir.exists()
        assert registry_path.exists()


# ============================================================================
# VAL-CROSS: End-to-End Flow Tests
# ============================================================================


class TestEndToEnd:
    """VAL-CROSS: Full pipeline integration tests."""

    def test_full_pipeline_raw_to_registry(self, tmp_path: Path) -> None:
        """VAL-CROSS-001: Full pipeline from raw errors to written registry."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        # Create error log with multiple entries
        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "test_error", "script": "test_script", "project": "/test", "msg": "error in /path/file.py line 42"}\n'
            )
            f.write(
                '{"ts": "2026-08-01T11:00:00+08:00", "type": "test_error", "script": "test_script", "project": "/test", "msg": "error in /path/file.py line 42"}\n'
            )
            f.write(
                '{"ts": "2026-08-02T10:00:00+08:00", "type": "test_error", "script": "test_script", "project": "/test", "msg": "error in /path/file.py line 42"}\n'
            )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False)

        # Verify registry was written
        assert registry_path.exists()

        entries = list(read_registry(registry_path).values())
        assert len(entries) == 1  # All 3 entries have same fingerprint

        entry = entries[0]
        assert entry["total_count"] == 3
        assert entry["distinct_days"] == ["2026-08-01", "2026-08-02"]
        assert entry["threshold_met"] == "days"  # 2 days, count < 5

    def test_dry_run_no_file_written(self, tmp_path: Path) -> None:
        """VAL-CROSS-002: Dry-run pipeline detects but doesn't write."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "error"}\n'
            )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=True)

        # Registry should NOT be written
        assert not registry_path.exists()

    def test_rerun_idempotency(self, tmp_path: Path) -> None:
        """VAL-REGISTRY-006: Idempotency - two runs produce identical registry except last_updated."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "error"}\n'
            )

        registry_path = tmp_path / "registry.jsonl"

        # First run
        run_pipeline(project_root, registry_path, dry_run=False)
        first_run = read_registry(registry_path)

        # Second run
        run_pipeline(project_root, registry_path, dry_run=False)
        second_run = read_registry(registry_path)

        # Compare (excluding last_updated which changes)
        for fp in first_run:
            assert fp in second_run
            first_entry = first_run[fp]
            second_entry = second_run[fp]

            # first_detected should be preserved
            assert first_entry["first_detected"] == second_entry["first_detected"]

            # Other fields should be identical
            assert first_entry["fingerprint"] == second_entry["fingerprint"]
            assert first_entry["total_count"] == second_entry["total_count"]
            assert first_entry["distinct_days"] == second_entry["distinct_days"]
            assert first_entry["threshold_met"] == second_entry["threshold_met"]

            # last_updated should be different (or very close)
            # (we just check it exists, actual time comparison is complex)
            assert "last_updated" in second_entry

    def test_multi_project_aggregation(self, tmp_path: Path) -> None:
        """VAL-CROSS-003: Multi-project flow aggregates correctly."""
        # Create two projects with overlapping errors
        project1 = tmp_path / "project1"
        project1.mkdir()
        log_dir1 = project1 / "memory" / "log"
        log_dir1.mkdir(parents=True)

        with (log_dir1 / "2026-08-01-errors.jsonl").open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "shared_error", "script": "test", "project": "/project1", "msg": "shared error"}\n'
            )
            f.write(
                '{"ts": "2026-08-01T11:00:00+08:00", "type": "unique_error_1", "script": "test", "project": "/project1", "msg": "unique to project1"}\n'
            )

        project2 = tmp_path / "project2"
        project2.mkdir()
        log_dir2 = project2 / "memory" / "log"
        log_dir2.mkdir(parents=True)

        with (log_dir2 / "2026-08-01-errors.jsonl").open("w") as f:
            f.write(
                '{"ts": "2026-08-01T12:00:00+08:00", "type": "shared_error", "script": "test", "project": "/project2", "msg": "shared error"}\n'
            )
            f.write(
                '{"ts": "2026-08-01T13:00:00+08:00", "type": "unique_error_2", "script": "test", "project": "/project2", "msg": "unique to project2"}\n'
            )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline([project1, project2], registry_path, dry_run=False)

        entries = list(read_registry(registry_path).values())
        assert len(entries) == 3  # shared + unique1 + unique2

        # Find shared error
        shared = [e for e in entries if e["type"] == "shared_error"][0]
        assert shared["total_count"] == 2
        assert sorted(shared["projects"]) == ["/project1", "/project2"]

        # Find unique errors
        unique1 = [e for e in entries if e["type"] == "unique_error_1"][0]
        assert unique1["total_count"] == 1
        assert unique1["projects"] == ["/project1"]

        unique2 = [e for e in entries if e["type"] == "unique_error_2"][0]
        assert unique2["total_count"] == 1
        assert unique2["projects"] == ["/project2"]

    def test_verbose_output(self, tmp_path: Path, capsys: Any) -> None:
        """VAL-CROSS-005: Verbose mode prints per-pattern detail."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "error"}\n'
            )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False, verbose=True)

        captured = capsys.readouterr()
        # Verbose output should contain pattern information
        assert "fingerprint:" in captured.out
        assert "count:" in captured.out
        assert "days:" in captured.out

    def test_mixed_threshold_outcomes(self, tmp_path: Path) -> None:
        """VAL-CROSS-006: Single run produces mix of all four threshold outcomes."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        # Create errors with different threshold outcomes
        with (log_dir / "2026-08-01-errors.jsonl").open("w") as f:
            # "both": 2+ days, 5+ count
            for i in range(5):
                f.write(
                    f'{{"ts": "2026-08-01T{10 + i}:00:00+08:00", "type": "both_test", "script": "test", "project": "/test", "msg": "both error"}}\n'
                )
            for i in range(5):
                f.write(
                    f'{{"ts": "2026-08-02T{10 + i}:00:00+08:00", "type": "both_test", "script": "test", "project": "/test", "msg": "both error"}}\n'
                )

            # "days": 2+ days, <5 count
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "days_test", "script": "test", "project": "/test", "msg": "days error"}\n'
            )
            f.write(
                '{"ts": "2026-08-02T10:00:00+08:00", "type": "days_test", "script": "test", "project": "/test", "msg": "days error"}\n'
            )

            # "count": <2 days, 5+ count
            for i in range(5):
                f.write(
                    f'{{"ts": "2026-08-01T{10 + i}:00:00+08:00", "type": "count_test", "script": "test", "project": "/test", "msg": "count error"}}\n'
                )

            # null: <2 days, <5 count
            f.write(
                '{"ts": "2026-08-01T10:00:00+08:00", "type": "null_test", "script": "test", "project": "/test", "msg": "null error"}\n'
            )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False)

        entries = list(read_registry(registry_path).values())
        thresholds = [e["threshold_met"] for e in entries]

        assert "both" in thresholds
        assert "days" in thresholds
        assert "count" in thresholds
        assert None in thresholds

    def test_performance_budget(self, tmp_path: Path) -> None:
        """VAL-CROSS-007: Performance budgets hold."""
        import time

        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        # Generate 100 entries
        with (log_dir / "2026-08-01-errors.jsonl").open("w") as f:
            for i in range(100):
                f.write(
                    f'{{"ts": "2026-08-01T{10 + i % 12:02d}:00:00+08:00", "type": "perf_test", "script": "test", "project": "/test", "msg": "performance error {i}"}}\n'
                )

        registry_path = tmp_path / "registry.jsonl"

        start = time.time()
        run_pipeline(project_root, registry_path, dry_run=False)
        elapsed = time.time() - start

        # 100 entries should complete in <1 second
        assert elapsed < 1.0, f"100 entries took {elapsed:.2f}s, expected <1s"


# ============================================================================
# Real Data Integration Tests
# ============================================================================


class TestRealDataEndToEnd:
    """Integration tests with real error data from the repository."""

    @pytest.mark.skipif(not REAL_ERRORS, reason="No real error data found")
    def test_real_data_full_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline on real error data."""
        # Use the actual memory project
        memory_root = Path("/Users/busiji/memory")
        if not memory_root.exists():
            pytest.skip("Memory project not found")

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(memory_root, registry_path, dry_run=False)

        assert registry_path.exists()
        entries = list(read_registry(registry_path).values())

        # Should have detected some patterns
        assert len(entries) > 0

        # All entries should have required fields
        required_fields = {
            "fingerprint",
            "type",
            "script",
            "normalized_msg",
            "status",
            "first_seen",
            "last_seen",
            "first_detected",
            "last_updated",
            "distinct_days",
            "total_count",
            "projects",
            "threshold_met",
            "sample_first",
            "sample_last",
        }

        for entry in entries:
            assert required_fields.issubset(entry.keys())
            assert re.fullmatch(r"[0-9a-f]{16}", entry["fingerprint"])

    @pytest.mark.skipif(not REAL_ERRORS, reason="No real error data found")
    def test_real_data_curl_pattern_exists(self, tmp_path: Path) -> None:
        """Real data should contain the curl blank-arg pattern."""
        memory_root = Path("/Users/busiji/memory")
        if not memory_root.exists():
            pytest.skip("Memory project not found")

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(memory_root, registry_path, dry_run=False)

        entries = list(read_registry(registry_path).values())

        # Look for curl-related patterns
        curl_patterns = [e for e in entries if "curl" in e["normalized_msg"].lower()]

        # Should have at least one curl-related pattern
        assert len(curl_patterns) > 0, "No curl-related patterns found in real data"


# ============================================================================
# VAL-TEST-ARTIFACT: Test Artifact Filtering Tests
# ============================================================================


class TestTestArtifactFiltering:
    """Tests for _is_test_artifact() — prevents false-positive findings."""

    @staticmethod
    def _make_entry(
        session_id: str = "",
        expected_path: str = "",
        msg: str = "",
        ctx: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "ts": "2026-07-24T09:37:47+08:00",
            "type": "transcript_missing",
            "script": "session_end_logger",
            "project": "/Users/busiji/memory",
            "msg": msg,
            "ctx": ctx if ctx is not None else {},
        }
        if session_id:
            entry["ctx"]["session_id"] = session_id
        if expected_path:
            entry["ctx"]["expected_path"] = expected_path
        return entry

    def test_test_session_id_filtered(self) -> None:
        """session_id='test' is recognized as a test artifact."""
        entry = self._make_entry(
            session_id="test",
            expected_path="/Users/x/.factory/sessions/test.jsonl",
            msg="transcript not found: /Users/x/.factory/sessions/test.jsonl",
        )
        assert _is_test_artifact(entry) is True

    def test_test_dash_prefix_session_id_filtered(self) -> None:
        """session_id='test-verification-123' is a test artifact."""
        entry = self._make_entry(
            session_id="test-verification-123",
            expected_path="/private/tmp/nonexist.jsonl",
            msg="transcript not found: /private/tmp/nonexist.jsonl",
        )
        assert _is_test_artifact(entry) is True

    def test_test_no_transcript_session_id_filtered(self) -> None:
        """session_id='test-no-transcript' is a test artifact."""
        entry = self._make_entry(
            session_id="test-no-transcript",
            expected_path="/Users/x/test-no-transcript.jsonl",
            msg="transcript not found: /Users/x/test-no-transcript.jsonl",
        )
        assert _is_test_artifact(entry) is True

    def test_debug_prefix_filtered(self) -> None:
        """session_id='debug-123' is a test artifact."""
        entry = self._make_entry(session_id="debug-123")
        assert _is_test_artifact(entry) is True

    def test_dummy_prefix_filtered(self) -> None:
        """session_id='dummy' is a test artifact."""
        entry = self._make_entry(session_id="dummy")
        assert _is_test_artifact(entry) is True

    def test_tmp_path_filtered(self) -> None:
        """Paths under /tmp/ are recognized as test artifacts."""
        entry = self._make_entry(
            session_id="a1b2c3d4",
            expected_path="/tmp/x.jsonl",
            msg="transcript not found: /tmp/x.jsonl",
        )
        assert _is_test_artifact(entry) is True

    def test_private_tmp_path_filtered(self) -> None:
        """Paths under /private/tmp/ (macOS canonical /tmp) are test artifacts."""
        entry = self._make_entry(
            session_id="a1b2c3d4",
            expected_path="/private/tmp/nonexist.jsonl",
            msg="transcript not found: /private/tmp/nonexist.jsonl",
        )
        assert _is_test_artifact(entry) is True

    def test_var_tmp_path_filtered(self) -> None:
        """Paths under /var/tmp/ are test artifacts."""
        entry = self._make_entry(
            session_id="real-session",
            expected_path="/var/tmp/transcript.jsonl",
            msg="transcript not found: /var/tmp/transcript.jsonl",
        )
        assert _is_test_artifact(entry) is True

    def test_real_session_not_filtered(self) -> None:
        """A real-looking entry with UUID session_id and ~/.factory path passes."""
        entry = self._make_entry(
            session_id="a1b2c3d4",
            expected_path="/Users/busiji/.factory/sessions/-Users-busiji-memory/a1b2c3d4.jsonl",
            msg="transcript not found: /Users/busiji/.factory/sessions/-Users-busiji-memory/a1b2c3d4.jsonl",
        )
        assert _is_test_artifact(entry) is False

    def test_contest_not_filtered(self) -> None:
        """session_id='contest' does NOT start with 'test' — not filtered."""
        entry = self._make_entry(session_id="contest")
        assert _is_test_artifact(entry) is False

    def test_no_ctx_not_filtered(self) -> None:
        """Entries without ctx are not filtered."""
        entry: dict[str, Any] = {"ts": "2026-01-01T00:00:00+08:00", "type": "t", "msg": "error"}
        assert _is_test_artifact(entry) is False

    def test_empty_session_id_not_filtered(self) -> None:
        """Empty session_id does not trigger filtering."""
        entry = self._make_entry(
            session_id="",
            expected_path="/Users/x/app/file.jsonl",
            msg="error in /Users/x/app/file.jsonl",
        )
        assert _is_test_artifact(entry) is False

    def test_case_insensitive_session_id(self) -> None:
        """session_id='TEST-123' (uppercase) is still filtered."""
        entry = self._make_entry(session_id="TEST-123")
        assert _is_test_artifact(entry) is True


class TestPipelineArtifactFiltering:
    """End-to-end tests verifying the pipeline filters test artifacts."""

    def test_pipeline_excludes_test_artifacts(self, tmp_path: Path) -> None:
        """Pipeline filters entries with test session_ids before grouping."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            # 5 test entries (same fingerprint, would trigger 'both' threshold)
            for i in range(5):
                f.write(
                    json.dumps(
                        {
                            "ts": f"2026-08-0{1 + i % 2}T10:00:00+08:00",
                            "type": "transcript_missing",
                            "script": "session_end_logger",
                            "project": str(project_root),
                            "ctx": {"session_id": "test", "expected_path": f"/tmp/file{i}.jsonl"},
                            "msg": f"transcript not found: /tmp/file{i}.jsonl",
                        }
                    )
                    + "\n"
                )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False)

        # Registry should be empty (all entries were test artifacts)
        assert registry_path.exists()
        with registry_path.open() as f:
            content = f.read()
        assert content == "", "Test artifacts should be filtered out, registry must be empty"

    def test_pipeline_mixed_entries(self, tmp_path: Path) -> None:
        """Pipeline keeps real entries while filtering test entries."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            # Test artifact (should be filtered)
            f.write(
                json.dumps(
                    {
                        "ts": "2026-08-01T10:00:00+08:00",
                        "type": "transcript_missing",
                        "script": "session_end_logger",
                        "project": str(project_root),
                        "ctx": {"session_id": "test", "expected_path": "/tmp/x.jsonl"},
                        "msg": "transcript not found: /tmp/x.jsonl",
                    }
                )
                + "\n"
            )
            # Real entry (should be kept)
            f.write(
                json.dumps(
                    {
                        "ts": "2026-08-01T11:00:00+08:00",
                        "type": "llm_api_error",
                        "script": "daily_summary_generator",
                        "project": str(project_root),
                        "ctx": {"session_id": "a1b2c3d4"},
                        "msg": "LLM API error in /Users/x/app.py",
                    }
                )
                + "\n"
            )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False)

        entries = list(read_registry(registry_path).values())
        # Only the real entry should appear
        assert len(entries) == 1
        assert entries[0]["type"] == "llm_api_error"

    def test_pipeline_verbose_reports_excluded(self, tmp_path: Path, capsys: Any) -> None:
        """Verbose mode reports how many test artifacts were excluded."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        log_dir = project_root / "memory" / "log"
        log_dir.mkdir(parents=True)

        error_file = log_dir / "2026-08-01-errors.jsonl"
        with error_file.open("w") as f:
            for i in range(3):
                f.write(
                    json.dumps(
                        {
                            "ts": "2026-08-01T10:00:00+08:00",
                            "type": "transcript_missing",
                            "script": "session_end_logger",
                            "project": str(project_root),
                            "ctx": {"session_id": "test", "expected_path": f"/tmp/f{i}.jsonl"},
                            "msg": f"transcript not found: /tmp/f{i}.jsonl",
                        }
                    )
                    + "\n"
                )

        registry_path = tmp_path / "registry.jsonl"
        run_pipeline(project_root, registry_path, dry_run=False, verbose=True)

        captured = capsys.readouterr()
        assert "excluded" in captured.err.lower() or "excluded" in captured.out.lower()


# ============================================================================
# INFRA-186: Resolved Pattern Persistence & Resolve Command Tests
# ============================================================================


class TestMergePatternsResolvedPersistence:
    """INFRA-186: merge_patterns() preserves resolved entries no longer detected."""

    @staticmethod
    def _make_group(fp: str, error_type: str = "test_error") -> PatternGroup:
        return PatternGroup(
            fingerprint=fp,
            type=error_type,
            script="test_script",
            normalized_msg="test message",
            status="detected",
            first_seen="2026-07-12T11:07:05+08:00",
            last_seen="2026-07-12T11:07:05+08:00",
            distinct_days=["2026-07-12"],
            total_count=5,
            projects=["/test"],
            sample_first={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            sample_last={"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        )

    def test_resolved_entry_not_detected_is_preserved(self) -> None:
        """INFRA-186: A resolved entry absent from current detection stays in registry."""
        existing = {
            "resolved_fp_001": {
                "fingerprint": "resolved_fp_001",
                "type": "test_error",
                "script": "test_script",
                "normalized_msg": "old resolved error",
                "status": "resolved",
                "resolved_at": "2026-07-15T10:00:00+08:00",
                "first_detected": "2026-01-01T00:00:00+08:00",
                "last_updated": "2026-07-15T10:00:00+08:00",
            },
        }

        # Current detection has a different pattern, resolved one is absent
        detected = {"detected_fp_002": self._make_group("detected_fp_002")}
        merged = merge_patterns(detected, existing)

        # Both the detected and the resolved-absent entries should be present
        merged_fps = {e["fingerprint"] for e in merged}
        assert "resolved_fp_001" in merged_fps
        assert "detected_fp_002" in merged_fps

        # The resolved entry keeps its status and resolved_at
        resolved_entry = next(e for e in merged if e["fingerprint"] == "resolved_fp_001")
        assert resolved_entry["status"] == "resolved"
        assert resolved_entry["resolved_at"] == "2026-07-15T10:00:00+08:00"

    def test_detected_entry_not_detected_is_dropped(self) -> None:
        """INFRA-186: A non-resolved entry absent from current detection is dropped."""
        existing = {
            "detected_fp_001": {
                "fingerprint": "detected_fp_001",
                "type": "test_error",
                "script": "test_script",
                "normalized_msg": "old detected error",
                "status": "detected",
                "first_detected": "2026-01-01T00:00:00+08:00",
                "last_updated": "2026-07-15T10:00:00+08:00",
            },
        }

        # Current detection is empty — old detected entry should be dropped
        detected: dict[str, PatternGroup] = {}
        merged = merge_patterns(detected, existing)

        merged_fps = {e["fingerprint"] for e in merged}
        assert "detected_fp_001" not in merged_fps

    def test_resolved_and_detected_both_preserved(self) -> None:
        """INFRA-186: Resolved entry stays while detected entry gets merged."""
        existing = {
            "resolved_fp": {
                "fingerprint": "resolved_fp",
                "type": "resolved_type",
                "script": "test_script",
                "normalized_msg": "resolved message",
                "status": "resolved",
                "resolved_at": "2026-07-15T10:00:00+08:00",
                "first_detected": "2026-01-01T00:00:00+08:00",
            },
            "detected_fp": {
                "fingerprint": "detected_fp",
                "type": "test_error",
                "script": "test_script",
                "normalized_msg": "test message",
                "status": "detected",
                "first_detected": "2026-06-01T00:00:00+08:00",
            },
        }

        # Only detected_fp is in current detection
        detected = {"detected_fp": self._make_group("detected_fp")}
        merged = merge_patterns(detected, existing)

        merged_fps = {e["fingerprint"] for e in merged}
        assert merged_fps == {"resolved_fp", "detected_fp"}

    def test_result_sorted_by_fingerprint(self) -> None:
        """INFRA-186: Result is sorted by fingerprint for determinism."""
        existing = {
            "zzz_resolved": {
                "fingerprint": "zzz_resolved",
                "status": "resolved",
                "resolved_at": "2026-07-15T10:00:00+08:00",
                "first_detected": "2026-01-01T00:00:00+08:00",
            },
            "aaa_resolved": {
                "fingerprint": "aaa_resolved",
                "status": "resolved",
                "resolved_at": "2026-07-15T10:00:00+08:00",
                "first_detected": "2026-01-01T00:00:00+08:00",
            },
        }

        # detected pattern sorts between the two resolved entries
        detected = {"mmm_detected": self._make_group("mmm_detected")}
        merged = merge_patterns(detected, existing)

        fps = [e["fingerprint"] for e in merged]
        assert fps == sorted(fps)
        assert fps == ["aaa_resolved", "mmm_detected", "zzz_resolved"]

    def test_resolved_entry_re_detected_keeps_resolved_status(self) -> None:
        """INFRA-186: When a resolved entry is re-detected, status stays resolved (INFRA-184)."""
        existing = {
            "resolved_fp": {
                "fingerprint": "resolved_fp",
                "status": "resolved",
                "resolved_at": "2026-07-15T10:00:00+08:00",
                "first_detected": "2026-01-01T00:00:00+08:00",
            },
        }

        # The resolved pattern is now re-detected
        detected = {"resolved_fp": self._make_group("resolved_fp")}
        merged = merge_patterns(detected, existing)

        assert len(merged) == 1
        assert merged[0]["status"] == "resolved"
        assert merged[0]["resolved_at"] == "2026-07-15T10:00:00+08:00"


class TestResolvePatterns:
    """INFRA-186: --resolve and --resolve-type CLI command tests."""

    @staticmethod
    def _write_registry(
        registry_path: Path,
        entries: list[dict[str, Any]],
    ) -> None:
        """Helper to write a registry.jsonl file."""
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with registry_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    @staticmethod
    def _make_registry_entry(
        fp: str,
        error_type: str = "test_error",
        status: str = "detected",
    ) -> dict[str, Any]:
        return {
            "fingerprint": fp,
            "type": error_type,
            "script": "test_script",
            "normalized_msg": "test message",
            "status": status,
            "first_seen": "2026-07-12T11:07:05+08:00",
            "last_seen": "2026-07-12T11:07:05+08:00",
            "first_detected": "2026-08-01T00:00:00+08:00",
            "last_updated": "2026-08-01T00:00:00+08:00",
            "distinct_days": ["2026-07-12"],
            "total_count": 5,
            "projects": ["/test"],
            "threshold_met": "both",
            "sample_first": {"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
            "sample_last": {"ts": "2026-07-12T11:07:05+08:00", "msg": "test"},
        }

    def test_resolve_by_fingerprint(self, tmp_path: Path, capsys: Any) -> None:
        """INFRA-186: --resolve <fingerprint> marks a single pattern as resolved."""
        registry_path = tmp_path / "registry.jsonl"
        self._write_registry(
            registry_path,
            [
                self._make_registry_entry("fp_001"),
                self._make_registry_entry("fp_002"),
            ],
        )

        count = resolve_patterns(fingerprint="fp_001", registry_path=registry_path)

        assert count == 1
        registry = read_registry(registry_path)
        assert registry["fp_001"]["status"] == "resolved"
        assert "resolved_at" in registry["fp_001"]
        # Unmatched entry should be unchanged
        assert registry["fp_002"]["status"] == "detected"
        assert "resolved_at" not in registry["fp_002"]

        captured = capsys.readouterr()
        assert "Resolved 1 pattern(s)" in captured.out
        assert "fp_001" in captured.out

    def test_resolve_type_marks_all_of_type(self, tmp_path: Path, capsys: Any) -> None:
        """INFRA-186: --resolve-type <type> marks all patterns of that type."""
        registry_path = tmp_path / "registry.jsonl"
        self._write_registry(
            registry_path,
            [
                self._make_registry_entry("fp_001", error_type="transcript_missing"),
                self._make_registry_entry("fp_002", error_type="transcript_missing"),
                self._make_registry_entry("fp_003", error_type="llm_api_error"),
            ],
        )

        count = resolve_patterns(
            pattern_type="transcript_missing",
            registry_path=registry_path,
        )

        assert count == 2
        registry = read_registry(registry_path)
        assert registry["fp_001"]["status"] == "resolved"
        assert registry["fp_002"]["status"] == "resolved"
        # Different type should be unchanged
        assert registry["fp_003"]["status"] == "detected"

        captured = capsys.readouterr()
        assert "Resolved 2 pattern(s)" in captured.out

    def test_resolve_missing_registry(self, tmp_path: Path, capsys: Any) -> None:
        """INFRA-186: Resolve handles missing registry gracefully."""
        registry_path = tmp_path / "nonexistent.jsonl"
        count = resolve_patterns(fingerprint="fp_001", registry_path=registry_path)

        assert count == 0
        captured = capsys.readouterr()
        assert "no registry found" in captured.err

    def test_resolve_empty_registry(self, tmp_path: Path, capsys: Any) -> None:
        """INFRA-186: Resolve handles empty registry gracefully."""
        registry_path = tmp_path / "registry.jsonl"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("")

        count = resolve_patterns(fingerprint="fp_001", registry_path=registry_path)

        assert count == 0
        captured = capsys.readouterr()
        assert "registry is empty" in captured.err

    def test_resolve_no_matching_patterns(self, tmp_path: Path, capsys: Any) -> None:
        """INFRA-186: Resolve prints message when no patterns match."""
        registry_path = tmp_path / "registry.jsonl"
        self._write_registry(
            registry_path,
            [
                self._make_registry_entry("fp_001"),
            ],
        )

        count = resolve_patterns(fingerprint="nonexistent_fp", registry_path=registry_path)

        assert count == 0
        captured = capsys.readouterr()
        assert "No matching patterns found" in captured.out

    def test_resolve_no_matching_type(self, tmp_path: Path, capsys: Any) -> None:
        """INFRA-186: Resolve-type prints message when no patterns match the type."""
        registry_path = tmp_path / "registry.jsonl"
        self._write_registry(
            registry_path,
            [
                self._make_registry_entry("fp_001", error_type="type_a"),
            ],
        )

        count = resolve_patterns(
            pattern_type="nonexistent_type",
            registry_path=registry_path,
        )

        assert count == 0
        captured = capsys.readouterr()
        assert "No matching patterns found" in captured.out

    def test_resolve_already_resolved_stays_resolved(self, tmp_path: Path) -> None:
        """INFRA-186: Re-resolving an already-resolved entry keeps it resolved."""
        registry_path = tmp_path / "registry.jsonl"
        entry = self._make_registry_entry("fp_001", status="resolved")
        entry["resolved_at"] = "2026-07-15T10:00:00+08:00"
        self._write_registry(registry_path, [entry])

        count = resolve_patterns(fingerprint="fp_001", registry_path=registry_path)

        assert count == 1
        registry = read_registry(registry_path)
        assert registry["fp_001"]["status"] == "resolved"
        # resolved_at should be updated to current time
        assert registry["fp_001"]["resolved_at"] != "2026-07-15T10:00:00+08:00"

    def test_resolve_preserves_other_entries(self, tmp_path: Path) -> None:
        """INFRA-186: Resolving one pattern does not alter other entries."""
        registry_path = tmp_path / "registry.jsonl"
        self._write_registry(
            registry_path,
            [
                self._make_registry_entry("fp_001"),
                self._make_registry_entry("fp_002"),
                self._make_registry_entry("fp_003"),
            ],
        )

        resolve_patterns(fingerprint="fp_002", registry_path=registry_path)

        registry = read_registry(registry_path)
        # All three entries should still be present
        assert len(registry) == 3
        # Only fp_002 should be resolved
        assert registry["fp_001"]["status"] == "detected"
        assert registry["fp_002"]["status"] == "resolved"
        assert registry["fp_003"]["status"] == "detected"


class TestResolveCLIArgs:
    """INFRA-186: CLI argument parsing for --resolve and --resolve-type."""

    def test_resolve_flag_parsed(self) -> None:
        """--resolve FINGERPRINT is parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(["--resolve", "abc123def456"])
        assert args.resolve == "abc123def456"
        assert args.resolve_type is None

    def test_resolve_type_flag_parsed(self) -> None:
        """--resolve-type TYPE is parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(["--resolve-type", "transcript_missing"])
        assert args.resolve_type == "transcript_missing"
        assert args.resolve is None

    def test_resolve_and_resolve_type_mutually_exclusive(self) -> None:
        """--resolve and --resolve-type are mutually exclusive."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--resolve", "abc", "--resolve-type", "type_a"])

    def test_resolve_with_project_not_excluded(self) -> None:
        """--resolve can be combined with --project (but resolve takes priority in _main_inner)."""
        parser = build_parser()
        args = parser.parse_args(["--project", "/test", "--resolve", "abc"])
        assert args.resolve == "abc"
        assert args.project == "/test"

    def test_help_includes_resolve(self) -> None:
        """Help text includes --resolve and --resolve-type."""
        parser = build_parser()
        help_text = parser.format_help()
        assert "--resolve" in help_text
        assert "--resolve-type" in help_text


class TestResolveCLIMain:
    """INFRA-186: main() routes to resolve_patterns when --resolve is given."""

    def test_main_resolve_calls_resolve_patterns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() with --resolve invokes resolve_patterns and returns early."""
        # Set cwd to tmp_path so default registry path resolves there
        monkeypatch.chdir(tmp_path)
        # No registry → should print warning and return 0, no crash
        main(["--resolve", "nonexistent_fp"])

    def test_main_resolve_type_calls_resolve_patterns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: Any,
    ) -> None:
        """main() with --resolve-type invokes resolve_patterns and returns early."""
        monkeypatch.chdir(tmp_path)
        main(["--resolve-type", "transcript_missing"])
        captured = capsys.readouterr()
        assert "no registry found" in captured.err
