"""M6: Compatibility matrix for memory-core version checks.

Provides version compatibility checks between:
- memory-core package version
- ownership schema version
- hook schema version
- manifest version
- minimum installer version

Usage:
    from memory_core.compat import check_compatibility, CompatibilityReport
    report = check_compatibility()
    if report.has_errors:
        for err in report.errors:
            print(f"ERROR: {err}")
"""

import importlib.metadata
from dataclasses import dataclass, field
from typing import Any

from memory_core.constants import (
    CANONICAL_MEMORY_LOCK_SCHEMA,
    CURRENT_MEMORY_VERSION,
    OWNERSHIP_SCHEMA_VERSION,
)

# ---------------------------------------------------------------------------
# Version compatibility matrix
# ---------------------------------------------------------------------------

# Maps memory-core version → required versions of each component
_COMPAT_MATRIX: dict[str, dict[str, str]] = {
    "0.1.0": {
        "ownership_schema": "memory-ownership-v0",
        "hook_schema": "factory-hooks-v0",
        "manifest_version": "integrity-manifest-v1",
        "min_installer_version": "0.1.0",
        "memory_lock_schema": "context-package-v0",
    },
    "0.2.0": {
        "ownership_schema": "memory-ownership-v0",
        "hook_schema": "factory-hooks-v0",
        "manifest_version": "integrity-manifest-v1",
        "min_installer_version": "0.2.0",
        "memory_lock_schema": "context-package-v1",
    },
    "0.3.0": {
        "ownership_schema": "memory-ownership-v0",
        "hook_schema": "factory-hooks-v0",
        "manifest_version": "integrity-manifest-v1",
        "min_installer_version": "0.3.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.4.0": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.4.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.5.0": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.5.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.6.0": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.6.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.7.0": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.7.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.8.0": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.8.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.8.1": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.8.1",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.9.0": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.9.0",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
    "0.9.1": {
        "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
        "hook_schema": "factory-hooks-v1",
        "manifest_version": "integrity-manifest-v2",
        "min_installer_version": "0.9.1",
        "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
    },
}

# Current versions (what this code supports)
_CURRENT_VERSIONS: dict[str, str] = {
    "memory_core": CURRENT_MEMORY_VERSION,
    "ownership_schema": OWNERSHIP_SCHEMA_VERSION,
    "hook_schema": "factory-hooks-v1",
    "manifest_version": "integrity-manifest-v2",
    "memory_lock_schema": CANONICAL_MEMORY_LOCK_SCHEMA,
}


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompatibilityReport:
    """Result of a compatibility check.

    Attributes:
        memory_core_version: The installed memory-core version
        checks: Individual check results
        errors: Blocking incompatibilities
        warnings: Non-blocking incompatibilities
        has_errors: Whether any blocking errors exist
        has_warnings: Whether any warnings exist
    """

    memory_core_version: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_core_version": self.memory_core_version,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": self.checks,
        }


# ---------------------------------------------------------------------------
# Version parsing helpers
# ---------------------------------------------------------------------------

def _parse_version_tuple(ver: str) -> tuple[int, ...]:
    """Parse a version string like '0.1.0' into a comparable tuple."""
    return tuple(map(int, ver.split(".")))


def _get_installed_version() -> str:
    """Get the installed memory-core version."""
    try:
        return importlib.metadata.version("memory-core")
    except importlib.metadata.PackageNotFoundError:
        return CURRENT_MEMORY_VERSION


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def _check_version_registered(version: str) -> dict[str, Any]:
    """Check if the given version is in the compatibility matrix."""
    if version in _COMPAT_MATRIX:
        return {
            "check": "version_registered",
            "status": "ok",
            "detail": f"Version {version} is in compatibility matrix",
        }
    return {
        "check": "version_registered",
        "status": "warning",
        "detail": f"Version {version} not found in compatibility matrix; "
        f"known versions: {sorted(_COMPAT_MATRIX.keys())}",
    }


def _check_component(
    component: str,
    expected: str,
    actual: str,
) -> dict[str, Any]:
    """Check a single component version."""
    if expected == actual:
        return {
            "check": f"component_{component}",
            "status": "ok",
            "detail": f"{component}: {actual}",
        }
    return {
        "check": f"component_{component}",
        "status": "mismatch",
        "detail": f"{component}: expected {expected}, got {actual}",
    }


