from pathlib import Path

import pytest


@pytest.fixture
def repo_root():
    """仓库根目录"""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def workspace_root(repo_root):
    """memory_core 包根目录"""
    return repo_root / "memory_core"


@pytest.fixture
def tmp_memory_root(tmp_path):
    """临时 .memory 目录"""
    root = tmp_path / ".memory"
    root.mkdir()
    return root
