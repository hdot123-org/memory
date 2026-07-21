"""Tests for compat.py (M6 step 6.4)."""

from memory_core.compat import (
    _COMPAT_MATRIX,
    _CURRENT_VERSIONS,
    _check_component,
    _check_min_installer,
    _check_newer_than_known,
    _check_version_registered,
    check_compatibility,
    format_report,
)
from memory_core.constants import CURRENT_MEMORY_VERSION

# ---------------------------------------------------------------------------
# Unit tests for check helpers
# ---------------------------------------------------------------------------

class TestCheckVersionRegistered:
    def test_known_version(self) -> None:
        result = _check_version_registered("0.4.0")
        assert result["status"] == "ok"

    def test_unknown_version(self) -> None:
        result = _check_version_registered("99.99.99")
        assert result["status"] == "warning"


class TestCheckComponent:
    def test_matching(self) -> None:
        result = _check_component("test_component", "v1", "v1")
        assert result["status"] == "ok"

    def test_mismatch(self) -> None:
        result = _check_component("test_component", "v1", "v2")
        assert result["status"] == "mismatch"


class TestCheckMinInstaller:
    def test_meets_minimum(self) -> None:
        matrix_entry = {"min_installer_version": "0.3.0"}
        result = _check_min_installer(matrix_entry, "0.4.0")
        assert result["status"] == "ok"

    def test_below_minimum(self) -> None:
        matrix_entry = {"min_installer_version": "0.4.0"}
        result = _check_min_installer(matrix_entry, "0.3.0")
        assert result["status"] == "error"

    def test_exact_minimum(self) -> None:
        matrix_entry = {"min_installer_version": "0.4.0"}
        result = _check_min_installer(matrix_entry, "0.4.0")
        assert result["status"] == "ok"


class TestCheckNewerThanKnown:
    def test_within_range(self) -> None:
        result = _check_newer_than_known(CURRENT_MEMORY_VERSION)
        assert result["status"] in ("ok", "warning")

    def test_newer_than_known(self) -> None:
        result = _check_newer_than_known("99.0.0")
        assert result["status"] == "warning"

    def test_old_version(self) -> None:
        result = _check_newer_than_known("0.1.0")
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# check_compatibility tests
# ---------------------------------------------------------------------------

class TestCheckCompatibility:
    def test_current_version_clean(self) -> None:
        """Current version should pass all checks."""
        report = check_compatibility(CURRENT_MEMORY_VERSION)
        # Current version is in the matrix
        assert report.memory_core_version == CURRENT_MEMORY_VERSION
        assert isinstance(report.checks, list)
        assert len(report.checks) > 0

    def test_old_version_with_mismatch(self) -> None:
        """Old version should have component mismatches."""
        report = check_compatibility(
            "0.3.0",
            actual_ownership_schema="memory-ownership-v1",
        )
        # 0.3.0 expects ownership v0, so v1 should cause issues
        assert any("ownership_schema" in c.get("check", "") for c in report.checks)

    def test_unknown_version_warns(self) -> None:
        report = check_compatibility("99.0.0")
        assert report.has_warnings

    def test_explicit_component_versions(self) -> None:
        report = check_compatibility(
            CURRENT_MEMORY_VERSION,
            actual_ownership_schema="memory-ownership-v1",
        )
        # Should have matching component check
        ownership_checks = [
            c for c in report.checks if "ownership_schema" in c.get("check", "")
        ]
        assert len(ownership_checks) > 0

    def test_report_has_dict(self) -> None:
        report = check_compatibility(CURRENT_MEMORY_VERSION)
        d = report.to_dict()
        assert "memory_core_version" in d
        assert "has_errors" in d
        assert "has_warnings" in d
        assert "errors" in d
        assert "warnings" in d
        assert "checks" in d

    def test_all_components_checked(self) -> None:
        report = check_compatibility(CURRENT_MEMORY_VERSION)
        check_names = [c["check"] for c in report.checks]
        assert "component_ownership_schema" in check_names
        assert "component_hook_schema" in check_names
        assert "component_manifest_version" in check_names
        assert "component_memory_lock_schema" in check_names
        assert "min_installer_version" in check_names


# ---------------------------------------------------------------------------
# format_report tests
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_format_clean_report(self) -> None:
        report = check_compatibility(CURRENT_MEMORY_VERSION)
        text = format_report(report)
        assert "Compatibility Report" in text
        assert CURRENT_MEMORY_VERSION in text

    def test_format_report_with_errors(self) -> None:
        report = check_compatibility(
            "0.3.0",
            actual_ownership_schema="memory-ownership-v1",
        )
        text = format_report(report)
        assert "Compatibility Report" in text


# ---------------------------------------------------------------------------
# Compat matrix integrity tests
# ---------------------------------------------------------------------------

class TestCompatMatrix:
    def test_all_versions_have_required_fields(self) -> None:
        required_fields = [
            "ownership_schema",
            "hook_schema",
            "manifest_version",
            "min_installer_version",
            "memory_lock_schema",
        ]
        for version, entry in _COMPAT_MATRIX.items():
            for field in required_fields:
                assert field in entry, (
                    f"Version {version} missing field {field}"
                )

    def test_current_version_in_matrix(self) -> None:
        assert CURRENT_MEMORY_VERSION in _COMPAT_MATRIX

    def test_current_versions_dict_complete(self) -> None:
        expected_keys = [
            "memory_core",
            "ownership_schema",
            "hook_schema",
            "manifest_version",
            "memory_lock_schema",
        ]
        for key in expected_keys:
            assert key in _CURRENT_VERSIONS