def _check_min_installer(
    matrix_entry: dict[str, str],
    installed_version: str,
) -> dict[str, Any]:
    """Check that the installed version meets the minimum installer requirement."""
    min_ver = matrix_entry.get("min_installer_version", "0.0.0")
    try:
        min_tuple = _parse_version_tuple(min_ver)
        inst_tuple = _parse_version_tuple(installed_version)
        if inst_tuple >= min_tuple:
            return {
                "check": "min_installer_version",
                "status": "ok",
                "detail": f"Installed {installed_version} >= min {min_ver}",
            }
        return {
            "check": "min_installer_version",
            "status": "error",
            "detail": f"Installed {installed_version} < minimum {min_ver}; "
            f"please upgrade memory-core",
        }
    except (ValueError, AttributeError):
        return {
            "check": "min_installer_version",
            "status": "warning",
            "detail": f"Cannot compare versions: installed={installed_version}, min={min_ver}",
        }


def _check_newer_than_known(version: str) -> dict[str, Any]:
    """Check if installed version is newer than all known versions."""
    try:
        ver_tuple = _parse_version_tuple(version)
        max_known = max(
            (_parse_version_tuple(v) for v in _COMPAT_MATRIX),
            default=(0, 0, 0),
        )
        if ver_tuple > max_known:
            return {
                "check": "version_newer_than_known",
                "status": "warning",
                "detail": f"Version {version} is newer than known max; "
                f"compatibility matrix may be outdated",
            }
    except (ValueError, AttributeError):
        pass
    return {
        "check": "version_newer_than_known",
        "status": "ok",
        "detail": "Version within known range",
    }


# ---------------------------------------------------------------------------
# Main check function
# ---------------------------------------------------------------------------

def check_compatibility(
    version: str | None = None,
    *,
    actual_ownership_schema: str | None = None,
    actual_hook_schema: str | None = None,
    actual_manifest_version: str | None = None,
    actual_memory_lock_schema: str | None = None,
) -> CompatibilityReport:
    """Run all compatibility checks and return a report.

    Args:
        version: memory-core version to check (defaults to installed version)
        actual_ownership_schema: Override ownership schema version detection
        actual_hook_schema: Override hook schema version detection
        actual_manifest_version: Override manifest version detection
        actual_memory_lock_schema: Override memory lock schema detection

    Returns:
        CompatibilityReport with errors and warnings
    """
    report = CompatibilityReport()
    version = version or _get_installed_version()
    report.memory_core_version = version

    # Check 1: Version registered in matrix
    check = _check_version_registered(version)
    report.checks.append(check)
    if check["status"] == "warning":
        report.warnings.append(check["detail"])

    # Check 2: Newer than known
    check = _check_newer_than_known(version)
    report.checks.append(check)
    if check["status"] == "warning":
        report.warnings.append(check["detail"])

    # Get matrix entry for this version (or current if not found)
    matrix_entry = _COMPAT_MATRIX.get(version, _COMPAT_MATRIX.get(CURRENT_MEMORY_VERSION, {}))

    # Check 3: Component versions
    component_checks = [
        ("ownership_schema", actual_ownership_schema),
        ("hook_schema", actual_hook_schema),
        ("manifest_version", actual_manifest_version),
        ("memory_lock_schema", actual_memory_lock_schema),
    ]
    for component, actual_override in component_checks:
        expected = matrix_entry.get(component, "")
        actual = actual_override or _CURRENT_VERSIONS.get(component, "")
        check = _check_component(component, expected, actual)
        report.checks.append(check)
        if check["status"] == "mismatch":
            # Mismatches for critical components are errors
            if component in ("ownership_schema", "manifest_version"):
                report.errors.append(check["detail"])
            else:
                report.warnings.append(check["detail"])

    # Check 4: Minimum installer version
    check = _check_min_installer(matrix_entry, version)
    report.checks.append(check)
    if check["status"] == "error":
        report.errors.append(check["detail"])
    elif check["status"] == "warning":
        report.warnings.append(check["detail"])

    return report


def format_report(report: CompatibilityReport) -> str:
    """Format a CompatibilityReport as human-readable text."""
    lines = [
        "=" * 60,
        "Compatibility Report",
        "=" * 60,
        f"  memory-core version: {report.memory_core_version}",
        "",
    ]

    for check in report.checks:
        status_icon = {"ok": "✓", "warning": "⚠", "mismatch": "✗", "error": "✗"}.get(
            check["status"], "?"
        )
        lines.append(f"  {status_icon} {check['check']}: {check['detail']}")

    if report.errors:
        lines.append("")
        lines.append("  ERRORS (blocking):")
        for err in report.errors:
            lines.append(f"    ✗ {err}")

    if report.warnings:
        lines.append("")
        lines.append("  WARNINGS (non-blocking):")
        for warn in report.warnings:
            lines.append(f"    ⚠ {warn}")

    if not report.has_errors and not report.has_warnings:
        lines.append("")
        lines.append("  All compatibility checks passed ✓")

    lines.append("=" * 60)
    return "\n".join(lines)
