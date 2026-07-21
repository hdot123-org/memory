#!/usr/bin/env python3
"""Tests for VAL-GW-003, VAL-GW-004, VAL-GW-005: telemetry error handling, health report injection, IF-5 facade methods.

VAL-GW-003: Telemetry error handling paths tested (batch_capture failure, sync failure)
VAL-GW-004: Health report read/parse/inject into package tested
VAL-GW-005: IF-5 facade factory methods tested
"""


import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add repo root to path for imports
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import memory_hook_gateway as gw

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_sync_artifacts(tmp_path: Path, *, metrics_lines: list[str] | None = None,
                          offset: int = 0, last_sync_success: float = 0.0,
                          last_sync_attempt: float = 0.0) -> Path:
    """Create artifact root with metrics.jsonl and sidecar files for sync tests."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    metrics_file = artifact_root / "metrics.jsonl"
    if metrics_lines is not None:
        metrics_file.write_text("".join(metrics_lines), encoding="utf-8")
    else:
        metrics_file.write_text("", encoding="utf-8")

    offset_file = artifact_root / ".offset"
    offset_file.write_text(str(offset), encoding="utf-8")

    last_sync_success_file = artifact_root / ".last_sync_success"
    last_sync_success_file.write_text(str(last_sync_success), encoding="utf-8")

    last_sync_attempt_file = artifact_root / ".last_sync_attempt"
    last_sync_attempt_file.write_text(str(last_sync_attempt), encoding="utf-8")

    return artifact_root


# ===========================================================================
# VAL-GW-003: Telemetry error handling paths
# ===========================================================================

class TestMaybeSyncTelemetryBatchCaptureFailure:
    """Tests for batch_capture failure paths in _maybe_sync_telemetry."""

    def test_batch_capture_returns_false_updates_attempt(self, tmp_path):
        """When batch_capture returns False, .last_sync_attempt is updated but offset is not."""
        metrics_lines = [
            json.dumps({"event": "test_event", "data": "value1"}) + "\n",
            json.dumps({"event": "test_event", "data": "value2"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            offset=0,
            last_sync_success=time.time() - 7200,  # 2 hours ago
            last_sync_attempt=time.time() - 600,    # 10 minutes ago
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = False

        mock_socket = MagicMock()
        mock_sock_instance = MagicMock()
        mock_socket.create_connection.return_value = mock_sock_instance

        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection", mock_socket.create_connection):
            mock_tel_module = MagicMock()
            mock_tel_module.telemetry = mock_telemetry
            with patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}):
                gw._maybe_sync_telemetry(artifact_root)

        # batch_capture should have been called
        assert mock_telemetry.batch_capture.called
        # offset should NOT be updated on failure
        offset_content = (artifact_root / ".offset").read_text(encoding="utf-8").strip()
        assert offset_content == "0"
        # last_sync_attempt should be updated
        attempt_content = float((artifact_root / ".last_sync_attempt").read_text(encoding="utf-8").strip())
        assert attempt_content > time.time() - 10

    def test_batch_capture_raises_exception_handled_gracefully(self, tmp_path):
        """When batch_capture raises an exception, _maybe_sync_telemetry handles it gracefully."""
        metrics_lines = [
            json.dumps({"event": "test_event", "data": "value1"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.side_effect = RuntimeError("network error")

        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            mock_tel_module = MagicMock()
            mock_tel_module.telemetry = mock_telemetry
            with patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}):
                # Should not raise - top-level catch must handle it
                gw._maybe_sync_telemetry(artifact_root)

    def test_sync_top_level_exception_caught(self, tmp_path):
        """Top-level except in _maybe_sync_telemetry catches any exception gracefully."""
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )
        # Make metrics_file not exist to trigger an early path, but
        # corrupt the offset file to cause an error
        metrics_file = artifact_root / "metrics.jsonl"
        metrics_file.write_text(json.dumps({"event": "x"}) + "\n", encoding="utf-8")

        # Patch socket to succeed, but mock batch_capture to raise
        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            mock_tel_module = MagicMock()
            mock_tel_module.telemetry.batch_capture.side_effect = ConnectionError("fail")
            with patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}):
                # Must not raise
                gw._maybe_sync_telemetry(artifact_root)

    def test_sync_network_probe_failure(self, tmp_path):
        """When network probe fails, .last_sync_attempt is updated and sync exits early."""
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=[json.dumps({"event": "x"}) + "\n"],
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        import socket as socket_mod
        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection", side_effect=socket_mod.error("unreachable")):
            gw._maybe_sync_telemetry(artifact_root)

        # Should have updated last_sync_attempt
        attempt_val = float((artifact_root / ".last_sync_attempt").read_text(encoding="utf-8").strip())
        assert attempt_val > time.time() - 10
        # sync_status.json should reflect failure
        sync_status = json.loads((artifact_root / ".sync_status.json").read_text(encoding="utf-8"))
        assert sync_status["failure_count"] >= 1

    def test_sync_batch_capture_success_compacts_metrics(self, tmp_path):
        """When batch_capture succeeds, metrics.jsonl is compacted and offset reset."""
        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            json.dumps({"event": "ev2"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            mock_tel_module = MagicMock()
            mock_tel_module.telemetry = mock_telemetry
            with patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}):
                gw._maybe_sync_telemetry(artifact_root)

        # After success: offset reset to 0, metrics compacted (empty or fewer lines)
        offset_val = (artifact_root / ".offset").read_text(encoding="utf-8").strip()
        assert offset_val == "0"
        # sync_status should reflect success
        sync_status = json.loads((artifact_root / ".sync_status.json").read_text(encoding="utf-8"))
        assert sync_status["failure_count"] == 0
        assert sync_status["pending_count"] == 0


# ===========================================================================
# VAL-GW-004: Health report read/parse/inject
# ===========================================================================

class TestHealthReportInjection:
    """Tests for health report reading, parsing, and injection into context package."""

    def _build_main_mocks(self, tmp_path: Path, *, event: str = "session-start"):
        """Build common mocks for gateway main() invocations."""
        pkg = {
            "status": "ok",
            "missing_paths": [],
            "validation_errors": [],
            "host": "factory",
            "event": event,
            "package_kind": "context-package-v1",
        }
        return pkg

    def test_health_report_degraded_injected(self, tmp_path):
        """When health-report.json exists with degraded status, it is injected into package."""
        # Create the project structure with health-report.json
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_system = project_dir / "memory" / "system"
        memory_system.mkdir(parents=True)

        health_report = {
            "status": "degraded",
            "validation_errors": ["error1", "error2", "error3"],
        }
        (memory_system / "health-report.json").write_text(
            json.dumps(health_report), encoding="utf-8"
        )

        captured_packages = []

        def capture_build(*args, **kwargs):
            pkg = {
                "status": "ok",
                "missing_paths": [],
                "validation_errors": [],
                "host": "factory",
                "event": "session-start",
                "package_kind": "context-package-v1",
            }
            captured_packages.append(pkg)
            return pkg

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}
        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = capture_build
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            # Patch _discover_cwd to return our project_dir
            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                from memory_core.tools import memory_hook_metrics
                with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                    gw.main()

            # Check that the captured package has the health alert injected
            assert len(captured_packages) == 1
            pkg = captured_packages[0]
            assert "system_context" in pkg
            assert "previous_health_alert" in pkg["system_context"]
            alert = pkg["system_context"]["previous_health_alert"]
            assert alert["status"] == "degraded"
            assert alert["errors"] == ["error1", "error2", "error3"]
        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)

    def test_health_report_non_degraded_not_injected(self, tmp_path):
        """When health-report.json exists but status is not degraded, no injection occurs."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_system = project_dir / "memory" / "system"
        memory_system.mkdir(parents=True)

        health_report = {"status": "healthy", "validation_errors": []}
        (memory_system / "health-report.json").write_text(
            json.dumps(health_report), encoding="utf-8"
        )

        captured_packages = []

        def capture_build(*args, **kwargs):
            pkg = {
                "status": "ok",
                "missing_paths": [],
                "validation_errors": [],
                "host": "factory",
                "event": "session-start",
                "package_kind": "context-package-v1",
            }
            captured_packages.append(pkg)
            return pkg

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}
        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = capture_build
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                from memory_core.tools import memory_hook_metrics
                with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                    gw.main()

            pkg = captured_packages[0]
            # No health alert should be injected for non-degraded status
            assert "system_context" not in pkg or "previous_health_alert" not in pkg.get("system_context", {})
        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)

    def test_health_report_missing_no_injection(self, tmp_path):
        """When health-report.json does not exist, no health alert is injected."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        captured_packages = []

        def capture_build(*args, **kwargs):
            pkg = {
                "status": "ok",
                "missing_paths": [],
                "validation_errors": [],
                "host": "factory",
                "event": "session-start",
                "package_kind": "context-package-v1",
            }
            captured_packages.append(pkg)
            return pkg

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}
        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = capture_build
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                from memory_core.tools import memory_hook_metrics
                with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                    gw.main()

            pkg = captured_packages[0]
            assert "system_context" not in pkg or "previous_health_alert" not in pkg.get("system_context", {})
        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)

    def test_health_report_malformed_json_handled(self, tmp_path):
        """When health-report.json contains malformed JSON, it is handled gracefully."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_system = project_dir / "memory" / "system"
        memory_system.mkdir(parents=True)

        # Write malformed JSON
        (memory_system / "health-report.json").write_text(
            "{invalid json content", encoding="utf-8"
        )

        captured_packages = []

        def capture_build(*args, **kwargs):
            pkg = {
                "status": "ok",
                "missing_paths": [],
                "validation_errors": [],
                "host": "factory",
                "event": "session-start",
                "package_kind": "context-package-v1",
            }
            captured_packages.append(pkg)
            return pkg

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}
        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = capture_build
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                from memory_core.tools import memory_hook_metrics
                with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                    # Should not raise - except block handles malformed JSON
                    gw.main()

            pkg = captured_packages[0]
            assert "system_context" not in pkg or "previous_health_alert" not in pkg.get("system_context", {})
        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)

    def test_health_report_errors_limited_to_top5(self, tmp_path):
        """When health report has more than 5 validation_errors, only top 5 are injected."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_system = project_dir / "memory" / "system"
        memory_system.mkdir(parents=True)

        health_report = {
            "status": "degraded",
            "validation_errors": [f"error_{i}" for i in range(10)],
        }
        (memory_system / "health-report.json").write_text(
            json.dumps(health_report), encoding="utf-8"
        )

        captured_packages = []

        def capture_build(*args, **kwargs):
            pkg = {
                "status": "ok",
                "missing_paths": [],
                "validation_errors": [],
                "host": "factory",
                "event": "session-start",
                "package_kind": "context-package-v1",
            }
            captured_packages.append(pkg)
            return pkg

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}
        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = capture_build
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                from memory_core.tools import memory_hook_metrics
                with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                    gw.main()

            pkg = captured_packages[0]
            alert = pkg["system_context"]["previous_health_alert"]
            assert len(alert["errors"]) == 5
            assert alert["errors"] == ["error_0", "error_1", "error_2", "error_3", "error_4"]
        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)


# ===========================================================================
# VAL-GW-005: IF-5 facade factory methods
# ===========================================================================

class TestIF5FacadeFactoryMethods:
    """Tests for IF-5 facade factory methods and adapter functions."""

    def test_get_artifact_sink(self):
        """_get_artifact_sink returns an ArtifactSinkImpl instance."""
        sink = gw._get_artifact_sink()
        assert sink is not None
        assert hasattr(sink, "write")

    def test_get_error_sink(self):
        """_get_error_sink returns an ErrorSinkImpl instance."""
        sink = gw._get_error_sink()
        assert sink is not None
        assert hasattr(sink, "log")

    def test_get_host_delegate(self):
        """_get_host_delegate returns a delegate for known hosts."""
        delegate = gw._get_host_delegate("factory")
        assert delegate is not None

    def test_write_artifacts_via_sink(self):
        """_write_artifacts_via_sink delegates to artifact sink's write method."""
        mock_sink = MagicMock()
        mock_sink.write.return_value = {"contexts": "path1"}

        with patch.object(gw, "_get_artifact_sink", return_value=mock_sink):
            result = gw._write_artifacts_via_sink({"test": "package"})

        mock_sink.write.assert_called_once_with({"test": "package"})
        assert result == {"contexts": "path1"}

    def test_append_error_log_via_sink(self):
        """_append_error_log_via_sink delegates to error sink's log method."""
        mock_sink = MagicMock()

        with patch.object(gw, "_get_error_sink", return_value=mock_sink):
            gw._append_error_log_via_sink("test-component", "test message", {"key": "val"})

        mock_sink.log.assert_called_once_with("test-component", "test message", {"key": "val"})

    def test_resolve_route_target_via_policy(self):
        """_resolve_route_target_via_policy delegates to route policy's resolve method."""
        mock_policy = MagicMock()
        mock_policy.resolve.return_value = "target_path"

        with patch.object(gw, "_get_route_policy", return_value=mock_policy):
            result = gw._resolve_route_target_via_policy("test_kind")

        mock_policy.resolve.assert_called_once_with("test_kind")
        assert result == "target_path"

    def test_write_targets_via_policy(self):
        """_write_targets_via_policy delegates to write policy's get_targets method."""
        mock_policy = MagicMock()
        mock_policy.get_targets.return_value = {"target_a": "/path/a"}

        with patch.object(gw, "_get_write_policy", return_value=mock_policy):
            result = gw._write_targets_via_policy()

        mock_policy.get_targets.assert_called_once()
        assert "target_a" in result

    def test_get_policy_pack_via_registry(self):
        """_get_policy_pack_via_registry delegates to policy registry."""
        mock_registry = MagicMock()
        mock_registry.get_policy_pack.return_value = {"rule1": "value1"}

        with patch.object(gw, "_get_policy_registry", return_value=mock_registry):
            result = gw._get_policy_pack_via_registry("test_scope")

        mock_registry.get_policy_pack.assert_called_once_with("test_scope")
        assert result == {"rule1": "value1"}

    def test_resolve_policy_conflict_via_registry(self):
        """_resolve_policy_conflict_via_registry delegates to policy registry."""
        mock_registry = MagicMock()
        mock_registry.resolve_conflict.return_value = "resolved_value"

        with patch.object(gw, "_get_policy_registry", return_value=mock_registry):
            result = gw._resolve_policy_conflict_via_registry(
                "policy_key", ["val1", "val2"], "merge"
            )

        mock_registry.resolve_conflict.assert_called_once_with("policy_key", ["val1", "val2"], "merge")
        assert result == "resolved_value"

    def test_resolve_policy_conflict_default_strategy(self):
        """_resolve_policy_conflict_via_registry uses 'default' strategy when None."""
        mock_registry = MagicMock()
        mock_registry.resolve_conflict.return_value = "resolved"

        with patch.object(gw, "_get_policy_registry", return_value=mock_registry):
            gw._resolve_policy_conflict_via_registry(
                "key", ["a", "b"], None
            )

        mock_registry.resolve_conflict.assert_called_once_with("key", ["a", "b"], "default")

    def test_apply_hook_runtime_write_targets_with_env(self):
        """_apply_hook_runtime_write_targets adds hook_lifecycle when env var set."""
        targets = {"existing": "value"}
        with patch.dict(os.environ, {"MEMORY_HOOK_GLOBAL_STATE_ROOT": "/tmp/test_global"}):
            result = gw._apply_hook_runtime_write_targets(targets)

        assert "hook_lifecycle" in result
        assert "hook_global_state_root" in result
        assert result["existing"] == "value"

    def test_apply_hook_runtime_write_targets_without_env(self):
        """_apply_hook_runtime_write_targets returns unchanged targets without env var."""
        targets = {"existing": "value"}
        env = {k: v for k, v in os.environ.items() if k != "MEMORY_HOOK_GLOBAL_STATE_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = gw._apply_hook_runtime_write_targets(targets)

        assert result == {"existing": "value"}
        assert "hook_lifecycle" not in result


# ===========================================================================
# VAL-GW-003 (additional): Sync failure handling paths
# ===========================================================================

class TestSyncFailureHandling:
    """Additional tests for sync failure paths."""

    def test_sync_status_written_on_failure(self, tmp_path):
        """_write_sync_status correctly increments failure_count on failure."""
        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()

        gw._write_sync_status(artifact_root, success=False, pending_count=5)

        status = json.loads((artifact_root / ".sync_status.json").read_text(encoding="utf-8"))
        assert status["failure_count"] == 1
        assert status["pending_count"] == 5
        assert "last_failure_ts" in status

    def test_sync_status_written_on_success(self, tmp_path):
        """_write_sync_status correctly resets failure_count on success."""
        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()

        # First write a failure
        gw._write_sync_status(artifact_root, success=False, pending_count=3)
        # Then write success
        gw._write_sync_status(artifact_root, success=True, pending_count=0)

        status = json.loads((artifact_root / ".sync_status.json").read_text(encoding="utf-8"))
        assert status["failure_count"] == 0
        assert status["pending_count"] == 0
        assert "last_success_ts" in status

    def test_sync_status_accumulates_failures(self, tmp_path):
        """_write_sync_status accumulates failure_count across multiple failures."""
        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()

        gw._write_sync_status(artifact_root, success=False, pending_count=1)
        gw._write_sync_status(artifact_root, success=False, pending_count=2)
        gw._write_sync_status(artifact_root, success=False, pending_count=3)

        status = json.loads((artifact_root / ".sync_status.json").read_text(encoding="utf-8"))
        assert status["failure_count"] == 3
        assert status["pending_count"] == 3

    def test_maybe_sync_skips_within_success_window(self, tmp_path):
        """_maybe_sync_telemetry skips when last sync success is within 1 hour."""
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=[json.dumps({"event": "x"}) + "\n"],
            last_sync_success=time.time() - 1800,  # 30 minutes ago
        )

        # Should return early without attempting network probe
        with patch("socket.create_connection") as mock_conn:
            gw._maybe_sync_telemetry(artifact_root)
            mock_conn.assert_not_called()

    def test_maybe_sync_skips_within_backoff_window(self, tmp_path):
        """_maybe_sync_telemetry skips when last sync attempt is within 5 minutes."""
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=[json.dumps({"event": "x"}) + "\n"],
            last_sync_success=time.time() - 7200,  # 2 hours ago
            last_sync_attempt=time.time() - 60,    # 1 minute ago
        )

        with patch("socket.create_connection") as mock_conn:
            gw._maybe_sync_telemetry(artifact_root)
            mock_conn.assert_not_called()

    def test_batch_capture_exception_with_osterror_on_write(self, tmp_path):
        """When batch_capture raises and last_sync_attempt write fails with OSError."""
        metrics_lines = [json.dumps({"event": "test"}) + "\n"]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.side_effect = RuntimeError("network error")

        # Mock last_sync_attempt_file.write_text to raise OSError
        attempt_file = artifact_root / ".last_sync_attempt"
        original_write = attempt_file.write_text

        def raise_osterror(*args, **kwargs):
            raise OSError("disk full")

        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            mock_tel_module = MagicMock()
            mock_tel_module.telemetry = mock_telemetry
            with patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}):
                # Patch Path.write_text to raise OSError for attempt file
                with patch.object(Path, "write_text") as mock_write:
                    def side_effect(self_path, *args, **kwargs):
                        if ".last_sync_attempt" in str(self_path):
                            raise OSError("disk full")
                        return original_write(*args, **kwargs)
                    mock_write.side_effect = side_effect

                    # Should not raise - OSError is caught
                    gw._maybe_sync_telemetry(artifact_root)

    def test_top_level_exception_in_sync(self, tmp_path):
        """Top-level exception handler catches exceptions outside inner try block."""
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        # Create metrics file but make offset_file.read_text raise an exception
        metrics_file = artifact_root / "metrics.jsonl"
        metrics_file.write_text(json.dumps({"event": "x"}) + "\n", encoding="utf-8")

        offset_file = artifact_root / ".offset"
        original_read = offset_file.read_text

        with patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}), \
             patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            # Make offset read fail to trigger top-level exception
            with patch.object(Path, "read_text") as mock_read:
                def side_effect(self_path, *args, **kwargs):
                    if ".offset" in str(self_path):
                        raise RuntimeError("file corrupted")
                    return original_read(*args, **kwargs)
                mock_read.side_effect = side_effect

                # Should not raise - top-level exception is caught
                gw._maybe_sync_telemetry(artifact_root)


