"""Shared fixtures for memory-core test suite."""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def repo_root():
    return REPO_ROOT

@pytest.fixture
def workspace_root(repo_root):
    return repo_root / "memory_core"

@pytest.fixture
def tmp_memory_root(tmp_path):
    d = tmp_path / ".memory"
    d.mkdir()
    return d
