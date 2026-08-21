"""Test version consistency across pyproject.toml, __version__, and CURRENT_MEMORY_VERSION.

This is a CI regression guard: ensures release-please can bump all version
locations without version drift.
"""

import tomllib
from pathlib import Path


def _read_pyproject_version() -> str:
    """Read version from pyproject.toml [project].version."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def test_version_consistency_all_sources():
    """pyproject.toml version == __init__.py __version__ == constants.py CURRENT_MEMORY_VERSION."""
    from memory_core import __version__
    from memory_core.constants import CURRENT_MEMORY_VERSION

    pyproject_version = _read_pyproject_version()

    assert pyproject_version == __version__, (
        f"pyproject.toml version ({pyproject_version}) != __version__ ({__version__})"
    )
    assert pyproject_version == CURRENT_MEMORY_VERSION, (
        f"pyproject.toml version ({pyproject_version}) != CURRENT_MEMORY_VERSION ({CURRENT_MEMORY_VERSION})"
    )
    assert __version__ == CURRENT_MEMORY_VERSION, (
        f"__version__ ({__version__}) != CURRENT_MEMORY_VERSION ({CURRENT_MEMORY_VERSION})"
    )


def test_version_string_is_non_empty():
    """Version string must be a non-empty string matching semver-like pattern."""
    from memory_core import __version__
    from memory_core.constants import CURRENT_MEMORY_VERSION

    assert isinstance(__version__, str)
    assert len(__version__) > 0
    assert isinstance(CURRENT_MEMORY_VERSION, str)
    assert len(CURRENT_MEMORY_VERSION) > 0
    # Basic semver pattern check
    parts = __version__.split(".")
    assert len(parts) >= 2, f"Version '{__version__}' doesn't look like semver"


def test_constants_derives_from_init():
    """CURRENT_MEMORY_VERSION is the same object/value as __version__."""
    from memory_core import __version__
    from memory_core.constants import CURRENT_MEMORY_VERSION

    # They must be equal in value
    assert __version__ == CURRENT_MEMORY_VERSION
