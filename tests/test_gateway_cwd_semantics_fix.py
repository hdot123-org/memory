"""Tests for gateway cwd semantics fix (M1-3, VAL-GTW-001~005).

When PREFER_EXTERNAL_CWD=1 and the session is in a non-git outer directory
with a probe-routed inner repo, memory-root semantic operations (integrity
sign/verify, health-check, version-sync) must use REPO_ROOT (the project root
after probe routing) instead of cwd (which may be the outer non-git directory).

This prevents:
- split-brain resurrection: mkdir on outer memory/system/
- missing_manifest blocked: integrity verify on outer (no manifest) → blocked
- health-report written to outer instead of inner
- version probe running against non-git directory
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def gw_handlers():
    """Import _gateway_handlers module."""
    from memory_core.tools import _gateway_handlers as mod

    return mod


@pytest.fixture()
def gw_dispatch():
    """Import _gateway_dispatch module."""
    from memory_core.tools import _gateway_dispatch as mod

    return mod


@pytest.fixture()
def gw_config():
    """Import _gateway_config module."""
    from memory_core.tools import _gateway_config as mod

    return mod


@pytest.fixture()
def gw_artifacts():
    """Import _gateway_artifacts module."""
    from memory_core.tools import _gateway_artifacts as mod

    return mod


# ---------------------------------------------------------------------------
# VAL-GTW-001: Integrity sign writes to REPO_ROOT, not cwd
# ---------------------------------------------------------------------------


class TestIntegritySignUsesRepoRoot:
    """VAL-GTW-001: _integrity_sign must use REPO_ROOT, not cwd."""

    def test_integrity_sign_in_write_artifacts_uses_repo_root(self, gw_handlers, gw_config, monkeypatch, tmp_path):
        """_write_artifacts_and_emit_metrics passes REPO_ROOT to _integrity_sign,
        not the potentially-outer cwd."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        # Mock REPO_ROOT to point to inner
        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)

        sign_calls = []

        def tracking_sign(project_root):
            sign_calls.append(Path(project_root))
            # Don't actually sign

        # Mock _integrity_sign at _gateway_config level (where it's imported from)
        monkeypatch.setattr(gw_config, "_integrity_sign", tracking_sign)
        monkeypatch.setattr(gw_handlers, "ARTIFACT_ROOT", tmp_path / "artifacts")

        mock_writer = MagicMock()
        mock_writer.write.return_value = True

        args = MagicMock()
        args.host = "factory"
        args.event = "session-start"

        package = {"status": "ok", "missing_paths": [], "validation_errors": []}

        gw_handlers._write_artifacts_and_emit_metrics(args, mock_writer, package, outer_cwd, 0.0)

        # The sign should be called with REPO_ROOT (inner), not outer_cwd
        assert len(sign_calls) == 1
        assert sign_calls[0] == inner_root, f"Expected sign to use REPO_ROOT ({inner_root}), but got {sign_calls[0]}"


# ---------------------------------------------------------------------------
# VAL-GTW-002: Integrity verify uses REPO_ROOT, not cwd
# ---------------------------------------------------------------------------


