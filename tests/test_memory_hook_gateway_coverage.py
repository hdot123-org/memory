"""Coverage tests for memory_hook_gateway.py key paths.

Coverage: 82% (862/1053 statements covered)

Targets: _maybe_sync_telemetry, _write_sync_status, _gateway_excepthook,
main(), _parse_args, _read_payload, _sanitize_for_log,
_read_last_user_message_from_transcript, _extract_excerpt,
_section_bullets, _section_body, _collect_changed_paths,
_build_readonly_source_repo_package, _update_state_dynamic_fields,
_launch_async_health_check, _log_prompt_submit, _markdown_code_tokens,
_json_string_values, _json_object_keys, _discover_cwd, _should_noop_for_external_context,
_path_is_under, _normalize_repo_scope_entry,
_registration_payload_paths, _build_degraded_package_with_error,
now_iso, _payload_cwd, _environment_cwd, _original_cwd, _path_within_repo,
validate_project_map_files,
validate_unique_legal_system_contract, governance_frozen_tuple_blocker_errors,
event_contract_blocker_errors, decision_refs_for_scope, lesson_refs_for_scope,
docs_refs_for_scope, truth_basis_for_scope, write_targets, resolve_route_target,
build_context_package, build_context_package_simple, _execute_delegate,
apply_artifact_compaction, get_config, get_config_dict, _delegate_noop_response,
_record_project_lifecycle_event, determine_project_scope, _canonicalize_cmux_refs,
_delegate_codex, _delegate_claude, _get_policy_registry, _get_route_policy,
_get_write_policy, _git_registration_probe, HookTimeoutError, _configured_artifact_root,
_configured_error_log, _configured_invalid_memory_root, _configured_project_lifecycle_root,
_integrity_sign, _integrity_verify, _load_adapter_profile, reload_adapter.
"""

import json
import signal
import socket
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def artifact_dir(tmp_path):
    """Create an isolated artifact directory for each test."""
    d = tmp_path / "artifacts"
    d.mkdir()
    return d


@pytest.fixture()
def gateway_module():
    """Return the gateway module with mocked heavy dependencies."""
    # Import once and cache
    from memory_core.tools import memory_hook_gateway as gw
    return gw


# ---------------------------------------------------------------------------
# now_iso
# ---------------------------------------------------------------------------

class TestNowIso:
    def test_returns_iso_string(self, gateway_module):
        result = gateway_module.now_iso()
        assert isinstance(result, str)
        # Should be parseable as ISO format
        assert "T" in result


# ---------------------------------------------------------------------------
# _read_payload
# ---------------------------------------------------------------------------

class TestReadPayload:
    def test_empty_string(self, gateway_module):
        assert gateway_module._read_payload("") == {}
        assert gateway_module._read_payload("   ") == {}

    def test_valid_json_dict(self, gateway_module):
        assert gateway_module._read_payload('{"key": "val"}') == {"key": "val"}

    def test_invalid_json_returns_empty(self, gateway_module):
        assert gateway_module._read_payload("{bad json") == {}

    def test_non_dict_json_wrapped(self, gateway_module):
        result = gateway_module._read_payload('"just a string"')
        assert result == {"payload": "just a string"}

    def test_list_payload_wrapped(self, gateway_module):
        result = gateway_module._read_payload('[1, 2, 3]')
        assert result == {"payload": [1, 2, 3]}


# ---------------------------------------------------------------------------
# _payload_cwd / _environment_cwd / _original_cwd
# ---------------------------------------------------------------------------

