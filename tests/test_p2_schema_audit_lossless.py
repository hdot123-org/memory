"""P2 B.Q6-3: is_lossless() generic API + schema audit log tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from memory_core.tools.memory_hook_schema import (
    V1_VERSION,
    V2_VERSION,
    convert_to_v1,
    is_lossless,
)

# ---------------------------------------------------------------------------
# Test 1: is_lossless({}, {}) -> (True, [])
# ---------------------------------------------------------------------------

class TestIsLosslessEmptyDicts:
    def test_empty_dicts_are_lossless(self) -> None:
        assert is_lossless({}, {}) == (True, [])


# ---------------------------------------------------------------------------
# Test 2: is_lossless({"a":1}, {"a":1, "b":2}) -> (True, [])
# 新增字段不算丢
# ---------------------------------------------------------------------------

class TestIsLosslessNewKeysIgnored:
    def test_new_keys_in_output_not_loss(self) -> None:
        assert is_lossless({"a": 1}, {"a": 1, "b": 2}) == (True, [])


# ---------------------------------------------------------------------------
# Test 3: is_lossless({"a":1}, {}) -> (False, ["a"])
# ---------------------------------------------------------------------------

class TestIsLosslessDroppedKey:
    def test_dropped_top_level_key(self) -> None:
        lossless, dropped = is_lossless({"a": 1}, {})
        assert lossless is False
        assert dropped == ["a"]


# ---------------------------------------------------------------------------
# Test 4: is_lossless({"a":{"b":1}}, {"a":{}}) -> (False, ["a.b"])
# 嵌套字典键缺失
# ---------------------------------------------------------------------------

class TestIsLosslessNestedDict:
    def test_nested_dict_missing_key(self) -> None:
        lossless, dropped = is_lossless({"a": {"b": 1}}, {"a": {}})
        assert lossless is False
        assert "a.b" in dropped


# ---------------------------------------------------------------------------
# Test 5: expected_keys whitelist: is_lossless({"a":1}, {}, expected_keys={"a"}) -> (True, [])
# ---------------------------------------------------------------------------

class TestIsLosslessExpectedKeys:
    def test_expected_keys_whitelist(self) -> None:
        lossless, dropped = is_lossless({"a": 1}, {}, expected_keys={"a"})
        assert lossless is True
        assert dropped == []


# ---------------------------------------------------------------------------
# Test 6: Actual conversion + audit log interception via MEMORY_SCHEMA_AUDIT_LOG
# ---------------------------------------------------------------------------

class TestAuditLogWrittenOnDrop:
    def test_audit_log_file_written_when_conversion_drops_keys(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Construct a conversion that drops keys, intercept via env var."""
        audit_log = str(tmp_path / "schema-audit.log")
        monkeypatch.setenv("MEMORY_SCHEMA_AUDIT_LOG", audit_log)
        monkeypatch.delenv("MEMORY_HOOK_SCHEMA_AUDIT", raising=False)

        pkg: dict[str, Any] = {
            "schema_version": V2_VERSION,
            "repo_root": "/repo",
            "project_context": {"scope": "test"},
            "task_context": {"id": "t1"},
            "host": "codex",
            "event": "start",
            "status": "ok",
            "system_context": {"info": "diagnostic"},
            "missing_paths": ["/x"],
            "allowed_reads": [],
            "allowed_writes": [],
            "evidence_refs": [],
            "validation_errors": [],
            "generated_at": "2026-01-01T00:00:00+00:00",
        }

        result = convert_to_v1(pkg)

        # Verify conversion worked
        assert result["schema_version"] == V1_VERSION
        assert "system_context" not in result
        assert "missing_paths" not in result

        # Verify audit log was written
        assert Path(audit_log).exists()
        lines = Path(audit_log).read_text().strip().split("\n")
        assert len(lines) >= 1

        record = json.loads(lines[-1])
        assert record["event"] == "schema_convert"
        assert record["from_version"] == V2_VERSION
        assert record["to_version"] == V1_VERSION
        assert "system_context" in record["dropped_keys"]
        assert "missing_paths" in record["dropped_keys"]
        assert isinstance(record["input_size"], int)
        assert isinstance(record["output_size"], int)
