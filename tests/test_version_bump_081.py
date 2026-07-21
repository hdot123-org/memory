"""Tests for version bump 0.8.1 → 0.9.0.

Validates:
- VAL-VERSION-001: Version numbers are globally consistent at 0.9.0
- VAL-VERSION-002: CLI --version displays 0.9.0
- VAL-FIX-004: ruff passes (covered separately)
"""

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# VAL-VERSION-001: Version numbers are globally consistent at 0.9.0
# ---------------------------------------------------------------------------


class TestVersionConsistency:
    """VAL-VERSION-001: constants.py, pyproject.toml, compat.py all at 0.9.0."""

    def test_constants_current_memory_version_is_090(self) -> None:
        """constants.py CURRENT_MEMORY_VERSION must be '0.9.0'."""
        from memory_core.constants import CURRENT_MEMORY_VERSION
        assert CURRENT_MEMORY_VERSION == "0.9.0", (
            f"Expected CURRENT_MEMORY_VERSION='0.9.0', got '{CURRENT_MEMORY_VERSION}'"
        )

    def test_pyproject_toml_version_is_090(self) -> None:
        """pyproject.toml version must be '0.9.0'."""
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject_path.read_text(encoding="utf-8")
        # Look for version = "0.9.0" in [project] section
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
                assert "0.9.0" in stripped, (
                    f"Expected version = \"0.9.0\" in pyproject.toml, got: {stripped}"
                )
                found = True
                break
        assert found, "version field not found in [project] section of pyproject.toml"

    def test_compat_matrix_has_090_entry(self) -> None:
        """compat.py _COMPAT_MATRIX must contain '0.9.0' key."""
        from memory_core.compat import _COMPAT_MATRIX
        assert "0.9.0" in _COMPAT_MATRIX, (
            f"'0.9.0' not found in _COMPAT_MATRIX. "
            f"Known versions: {sorted(_COMPAT_MATRIX.keys())}"
        )

    def test_compat_matrix_090_has_required_fields(self) -> None:
        """_COMPAT_MATRIX['0.9.0'] must have all required component keys."""
        from memory_core.compat import _COMPAT_MATRIX
        entry = _COMPAT_MATRIX["0.9.0"]
        required_keys = {
            "ownership_schema",
            "hook_schema",
            "manifest_version",
            "min_installer_version",
            "memory_lock_schema",
        }
        missing = required_keys - set(entry.keys())
        assert not missing, f"_COMPAT_MATRIX['0.9.0'] missing keys: {missing}"

    def test_compat_matrix_090_min_installer_is_090(self) -> None:
        """_COMPAT_MATRIX['0.9.0']['min_installer_version'] must be '0.9.0'."""
        from memory_core.compat import _COMPAT_MATRIX
        assert _COMPAT_MATRIX["0.9.0"]["min_installer_version"] == "0.9.0"


# ---------------------------------------------------------------------------
# VAL-VERSION-002: CLI --version displays 0.9.0
# ---------------------------------------------------------------------------


class TestCLIVersionFlag:
    """VAL-VERSION-002: memory-init --version and memory-migrate --version show 0.9.0."""

    def test_memory_init_version_shows_090(self) -> None:
        """memory-init --version output must contain '0.9.0'."""
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory", "--version"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        # argparse prints version to stdout
        combined = result.stdout + result.stderr
        assert "0.9.0" in combined, (
            f"Expected '0.9.0' in memory-init --version output. "
            f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )

    def test_memory_migrate_version_shows_090(self) -> None:
        """memory-migrate --version output must contain '0.9.0'."""
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.migrate_project_memory", "--version"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        combined = result.stdout + result.stderr
        assert "0.9.0" in combined, (
            f"Expected '0.9.0' in memory-migrate --version output. "
            f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# adapter_toml_schema.py: default version uses CURRENT_MEMORY_VERSION
# ---------------------------------------------------------------------------


class TestAdapterTomlSchemaVersion:
    """adapter_toml_schema.py default version must reflect 0.9.0."""

    def test_adapter_config_default_version_is_090(self) -> None:
        """AdapterConfig default adapter_version must be '0.9.0'."""
        from memory_core.tools.adapter_toml_schema import AdapterConfig
        config = AdapterConfig(project_name="test", project_scope="test")
        assert config.adapter_version == "0.9.0", (
            f"Expected AdapterConfig default adapter_version='0.9.0', "
            f"got '{config.adapter_version}'"
        )