# ===========================================================================
# VAL-GW-003 (additional): PreToolUse guard in main()
# ===========================================================================

class TestPreToolUseGuard:
    """Tests for PreToolUse guard interception in main() (lines 1926-1949)."""

    def test_pretooluse_guard_executes_successfully(self, tmp_path):
        """When pre-tool-use event occurs and guard script exists, it is executed."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        captured_stdout = []

        def capture_stdout(*args, **kwargs):
            captured_stdout.append(args)
            return None

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}

        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "pre-tool-use", "--no-delegate"]
            sys.stdout = MagicMock()
            sys.stdout.write = capture_stdout

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = lambda *a, **kw: {"status": "ok"}
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                # Mock subprocess.run to simulate successful guard execution
                mock_proc = MagicMock()
                mock_proc.stdout = json.dumps({"decision": "block"})
                mock_proc.stderr = ""
                mock_proc.returncode = 0

                with patch("subprocess.run", return_value=mock_proc):
                    from memory_core.tools import memory_hook_metrics
                    with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                        result = gw.main()

                assert result == 0

        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)

    def test_pretooluse_guard_timeout(self, tmp_path):
        """When pre-tool-use guard times out, error is logged and fallback allows."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        captured_errors = []

        def mock_append_error(component, message, context=None):
            captured_errors.append({"component": component, "message": message})

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}

        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "pre-tool-use", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = lambda *a, **kw: {"status": "ok"}
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            import subprocess as subprocess_module
            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                with patch("subprocess.run", side_effect=subprocess_module.TimeoutExpired("cmd", 5)):
                    with patch.object(gw, "append_error_log", mock_append_error):
                        from memory_core.tools import memory_hook_metrics
                        with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                            result = gw.main()

                # Should fall back to allow decision
                assert result == 0
                # Should have logged timeout error
                assert len(captured_errors) > 0
                assert "pretooluse-guard" in captured_errors[0]["component"]

        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)

    def test_pretooluse_guard_exception(self, tmp_path):
        """When pre-tool-use guard raises exception, error is logged and fallback allows."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        captured_errors = []

        def mock_append_error(component, message, context=None):
            captured_errors.append({"component": component, "message": message})

        original_stdin = sys.stdin
        original_argv = sys.argv
        original_stdout = sys.stdout
        orig_attrs = {}

        try:
            sys.stdin = MagicMock()
            sys.stdin.read.return_value = "{}"
            sys.argv = ["gw", "--host", "factory", "--event", "pre-tool-use", "--no-delegate"]
            sys.stdout = MagicMock()

            for attr in ["is_memory_core_source_repo", "get_source_repo_mode",
                         "is_denied_project_root", "_should_noop_for_external_context",
                         "build_context_package", "write_artifacts",
                         "_integrity_verify", "_integrity_sign", "_execute_delegate",
                         "_launch_async_health_check", "_update_state_dynamic_fields",
                         "_maybe_sync_telemetry", "_log_prompt_submit"]:
                orig_attrs[attr] = getattr(gw, attr)

            gw.is_memory_core_source_repo = lambda cwd: False
            gw.get_source_repo_mode = lambda cwd: None
            gw.is_denied_project_root = lambda cwd: False
            gw._should_noop_for_external_context = lambda payload: False
            gw.build_context_package = lambda *a, **kw: {"status": "ok"}
            gw.write_artifacts = lambda package: {"snapshot": "x"}
            gw._integrity_verify = lambda cwd: None
            gw._integrity_sign = lambda cwd: None
            gw._execute_delegate = lambda *a, **kw: 0
            gw._launch_async_health_check = lambda cwd: None
            gw._update_state_dynamic_fields = lambda *a, **kw: None
            gw._maybe_sync_telemetry = lambda *a, **kw: None
            gw._log_prompt_submit = lambda *a, **kw: None

            with patch.object(gw, "_discover_cwd", return_value=project_dir):
                with patch("subprocess.run", side_effect=RuntimeError("guard failed")):
                    with patch.object(gw, "append_error_log", mock_append_error):
                        from memory_core.tools import memory_hook_metrics
                        with patch.object(memory_hook_metrics, "emit_metrics", lambda *a, **kw: None):
                            result = gw.main()

                # Should fall back to allow decision
                assert result == 0
                # Should have logged exception error
                assert len(captured_errors) > 0
                assert "pretooluse-guard" in captured_errors[0]["component"]

        finally:
            sys.stdin = original_stdin
            sys.argv = original_argv
            sys.stdout = original_stdout
            for attr, val in orig_attrs.items():
                setattr(gw, attr, val)