class TestIntegrityVerifyUsesRepoRoot:
    """VAL-GTW-002: _integrity_verify must use REPO_ROOT, not cwd."""

    def test_integrity_check_uses_repo_root(self, gw_handlers, gw_config, monkeypatch, tmp_path):
        """_handle_integrity_check passes REPO_ROOT to _integrity_verify,
        not the potentially-outer cwd."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)

        verify_calls = []

        def tracking_verify(project_root):
            verify_calls.append(Path(project_root))
            return {"ok": True}  # Pretend verify passed

        monkeypatch.setattr(gw_handlers, "_integrity_verify", tracking_verify)

        package = {"status": "ok", "missing_paths": [], "validation_errors": []}
        gw_handlers._handle_integrity_check(outer_cwd, package, "factory", "session-start")

        assert len(verify_calls) == 1
        assert verify_calls[0] == inner_root, (
            f"Expected verify to use REPO_ROOT ({inner_root}), but got {verify_calls[0]}"
        )


# ---------------------------------------------------------------------------
# VAL-GTW-003: Session-start not blocked when REPO_ROOT has manifest
# ---------------------------------------------------------------------------


class TestSessionStartNotBlocked:
    """VAL-GTW-003: Integrity check should not set status=blocked when
    REPO_ROOT has a valid manifest, even if outer cwd has none."""

    def test_session_start_not_blocked_with_valid_inner_manifest(self, gw_handlers, gw_config, monkeypatch, tmp_path):
        """When REPO_ROOT (inner) has valid manifest but outer cwd doesn't,
        session-start should not be blocked."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)

        def tracking_verify(project_root):
            # Verify is called with REPO_ROOT (inner) → returns ok
            return {"ok": True}

        monkeypatch.setattr(gw_handlers, "_integrity_verify", tracking_verify)

        package = {"status": "ok", "missing_paths": [], "validation_errors": []}
        gw_handlers._handle_integrity_check(outer_cwd, package, "factory", "session-start")

        # Status should remain "ok", not become "blocked"
        assert package["status"] == "ok", f"Session status should be 'ok' but got '{package['status']}'"


# ---------------------------------------------------------------------------
# VAL-GTW-004: Health check launched with REPO_ROOT, not cwd
# ---------------------------------------------------------------------------


class TestHealthCheckUsesRepoRoot:
    """VAL-GTW-004: _launch_async_health_check must use REPO_ROOT, not cwd."""

    def test_session_start_setup_launches_health_check_with_repo_root(
        self, gw_handlers, gw_config, monkeypatch, tmp_path
    ):
        """_handle_session_start_setup must pass REPO_ROOT to health check,
        not the potentially-outer cwd."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)

        health_calls = []

        def tracking_health(project_root):
            health_calls.append(Path(project_root))

        monkeypatch.setattr(gw_handlers, "_launch_async_health_check", tracking_health)
        monkeypatch.setattr(gw_handlers, "_update_state_dynamic_fields", lambda *a: None)
        monkeypatch.setattr(gw_handlers, "_maybe_sync_telemetry", lambda *a: None)

        # Mock version_sync import to avoid real infra_core
        mock_version_sync = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "infra_core": MagicMock(),
                "infra_core.engine": MagicMock(),
                "infra_core.engine.version_sync": mock_version_sync,
            },
        ):
            gw_handlers._handle_session_start_setup(outer_cwd)

        assert len(health_calls) == 1
        assert health_calls[0] == inner_root, (
            f"Expected health check to use REPO_ROOT ({inner_root}), but got {health_calls[0]}"
        )


# ---------------------------------------------------------------------------
# VAL-GTW-005: Version probe uses REPO_ROOT, not cwd
# ---------------------------------------------------------------------------


class TestVersionProbeUsesRepoRoot:
    """VAL-GTW-005: probe_version_and_sync must use REPO_ROOT, not cwd."""

    def test_version_probe_uses_repo_root(self, gw_handlers, gw_config, monkeypatch, tmp_path):
        """_handle_session_start_setup must pass REPO_ROOT to version probe,
        not the potentially-outer cwd."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)

        version_calls = []
        mock_version_sync = MagicMock()

        def tracking_probe(project_root, current_version):
            version_calls.append(Path(project_root))

        mock_version_sync.probe_version_and_sync = tracking_probe
        mock_version_sync.set_resign_hook = MagicMock()

        monkeypatch.setattr(gw_handlers, "_launch_async_health_check", lambda *a: None)
        monkeypatch.setattr(gw_handlers, "_update_state_dynamic_fields", lambda *a: None)
        monkeypatch.setattr(gw_handlers, "_maybe_sync_telemetry", lambda *a: None)

        with patch.dict(
            sys.modules,
            {
                "infra_core": MagicMock(),
                "infra_core.engine": MagicMock(),
                "infra_core.engine.version_sync": mock_version_sync,
            },
        ):
            gw_handlers._handle_session_start_setup(outer_cwd)

        assert len(version_calls) == 1
        assert version_calls[0] == inner_root, (
            f"Expected version probe to use REPO_ROOT ({inner_root}), but got {version_calls[0]}"
        )


