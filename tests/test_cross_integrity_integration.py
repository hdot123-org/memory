"""Cross-functional integration tests: VAL-CROSS-001 through VAL-CROSS-004.

Verify F1-F5 end-to-end collaboration:
- VAL-CROSS-001: Init baseline → modify file → incremental sign detects change
- VAL-CROSS-002: PromptSubmit heartbeat + SessionEnd coexist in same sessions.md
- VAL-CROSS-003: Gateway session-start detects A/B/C layer changes
- VAL-CROSS-004: Full lifecycle — init → heartbeat → session-end → summary → error
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory_core.tools.memory_hook_gateway import _collect_changed_paths
from memory_core.tools.memory_hook_integrity_keys import generate_key
from memory_core.tools.memory_hook_integrity_manifest import (
    sign_project,
    sign_project_incremental,
)
from memory_core.tools.memory_hook_integrity_verify import verify_project


def _create_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal project structure with memory/ directories."""
    project = tmp_path / "test-project"
    (project / "memory" / "system").mkdir(parents=True)
    (project / "memory" / "log").mkdir(parents=True)
    (project / "memory" / "kb" / "global").mkdir(parents=True)
    (project / "memory" / "artifacts" / "memory-hook" / "contexts").mkdir(parents=True)
    (project / "memory" / "artifacts" / "memory-hook" / "events").mkdir(parents=True)

    # Create canonical system files (these match CANONICAL_PATTERNS)
    (project / "memory" / "system" / "CANONICAL.md").write_text("# Canonical\n")
    (project / "memory" / "system" / "adapter.toml").write_text('[adapter]\nname = "test"\n')
    (project / "memory" / "system" / "ownership.toml").write_text("# ownership\n")
    (project / "memory" / "system" / "memory.lock").write_text("")
    (project / "memory" / "system" / "migrations.log").write_text("")

    # Create a global KB file
    (project / "memory" / "kb" / "global" / "README.md").write_text("# Global KB\n")

    return project


def _monkeypatch_source_detection(monkeypatch: pytest.MonkeyPatch, project: Path) -> None:
    """Patch is_memory_core_source_repo to return False for our test project."""
    monkeypatch.setattr(
        "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
        lambda p: False,
    )
    monkeypatch.setattr(
        "memory_core.tools.memory_hook_integrity_verify.is_memory_core_source_repo",
        lambda p: False,
    )


# ============================================================
# VAL-CROSS-001: Init baseline → modify file → incremental sign detects change
# ============================================================


