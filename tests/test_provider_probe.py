"""Tests for memory_hook_provider_probe module."""


import json
from unittest.mock import MagicMock, patch

import pytest  # noqa: F401


class TestProbeProviderAvailability:
    """Tests for probe_provider_availability function."""

    def test_probe_provider_availability_returns_dict_structure(self):
        """Test that probe_provider_availability returns expected dict structure."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        result = probe_provider_availability()

        assert isinstance(result, dict)
        assert "status" in result
        assert "requested_provider" in result
        assert "external_probe_provider" in result
        assert "external_probe_errors" in result
        assert "external_probe_ok" in result
        assert "legacy_probe_provider" in result
        assert "legacy_probe_errors" in result
        assert "legacy_probe_ok" in result
        assert "rollback_target" in result

    def test_probe_provider_availability_status_passed_when_legacy_ok(self):
        """Test that status is 'passed' when legacy provider is available."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                ("external-core", MagicMock(), ["some error"]),  # external fails
                ("legacy", MagicMock(), []),  # legacy succeeds
            ]

            result = probe_provider_availability()

            assert result["status"] == "passed"
            assert result["legacy_probe_ok"] is True
            assert result["external_probe_ok"] is False

    def test_probe_provider_availability_status_failed_when_legacy_fails(self):
        """Test that status is 'failed' when legacy provider fails."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                ("external-core", MagicMock(), ["external error"]),
                ("legacy", MagicMock(), ["legacy error"]),
            ]

            result = probe_provider_availability()

            assert result["status"] == "failed"
            assert result["legacy_probe_ok"] is False
            assert result["legacy_probe_errors"] == ["legacy error"]

    def test_probe_provider_availability_external_probe_success(self):
        """Test external probe success scenario."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                ("external-core", MagicMock(), []),  # external succeeds
                ("legacy", MagicMock(), []),  # legacy succeeds
            ]

            result = probe_provider_availability()

            assert result["external_probe_ok"] is True
            assert result["external_probe_errors"] == []

    def test_probe_provider_availability_external_probe_failure(self):
        """Test external probe failure with exception."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                Exception("external provider crashed"),  # external raises exception
                ("legacy", MagicMock(), []),  # legacy succeeds
            ]

            result = probe_provider_availability()

            assert result["external_probe_ok"] is False
            assert "external provider crashed" in result["external_probe_errors"][0]

    def test_probe_provider_availability_legacy_probe_failure_with_exception(self):
        """Test legacy probe failure with exception."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                ("external-core", MagicMock(), ["external error"]),
                Exception("legacy provider crashed"),  # legacy raises exception
            ]

            result = probe_provider_availability()

            assert result["legacy_probe_ok"] is False
            assert result["status"] == "failed"
            assert "legacy provider crashed" in result["legacy_probe_errors"][0]

    def test_probe_provider_availability_uses_env_requested_provider(self, monkeypatch):
        """Test that requested_provider is read from environment."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        monkeypatch.setenv("MEMORY_HOOK_CORE_PROVIDER", "external-core")

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                ("external-core", MagicMock(), []),
                ("legacy", MagicMock(), []),
            ]

            result = probe_provider_availability()

            assert result["requested_provider"] == "external-core"

    def test_probe_provider_availability_default_requested_provider(self, monkeypatch):
        """Test that default requested_provider is 'legacy' when env not set."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        monkeypatch.delenv("MEMORY_HOOK_CORE_PROVIDER", raising=False)

        with patch(
            "memory_core.tools.memory_hook_provider_probe.gateway._resolve_core_builder"
        ) as mock_resolve:
            mock_resolve.side_effect = [
                ("external-core", MagicMock(), []),
                ("legacy", MagicMock(), []),
            ]

            result = probe_provider_availability()

            assert result["requested_provider"] == "legacy"

    def test_probe_provider_availability_rollback_target_is_legacy(self):
        """Test that rollback_target is always 'legacy'."""
        from memory_core.tools.memory_hook_provider_probe import probe_provider_availability

        result = probe_provider_availability()

        assert result["rollback_target"] == "legacy"


class TestRunRollbackDrill:
    """Tests for run_rollback_drill alias."""

    def test_run_rollback_drill_is_alias(self):
        """Test that run_rollback_drill is an alias for probe_provider_availability."""
        from memory_core.tools.memory_hook_provider_probe import (
            probe_provider_availability,
            run_rollback_drill,
        )

        assert run_rollback_drill is probe_provider_availability


class TestMain:
    """Tests for main function."""

    def test_main_returns_0_when_passed(self):
        """Test main returns 0 when probe status is passed."""
        from memory_core.tools.memory_hook_provider_probe import main

        with patch(
            "memory_core.tools.memory_hook_provider_probe.probe_provider_availability"
        ) as mock_probe:
            mock_probe.return_value = {"status": "passed"}

            result = main()

            assert result == 0

    def test_main_returns_1_when_failed(self):
        """Test main returns 1 when probe status is failed."""
        from memory_core.tools.memory_hook_provider_probe import main

        with patch(
            "memory_core.tools.memory_hook_provider_probe.probe_provider_availability"
        ) as mock_probe:
            mock_probe.return_value = {"status": "failed"}

            result = main()

            assert result == 1

    def test_main_prints_json_output(self, capsys):
        """Test main prints JSON output."""
        from memory_core.tools.memory_hook_provider_probe import main

        with patch(
            "memory_core.tools.memory_hook_provider_probe.probe_provider_availability"
        ) as mock_probe:
            mock_probe.return_value = {
                "status": "passed",
                "requested_provider": "legacy",
            }

            main()

            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert output["status"] == "passed"
            assert output["requested_provider"] == "legacy"


class TestModuleExecution:
    """Tests for module execution as script."""

    def test_module_has_main_entry_point(self):
        """Test that module has __main__ entry point."""
        import memory_core.tools.memory_hook_provider_probe as module

        assert hasattr(module, "main")

    def test_module_exposes_probe_provider_availability(self):
        """Test that module exposes probe_provider_availability function."""
        import memory_core.tools.memory_hook_provider_probe as module

        assert hasattr(module, "probe_provider_availability")
        assert callable(module.probe_provider_availability)