# ---------------------------------------------------------------------------
# Integration: outer directory must not have memory/ created
# ---------------------------------------------------------------------------


class TestOuterDirectoryNotPolluted:
    """Integration test: when cwd is outer non-git directory and
    REPO_ROOT is inner, memory operations must not create memory/ in outer."""

    def test_integrity_sign_does_not_create_memory_in_outer(self, gw_config, monkeypatch, tmp_path):
        """Calling _integrity_sign with REPO_ROOT should not create
        memory/system/ in the outer directory."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        (inner_root / "memory" / "system").mkdir(parents=True)
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        # Take a snapshot of outer before
        outer_before = set()
        for p in outer_cwd.rglob("*"):
            outer_before.add(p.relative_to(outer_cwd))

        # Call _integrity_sign with inner (REPO_ROOT)
        gw_config._integrity_sign(inner_root)

        # Take a snapshot of outer after
        outer_after = set()
        for p in outer_cwd.rglob("*"):
            outer_after.add(p.relative_to(outer_cwd))

        # No new files/dirs in outer
        new_items = outer_after - outer_before
        assert not new_items, (
            f"Outer directory should not be modified by integrity sign, but found new items: {new_items}"
        )


# ---------------------------------------------------------------------------
# _inject_health_alert uses REPO_ROOT
# ---------------------------------------------------------------------------


class TestInjectHealthAlertUsesRepoRoot:
    """_inject_health_alert must read from REPO_ROOT, not cwd."""

    def test_inject_health_alert_reads_from_repo_root(self, gw_handlers, gw_config, monkeypatch, tmp_path):
        """_inject_health_alert reads health-report.json from REPO_ROOT,
        not from the potentially-outer cwd."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        # Put a degraded health report in inner
        (inner_root / "memory" / "system").mkdir(parents=True)
        health_report = inner_root / "memory" / "system" / "health-report.json"
        health_report.write_text(
            json.dumps(
                {
                    "status": "degraded",
                    "validation_errors": ["test_error_1"],
                }
            )
        )

        # Patch REPO_ROOT in both modules
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)

        package: dict = {}
        gw_handlers._inject_health_alert(outer_cwd, package)

        # Should have read from inner (REPO_ROOT) and injected alert
        assert "system_context" in package
        assert package["system_context"]["previous_health_alert"]["status"] == "degraded"


# ---------------------------------------------------------------------------
# _handle_session_start_setup: _update_state_dynamic_fields uses REPO_ROOT
# ---------------------------------------------------------------------------


class TestUpdateStateUsesRepoRoot:
    """_update_state_dynamic_fields must use REPO_ROOT, not cwd."""

    def test_state_update_uses_repo_root(self, gw_handlers, gw_config, monkeypatch, tmp_path):
        """_handle_session_start_setup passes REPO_ROOT to state update,
        not the potentially-outer cwd."""
        inner_root = tmp_path / "inner"
        inner_root.mkdir()
        outer_cwd = tmp_path / "outer"
        outer_cwd.mkdir()

        monkeypatch.setattr(gw_config, "REPO_ROOT", inner_root)
        monkeypatch.setattr(gw_handlers, "REPO_ROOT", inner_root)

        state_calls = []

        def tracking_state(project_root, scope):
            state_calls.append(Path(project_root))

        monkeypatch.setattr(gw_handlers, "_launch_async_health_check", lambda *a: None)
        monkeypatch.setattr(gw_handlers, "_update_state_dynamic_fields", tracking_state)
        monkeypatch.setattr(gw_handlers, "_maybe_sync_telemetry", lambda *a: None)

        mock_version_sync = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "infra_core": MagicMock(),
                "infra_core.engine": MagicMock(),
                "infra_core.engine.version_sync": mock_version_sync,
            },
        ):
            gw_handlers._handle_session_start_setup(outer_cwd)

        assert len(state_calls) == 1
        assert state_calls[0] == inner_root, (
            f"Expected state update to use REPO_ROOT ({inner_root}), but got {state_calls[0]}"
        )