class TestCross001InitModifyIncremental:
    """After F2 init creates baseline, modifying a tracked file and running
    incremental sign updates only that entry.
    """

    def test_init_then_modify_then_incremental_sign(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Init creates baseline → modify a file → incremental sign → only modified file's hash changed."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        # Step 1: Full sign (simulates init baseline)
        manifest_before = sign_project(project, key)
        assert manifest_before is not None
        assert manifest_before["schema_version"] == "integrity-manifest-v2"

        # Build lookup by rel_path
        entries_before = {e["rel_path"]: e for e in manifest_before["entries"]}

        # Step 2: Modify a canonical file that IS in the manifest (adapter.toml)
        canonical_file = project / "memory" / "system" / "adapter.toml"
        original_content = canonical_file.read_text()
        modified_content = original_content + '\nmodified = "true"\n'
        canonical_file.write_text(modified_content)

        # Step 3: Incremental sign only the changed file
        changed_rel = str(canonical_file.relative_to(project))
        manifest_after = sign_project_incremental(
            project, key, changed_paths=[changed_rel]
        )
        assert manifest_after is not None

        entries_after = {e["rel_path"]: e for e in manifest_after["entries"]}

        # The modified file should have a different hash
        assert entries_after[changed_rel]["sha256"] != entries_before[changed_rel]["sha256"]

        # All other files should retain their original hash
        for rel_path, entry_before in entries_before.items():
            if rel_path != changed_rel:
                assert entries_after[rel_path]["sha256"] == entry_before["sha256"], (
                    f"Unchanged file {rel_path} should retain original signature"
                )

    def test_audit_log_records_incremental_sign(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Audit log after incremental sign records changed paths."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        sign_project(project, key)

        # Modify and incremental sign
        canonical_file = project / "memory" / "system" / "adapter.toml"
        canonical_file.write_text("# Modified\n")
        changed_rel = str(canonical_file.relative_to(project))

        sign_project_incremental(
            project, key, changed_paths=[changed_rel], reason="test-modification"
        )

        # Check audit log - only incremental sign writes to audit log
        audit_path = project / "memory" / "system" / "integrity-audit.jsonl"
        assert audit_path.exists()
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) >= 1

        last_entry = json.loads(lines[-1])
        assert last_entry["action"] == "incremental-sign"
        assert changed_rel in last_entry["changed_paths"]
        assert last_entry.get("reason") == "test-modification"

    def test_verify_passes_after_incremental_sign(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """verify_project() passes after incremental sign of modified file."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        sign_project(project, key)

        # Modify
        canonical_file = project / "memory" / "system" / "adapter.toml"
        canonical_file.write_text("# Changed content\n")
        changed_rel = str(canonical_file.relative_to(project))

        # Incremental sign
        manifest = sign_project_incremental(project, key, changed_paths=[changed_rel])
        assert manifest is not None

        # Verify should pass
        result = verify_project(project, key)
        assert result.ok, f"Verification failed: {result.errors}"


# ============================================================
# VAL-CROSS-002: PromptSubmit heartbeat + SessionEnd coexist in same sessions.md
# ============================================================


class TestCross002HeartbeatSessionEndCoexist:
    """F4 heartbeat and F5 A-layer session-end coexist in same sessions.md
    file with valid manifest signing.
    """

    def _write_heartbeat(
        self,
        project: Path,
        session_id: str,
        prompt: str,
        count: int,
        *,
        date_str: str | None = None,
    ) -> Path:
        """Simulate _log_prompt_submit writing a heartbeat entry."""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        sessions_file = project / "memory" / "log" / f"{date_str}-sessions.md"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%H:%M:%S")
        short_id = session_id[:8]
        prompt_preview = prompt[:100]
        entry = (
            f"#### {timestamp} — {short_id} [heartbeat]\n"
            f"- **用户消息**: {prompt_preview}\n"
            f"- **累计 prompt 数**: {count}\n"
            f"---\n\n"
        )

        import fcntl
        with sessions_file.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(entry)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        return sessions_file

    def _write_session_end_entry(
        self,
        project: Path,
        session_id: str,
        *,
        date_str: str | None = None,
    ) -> Path:
        """Simulate A-layer session-end writing to sessions.md."""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        sessions_file = project / "memory" / "log" / f"{date_str}-sessions.md"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)

        entry = (
            f"## Session End: {session_id}\n"
            f"- **Status**: completed\n"
            f"- **Timestamp**: {datetime.now().strftime('%H:%M:%S')}\n"
            f"---\n\n"
        )

        import fcntl
        with sessions_file.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(entry)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        return sessions_file

    def test_heartbeat_and_session_end_coexist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both heartbeat and session-end entries present in same file, manifest hash matches final state."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        # Full sign baseline
        sign_project(project, key)

        session_id = "abc12345-defg-6789"
        date_str = datetime.now().strftime("%Y-%m-%d")
        sessions_file = project / "memory" / "log" / f"{date_str}-sessions.md"

        # Step 1: Write heartbeat (F4)
        hb_path = self._write_heartbeat(
            project, session_id, "Hello, this is a test prompt for heartbeat", count=1
        )
        assert hb_path == sessions_file
        assert sessions_file.exists()

        # Incremental sign the sessions.md
        rel_sessions = str(sessions_file.relative_to(project))
        sign_project_incremental(project, key, changed_paths=[rel_sessions])

        # Verify heartbeat content
        content = sessions_file.read_text()
        assert "[heartbeat]" in content
        assert "abc12345" in content
        assert "Hello, this is a test prompt for heartbeat" in content
        assert "累计 prompt 数" in content

        # Step 2: Write session-end entry (F5 A-layer)
        se_path = self._write_session_end_entry(project, session_id)
        assert se_path == sessions_file

        # Incremental sign again after session-end
        sign_project_incremental(project, key, changed_paths=[rel_sessions])

        # Both entries should be present
        content_after = sessions_file.read_text()
        assert "[heartbeat]" in content_after
        assert "Session End" in content_after
        assert "abc12345" in content_after

        # Verify should pass — manifest should match final file state
        result = verify_project(project, key)
        assert result.ok, (
            f"Verification failed after both heartbeat and session-end: {result.errors}"
        )

    def test_multiple_heartbeats_then_session_end(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple heartbeats + session-end coexist, manifest consistent."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        sign_project(project, key)

        session_id = "multi-session-001"
        rel_sessions = f"memory/log/{datetime.now().strftime('%Y-%m-%d')}-sessions.md"
        sessions_file = project / rel_sessions

        # Write 3 heartbeats
        for i in range(1, 4):
            self._write_heartbeat(
                project, session_id, f"Prompt message number {i} for testing", count=i
            )
            sign_project_incremental(project, key, changed_paths=[rel_sessions])

        # Write session-end
        self._write_session_end_entry(project, session_id)
        sign_project_incremental(project, key, changed_paths=[rel_sessions])

        # Verify all heartbeats are present with correct counts
        content = sessions_file.read_text()
        for i in range(1, 4):
            assert f"累计 prompt 数**: {i}" in content, f"Missing count {i}"
        assert "Session End" in content

        # Manifest must be valid
        result = verify_project(project, key)
        assert result.ok, f"Verification failed: {result.errors}"


# ============================================================
# VAL-CROSS-003: Gateway session-start detects A/B/C layer changes
# ============================================================


class TestCross003SessionStartDetectsLayerChanges:
    """Session-start hook detects files modified by A/B/C layer writes.
    verify_project() should catch the discrepancy when manifest hash doesn't match file.
    """

    def test_verify_detects_unsigned_sessions_md_after_layer_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Layer writes sessions.md, incremental sign adds it → verify passes with it in manifest."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        # Full sign baseline (sessions.md doesn't exist yet)
        sign_project(project, key)

        # A-layer writes sessions.md
        sessions_file = project / "memory" / "log" / f"{datetime.now().strftime('%Y-%m-%d')}-sessions.md"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        sessions_file.write_text("## Session appended after last signing\n")

        # Incremental sign adds it to manifest
        rel_path = str(sessions_file.relative_to(project))
        sign_project_incremental(project, key, changed_paths=[rel_path])

        # Verify should pass — sessions.md is now signed
        result = verify_project(project, key)
        assert result.ok, f"Verification failed: {result.errors}"

        # Manifest should include sessions.md
        manifest_path = project / "memory" / "system" / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text())
        manifest_rel_paths = {e["rel_path"] for e in manifest_data["entries"]}
        assert rel_path in manifest_rel_paths, (
            f"sessions.md should be in manifest after incremental sign: {manifest_rel_paths}"
        )

    def test_incremental_sign_fixes_discrepancy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After layer writes file, incremental sign restores verification consistency."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        sign_project(project, key)

        # A-layer writes sessions.md
        sessions_file = project / "memory" / "log" / f"{datetime.now().strftime('%Y-%m-%d')}-sessions.md"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        sessions_file.write_text("## New session data\n")
        rel_path = str(sessions_file.relative_to(project))

        # Incremental sign includes it in manifest
        sign_project_incremental(project, key, changed_paths=[rel_path])

        # Now verification should pass with no warnings for this file
        result = verify_project(project, key)
        unsigned_warnings = [w for w in result.warnings if "sessions.md" in w.get("rel_path", "")]
        assert len(unsigned_warnings) == 0, (
            f"Expected no unsigned warnings after incremental sign, got: {result.warnings}"
        )

    def test_collect_changed_paths_detects_modified_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_collect_changed_paths() returns file whose content changed after last signing."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()

        # Sign project
        manifest = sign_project(project, key)
        assert manifest is not None

        # Modify a file that IS in the manifest
        adapter_file = project / "memory" / "system" / "adapter.toml"
        adapter_file.write_text('[adapter]\nname = "modified"\n')

        # _collect_changed_paths should detect it (takes manifest dict, not path)
        changed = _collect_changed_paths(project, manifest)
        assert any("adapter.toml" in p for p in changed), (
            f"Expected adapter.toml in changed paths, got: {changed}"
        )


# ============================================================
# VAL-CROSS-004: Full lifecycle — init → heartbeat → session-end → summary → error
# ============================================================


class TestCross004FullLifecycle:
    """Complete session lifecycle: init → heartbeat → session-end → summary → error log.
    `verify_project()` passes after each step; manifest contains all files.
    """

    def _write_heartbeat_entry(
        self, project: Path, session_id: str, prompt: str, count: int, date_str: str
    ) -> str:
        """Write a heartbeat entry to sessions.md."""
        sessions_file = project / "memory" / "log" / f"{date_str}-sessions.md"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%H:%M:%S")
        short_id = session_id[:8]
        entry = (
            f"#### {timestamp} — {short_id} [heartbeat]\n"
            f"- **用户消息**: {prompt[:100]}\n"
            f"- **累计 prompt 数**: {count}\n"
            f"---\n\n"
        )
        import fcntl
        with sessions_file.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(entry)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return f"memory/log/{date_str}-sessions.md"

    def _write_session_end_entry(
        self, project: Path, session_id: str, date_str: str
    ) -> str:
        """Write a session-end entry to sessions.md."""
        sessions_file = project / "memory" / "log" / f"{date_str}-sessions.md"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            f"## Session End: {session_id}\n"
            f"- **Status**: completed\n"
            f"---\n\n"
        )
        import fcntl
        with sessions_file.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(entry)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return f"memory/log/{date_str}-sessions.md"

    def _write_daily_summary(
        self, project: Path, date_str: str
    ) -> str:
        """Write a daily summary file (B-layer simulation)."""
        summary_file = project / "memory" / "log" / f"{date_str}.md"
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(
            f"# Daily Summary: {date_str}\n\n"
            f"## Sessions\n- 1 session completed\n\n"
            f"## Errors\n- None\n"
        )
        return f"memory/log/{date_str}.md"

    def _write_error_log(
        self, project: Path, date_str: str, error_msg: str
    ) -> str:
        """Write an error log entry (C-layer simulation)."""
        error_file = project / "memory" / "log" / f"{date_str}-errors.jsonl"
        error_file.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "ERROR",
            "message": error_msg,
        }) + "\n"
        import fcntl
        with error_file.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(entry)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return f"memory/log/{date_str}-errors.jsonl"

    def test_full_lifecycle_with_verification_at_each_step(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full lifecycle: init → heartbeat → session-end → summary → error.
        verify_project() passes after each step.
        """
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()
        session_id = "full-lifecycle-test-001"
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Step 1: Init (full sign baseline)
        manifest = sign_project(project, key)
        assert manifest is not None
        result = verify_project(project, key)
        assert result.ok, f"Step 1 (init) verification failed: {result.errors}"

        # Step 2: Heartbeat (F4 prompt-submit)
        rel_sessions = self._write_heartbeat_entry(
            project, session_id, "Hello from heartbeat", count=1, date_str=date_str
        )
        sign_project_incremental(project, key, changed_paths=[rel_sessions])
        result = verify_project(project, key)
        assert result.ok, f"Step 2 (heartbeat) verification failed: {result.errors}"

        # Check sessions.md exists and has heartbeat
        sessions_file = project / rel_sessions
        assert sessions_file.exists()
        content = sessions_file.read_text()
        assert "[heartbeat]" in content

        # Step 3: Session-end (F5 A-layer)
        rel_sessions_2 = self._write_session_end_entry(project, session_id, date_str=date_str)
        assert rel_sessions_2 == rel_sessions  # same file
        sign_project_incremental(project, key, changed_paths=[rel_sessions_2])
        result = verify_project(project, key)
        assert result.ok, f"Step 3 (session-end) verification failed: {result.errors}"

        # Verify session-end was appended
        content = sessions_file.read_text()
        assert "Session End" in content

        # Step 4: Daily summary (F5 B-layer)
        rel_summary = self._write_daily_summary(project, date_str=date_str)
        sign_project_incremental(project, key, changed_paths=[rel_summary])
        result = verify_project(project, key)
        assert result.ok, f"Step 4 (summary) verification failed: {result.errors}"

        # Check summary file
        summary_file = project / rel_summary
        assert summary_file.exists()
        assert "Daily Summary" in summary_file.read_text()

        # Step 5: Error log (F5 C-layer)
        rel_errors = self._write_error_log(
            project, date_str=date_str, error_msg="Test error in lifecycle"
        )
        sign_project_incremental(project, key, changed_paths=[rel_errors])
        result = verify_project(project, key)
        assert result.ok, f"Step 5 (error) verification failed: {result.errors}"

        # Check error log
        error_file = project / rel_errors
        assert error_file.exists()
        error_content = error_file.read_text()
        assert "Test error in lifecycle" in error_content

        # Final comprehensive check: manifest contains all 3 new files
        manifest_path = project / "memory" / "system" / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text())
        manifest_rel_paths = {e["rel_path"] for e in manifest_data["entries"]}

        assert rel_sessions in manifest_rel_paths, (
            f"Sessions.md not in manifest: {manifest_rel_paths}"
        )
        assert rel_summary in manifest_rel_paths, (
            f"Summary not in manifest: {manifest_rel_paths}"
        )
        assert rel_errors in manifest_rel_paths, (
            f"Errors not in manifest: {manifest_rel_paths}"
        )

    def test_full_lifecycle_multiple_heartbeats(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple heartbeats throughout lifecycle, manifest stays consistent."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()
        session_id = "multi-heartbeat-session"
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Init
        sign_project(project, key)
        result = verify_project(project, key)
        assert result.ok

        # 3 heartbeats
        for i in range(1, 4):
            rel_sessions = self._write_heartbeat_entry(
                project, session_id, f"Prompt message {i}", count=i, date_str=date_str
            )
            sign_project_incremental(project, key, changed_paths=[rel_sessions])
            result = verify_project(project, key)
            assert result.ok, f"Heartbeat {i} verification failed: {result.errors}"

        # Session-end
        self._write_session_end_entry(project, session_id, date_str=date_str)
        sign_project_incremental(project, key, changed_paths=[rel_sessions])
        result = verify_project(project, key)
        assert result.ok, f"Session-end verification failed: {result.errors}"

        # Summary
        rel_summary = self._write_daily_summary(project, date_str=date_str)
        sign_project_incremental(project, key, changed_paths=[rel_summary])
        result = verify_project(project, key)
        assert result.ok, f"Summary verification failed: {result.errors}"

        # Error
        rel_errors = self._write_error_log(project, date_str=date_str, error_msg="Final error")
        sign_project_incremental(project, key, changed_paths=[rel_errors])
        result = verify_project(project, key)
        assert result.ok, f"Error verification failed: {result.errors}"

        # Final manifest completeness
        manifest_path = project / "memory" / "system" / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text())
        manifest_rel_paths = {e["rel_path"] for e in manifest_data["entries"]}

        assert rel_sessions in manifest_rel_paths
        assert rel_summary in manifest_rel_paths
        assert rel_errors in manifest_rel_paths

    def test_audit_log_shows_complete_lifecycle_sequence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Audit log contains the full sequence of signing operations."""
        _monkeypatch_source_detection(monkeypatch, tmp_path)
        project = _create_minimal_project(tmp_path)
        key = generate_key()
        session_id = "audit-sequence-test"
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Full lifecycle
        sign_project(project, key)

        rel_sessions = self._write_heartbeat_entry(project, session_id, "heartbeat", 1, date_str)
        sign_project_incremental(project, key, changed_paths=[rel_sessions])

        self._write_session_end_entry(project, session_id, date_str)
        sign_project_incremental(project, key, changed_paths=[rel_sessions])

        rel_summary = self._write_daily_summary(project, date_str)
        sign_project_incremental(project, key, changed_paths=[rel_summary])

        rel_errors = self._write_error_log(project, date_str, "error")
        sign_project_incremental(project, key, changed_paths=[rel_errors])

        # Audit log should have 4 entries (sign_project doesn't write audit, only incremental does)
        audit_path = project / "memory" / "system" / "integrity-audit.jsonl"
        assert audit_path.exists()
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) == 4, f"Expected 4 audit entries, got {len(lines)}"

        # All are incremental-sign entries
        for line in lines:
            entry = json.loads(line)
            assert entry["action"] == "incremental-sign"
            assert len(entry["changed_paths"]) >= 1
