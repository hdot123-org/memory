"""Regression test for PR #933: prevent duplicate function definitions in _init_pipeline.py.

This test ensures that _find_repo_root and _is_memory_repo are each defined only once
in the module, preventing mypy no-redef errors that caused PR #933 to fail CI.
"""

import inspect
from pathlib import Path


def test_no_duplicate_find_repo_root_definition():
    """Verify _find_repo_root is defined exactly once in _init_pipeline.py."""
    from memory_core.tools import _init_pipeline

    source = inspect.getsource(_init_pipeline)
    # Count function definition occurrences (not calls or references)
    definition_count = source.count("def _find_repo_root(")
    assert definition_count == 1, (
        f"Expected exactly 1 definition of _find_repo_root, found {definition_count}. "
        "Duplicate definitions cause mypy no-redef errors (see PR #933)."
    )


def test_no_duplicate_is_memory_repo_definition():
    """Verify _is_memory_repo is defined exactly once in _init_pipeline.py."""
    from memory_core.tools import _init_pipeline

    source = inspect.getsource(_init_pipeline)
    # Count function definition occurrences (not calls or references)
    definition_count = source.count("def _is_memory_repo(")
    assert definition_count == 1, (
        f"Expected exactly 1 definition of _is_memory_repo, found {definition_count}. "
        "Duplicate definitions cause mypy no-redef errors (see PR #933)."
    )


def test_find_repo_root_uses_subprocess():
    """Verify _find_repo_root uses git subprocess (authoritative implementation)."""
    from memory_core.tools._init_pipeline import _find_repo_root

    source = inspect.getsource(_find_repo_root)
    # The authoritative implementation uses subprocess.run with git rev-parse
    assert "subprocess.run" in source or "subprocess" in source, (
        "_find_repo_root should use subprocess to call git rev-parse --show-toplevel"
    )
    assert "git" in source and "rev-parse" in source, "_find_repo_root should call git rev-parse --show-toplevel"


def test_is_memory_repo_uses_gateway_marker():
    """Verify _is_memory_repo uses gateway marker (authoritative implementation)."""
    from memory_core.tools._init_pipeline import _is_memory_repo

    source = inspect.getsource(_is_memory_repo)
    # The authoritative implementation checks for the gateway marker file
    assert "memory_hook_gateway.py" in source, "_is_memory_repo should check for memory_hook_gateway.py marker file"


def test_functions_are_callable():
    """Verify both functions can be imported and called without errors."""
    from memory_core.tools._init_pipeline import (
        _find_repo_root,
        _is_memory_repo,
    )

    # _find_repo_root should return None or a Path for any input
    test_path = Path("/tmp")
    result = _find_repo_root(test_path)
    assert result is None or isinstance(result, Path)

    # _is_memory_repo should return a boolean for any Path input
    result = _is_memory_repo(test_path)
    assert isinstance(result, bool)
