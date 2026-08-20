"""Tests for version consistency across the codebase.

Validates:
- VAL-VERSION-001: Version numbers are globally consistent (constants ↔ pyproject ↔ compat)
- VAL-VERSION-002: CLI --version displays CURRENT_MEMORY_VERSION
- Compat fallback works for versions not explicitly in _COMPAT_MATRIX
"""

import subprocess
import sys
from pathlib import Path

import tomllib

from memory_core.constants import CURRENT_MEMORY_VERSION

# ---------------------------------------------------------------------------
# VAL-VERSION-001: Version numbers are globally consistent
# ---------------------------------------------------------------------------


class TestVersionConsistency:
    """VAL-VERSION-001: constants.py, pyproject.toml, compat.py all share CURRENT_MEMORY_VERSION."""

    def test_constants_matches_pyproject(self) -> None:
        """constants.py CURRENT_MEMORY_VERSION must match pyproject.toml version."""
        from memory_core.constants import CURRENT_MEMORY_VERSION
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            config = tomllib.load(f)
        pyproject_version = config["project"]["version"]
        assert pyproject_version == CURRENT_MEMORY_VERSION, (
            f"constants.CURRENT_MEMORY_VERSION='{CURRENT_MEMORY_VERSION}' "
            f"does not match pyproject.toml version='{pyproject_version}'"
        )

    def test_pyproject_toml_has_version_field(self) -> None:
        """pyproject.toml version field must reflect CURRENT_MEMORY_VERSION."""
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject_path.read_text(encoding="utf-8")
        # Look for the version field in [project] section
        found = False
        in_project_section = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[project]":
                in_project_section = True
                continue
            if stripped.startswith("[") and in_project_section:
                break
            if in_project_section and stripped.startswith("version"):
                assert CURRENT_MEMORY_VERSION in stripped, (
                    f"Expected version = \"{CURRENT_MEMORY_VERSION}\" in pyproject.toml, got: {stripped}"
                )
                found = True
                break
        assert found, "version field not found in [project] section of pyproject.toml"

    def test_compat_entry_for_current_version(self) -> None:
        """CURRENT_MEMORY_VERSION must resolve to a compat entry (matrix or fallback)."""
        from memory_core.compat import _get_compat_entry
        entry = _get_compat_entry(CURRENT_MEMORY_VERSION)
        required_keys = {
            "ownership_schema",
            "hook_schema",
            "manifest_version",
            "min_installer_version",
            "memory_lock_schema",
        }
        missing = required_keys - set(entry.keys())
        assert not missing, (
            f"compat entry for '{CURRENT_MEMORY_VERSION}' missing keys: {missing}"
        )

    def test_compat_entry_has_required_fields(self) -> None:
        """compat entry for CURRENT_MEMORY_VERSION must have all required component keys."""
        from memory_core.compat import _get_compat_entry
        entry = _get_compat_entry(CURRENT_MEMORY_VERSION)
        required_keys = {
            "ownership_schema",
            "hook_schema",
            "manifest_version",
            "min_installer_version",
            "memory_lock_schema",
        }
        missing = required_keys - set(entry.keys())
        assert not missing, f"compat entry for '{CURRENT_MEMORY_VERSION}' missing keys: {missing}"

    def test_compat_entry_min_installer_matches(self) -> None:
        """compat entry['min_installer_version'] for CURRENT_MEMORY_VERSION must equal CURRENT_MEMORY_VERSION."""
        from memory_core.compat import _get_compat_entry
        entry = _get_compat_entry(CURRENT_MEMORY_VERSION)
        assert entry["min_installer_version"] == CURRENT_MEMORY_VERSION


# ---------------------------------------------------------------------------
# VAL-VERSION-002: CLI --version displays CURRENT_MEMORY_VERSION
# ---------------------------------------------------------------------------


class TestCLIVersionFlag:
    """VAL-VERSION-002: memory-init --version and memory-migrate --version show CURRENT_MEMORY_VERSION."""

    def test_memory_init_version_output(self) -> None:
        """memory-init --version output must contain CURRENT_MEMORY_VERSION."""
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory", "--version"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        # argparse prints version to stdout
        combined = result.stdout + result.stderr
        assert CURRENT_MEMORY_VERSION in combined, (
            f"Expected '{CURRENT_MEMORY_VERSION}' in memory-init --version output. "
            f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )

    def test_memory_migrate_version_output(self) -> None:
        """memory-migrate --version output must contain CURRENT_MEMORY_VERSION."""
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.migrate_project_memory", "--version"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        combined = result.stdout + result.stderr
        assert CURRENT_MEMORY_VERSION in combined, (
            f"Expected '{CURRENT_MEMORY_VERSION}' in memory-migrate --version output. "
            f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# adapter_toml_schema.py: default version uses CURRENT_MEMORY_VERSION
# ---------------------------------------------------------------------------


class TestAdapterTomlSchemaVersion:
    """adapter_toml_schema.py default version must reflect CURRENT_MEMORY_VERSION."""

    def test_adapter_config_default_version(self) -> None:
        """AdapterConfig default adapter_version must be CURRENT_MEMORY_VERSION."""
        from memory_core.tools.adapter_toml_schema import AdapterConfig
        config = AdapterConfig(project_name="test", project_scope="test")
        assert config.adapter_version == CURRENT_MEMORY_VERSION, (
            f"Expected AdapterConfig default adapter_version='{CURRENT_MEMORY_VERSION}', "
            f"got '{config.adapter_version}'"
        )


# ---------------------------------------------------------------------------
# Compat fallback behavior (versions not in _COMPAT_MATRIX)
# ---------------------------------------------------------------------------


class TestCompatFallback:
    """Test that _get_compat_entry provides a working fallback for unknown versions."""

    def test_unknown_version_returns_default_entry(self) -> None:
        """A version not in _COMPAT_MATRIX should still return a valid compat entry."""
        from memory_core.compat import _get_compat_entry
        entry = _get_compat_entry("99.99.99")
        required_keys = {
            "ownership_schema",
            "hook_schema",
            "manifest_version",
            "min_installer_version",
            "memory_lock_schema",
        }
        assert required_keys <= set(entry.keys())

    def test_current_version_compat_entry_works(self) -> None:
        """CURRENT_MEMORY_VERSION should produce a valid compat entry (via matrix or fallback)."""
        from memory_core.compat import _get_compat_entry
        entry = _get_compat_entry(CURRENT_MEMORY_VERSION)
        assert entry["min_installer_version"] == CURRENT_MEMORY_VERSION
