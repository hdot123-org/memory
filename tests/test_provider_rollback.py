"""Tests for memory_hook_provider_rollback module."""

import json

from memory_core.tools.memory_hook_provider_rollback import (
    main,
    run_rollback_drill,
)


class TestRunRollbackDrill:
    def test_returns_dict_with_required_keys(self):
        result = run_rollback_drill()
        assert isinstance(result, dict)
        assert "status" in result
        assert "requested_provider" in result
        assert "external_probe_provider" in result
        assert "legacy_probe_provider" in result
        assert "rollback_target" in result

    def test_status_is_passed_or_failed(self):
        result = run_rollback_drill()
        assert result["status"] in ("passed", "failed")

    def test_rollback_target_is_legacy(self):
        result = run_rollback_drill()
        assert result["rollback_target"] == "legacy"

    def test_requested_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("MEMORY_HOOK_CORE_PROVIDER", "external-core")
        result = run_rollback_drill()
        assert result["requested_provider"] == "external-core"

    def test_requested_provider_default(self, monkeypatch):
        monkeypatch.delenv("MEMORY_HOOK_CORE_PROVIDER", raising=False)
        result = run_rollback_drill()
        assert result["requested_provider"] == "legacy"

    def test_passed_when_legacy_probe_ok(self):
        """Legacy provider should always be available, so status is 'passed'."""
        result = run_rollback_drill()
        assert result["status"] == "passed"
        assert result["legacy_probe_ok"] is True


class TestMain:
    def test_returns_zero_on_pass(self, monkeypatch):
        """main() should return 0 when run_rollback_drill passes."""
        # On any environment where legacy provider works, main returns 0
        result = main()
        assert result == 0

    def test_prints_json(self, capsys):
        main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "status" in parsed
        assert "rollback_target" in parsed
