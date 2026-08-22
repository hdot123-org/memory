"""Tests for rebuild_path_index and memory-lifecycle-rebuild CLI."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_core.tools.project_lifecycle import rebuild_main, rebuild_path_index


def _write_project_file(projects_dir: Path, project_id: str, record: dict) -> None:
    """Helper to write a per-project JSON file."""
    path = projects_dir / f"{project_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _make_record(
    local_path: str,
    project_id: str,
    project_name: str,
    status: str = "active",
    path_exists: bool = True,
    observed_at: str = "2026-07-26T12:00:00+08:00",
    first_observed_at: str | None = None,
    git_root: str | None = None,
    git_remote: str | None = None,
) -> dict:
    """Build a minimal lifecycle record for testing."""
    return {
        "schema_version": "project-lifecycle-v1",
        "project_id": project_id,
        "project_name": project_name,
        "status": status,
        "host": "factory",
        "event": "session-start",
        "observed_at": observed_at,
        "first_observed_at": first_observed_at or observed_at,
        "local_path": local_path,
        "path_exists": path_exists,
        "git_root": git_root or local_path,
        "git_remote": git_remote,
        "identity_source": "git_remote" if git_remote else "path",
        "identity_value": git_remote or local_path,
        "payload_cwd": local_path,
        "retention_policy": "preserve-memory-on-missing-path",
    }


# ── VAL-REBUILD-001: scans all projects/*.json ──────────────────────────


def test_rebuild_scans_all_project_files(tmp_path: Path) -> None:
    """rebuild_path_index traverses all projects/*.json and reports total_files_scanned."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    for i in range(3):
        record = _make_record(
            local_path=f"/tmp/project-{i}",
            project_id=f"proj-{i}",
            project_name=f"project-{i}",
        )
        _write_project_file(projects_dir, f"proj-{i}", record)

    result = rebuild_path_index(tmp_path)
    assert result["total_files_scanned"] == 3


# ── VAL-REBUILD-002: filters status != active ───────────────────────────


def test_rebuild_filters_inactive(tmp_path: Path) -> None:
    """Records with status != active are excluded from paths and counted in skipped_inactive."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    active = _make_record(
        local_path="/tmp/active-proj",
        project_id="active-001",
        project_name="active-proj",
        status="active",
    )
    inactive = _make_record(
        local_path="/tmp/inactive-proj",
        project_id="inactive-001",
        project_name="inactive-proj",
        status="missing",
    )
    _write_project_file(projects_dir, "active-001", active)
    _write_project_file(projects_dir, "inactive-001", inactive)

    result = rebuild_path_index(tmp_path)

    assert "/tmp/active-proj" in result["paths"]
    assert "/tmp/inactive-proj" not in result["paths"]
    assert result["skipped_inactive"] == 1


# ── VAL-REBUILD-003: filters path_exists == False ───────────────────────


def test_rebuild_filters_path_not_exists(tmp_path: Path) -> None:
    """Records with path_exists=False are excluded from paths."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    exists = _make_record(
        local_path="/tmp/exists-proj",
        project_id="exists-001",
        project_name="exists-proj",
        path_exists=True,
    )
    missing = _make_record(
        local_path="/tmp/missing-proj",
        project_id="missing-001",
        project_name="missing-proj",
        path_exists=False,
    )
    _write_project_file(projects_dir, "exists-001", exists)
    _write_project_file(projects_dir, "missing-001", missing)

    result = rebuild_path_index(tmp_path)

    assert "/tmp/exists-proj" in result["paths"]
    assert "/tmp/missing-proj" not in result["paths"]
    assert result.get("skipped_missing", 0) >= 1


# ── VAL-REBUILD-004: dedup by local_path, keep latest observed_at ────────


def test_rebuild_dedupes_by_local_path(tmp_path: Path) -> None:
    """When two records share a local_path, the one with latest observed_at wins."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    old_record = _make_record(
        local_path="/tmp/shared-path",
        project_id="old-project",
        project_name="shared-proj",
        observed_at="2026-01-01T00:00:00+08:00",
    )
    new_record = _make_record(
        local_path="/tmp/shared-path",
        project_id="new-project",
        project_name="shared-proj",
        observed_at="2026-07-26T12:00:00+08:00",
    )
    _write_project_file(projects_dir, "old-project", old_record)
    _write_project_file(projects_dir, "new-project", new_record)

    result = rebuild_path_index(tmp_path)

    assert len(result["paths"]) == 1
    assert result["paths"]["/tmp/shared-path"]["project_id"] == "new-project"
    assert result["deduplicated"] >= 1


# ── VAL-REBUILD-005: atomic write (temp + rename) ───────────────────────


def test_rebuild_atomic_write(tmp_path: Path) -> None:
    """rebuild_path_index writes path-index.json via temp file + os.replace."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    record = _make_record(
        local_path="/tmp/atomic-test",
        project_id="atomic-001",
        project_name="atomic-test",
    )
    _write_project_file(projects_dir, "atomic-001", record)

    replace_called = False
    original_replace = os.replace

    def tracking_replace(src: str, dst: str) -> None:
        nonlocal replace_called
        replace_called = True
        original_replace(src, dst)

    with patch("os.replace", side_effect=tracking_replace):
        rebuild_path_index(tmp_path)

    assert replace_called, "os.replace must be called for atomic write"

    index_path = tmp_path / "path-index.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert "/tmp/atomic-test" in data["paths"]


# ── VAL-REBUILD-006: idempotent ─────────────────────────────────────────


def test_rebuild_idempotent(tmp_path: Path) -> None:
    """Running rebuild twice produces identical path-index.json."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    for i in range(2):
        record = _make_record(
            local_path=f"/tmp/idem-proj-{i}",
            project_id=f"idem-{i}",
            project_name=f"idem-proj-{i}",
        )
        _write_project_file(projects_dir, f"idem-{i}", record)

    rebuild_path_index(tmp_path)
    index_path = tmp_path / "path-index.json"
    first_content = index_path.read_text(encoding="utf-8")

    rebuild_path_index(tmp_path)
    second_content = index_path.read_text(encoding="utf-8")

    assert first_content == second_content


# ── VAL-REBUILD-007: CLI --dry-run ──────────────────────────────────────


def test_rebuild_cli_dry_run(tmp_path: Path, capsys) -> None:
    """--dry-run prints stats but does NOT modify path-index.json."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    record = _make_record(
        local_path="/tmp/dryrun-proj",
        project_id="dryrun-001",
        project_name="dryrun-proj",
    )
    _write_project_file(projects_dir, "dryrun-001", record)

    # Pre-create a path-index.json with known content
    index_path = tmp_path / "path-index.json"
    original_content = '{"schema_version": "project-lifecycle-path-index-v1", "paths": {}}\n'
    index_path.write_text(original_content, encoding="utf-8")
    original_mtime = index_path.stat().st_mtime_ns

    with pytest.raises(SystemExit) as exc_info:
        rebuild_main(
            [
                "--lifecycle-root",
                str(tmp_path),
                "--dry-run",
            ]
        )

    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "dry-run" in captured.out.lower() or "total_files_scanned" in captured.out

    # Verify file was NOT modified
    assert index_path.read_text(encoding="utf-8") == original_content
    assert index_path.stat().st_mtime_ns == original_mtime


# ── VAL-REBUILD-008: CLI --json ─────────────────────────────────────────


def test_rebuild_cli_json_output(tmp_path: Path, capsys) -> None:
    """--json emits valid JSON with required keys."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    record = _make_record(
        local_path="/tmp/json-proj",
        project_id="json-001",
        project_name="json-proj",
    )
    _write_project_file(projects_dir, "json-001", record)

    with pytest.raises(SystemExit) as exc_info:
        rebuild_main(
            [
                "--lifecycle-root",
                str(tmp_path),
                "--json",
            ]
        )

    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert "total_files_scanned" in output
    assert "active_entries" in output
    assert "skipped_inactive" in output
    assert "deduplicated" in output
    assert "paths" in output


# ── VAL-REBUILD-009: real-world rebuild covers consumer projects ─────────


def test_rebuild_real_environment(tmp_path: Path) -> None:
    """Rebuild from a fixture mimicking the real lifecycle root covers all projects."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    consumer_projects = [
        ("transcripts", "transcripts-cb7dfe295332"),
        ("youzy", "youzy-10730b92d823"),
        ("workbot", "workbot-684250a689d3"),
        ("openmontage", "openmontage-ab49baa0bbe0"),
        ("gateway-admin", "gateway-admin-600d27df7b15"),
        ("ecxf-exam", "ecxf-exam-9ca162f2ca91"),
        ("ecxf-scraper", "ecxf-scraper-267717ec8a81"),
    ]

    for name, pid in consumer_projects:
        record = _make_record(
            local_path=f"/Users/testuser/projects/{name}",
            project_id=pid,
            project_name=name,
            git_remote=f"https://github.com/testuser/{name}.git",
        )
        _write_project_file(projects_dir, pid, record)

    # Add memory-core itself
    mc_record = _make_record(
        local_path="/Users/testuser/memory",
        project_id="memory-ea40a30ce4d8",
        project_name="memory",
        git_remote="https://github.com/hdot123-org/memory.git",
    )
    _write_project_file(projects_dir, "memory-ea40a30ce4d8", mc_record)

    result = rebuild_path_index(tmp_path)

    assert result["total_files_scanned"] == 8
    assert result["active_entries"] == 8
    assert len(result["paths"]) == 8

    # All consumer projects present
    paths = result["paths"]
    for name, _ in consumer_projects:
        assert any(name in p for p in paths), f"Missing consumer project: {name}"


# ── Additional edge case tests ───────────────────────────────────────────


def test_rebuild_empty_projects_dir(tmp_path: Path) -> None:
    """rebuild_path_index handles empty projects/ directory gracefully."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    result = rebuild_path_index(tmp_path)

    assert result["total_files_scanned"] == 0
    assert result["active_entries"] == 0
    assert len(result["paths"]) == 0


def test_rebuild_skips_non_json_files(tmp_path: Path) -> None:
    """Non-.json files in projects/ are ignored."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Write a non-JSON file
    (projects_dir / "readme.txt").write_text("ignore me", encoding="utf-8")

    record = _make_record(
        local_path="/tmp/valid-proj",
        project_id="valid-001",
        project_name="valid-proj",
    )
    _write_project_file(projects_dir, "valid-001", record)

    result = rebuild_path_index(tmp_path)

    assert result["total_files_scanned"] == 1
    assert "/tmp/valid-proj" in result["paths"]


def test_rebuild_handles_malformed_json(tmp_path: Path) -> None:
    """Malformed JSON files are skipped without crashing."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Write malformed JSON
    (projects_dir / "broken-001.json").write_text("{invalid json", encoding="utf-8")

    record = _make_record(
        local_path="/tmp/good-proj",
        project_id="good-001",
        project_name="good-proj",
    )
    _write_project_file(projects_dir, "good-001", record)

    result = rebuild_path_index(tmp_path)

    # Should still process the good file
    assert "/tmp/good-proj" in result["paths"]


def test_rebuild_preserves_first_observed_at_on_dedup(tmp_path: Path) -> None:
    """When deduplicating, the earliest first_observed_at is preserved."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    old_record = _make_record(
        local_path="/tmp/shared",
        project_id="old-proj",
        project_name="shared",
        observed_at="2026-01-01T00:00:00+08:00",
        first_observed_at="2025-06-01T00:00:00+08:00",
    )
    new_record = _make_record(
        local_path="/tmp/shared",
        project_id="new-proj",
        project_name="shared",
        observed_at="2026-07-26T12:00:00+08:00",
        first_observed_at="2026-03-01T00:00:00+08:00",
    )
    _write_project_file(projects_dir, "old-proj", old_record)
    _write_project_file(projects_dir, "new-proj", new_record)

    result = rebuild_path_index(tmp_path)

    # The new record wins (latest observed_at), but first_observed_at should be earliest
    entry = result["paths"]["/tmp/shared"]
    assert entry["project_id"] == "new-proj"
    # first_observed_at should be the earliest across both records
    assert entry["first_observed_at"] == "2025-06-01T00:00:00+08:00"