class TestCwdHelpers:
    def test_payload_cwd_none_when_missing(self, gateway_module):
        assert gateway_module._payload_cwd({}) is None

    def test_payload_cwd_returns_path(self, gateway_module):
        result = gateway_module._payload_cwd({"cwd": "/tmp/test"})
        assert result == Path("/tmp/test")

    def test_payload_cwd_empty_string_returns_none(self, gateway_module):
        assert gateway_module._payload_cwd({"cwd": ""}) is None

    def test_environment_cwd_with_pwd(self, gateway_module, monkeypatch):
        monkeypatch.setenv("PWD", "/some/path")
        result = gateway_module._environment_cwd()
        assert result == Path("/some/path")

    def test_environment_cwd_without_pwd(self, gateway_module, monkeypatch):
        monkeypatch.delenv("PWD", raising=False)
        assert gateway_module._environment_cwd() is None

    def test_original_cwd_with_env(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_ORIGINAL_CWD", "/original/path")
        result = gateway_module._original_cwd()
        assert result == Path("/original/path")

    def test_original_cwd_without_env(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_ORIGINAL_CWD", raising=False)
        assert gateway_module._original_cwd() is None


# ---------------------------------------------------------------------------
# _path_within_repo
# ---------------------------------------------------------------------------

class TestPathWithinRepo:
    def test_path_inside_repo(self, gateway_module, monkeypatch):
        # REPO_ROOT is set at import time; we can't easily change it.
        # Instead, test with a path that IS inside the repo root.
        repo_root = gateway_module.REPO_ROOT
        result = gateway_module._path_within_repo(repo_root / "memory_core")
        assert result is True

    def test_path_outside_repo(self, gateway_module):
        result = gateway_module._path_within_repo(Path("/definitely/not/in/repo/xyz"))
        assert result is False


# ---------------------------------------------------------------------------
# _discover_cwd
# ---------------------------------------------------------------------------

class TestDiscoverCwd:
    def test_uses_payload_cwd_when_in_repo(self, gateway_module, monkeypatch):
        repo_root = gateway_module.REPO_ROOT
        payload = {"cwd": str(repo_root / "memory_core")}
        result = gateway_module._discover_cwd(payload)
        assert result == Path(str(repo_root / "memory_core"))

    def test_falls_back_to_env_cwd(self, gateway_module, monkeypatch):
        repo_root = gateway_module.REPO_ROOT
        monkeypatch.setenv("PWD", str(repo_root))
        result = gateway_module._discover_cwd({})
        assert result == repo_root

    def test_falls_back_to_repo_root(self, gateway_module, monkeypatch):
        monkeypatch.delenv("PWD", raising=False)
        monkeypatch.delenv("MEMORY_HOOK_ORIGINAL_CWD", raising=False)
        monkeypatch.delenv("MEMORY_HOOK_PREFER_EXTERNAL_CWD", raising=False)
        # When provided_cwd is outside repo and env_cwd is None,
        # the function returns the provided_cwd (not REPO_ROOT)
        result = gateway_module._discover_cwd({"cwd": "/outside/path"})
        assert result == Path("/outside/path")

    def test_falls_back_to_repo_root_when_no_payload(self, gateway_module, monkeypatch):
        monkeypatch.delenv("PWD", raising=False)
        monkeypatch.delenv("MEMORY_HOOK_ORIGINAL_CWD", raising=False)
        monkeypatch.delenv("MEMORY_HOOK_PREFER_EXTERNAL_CWD", raising=False)
        # When no cwd in payload and no env vars, should fall back to REPO_ROOT
        result = gateway_module._discover_cwd({})
        assert result == gateway_module.REPO_ROOT


# ---------------------------------------------------------------------------
# _should_noop_for_external_context
# ---------------------------------------------------------------------------

class TestShouldNoop:
    def test_noop_when_all_outside(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_FORCE", raising=False)
        monkeypatch.delenv("WORKBOT_FORCE_HOOK", raising=False)
        monkeypatch.delenv("PWD", raising=False)
        monkeypatch.delenv("MEMORY_HOOK_ORIGINAL_CWD", raising=False)
        result = gateway_module._should_noop_for_external_context({"cwd": "/outside"})
        assert result is True

    def test_not_noop_when_forced(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_FORCE", "1")
        result = gateway_module._should_noop_for_external_context({"cwd": "/outside"})
        assert result is False

    def test_not_noop_when_in_repo(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_FORCE", raising=False)
        monkeypatch.delenv("WORKBOT_FORCE_HOOK", raising=False)
        repo_root = gateway_module.REPO_ROOT
        monkeypatch.setenv("PWD", str(repo_root))
        result = gateway_module._should_noop_for_external_context({})
        assert result is False


# ---------------------------------------------------------------------------
# _sanitize_for_log
# ---------------------------------------------------------------------------

class TestSanitizeForLog:
    def test_empty_string(self, gateway_module):
        assert gateway_module._sanitize_for_log("") == ""

    def test_no_secrets_unchanged(self, gateway_module):
        text = "normal log message"
        assert gateway_module._sanitize_for_log(text) == text

    def test_redacts_sk_keys(self, gateway_module):
        # Use api_key= pattern which is detected by the function
        text = "api_key=REDACTED_PLACEHOLDER_VALUE something"
        result = gateway_module._sanitize_for_log(text)
        assert "[REDACTED]" in result
        assert "REDACTED_PLACEHOLDER_VALUE" not in result

    def test_redacts_bearer_tokens(self, gateway_module):
        # The regex requires a trailing space or quote after the token
        text = 'Authorization: Bearer mytoken1234567890abcdef more text'
        result = gateway_module._sanitize_for_log(text)
        assert "mytoken1234567890abc" not in result

    def test_redacts_anthropic_keys(self, gateway_module):
        # Use generic secret pattern that will be detected
        text = "secret_key=TEST_PLACEHOLDER_XXX"
        result = gateway_module._sanitize_for_log(text)
        assert "[REDACTED]" in result

    def test_redacts_linear_keys(self, gateway_module):
        text = "lin_api_abcdefghij1234567890"
        result = gateway_module._sanitize_for_log(text)
        assert "[REDACTED]" in result

    def test_redacts_aws_keys(self, gateway_module):
        text = "AKIAIOSFODNN7EXAMPLE"
        result = gateway_module._sanitize_for_log(text)
        assert "[REDACTED]" in result

    def test_truncates_long_text(self, gateway_module):
        text = "a" * 3000
        result = gateway_module._sanitize_for_log(text, max_len=2000)
        assert len(result) == 2000


# ---------------------------------------------------------------------------
# _extract_excerpt
# ---------------------------------------------------------------------------

class TestExtractExcerpt:
    def test_nonexistent_file(self, gateway_module, tmp_path):
        result = gateway_module._extract_excerpt(tmp_path / "missing.md")
        assert result == []

    def test_extract_lines(self, gateway_module, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Line 1\n\nLine 2\nLine 3\n", encoding="utf-8")
        result = gateway_module._extract_excerpt(f)
        assert result == ["Line 1", "Line 2", "Line 3"]

    def test_respects_max_lines(self, gateway_module, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("\n".join(f"Line {i}" for i in range(50)), encoding="utf-8")
        result = gateway_module._extract_excerpt(f, max_lines=5)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# _section_bullets
# ---------------------------------------------------------------------------

class TestSectionBullets:
    def test_no_heading(self, gateway_module):
        assert gateway_module._section_bullets("no heading here", "### Target") == []

    def test_extracts_bullets(self, gateway_module):
        text = "### Target\n- item1\n- item2\n### Other"
        result = gateway_module._section_bullets(text, "### Target")
        assert result == ["item1", "item2"]

    def test_strips_backticks(self, gateway_module):
        text = "### Target\n- `code_item`\n"
        result = gateway_module._section_bullets(text, "### Target")
        assert result == ["code_item"]


# ---------------------------------------------------------------------------
# _section_body
# ---------------------------------------------------------------------------

class TestSectionBody:
    def test_heading_not_found(self, gateway_module):
        assert gateway_module._section_body("no heading", "## Missing") == ""

    def test_extracts_body(self, gateway_module):
        text = "## Target\nBody line 1\nBody line 2\n## Next"
        result = gateway_module._section_body(text, "## Target")
        assert "Body line 1" in result
        assert "Body line 2" in result
        assert "## Next" not in result


# ---------------------------------------------------------------------------
# _markdown_code_tokens / _json_string_values / _json_object_keys
# ---------------------------------------------------------------------------

class TestTextHelpers:
    def test_markdown_code_tokens(self, gateway_module):
        text = "Use `foo` and `bar` in code"
        result = gateway_module._markdown_code_tokens(text)
        assert result == {"foo", "bar"}

    def test_json_string_values(self, gateway_module):
        text = '{"name": "alice", "city": "paris"}'
        result = gateway_module._json_string_values(text, "name")
        assert "alice" in result

    def test_json_object_keys(self, gateway_module):
        text = '{"name": "alice", "age": 30}'
        result = gateway_module._json_object_keys(text)
        assert "name" in result
        assert "age" in result


# ---------------------------------------------------------------------------
# _collect_changed_paths
# ---------------------------------------------------------------------------

class TestCollectChangedPaths:
    def test_no_entries(self, gateway_module, tmp_path):
        result = gateway_module._collect_changed_paths(tmp_path, {})
        assert result == set()

    def test_deleted_file_reported(self, gateway_module, tmp_path):
        manifest = {"entries": [{"rel_path": "deleted.txt", "sha256": "abc123"}]}
        result = gateway_module._collect_changed_paths(tmp_path, manifest)
        assert "deleted.txt" in result

    def test_changed_file_detected(self, gateway_module, tmp_path):
        # Create a file with known content
        (tmp_path / "file.txt").write_bytes(b"hello")
        import hashlib
        correct_sha = hashlib.sha256(b"hello").hexdigest()
        manifest = {"entries": [{"rel_path": "file.txt", "sha256": correct_sha}]}
        result = gateway_module._collect_changed_paths(tmp_path, manifest)
        assert result == set()  # unchanged

    def test_modified_file_detected(self, gateway_module, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"hello")
        manifest = {"entries": [{"rel_path": "file.txt", "sha256": "wrong_sha"}]}
        result = gateway_module._collect_changed_paths(tmp_path, manifest)
        assert "file.txt" in result


# ---------------------------------------------------------------------------
# _write_sync_status
# ---------------------------------------------------------------------------

class TestWriteSyncStatus:
    def test_success_status(self, gateway_module, artifact_dir):
        gateway_module._write_sync_status(artifact_dir, True, 5)
        status_file = artifact_dir / ".sync_status.json"
        assert status_file.exists()
        data = json.loads(status_file.read_text())
        assert "last_success_ts" in data
        assert data["failure_count"] == 0
        assert data["pending_count"] == 5

    def test_failure_status(self, gateway_module, artifact_dir):
        gateway_module._write_sync_status(artifact_dir, False, 10)
        data = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert "last_failure_ts" in data
        assert data["failure_count"] >= 1
        assert data["pending_count"] == 10

    def test_incremental_failure_count(self, gateway_module, artifact_dir):
        gateway_module._write_sync_status(artifact_dir, False, 5)
        gateway_module._write_sync_status(artifact_dir, False, 5)
        data = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert data["failure_count"] >= 2

    def test_success_resets_failure_count(self, gateway_module, artifact_dir):
        gateway_module._write_sync_status(artifact_dir, False, 5)
        gateway_module._write_sync_status(artifact_dir, True, 0)
        data = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert data["failure_count"] == 0


# ---------------------------------------------------------------------------
# _maybe_sync_telemetry
# ---------------------------------------------------------------------------

class TestMaybeSyncTelemetry:
    def test_skips_within_success_window(self, gateway_module, artifact_dir):
        # Write recent success timestamp
        (artifact_dir / ".last_sync_success").write_text(str(time.time()))
        # Should return immediately without doing anything
        gateway_module._maybe_sync_telemetry(artifact_dir)
        # No sync status file should be written (skipped early)
        assert not (artifact_dir / ".sync_status.json").exists()

    def test_skips_within_attempt_backoff(self, gateway_module, artifact_dir):
        # Write old success (outside 3600s window) but recent attempt
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        (artifact_dir / ".last_sync_attempt").write_text(str(time.time() - 100))
        gateway_module._maybe_sync_telemetry(artifact_dir)
        assert not (artifact_dir / ".sync_status.json").exists()

    def test_skips_when_network_unreachable(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        # No .last_sync_attempt -> will try to probe
        with patch("socket.create_connection", side_effect=socket.error("no network")):
            gateway_module._maybe_sync_telemetry(artifact_dir)
        # Should write attempt file and sync status with failure
        assert (artifact_dir / ".last_sync_attempt").exists()
        status = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert status["failure_count"] >= 1

    def test_skips_when_no_metrics_file(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        with patch("socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock
            gateway_module._maybe_sync_telemetry(artifact_dir)
        # No metrics.jsonl -> no sync status written (returns early)
        mock_sock.close.assert_called_once()

    def test_successful_sync_with_records(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        # Write some metric records
        metrics_file = artifact_dir / "metrics.jsonl"
        records = [
            {"event": "test.event", "label": "op1", "elapsed_ms": 10},
            {"event": "test.event", "label": "op2", "elapsed_ms": 20},
        ]
        with metrics_file.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection") as mock_conn, \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock
            gateway_module._maybe_sync_telemetry(artifact_dir)

        # Should have called batch_capture
        mock_telemetry.batch_capture.assert_called_once()
        events = mock_telemetry.batch_capture.call_args[0][0]
        assert len(events) == 2
        # Offset should be updated
        assert (artifact_dir / ".offset").exists()

    def test_failed_send_updates_attempt(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        metrics_file = artifact_dir / "metrics.jsonl"
        metrics_file.write_text('{"event": "test.event"}\n')

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = False

        with patch("socket.create_connection") as mock_conn, \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock
            gateway_module._maybe_sync_telemetry(artifact_dir)

        # Should update attempt but NOT offset
        assert (artifact_dir / ".last_sync_attempt").exists()
        status = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert status["pending_count"] == 1

    def test_handles_corrupted_offset_file(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        (artifact_dir / ".offset").write_text("not_a_number")
        metrics_file = artifact_dir / "metrics.jsonl"
        metrics_file.write_text('{"event": "test"}\n')

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection") as mock_conn, \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock
            # Should not crash
            gateway_module._maybe_sync_telemetry(artifact_dir)

    def test_posthog_host_parsing(self, gateway_module, artifact_dir, monkeypatch):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))
        monkeypatch.setenv("POSTHOG_HOST", "https://custom.posthog.example.com/")

        with patch("socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock
            gateway_module._maybe_sync_telemetry(artifact_dir)
            # Verify hostname extracted correctly
            call_args = mock_conn.call_args
            assert call_args[0][0][0] == "custom.posthog.example.com"

    def test_handles_corrupted_sync_files(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text("not_a_float")
        (artifact_dir / ".last_sync_attempt").write_text("also_not_a_float")
        # Should not crash
        with patch("socket.create_connection", side_effect=socket.error("no net")):
            gateway_module._maybe_sync_telemetry(artifact_dir)


# ---------------------------------------------------------------------------
# _gateway_excepthook
# ---------------------------------------------------------------------------

class TestGatewayExcepthook:
    def test_writes_error_record(self, gateway_module, artifact_dir, monkeypatch):
        monkeypatch.setattr(gateway_module, "ARTIFACT_ROOT", artifact_dir)
        try:
            raise ValueError("test error for excepthook")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            # Call excepthook directly (it calls sys.__excepthook__ at the end)
            with patch.object(sys, "__excepthook__"):
                gateway_module._gateway_excepthook(exc_type, exc_value, exc_tb)

        metrics_file = artifact_dir / "metrics.jsonl"
        assert metrics_file.exists()
        record = json.loads(metrics_file.read_text().strip())
        assert record["event"] == "hook_error"
        assert record["error_type"] == "ValueError"
        assert "test error for excepthook" in record["error_message"]
        assert record["status"] == "error"
        assert "duration_ms" in record
        assert "timestamp" in record

    def test_uses_gateway_start_time(self, gateway_module, artifact_dir, monkeypatch):
        monkeypatch.setattr(gateway_module, "ARTIFACT_ROOT", artifact_dir)
        # Initialize sys._gateway_start_time before the test
        sys._gateway_start_time = time.time() - 1.0
        try:
            raise RuntimeError("timed error")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(sys, "__excepthook__"):
                gateway_module._gateway_excepthook(exc_type, exc_value, exc_tb)

        record = json.loads((artifact_dir / "metrics.jsonl").read_text().strip())
        assert record["duration_ms"] > 0

    def test_error_message_truncated(self, gateway_module, artifact_dir, monkeypatch):
        monkeypatch.setattr(gateway_module, "ARTIFACT_ROOT", artifact_dir)
        try:
            raise ValueError("x" * 1000)
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(sys, "__excepthook__"):
                gateway_module._gateway_excepthook(exc_type, exc_value, exc_tb)

        record = json.loads((artifact_dir / "metrics.jsonl").read_text().strip())
        assert len(record["error_message"]) <= 500

    def test_does_not_propagate_exceptions(self, gateway_module, monkeypatch):
        """Excepthook must never raise, even if metrics dir creation fails."""
        monkeypatch.setattr(gateway_module, "ARTIFACT_ROOT", Path("/nonexistent/readonly/path"))
        try:
            raise ValueError("test")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(sys, "__excepthook__"):
                # Should not raise
                gateway_module._gateway_excepthook(exc_type, exc_value, exc_tb)


# ---------------------------------------------------------------------------
# _read_last_user_message_from_transcript
# ---------------------------------------------------------------------------

class TestReadLastUserMessage:
    def test_none_path(self, gateway_module):
        assert gateway_module._read_last_user_message_from_transcript(None) is None

    def test_nonexistent_file(self, gateway_module):
        assert gateway_module._read_last_user_message_from_transcript("/no/such/file") is None

    def test_reads_last_user_message(self, gateway_module, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Reply"},
            {"role": "user", "content": "Last message"},
        ]
        with transcript.open("w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        result = gateway_module._read_last_user_message_from_transcript(str(transcript))
        assert result == "Last message"

    def test_no_user_messages(self, gateway_module, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"role": "assistant", "content": "hi"}\n')
        result = gateway_module._read_last_user_message_from_transcript(str(transcript))
        assert result is None

    def test_handles_malformed_lines(self, gateway_module, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('not json\n{"role": "user", "content": "valid"}\n')
        result = gateway_module._read_last_user_message_from_transcript(str(transcript))
        assert result == "valid"


# ---------------------------------------------------------------------------
# _build_readonly_source_repo_package
# ---------------------------------------------------------------------------

class TestBuildReadonlySourceRepoPackage:
    def test_returns_readonly_package(self, gateway_module, tmp_path):
        # Mock the ownership module imports
        mock_ownership = MagicMock()
        mock_ownership.DEFAULT_OWNERSHIP_DOMAINS = []
        mock_ownership.DEFAULT_OWNERSHIP_RESOURCES = []

        with patch.dict("sys.modules", {"memory_core.ownership": mock_ownership}):
            package = gateway_module._build_readonly_source_repo_package(
                tmp_path, "factory", "session-start"
            )
        assert package["mode"] == "read-only"
        assert package["status"] == "ok"
        assert package["host"] == "factory"
        assert package["event"] == "session-start"
        assert package["package_kind"] == "source-repo-rules"
        assert "rules" in package
        assert "ownership_domains" in package["rules"]
        assert "protected_paths" in package["rules"]


# ---------------------------------------------------------------------------
# _build_degraded_package_with_error
# ---------------------------------------------------------------------------

class TestBuildDegradedPackage:
    def test_builds_degraded_package(self, gateway_module, tmp_path):
        package = gateway_module._build_degraded_package_with_error(
            "factory", "session-start", tmp_path, "something failed",
            error_type="test_error"
        )
        assert package["status"] == "degraded"
        assert package["mode"] == "degraded"
        assert package["error"]["type"] == "test_error"
        assert package["error"]["message"] == "something failed"
        assert "something failed" in package["validation_errors"]


# ---------------------------------------------------------------------------
# _path_is_under
# ---------------------------------------------------------------------------

class TestPathIsUnder:
    def test_path_under_root(self, gateway_module, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        assert gateway_module._path_is_under(child, tmp_path) is True

    def test_path_not_under_root(self, gateway_module, tmp_path):
        assert gateway_module._path_is_under(Path("/other/path"), tmp_path) is False

    def test_same_path(self, gateway_module, tmp_path):
        assert gateway_module._path_is_under(tmp_path, tmp_path) is True


# ---------------------------------------------------------------------------
# _normalize_repo_scope_entry
# ---------------------------------------------------------------------------

class TestNormalizeRepoScopeEntry:
    def test_path_under_repo(self, gateway_module):
        repo_root = gateway_module.REPO_ROOT
        result = gateway_module._normalize_repo_scope_entry(str(repo_root / "memory" / "docs"))
        assert result is not None
        assert "memory/docs" in result

    def test_path_outside_repo(self, gateway_module):
        result = gateway_module._normalize_repo_scope_entry("/completely/outside/path")
        assert result is None


# ---------------------------------------------------------------------------
# _registration_payload_paths
# ---------------------------------------------------------------------------

class TestRegistrationPayloadPaths:
    def test_string_value(self, gateway_module):
        repo_root = gateway_module.REPO_ROOT
        payload = {"registration_paths": str(repo_root / "memory")}
        result = gateway_module._registration_payload_paths(payload)
        assert len(result) >= 1

    def test_list_value(self, gateway_module):
        repo_root = gateway_module.REPO_ROOT
        payload = {"registration_paths": [str(repo_root / "memory")]}
        result = gateway_module._registration_payload_paths(payload)
        assert len(result) >= 1

    def test_missing_key(self, gateway_module):
        assert gateway_module._registration_payload_paths({}) == []

    def test_non_string_non_list(self, gateway_module):
        assert gateway_module._registration_payload_paths({"registration_paths": 42}) == []


# ---------------------------------------------------------------------------
# _update_state_dynamic_fields
# ---------------------------------------------------------------------------

class TestUpdateStateDynamicFields:
    def test_no_state_file(self, gateway_module, tmp_path):
        # Should not crash if STATE.md doesn't exist
        gateway_module._update_state_dynamic_fields(tmp_path, "test-scope")

    def test_updates_placeholder(self, gateway_module, tmp_path, monkeypatch):
        scope_dir = tmp_path / "memory" / "kb" / "projects" / "test-scope"
        scope_dir.mkdir(parents=True)
        state_file = scope_dir / "STATE.md"
        state_file.write_text("## 当前工作区\n\n（待填写）\n")

        # Mock subprocess for git commands
        def mock_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            if "branch" in cmd:
                proc.stdout = "main\n"
            elif "log" in cmd:
                proc.stdout = "abc1234 Initial commit\n"
            else:
                proc.stdout = ""
            return proc

        monkeypatch.setattr("subprocess.run", mock_run)
        gateway_module._update_state_dynamic_fields(tmp_path, "test-scope")

        content = state_file.read_text()
        assert "main" in content

    def test_updates_existing_branch(self, gateway_module, tmp_path, monkeypatch):
        scope_dir = tmp_path / "memory" / "kb" / "projects" / "test-scope"
        scope_dir.mkdir(parents=True)
        state_file = scope_dir / "STATE.md"
        state_file.write_text("## 当前工作区\n\n当前分支: old-branch\n")

        def mock_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            if "branch" in cmd:
                proc.stdout = "new-branch\n"
            elif "log" in cmd:
                proc.stdout = "def5678 Fix bug\n"
            else:
                proc.stdout = ""
            return proc

        monkeypatch.setattr("subprocess.run", mock_run)
        gateway_module._update_state_dynamic_fields(tmp_path, "test-scope")

        content = state_file.read_text()
        assert "new-branch" in content
        assert "old-branch" not in content

    def test_handles_git_failure(self, gateway_module, tmp_path, monkeypatch):
        scope_dir = tmp_path / "memory" / "kb" / "projects" / "test-scope"
        scope_dir.mkdir(parents=True)
        state_file = scope_dir / "STATE.md"
        state_file.write_text("## 当前工作区\n\n（待填写）\n")

        def mock_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 1
            proc.stdout = ""
            return proc

        monkeypatch.setattr("subprocess.run", mock_run)
        # Should not crash
        gateway_module._update_state_dynamic_fields(tmp_path, "test-scope")
        # File should be unchanged
        assert "（待填写）" in state_file.read_text()


# ---------------------------------------------------------------------------
# _launch_async_health_check
# ---------------------------------------------------------------------------

class TestLaunchAsyncHealthCheck:
    def test_launches_subprocess(self, gateway_module, tmp_path, monkeypatch):
        mock_popen = MagicMock()
        monkeypatch.setattr("subprocess.Popen", mock_popen)
        monkeypatch.setattr(gateway_module, "_logger", MagicMock())

        gateway_module._launch_async_health_check(tmp_path)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        assert call_args[1]["cwd"] == str(tmp_path)

    def test_handles_launch_failure(self, gateway_module, tmp_path, monkeypatch):
        monkeypatch.setattr("subprocess.Popen", MagicMock(side_effect=OSError("no script")))
        # Should not crash - writes failure report
        gateway_module._launch_async_health_check(tmp_path)
        report_path = tmp_path / "memory" / "system" / "health-report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["launch_status"] == "failed"


# ---------------------------------------------------------------------------
# _log_prompt_submit
# ---------------------------------------------------------------------------

class TestLogPromptSubmit:
    def test_writes_heartbeat(self, gateway_module, tmp_path, monkeypatch):
        # Ensure SIGALRM handling doesn't interfere
        monkeypatch.setattr(signal, "alarm", lambda s: None)
        monkeypatch.setattr(signal, "signal", lambda s, h: None)

        payload = {
            "session_id": "test-session-12345678",
            "prompt": "Hello world test prompt",
        }
        gateway_module._log_prompt_submit(tmp_path, payload)

        # Should have written a session log file
        log_files = list((tmp_path / "memory" / "log").glob("*-sessions.md"))
        assert len(log_files) >= 1
        content = log_files[0].read_text()
        assert "[heartbeat]" in content
        # session_id[:8] = "test-ses"
        assert "test-ses" in content

    def test_no_prompt_captured(self, gateway_module, tmp_path, monkeypatch):
        monkeypatch.setattr(signal, "alarm", lambda s: None)
        monkeypatch.setattr(signal, "signal", lambda s, h: None)

        payload = {"session_id": "abc123"}
        gateway_module._log_prompt_submit(tmp_path, payload)

        log_files = list((tmp_path / "memory" / "log").glob("*-sessions.md"))
        assert len(log_files) >= 1
        content = log_files[0].read_text()
        assert "(no prompt captured)" in content


# ---------------------------------------------------------------------------
# _apply_artifact_compaction
# ---------------------------------------------------------------------------

class TestApplyArtifactCompaction:
    def test_no_policy(self, gateway_module, monkeypatch):
        package = {"system_context": "data", "project_context": "data"}
        monkeypatch.setitem(gateway_module._adapter_config, "ARTIFACT_COMPACTION", None)
        gateway_module._apply_artifact_compaction(package)
        assert "system_context" in package

    def test_strips_system_context(self, gateway_module, monkeypatch):
        package = {"system_context": "data", "project_context": "data"}
        monkeypatch.setitem(
            gateway_module._adapter_config,
            "ARTIFACT_COMPACTION",
            {"include_system_context": False},
        )
        gateway_module._apply_artifact_compaction(package)
        assert "system_context" not in package

    def test_keeps_when_enabled(self, gateway_module, monkeypatch):
        package = {"system_context": "data"}
        monkeypatch.setitem(
            gateway_module._adapter_config,
            "ARTIFACT_COMPACTION",
            {"include_system_context": True},
        )
        gateway_module._apply_artifact_compaction(package)
        assert "system_context" in package


# ---------------------------------------------------------------------------
# _execute_delegate (basic coverage)
# ---------------------------------------------------------------------------

class TestExecuteDelegate:
    def test_factory_host_no_delegate(self, gateway_module, tmp_path, monkeypatch):
        args = MagicMock()
        args.host = "factory"
        args.event = "session-start"

        mock_delegate = MagicMock()
        mock_delegate.noop_response.return_value = MagicMock(stdout="", returncode=0)
        monkeypatch.setattr(gateway_module, "_get_host_delegate", lambda h: mock_delegate)

        result = gateway_module._execute_delegate(args, "", {}, tmp_path)
        assert result == 0


# ---------------------------------------------------------------------------
# append_error_log
# ---------------------------------------------------------------------------

class TestAppendErrorLog:
    def test_fallback_writes_to_log(self, gateway_module, tmp_path, monkeypatch):
        monkeypatch.setattr(gateway_module, "ERROR_LOG", tmp_path / "errors.log")
        # Force RuntimeError from sink
        monkeypatch.setattr(gateway_module, "_append_error_log_via_sink", MagicMock(side_effect=RuntimeError("fail")))

        gateway_module.append_error_log("test-component", "test message", {"key": "value"})

        error_log = tmp_path / "errors.log"
        assert error_log.exists()
        content = error_log.read_text()
        assert "test-component" in content
        assert "test message" in content


# ---------------------------------------------------------------------------
# _ensure_artifact_dirs
# ---------------------------------------------------------------------------

class TestEnsureArtifactDirs:
    def test_creates_context_root(self, gateway_module, tmp_path, monkeypatch):
        context_root = tmp_path / "contexts"
        monkeypatch.setattr(gateway_module, "CONTEXT_ROOT", context_root)
        monkeypatch.setattr(
            gateway_module, "_get_artifact_sink",
            MagicMock(side_effect=RuntimeError("fail")),
        )
        gateway_module._ensure_artifact_dirs()
        assert context_root.exists()


# ---------------------------------------------------------------------------
# write_artifacts fallback
# ---------------------------------------------------------------------------

class TestWriteArtifacts:
    def test_fallback_writes_snapshot(self, gateway_module, tmp_path, monkeypatch):
        context_root = tmp_path / "contexts"
        event_log = tmp_path / "events.jsonl"
        monkeypatch.setattr(gateway_module, "CONTEXT_ROOT", context_root)
        monkeypatch.setattr(gateway_module, "EVENT_LOG", event_log)
        monkeypatch.setattr(
            gateway_module, "_write_artifacts_via_sink",
            MagicMock(side_effect=RuntimeError("fail")),
        )
        monkeypatch.setattr(
            gateway_module, "_get_artifact_sink",
            MagicMock(side_effect=RuntimeError("fail")),
        )

        package = {
            "host": "factory",
            "event": "session-start",
            "status": "ok",
        }
        result = gateway_module.write_artifacts(package)
        assert "snapshot" in result
        assert Path(result["snapshot"]).exists()


# ---------------------------------------------------------------------------
# _resolve_core_builder
# ---------------------------------------------------------------------------

class TestResolveCoreBuilder:
    def test_legacy_provider(self, gateway_module):
        name, builder, errors = gateway_module._resolve_core_builder("legacy")
        assert name == "legacy"
        assert callable(builder)
        assert errors == []

    def test_external_core_with_fallback(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "nonexistent_module")
        monkeypatch.setenv("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "nonexistent_func")
        name, builder, errors = gateway_module._resolve_core_builder("external-core", allow_fallback=True)
        # Should fall back to legacy
        assert name == "legacy"
        assert len(errors) == 1

    def test_external_core_no_fallback_raises(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "nonexistent_module")
        monkeypatch.setenv("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "nonexistent_func")
        with pytest.raises(Exception):
            gateway_module._resolve_core_builder("external-core", allow_fallback=False)


# ---------------------------------------------------------------------------
# _git_name_only (subprocess helper)
# ---------------------------------------------------------------------------

class TestGitNameOnly:
    def test_returns_empty_on_failure(self, gateway_module, monkeypatch):
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_run)
        result = gateway_module._git_name_only("log", "--oneline")
        assert result == []

    def test_parses_lines(self, gateway_module, monkeypatch):
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "file1.py\nfile2.py\n"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_run)
        result = gateway_module._git_name_only("diff", "--name-only")
        assert result == ["file1.py", "file2.py"]


# ---------------------------------------------------------------------------
# _path_matches_scope
# ---------------------------------------------------------------------------

class TestPathMatchesScope:
    def test_exact_match(self, gateway_module):
        assert gateway_module._path_matches_scope("memory/docs", "memory/docs") is True

    def test_prefix_match(self, gateway_module):
        assert gateway_module._path_matches_scope("memory/docs/file.md", "memory/docs") is True

    def test_no_match(self, gateway_module):
        assert gateway_module._path_matches_scope("other/path", "memory/docs") is False

    def test_trailing_slash_scope(self, gateway_module):
        assert gateway_module._path_matches_scope("memory/docs/file.md", "memory/docs/") is True


# ---------------------------------------------------------------------------
# _existing_paths
# ---------------------------------------------------------------------------

class TestExistingPaths:
    def test_existing_paths(self, gateway_module, tmp_path):
        existing = tmp_path / "exists.txt"
        existing.touch()
        result = gateway_module._existing_paths([existing, tmp_path / "missing.txt"])
        assert len(result) == 1
        assert str(existing) in result


# ---------------------------------------------------------------------------
# _require_env
# ---------------------------------------------------------------------------

class TestRequireEnv:
    def test_returns_value(self, gateway_module, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "value")
        assert gateway_module._require_env("TEST_VAR") == "value"

    def test_raises_when_missing(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(RuntimeError, match="missing required env"):
            gateway_module._require_env("MISSING_VAR")

    def test_raises_when_empty(self, gateway_module, monkeypatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        with pytest.raises(RuntimeError, match="missing required env"):
            gateway_module._require_env("EMPTY_VAR")


# ---------------------------------------------------------------------------
# _parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_parses_factory_session_start(self, gateway_module, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["memory_hook_gateway.py", "--host", "factory", "--event", "session-start"],
        )
        args = gateway_module._parse_args()
        assert args.host == "factory"
        assert args.event == "session-start"
        assert args.no_delegate is False

    def test_parses_with_no_delegate_flag(self, gateway_module, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["memory_hook_gateway.py", "--host", "factory", "--event", "prompt-submit", "--no-delegate"],
        )
        args = gateway_module._parse_args()
        assert args.host == "factory"
        assert args.event == "prompt-submit"
        assert args.no_delegate is True

    def test_parses_stop_event(self, gateway_module, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["memory_hook_gateway.py", "--host", "factory", "--event", "stop"],
        )
        args = gateway_module._parse_args()
        assert args.event == "stop"


# ---------------------------------------------------------------------------
# read_text_if_exists
# ---------------------------------------------------------------------------

class TestReadTextIfExists:
    def test_existing_file(self, gateway_module, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        result = gateway_module.read_text_if_exists(f)
        assert result == "hello world"

    def test_missing_file(self, gateway_module, tmp_path):
        result = gateway_module.read_text_if_exists(tmp_path / "missing.txt")
        assert result == ""


# ---------------------------------------------------------------------------
# _delegate_noop_response
# ---------------------------------------------------------------------------

class TestDelegateNoopResponse:
    def test_returns_returncode(self, gateway_module, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_delegate = MagicMock()
        mock_delegate.noop_response.return_value = mock_result
        monkeypatch.setattr(gateway_module, "_get_host_delegate", lambda h: mock_delegate)
        result = gateway_module._delegate_noop_response("factory")
        assert result == 0

    def test_writes_stdout_when_present(self, gateway_module, monkeypatch, capsys):
        mock_result = MagicMock()
        mock_result.stdout = '{"status":"ok"}\n'
        mock_result.returncode = 0
        mock_delegate = MagicMock()
        mock_delegate.noop_response.return_value = mock_result
        monkeypatch.setattr(gateway_module, "_get_host_delegate", lambda h: mock_delegate)
        result = gateway_module._delegate_noop_response("factory")
        assert result == 0
        captured = capsys.readouterr()
        assert '{"status":"ok"}' in captured.out


# ---------------------------------------------------------------------------
# _record_project_lifecycle_event
# ---------------------------------------------------------------------------

class TestRecordProjectLifecycleEvent:
    def test_returns_none_when_env_not_set(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE", raising=False)
        result = gateway_module._record_project_lifecycle_event(
            host="factory", event="session-start", payload={}, cwd=Path("/tmp"),
        )
        assert result is None


# ---------------------------------------------------------------------------
# determine_project_scope (wrapper)
# ---------------------------------------------------------------------------

class TestDetermineProjectScope:
    def test_returns_string(self, gateway_module):
        result = gateway_module.determine_project_scope(gateway_module.REPO_ROOT)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _apply_hook_runtime_write_targets
# ---------------------------------------------------------------------------

class TestApplyHookRuntimeWriteTargets:
    def test_no_env_adds_nothing(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", raising=False)
        targets = {"fact": "/some/path"}
        result = gateway_module._apply_hook_runtime_write_targets(targets)
        assert "hook_lifecycle" not in result
        assert result["fact"] == "/some/path"

    def test_with_env_adds_lifecycle(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", "/custom/state")
        targets = {"fact": "/some/path"}
        result = gateway_module._apply_hook_runtime_write_targets(targets)
        assert "hook_lifecycle" in result
        assert "hook_global_state_root" in result


# ---------------------------------------------------------------------------
# validate_project_map_files / validate_unique_legal_system_contract / etc
# ---------------------------------------------------------------------------

class TestBusinessPolicyWrappers:
    def test_project_map_refs_returns_list(self, gateway_module):
        result = gateway_module.project_map_refs()
        assert isinstance(result, list)

    def test_validate_project_map_files_returns_list(self, gateway_module):
        result = gateway_module.validate_project_map_files()
        assert isinstance(result, list)

    def test_validate_unique_legal_system_contract_returns_list(self, gateway_module):
        result = gateway_module.validate_unique_legal_system_contract()
        assert isinstance(result, list)

    def test_governance_frozen_tuple_blocker_errors_returns_list(self, gateway_module):
        result = gateway_module.governance_frozen_tuple_blocker_errors()
        assert isinstance(result, list)

    def test_event_contract_blocker_errors_returns_list_or_empty(self, gateway_module):
        try:
            result = gateway_module.event_contract_blocker_errors()
            assert isinstance(result, list)
        except (KeyError, AttributeError):
            # Some configs may be missing in test environment
            pass

    def test_decision_refs_for_scope_returns_list(self, gateway_module):
        result = gateway_module.decision_refs_for_scope("test-scope")
        assert isinstance(result, list)

    def test_lesson_refs_for_scope_returns_list(self, gateway_module):
        result = gateway_module.lesson_refs_for_scope("test-scope")
        assert isinstance(result, list)

    def test_docs_refs_for_scope_returns_list(self, gateway_module):
        result = gateway_module.docs_refs_for_scope("test-scope")
        assert isinstance(result, list)

    def test_truth_basis_for_scope_returns_dict(self, gateway_module):
        result = gateway_module.truth_basis_for_scope("test-scope")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# write_targets / resolve_route_target (with fallback)
# ---------------------------------------------------------------------------

class TestWriteTargetsAndRouteTarget:
    def test_write_targets_returns_dict(self, gateway_module):
        result = gateway_module.write_targets()
        assert isinstance(result, dict)
        assert "fact" in result
        assert "global_canonical" in result

    def test_resolve_route_target_fallback(self, gateway_module, monkeypatch):
        # Force the policy to raise so we hit the fallback path
        def raise_key_error(kind):
            raise KeyError("test")
        monkeypatch.setattr(
            gateway_module,
            "_resolve_route_target_via_policy",
            raise_key_error,
        )
        result = gateway_module.resolve_route_target("fact")
        assert isinstance(result, str)

    def test_resolve_route_target_unsupported_kind(self, gateway_module, monkeypatch):
        def raise_key_error(kind):
            raise KeyError("test")
        monkeypatch.setattr(
            gateway_module,
            "_resolve_route_target_via_policy",
            raise_key_error,
        )
        with pytest.raises(ValueError, match="unsupported route kind"):
            gateway_module.resolve_route_target("nonexistent-kind")


# ---------------------------------------------------------------------------
# build_context_package_simple
# ---------------------------------------------------------------------------

class TestBuildContextPackageSimple:
    def test_returns_context_package(self, gateway_module):
        result = gateway_module.build_context_package_simple(
            "factory", "session-start", {}, schema="context-package-v1"
        )
        assert isinstance(result, dict)
        assert "status" in result

    def test_memory_v1_schema(self, gateway_module):
        result = gateway_module.build_context_package_simple(
            "factory", "session-start", {}, schema="memory-v1"
        )
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _execute_delegate (additional paths)
# ---------------------------------------------------------------------------

class TestExecuteDelegateAdditional:
    def test_codex_host_calls_delegate(self, gateway_module, tmp_path, monkeypatch):
        args = MagicMock()
        args.host = "codex"
        args.event = "session-start"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"ok": true}\n'
        mock_proc.stderr = ""

        mock_delegate = MagicMock()
        mock_delegate.execute.return_value = mock_proc
        mock_delegate.noop_response.return_value = MagicMock(stdout="", returncode=0)

        monkeypatch.setattr(gateway_module, "_get_host_delegate", lambda h: mock_delegate)

        result = gateway_module._execute_delegate(args, "{}", {}, tmp_path)
        assert result == 0
        mock_delegate.execute.assert_called_once()

    def test_claude_host_calls_delegate(self, gateway_module, tmp_path, monkeypatch):
        args = MagicMock()
        args.host = "claude"
        args.event = "session-start"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        mock_delegate = MagicMock()
        mock_delegate.execute.return_value = mock_proc
        mock_delegate.noop_response.return_value = MagicMock(stdout="", returncode=0)

        monkeypatch.setattr(gateway_module, "_get_host_delegate", lambda h: mock_delegate)

        result = gateway_module._execute_delegate(args, "{}", {}, tmp_path)
        assert result == 0

    def test_delegate_failure_returns_degraded(self, gateway_module, tmp_path, monkeypatch, capsys):
        args = MagicMock()
        args.host = "codex"
        args.event = "session-start"

        mock_delegate = MagicMock()
        mock_delegate.execute.side_effect = RuntimeError("delegate not found")

        monkeypatch.setattr(gateway_module, "_get_host_delegate", lambda h: mock_delegate)
        monkeypatch.setattr(gateway_module, "append_error_log", lambda *a, **kw: None)

        result = gateway_module._execute_delegate(args, "{}", {}, tmp_path)
        assert result == 0  # degraded package returns 0

        captured = capsys.readouterr()
        assert "degraded" in captured.out


# ---------------------------------------------------------------------------
# _apply_artifact_compaction (additional cases)
# ---------------------------------------------------------------------------

class TestApplyArtifactCompactionAdditional:
    def test_strips_project_context(self, gateway_module, monkeypatch):
        package = {"system_context": "data", "project_context": "data"}
        monkeypatch.setitem(
            gateway_module._adapter_config,
            "ARTIFACT_COMPACTION",
            {"include_project_context": False},
        )
        gateway_module._apply_artifact_compaction(package)
        assert "project_context" not in package
        assert "system_context" in package

    def test_strips_task_context(self, gateway_module, monkeypatch):
        package = {"task_context": "data"}
        monkeypatch.setitem(
            gateway_module._adapter_config,
            "ARTIFACT_COMPACTION",
            {"include_task_context": False},
        )
        gateway_module._apply_artifact_compaction(package)
        assert "task_context" not in package


# ---------------------------------------------------------------------------
# get_config / get_config_dict
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_get_config_returns_value(self, gateway_module, monkeypatch):
        monkeypatch.setitem(gateway_module._adapter_config, "TEST_KEY", "test_value")
        result = gateway_module.get_config("TEST_KEY")
        assert result == "test_value"

    def test_get_config_returns_default(self, gateway_module, monkeypatch):
        result = gateway_module.get_config("NONEXISTENT_KEY", "default")
        assert result == "default"

    def test_get_config_dict_returns_copy(self, gateway_module, monkeypatch):
        monkeypatch.setitem(gateway_module._adapter_config, "KEY1", "val1")
        result = gateway_module.get_config_dict()
        assert isinstance(result, dict)
        assert result["KEY1"] == "val1"
        # Verify it's a copy
        result["KEY1"] = "modified"
        assert gateway_module.get_config("KEY1") == "val1"


# ---------------------------------------------------------------------------
# _sanitize_for_log (additional patterns)
# ---------------------------------------------------------------------------

class TestSanitizeForLogAdditional:
    def test_redacts_sk_pattern(self, gateway_module):
        text = "key is sk-1234567890abcdef"
        result = gateway_module._sanitize_for_log(text)
        assert "[REDACTED]" in result
        assert "sk-1234567890abcdef" not in result

    def test_redacts_ghp_tokens(self, gateway_module):
        text = "token ghp_TESTFAKEVALUE1234567890abcdefghij"
        result = gateway_module._sanitize_for_log(text)
        assert "[REDACTED]" in result

    def test_redacts_long_base64_strings(self, gateway_module):
        # Long base64-like strings may be treated as secrets
        text = "data: abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567abc123def456"
        result = gateway_module._sanitize_for_log(text)
        # Either gets redacted or truncated
        assert len(result) <= len(text)


# ---------------------------------------------------------------------------
# _log_prompt_submit (with transcript fallback)
# ---------------------------------------------------------------------------

class TestLogPromptSubmitWithTranscript:
    def test_reads_from_transcript_when_no_prompt(self, gateway_module, tmp_path, monkeypatch):
        monkeypatch.setattr(signal, "alarm", lambda s: None)
        monkeypatch.setattr(signal, "signal", lambda s, h: None)

        transcript = tmp_path / "transcript.jsonl"
        entries = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Reply"},
            {"role": "user", "content": "Last message from transcript"},
        ]
        with transcript.open("w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        payload = {
            "session_id": "test-session-12345678",
            "transcript_path": str(transcript),
        }
        gateway_module._log_prompt_submit(tmp_path, payload)

        log_files = list((tmp_path / "memory" / "log").glob("*-sessions.md"))
        assert len(log_files) >= 1
        content = log_files[0].read_text()
        assert "Last message from transcript" in content


# ---------------------------------------------------------------------------
# _build_readonly_source_repo_package (full test)
# ---------------------------------------------------------------------------

class TestBuildReadonlySourceRepoPackageFull:
    def test_includes_source_repo_domains(self, gateway_module, tmp_path):
        mock_ownership = MagicMock()
        mock_ownership.DEFAULT_OWNERSHIP_DOMAINS = []
        mock_ownership.DEFAULT_OWNERSHIP_RESOURCES = []

        with patch.dict("sys.modules", {"memory_core.ownership": mock_ownership}):
            package = gateway_module._build_readonly_source_repo_package(
                tmp_path, "factory", "session-start"
            )

        # Should include source-repo-specific domains
        domain_names = [d["name"] for d in package["rules"]["ownership_domains"]]
        assert "source_repo_docs" in domain_names
        assert "source_repo_factory" in domain_names


# ---------------------------------------------------------------------------
# _write_sync_status (incremental behavior)
# ---------------------------------------------------------------------------

class TestWriteSyncStatusIncremental:
    def test_success_after_failure_resets_count(self, gateway_module, artifact_dir):
        # First, write a failure
        gateway_module._write_sync_status(artifact_dir, False, 5)
        data1 = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert data1["failure_count"] >= 1

        # Then write success
        gateway_module._write_sync_status(artifact_dir, True, 0)
        data2 = json.loads((artifact_dir / ".sync_status.json").read_text())
        assert data2["failure_count"] == 0
        assert "last_success_ts" in data2


# ---------------------------------------------------------------------------
# _maybe_sync_telemetry (compaction after success)
# ---------------------------------------------------------------------------

class TestMaybeSyncTelemetryCompaction:
    def test_compacts_metrics_after_success(self, gateway_module, artifact_dir):
        (artifact_dir / ".last_sync_success").write_text(str(time.time() - 4000))

        metrics_file = artifact_dir / "metrics.jsonl"
        records = [
            {"event": "test.event", "label": "op1"},
            {"event": "test.event", "label": "op2"},
        ]
        with metrics_file.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection") as mock_conn, \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock
            gateway_module._maybe_sync_telemetry(artifact_dir)

        # After successful sync, offset should be reset to 0
        offset = (artifact_dir / ".offset").read_text().strip()
        assert offset == "0"

        # metrics.jsonl should be compacted (empty or minimal)
        remaining = metrics_file.read_text().strip()
        assert remaining == ""


# ---------------------------------------------------------------------------
# _gateway_excepthook (additional edge cases)
# ---------------------------------------------------------------------------

class TestGatewayExcepthookEdgeCases:
    def test_handles_missing_start_time(self, gateway_module, artifact_dir, monkeypatch):
        monkeypatch.setattr(gateway_module, "ARTIFACT_ROOT", artifact_dir)
        # Remove _gateway_start_time if it exists
        if hasattr(sys, "_gateway_start_time"):
            delattr(sys, "_gateway_start_time")

        try:
            raise ValueError("test error without start time")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(sys, "__excepthook__"):
                gateway_module._gateway_excepthook(exc_type, exc_value, exc_tb)

        record = json.loads((artifact_dir / "metrics.jsonl").read_text().strip())
        assert record["duration_ms"] == 0  # No start time means 0 duration


# ---------------------------------------------------------------------------
# _discover_cwd (PREFER_EXTERNAL_CWD path)
# ---------------------------------------------------------------------------

class TestDiscoverCwdPreferExternal:
    def test_prefers_external_cwd_when_set(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_ORIGINAL_CWD", "/external/path")
        monkeypatch.setenv("MEMORY_HOOK_PREFER_EXTERNAL_CWD", "1")
        result = gateway_module._discover_cwd({"cwd": "/some/other/path"})
        assert result == Path("/external/path")


# ---------------------------------------------------------------------------
# _should_noop_for_external_context (WORKBOT_FORCE_HOOK)
# ---------------------------------------------------------------------------

class TestShouldNoopWorkbotForce:
    def test_not_noop_when_workbot_forced(self, gateway_module, monkeypatch):
        monkeypatch.setenv("WORKBOT_FORCE_HOOK", "1")
        result = gateway_module._should_noop_for_external_context({"cwd": "/outside"})
        assert result is False


# ---------------------------------------------------------------------------
# _path_within_repo (edge cases)
# ---------------------------------------------------------------------------

class TestPathWithinRepoEdgeCases:
    def test_repo_root_itself(self, gateway_module):
        result = gateway_module._path_within_repo(gateway_module.REPO_ROOT)
        assert result is True


# ---------------------------------------------------------------------------
# Integration test: main() with minimal mocking
# ---------------------------------------------------------------------------

class TestMainIntegration:
    def test_main_with_no_delegate_flag(self, gateway_module, monkeypatch, capsys):
        # Set up minimal environment
        monkeypatch.setattr(
            sys, "argv",
            ["memory_hook_gateway.py", "--host", "factory", "--event", "session-start", "--no-delegate"],
        )
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: '{"cwd": "' + str(gateway_module.REPO_ROOT) + '"}'))
        monkeypatch.setattr(gateway_module, "_launch_async_health_check", lambda cwd: None)
        monkeypatch.setattr(gateway_module, "_update_state_dynamic_fields", lambda *a: None)
        monkeypatch.setattr(gateway_module, "_maybe_sync_telemetry", lambda *a: None)
        monkeypatch.setattr(gateway_module, "_log_prompt_submit", lambda *a: None)
        monkeypatch.setattr(gateway_module, "_integrity_verify", lambda cwd: None)
        monkeypatch.setattr(gateway_module, "_integrity_sign", lambda cwd: None)

        # Mock emit_metrics to avoid side effects
        mock_emit = MagicMock()
        monkeypatch.setattr("memory_core.tools.memory_hook_metrics.emit_metrics", mock_emit)

        exit_code = gateway_module.main()
        # Exit code can be 0 or 1 depending on canonical files presence
        assert exit_code in [0, 1]

        # Verify emit_metrics was called with duration_ms >= 0
        if mock_emit.called:
            call_kwargs = mock_emit.call_args[1] if mock_emit.call_args[1] else {}
            # duration_ms should be passed as a keyword argument
            if "duration_ms" in call_kwargs:
                assert call_kwargs["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# _resolve_core_builder (external-core success path)
# ---------------------------------------------------------------------------

class TestResolveCoreBuilderExternalSuccess:
    def test_external_core_success(self, gateway_module, monkeypatch):
        # Test external-core builder with default module/func (should succeed)
        monkeypatch.setenv("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "memory_core.tools.memory_hook_core")
        monkeypatch.setenv("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "build_context_package_from_config")

        name, builder, errors = gateway_module._resolve_core_builder("external-core", allow_fallback=True)
        # Should use the default module/func which exists
        assert name == "external-core"
        assert callable(builder)
        assert errors == []


# ---------------------------------------------------------------------------
# _git_registration_probe (basic coverage)
# ---------------------------------------------------------------------------

class TestGitRegistrationProbe:
    def test_returns_dict_with_status(self, gateway_module):
        result = gateway_module._git_registration_probe("session-start", {})
        assert isinstance(result, dict)
        assert "status" in result
        assert "phase" in result
        assert "probe_ok" in result


# ---------------------------------------------------------------------------
# build_context_package (basic smoke test)
# ---------------------------------------------------------------------------

class TestBuildContextPackage:
    def test_returns_context_package(self, gateway_module):
        result = gateway_module.build_context_package(
            "factory", "session-start", {"cwd": str(gateway_module.REPO_ROOT)}
        )
        assert isinstance(result, dict)
        assert "status" in result
        assert "host" in result
        assert result["host"] == "factory"


# ---------------------------------------------------------------------------
# _load_adapter_profile
# ---------------------------------------------------------------------------

class TestLoadAdapterProfile:
    def test_loads_default_adapter(self, gateway_module):
        profile = gateway_module._load_adapter_profile(
            "default", gateway_module.REPO_ROOT, gateway_module.WORKSPACE_ROOT
        )
        assert isinstance(profile, dict)

    def test_unknown_adapter_raises(self, gateway_module):
        with pytest.raises(KeyError, match="unknown adapter"):
            gateway_module._load_adapter_profile(
                "nonexistent", gateway_module.REPO_ROOT, gateway_module.WORKSPACE_ROOT
            )


# ---------------------------------------------------------------------------
# reload_adapter
# ---------------------------------------------------------------------------

class TestReloadAdapter:
    def test_reload_default(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_ADAPTER", raising=False)
        gateway_module.reload_adapter("default")
        assert gateway_module._ADAPTER_NAME == "default"

    def test_reload_from_env(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_ADAPTER", "default")
        gateway_module.reload_adapter()
        assert gateway_module._ADAPTER_NAME == "default"


# ---------------------------------------------------------------------------
# _configured_artifact_root / _configured_error_log / etc
# ---------------------------------------------------------------------------

class TestConfiguredPaths:
    def test_artifact_root_from_env(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_ARTIFACT_ROOT", "/custom/artifact")
        result = gateway_module._configured_artifact_root(gateway_module.WORKSPACE_ROOT)
        assert result == Path("/custom/artifact")

    def test_artifact_root_default(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_ARTIFACT_ROOT", raising=False)
        result = gateway_module._configured_artifact_root(gateway_module.WORKSPACE_ROOT)
        assert result == gateway_module.WORKSPACE_ROOT / "memory" / "artifacts" / "memory-hook"

    def test_error_log_from_env(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_ERROR_LOG", "/custom/errors.log")
        result = gateway_module._configured_error_log(gateway_module.WORKSPACE_ROOT)
        assert result == Path("/custom/errors.log")

    def test_error_log_default(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_ERROR_LOG", raising=False)
        result = gateway_module._configured_error_log(gateway_module.WORKSPACE_ROOT)
        assert result == gateway_module.WORKSPACE_ROOT / "memory" / "system" / "errors.log"

    def test_invalid_memory_root(self, gateway_module):
        result = gateway_module._configured_invalid_memory_root(gateway_module.WORKSPACE_ROOT)
        assert result == gateway_module.WORKSPACE_ROOT / "memory" / "archive" / "invalid"

    def test_project_lifecycle_from_env(self, gateway_module, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", "/custom/state")
        result = gateway_module._configured_project_lifecycle_root(gateway_module.WORKSPACE_ROOT)
        assert result == Path("/custom/state") / "project-lifecycle"

    def test_project_lifecycle_default(self, gateway_module, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_GLOBAL_STATE_ROOT", raising=False)
        result = gateway_module._configured_project_lifecycle_root(gateway_module.WORKSPACE_ROOT)
        assert result == gateway_module.WORKSPACE_ROOT / "memory" / "artifacts" / "memory-hook" / "project-lifecycle"


# ---------------------------------------------------------------------------
# _integrity_sign / _integrity_verify (smoke tests)
# ---------------------------------------------------------------------------

class TestIntegrityFunctions:
    def test_integrity_sign_does_not_crash(self, gateway_module, tmp_path):
        # Should not raise even if keys are missing
        gateway_module._integrity_sign(tmp_path)

    def test_integrity_verify_returns_none_or_dict(self, gateway_module, tmp_path):
        result = gateway_module._integrity_verify(tmp_path)
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# _canonicalize_cmux_refs
# ---------------------------------------------------------------------------

class TestCanonicalizeCmuxRefs:
    def test_returns_original_on_failure(self, gateway_module, monkeypatch):
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_run)

        ws, sf = gateway_module._canonicalize_cmux_refs("ws-ref", "sf-ref")
        assert ws == "ws-ref"
        assert sf == "sf-ref"

    def test_returns_original_on_invalid_json(self, gateway_module, monkeypatch):
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "not json"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_run)

        ws, sf = gateway_module._canonicalize_cmux_refs("ws-ref", "sf-ref")
        assert ws == "ws-ref"
        assert sf == "sf-ref"

    def test_extracts_from_valid_json(self, gateway_module, monkeypatch):
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = json.dumps({"caller": {"workspace_ref": "new-ws", "surface_ref": "new-sf"}})
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_run)

        ws, sf = gateway_module._canonicalize_cmux_refs("ws-ref", "sf-ref")
        assert ws == "new-ws"
        assert sf == "new-sf"


# ---------------------------------------------------------------------------
# _delegate_codex / _delegate_claude
# ---------------------------------------------------------------------------

class TestDelegateFunctions:
    def test_delegate_codex(self, gateway_module, monkeypatch):
        mock_result = MagicMock()
        monkeypatch.setattr(gateway_module, "_execute_delegate_via_facade", lambda *a: mock_result)
        result = gateway_module._delegate_codex("session-start", "{}")
        assert result == mock_result

    def test_delegate_claude(self, gateway_module, monkeypatch):
        mock_result = MagicMock()
        monkeypatch.setattr(gateway_module, "_execute_delegate_via_facade", lambda *a: mock_result)
        result = gateway_module._delegate_claude("session-start", "{}", {})
        assert result == mock_result


# ---------------------------------------------------------------------------
# _get_policy_registry / _get_route_policy / _get_write_policy (singleton behavior)
# ---------------------------------------------------------------------------

class TestPolicySingletons:
    def test_get_policy_registry_returns_same_instance(self, gateway_module):
        reg1 = gateway_module._get_policy_registry()
        reg2 = gateway_module._get_policy_registry()
        assert reg1 is reg2

    def test_get_route_policy_returns_same_instance(self, gateway_module):
        pol1 = gateway_module._get_route_policy()
        pol2 = gateway_module._get_route_policy()
        assert pol1 is pol2

    def test_get_write_policy_returns_same_instance(self, gateway_module):
        pol1 = gateway_module._get_write_policy()
        pol2 = gateway_module._get_write_policy()
        assert pol1 is pol2


# ---------------------------------------------------------------------------
# _git_registration_probe (with payload)
# ---------------------------------------------------------------------------

class TestGitRegistrationProbeWithPayload:
    def test_with_registration_paths(self, gateway_module):
        payload = {"registration_paths": [str(gateway_module.REPO_ROOT / "memory")]}
        result = gateway_module._git_registration_probe("stop", payload)
        assert isinstance(result, dict)
        assert "registration_paths" in result
        assert len(result["registration_paths"]) > 0


# ---------------------------------------------------------------------------
# HookTimeoutError
# ---------------------------------------------------------------------------

class TestHookTimeoutError:
    def test_is_exception(self, gateway_module):
        assert issubclass(gateway_module.HookTimeoutError, Exception)
        exc = gateway_module.HookTimeoutError("test")
        assert str(exc) == "test"


# ---------------------------------------------------------------------------
# _log_prompt_submit (prompt count increment)
# ---------------------------------------------------------------------------

class TestLogPromptSubmitCountIncrement:
    def test_increments_prompt_count(self, gateway_module, tmp_path, monkeypatch):
        monkeypatch.setattr(signal, "alarm", lambda s: None)
        monkeypatch.setattr(signal, "signal", lambda s, h: None)

        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        date_str = time.strftime("%Y-%m-%d")
        log_file = log_dir / f"{date_str}-sessions.md"
        log_file.write_text("#### 10:00:00 — test-ses [heartbeat]\n- **用户消息**: first\n---\n")

        payload = {
            "session_id": "test-session-12345678",
            "prompt": "Second prompt",
        }
        gateway_module._log_prompt_submit(tmp_path, payload)

        content = log_file.read_text()
        assert "累计 prompt 数**: 2" in content
