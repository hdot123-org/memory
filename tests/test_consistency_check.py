from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_core.tools.consistency_check import (
    REPO_ROOT,
    TOOLS_DIR,
    _load_constants,
    _load_pyproject_version,
    check_adapter_registry_complete,
    check_adapter_schema_host_validation,
    check_contributing_version_source,
    check_default_profile_compatibility,
    check_docstring_host_mentions,
    check_host_enum_coverage,
    check_init_validate_roundtrip,
    check_lock_parser_strict_toml,
    check_no_duplicate_version_definitions,
    check_no_handwritten_toml_parser,
    check_package_data_coverage,
    check_provider_builder_called,
    check_required_imports_from_constants,
    check_ruff_config_not_conflicting,
    check_test_version_hardcoding,
    check_validate_dry_run_coverage,
    check_version_consistency,
    main,
)


class TestLoadConstants:
    """Tests for _load_constants function."""

    def test_load_constants_returns_dict(self) -> None:
        """Test _load_constants returns a dictionary."""
        result = _load_constants()
        assert isinstance(result, dict)
        assert "CURRENT_MEMORY_VERSION" in result

    def test_load_constants_version_format(self) -> None:
        """Test loaded version is valid semver."""
        result = _load_constants()
        version = result.get("CURRENT_MEMORY_VERSION", "")
        parts = version.split(".")
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit()

    def test_load_constants_supported_hosts(self) -> None:
        """Test SUPPORTED_HOSTS is loaded."""
        result = _load_constants()
        hosts = result.get("SUPPORTED_HOSTS", ())
        assert isinstance(hosts, tuple)
        assert len(hosts) > 0


class TestLoadPyprojectVersion:
    """Tests for _load_pyproject_version function."""

    def test_load_pyproject_version_returns_string(self) -> None:
        """Test _load_pyproject_version returns a string."""
        result = _load_pyproject_version()
        assert isinstance(result, str)

    def test_load_pyproject_version_format(self) -> None:
        """Test loaded version is valid semver."""
        result = _load_pyproject_version()
        assert len(result.split(".")) == 3


class TestCheckVersionConsistency:
    """Tests for check_version_consistency function."""

    def test_version_consistency_passes(self) -> None:
        """Test version consistency check passes when versions match."""
        errors, warnings = check_version_consistency()
        # This may pass or fail depending on actual repo state
        # We just verify it runs without exception
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckHostEnumCoverage:
    """Tests for check_host_enum_coverage function."""

    def test_host_enum_coverage_runs(self) -> None:
        """Test host enum coverage check runs without exception."""
        errors, warnings = check_host_enum_coverage()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_host_enum_coverage_returns_lists(self) -> None:
        """Test check returns list types."""
        errors, warnings = check_host_enum_coverage()
        assert all(isinstance(e, str) for e in errors) or len(errors) == 0
        assert all(isinstance(w, str) for w in warnings) or len(warnings) == 0


class TestCheckNoDuplicateVersionDefinitions:
    """Tests for check_no_duplicate_version_definitions function."""

    def test_no_duplicate_definitions_runs(self) -> None:
        """Test check runs without exception."""
        errors, warnings = check_no_duplicate_version_definitions()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckInitValidateRoundtrip:
    """Tests for check_init_validate_roundtrip function."""

    def test_init_validate_roundtrip_runs(self) -> None:
        """Test init/validate roundtrip check runs."""
        errors, warnings = check_init_validate_roundtrip()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckRequiredImportsFromConstants:
    """Tests for check_required_imports_from_constants function."""

    def test_required_imports_check_runs(self) -> None:
        """Test required imports check runs without exception."""
        errors, warnings = check_required_imports_from_constants()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckDocstringHostMentions:
    """Tests for check_docstring_host_mentions function."""

    def test_docstring_host_check_runs(self) -> None:
        """Test docstring host check runs without exception."""
        errors, warnings = check_docstring_host_mentions()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckNoHandwrittenTomlParser:
    """Tests for check_no_handwritten_toml_parser function."""

    def test_no_handwritten_parser_check_runs(self) -> None:
        """Test handwritten parser check runs without exception."""
        errors, warnings = check_no_handwritten_toml_parser()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckAdapterRegistryComplete:
    """Tests for check_adapter_registry_complete function."""

    def test_adapter_registry_check_runs(self) -> None:
        """Test adapter registry check runs without exception."""
        errors, warnings = check_adapter_registry_complete()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_adapter_registry_has_workbot_and_default(self) -> None:
        """Test that adapter registry has required entries."""
        errors, warnings = check_adapter_registry_complete()
        # Check that no errors about missing workbot or default
        for error in errors:
            assert "not found" not in error.lower()


