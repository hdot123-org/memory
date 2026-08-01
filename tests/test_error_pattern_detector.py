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
    compute_fingerprint,
    evaluate_threshold,
    group_by_fingerprint,
    normalize_error_msg,
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
        assert "retried N times after N ms" == result


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
        r1 = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parent.parent))
        r2 = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parent.parent))
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
    def _make_entry(ts: str, msg: str, error_type: str = "llm_api_error",
                    script: str = "daily_summary_generator",
                    project: str = "/Users/busiji/memory") -> dict[str, Any]:
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
            self._make_entry("2026-07-12T09:00:00+08:00", "err in /x/a.py", error_type="hook_timeout", script="session_end"),
            self._make_entry("2026-07-12T10:00:00+08:00", "err in /y/b.py", error_type="hook_timeout", script="session_end"),
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
            fingerprint="abc123", type="test", script="test", normalized_msg="test",
            status="detected", first_seen="2026-07-12T09:00:00+08:00",
            last_seen="2026-07-12T09:00:00+08:00", distinct_days=distinct_days,
            total_count=total_count, projects=["/test"],
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
            {"ts": "2026-07-12T23:00:00+08:00", "type": "test", "script": "test", "project": "/test", "msg": "err in /a.py"},
            {"ts": "2026-07-12T15:00:00+00:00", "type": "test", "script": "test", "project": "/test", "msg": "err in /b.py"},
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