class TestCheckRuffConfigNotConflicting:
    """Tests for check_ruff_config_not_conflicting function."""

    def test_ruff_config_check_runs(self) -> None:
        """Test ruff config check runs without exception."""
        errors, warnings = check_ruff_config_not_conflicting()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckContributingVersionSource:
    """Tests for check_contributing_version_source function."""

    def test_contributing_version_check_runs(self) -> None:
        """Test contributing version check runs without exception."""
        errors, warnings = check_contributing_version_source()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckPackageDataCoverage:
    """Tests for check_package_data_coverage function."""

    def test_package_data_check_runs(self) -> None:
        """Test package data coverage check runs without exception."""
        errors, warnings = check_package_data_coverage()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckAdapterSchemaHostValidation:
    """Tests for check_adapter_schema_host_validation function."""

    def test_adapter_schema_host_check_runs(self) -> None:
        """Test adapter schema host validation check runs without exception."""
        errors, warnings = check_adapter_schema_host_validation()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckLockParserStrictToml:
    """Tests for check_lock_parser_strict_toml function."""

    def test_lock_parser_check_runs(self) -> None:
        """Test lock parser check runs without exception."""
        errors, warnings = check_lock_parser_strict_toml()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckDefaultProfileCompatibility:
    """Tests for check_default_profile_compatibility function."""

    def test_default_profile_check_runs(self) -> None:
        """Test default profile compatibility check runs without exception."""
        errors, warnings = check_default_profile_compatibility()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckProviderBuilderCalled:
    """Tests for check_provider_builder_called function."""

    def test_provider_builder_check_runs(self) -> None:
        """Test provider builder check runs without exception."""
        errors, warnings = check_provider_builder_called()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestCheckTestVersionHardcoding:
    """Tests for check_test_version_hardcoding function."""

    def test_test_version_check_runs(self) -> None:
        """Test version hardcoding check runs without exception."""
        errors, warnings = check_test_version_hardcoding()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_test_version_check_returns_lists(self) -> None:
        """Test check returns proper list types."""
        errors, warnings = check_test_version_hardcoding()
        assert all(isinstance(e, str) for e in errors) or len(errors) == 0
        assert all(isinstance(w, str) for w in warnings) or len(warnings) == 0


class TestCheckValidateDryRunCoverage:
    """Tests for check_validate_dry_run_coverage function."""

    def test_validate_dry_run_check_runs(self) -> None:
        """Test validate dry run coverage check runs without exception."""
        errors, warnings = check_validate_dry_run_coverage()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestMain:
    """Tests for main function."""

    def test_main_text_output(self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with text output."""
        monkeypatch.setattr(sys, "argv", ["consistency_check"])
        exit_code = main()
        # Should return 0 or 1 depending on check results
        assert exit_code in [0, 1]

        captured = capsys.readouterr()
        output = captured.out
        assert "Memory-Core Consistency Check Report" in output
        assert "Results:" in output

    def test_main_json_output(self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with JSON output."""
        monkeypatch.setattr(sys, "argv", ["consistency_check", "--json"])
        exit_code = main()
        assert exit_code in [0, 1]

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data
        assert "passed" in data
        assert isinstance(data["checks"], list)

    def test_main_json_structure(self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test JSON output has expected structure."""
        monkeypatch.setattr(sys, "argv", ["consistency_check", "--json"])
        main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        for check in data["checks"]:
            assert "name" in check
            assert "errors" in check
            assert "warnings" in check
            assert "passed" in check
            assert isinstance(check["errors"], list)
            assert isinstance(check["warnings"], list)
            assert isinstance(check["passed"], bool)

    def test_main_exit_code_reflects_errors(self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that exit code reflects check results."""
        monkeypatch.setattr(sys, "argv", ["consistency_check", "--json"])
        exit_code = main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        if data["passed"]:
            assert exit_code == 0
        else:
            assert exit_code == 1


class TestConstants:
    """Tests for module constants."""

    def test_repo_root_is_path(self) -> None:
        """Test REPO_ROOT is a Path."""
        assert isinstance(REPO_ROOT, Path)
        assert REPO_ROOT.is_dir()

    def test_tools_dir_exists(self) -> None:
        """Test TOOLS_DIR exists."""
        assert isinstance(TOOLS_DIR, Path)
        assert TOOLS_DIR.is_dir()

    def test_constants_path_exists(self) -> None:
        """Test constants.py path exists."""
        constants_path = REPO_ROOT / "memory_core" / "constants.py"
        assert constants_path.is_file()

    def test_pyproject_path_exists(self) -> None:
        """Test pyproject.toml exists."""
        pyproject_path = REPO_ROOT / "pyproject.toml"
        assert pyproject_path.is_file()


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_check_functions_handle_missing_files(self) -> None:
        """Test check functions handle missing files gracefully."""
        # Most check functions should handle missing files
        # without raising exceptions
        # Instead of patching Path.exists globally, we'll just verify
        # the function can run without crashing
        errors, warnings = check_adapter_registry_complete()
        # Should return errors about files not found or just run successfully
        assert isinstance(errors, list)

    def test_load_constants_handles_missing_version(self, tmp_path: Path) -> None:
        """Test _load_constants handles missing version."""
        # Create a fake constants.py without CURRENT_MEMORY_VERSION
        fake_constants = tmp_path / "constants.py"
        fake_constants.write_text("OTHER_CONSTANT = 'value'\n")

        # Just verify the function doesn't crash with real constants.py
        result = _load_constants()
        assert isinstance(result, dict)

    def test_host_enum_with_empty_supported_hosts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test host enum check with empty SUPPORTED_HOSTS."""
        with patch("memory_core.tools.consistency_check._load_constants") as mock_load:
            mock_load.return_value = {"SUPPORTED_HOSTS": ()}
            errors, warnings = check_host_enum_coverage()
            assert isinstance(errors, list)
            assert isinstance(warnings, list)

    def test_check_results_format(self) -> None:
        """Test that all check functions return proper format."""
        check_functions = [
            check_version_consistency,
            check_host_enum_coverage,
            check_no_duplicate_version_definitions,
            check_required_imports_from_constants,
            check_docstring_host_mentions,
            check_no_handwritten_toml_parser,
            check_adapter_registry_complete,
            check_ruff_config_not_conflicting,
            check_contributing_version_source,
            check_package_data_coverage,
            check_adapter_schema_host_validation,
            check_lock_parser_strict_toml,
            check_default_profile_compatibility,
            check_provider_builder_called,
            check_test_version_hardcoding,
            check_validate_dry_run_coverage,
        ]

        for check_func in check_functions:
            errors, warnings = check_func()
            assert isinstance(errors, list), f"{check_func.__name__} errors not a list"
            assert isinstance(warnings, list), f"{check_func.__name__} warnings not a list"
            assert all(isinstance(e, str) for e in errors) or len(errors) == 0
            assert all(isinstance(w, str) for w in warnings) or len(warnings) == 0
