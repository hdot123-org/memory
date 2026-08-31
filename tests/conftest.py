import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _setup_engine_path():
    """Ensure engine directory is on sys.path for @patch decorators.

    @patch("infra_core.engine.evolution_utils.*") requires the module to be
    importable at class definition time. The engine package uses bare imports
    (from evolution_adapters import ...), so we need the engine directory on sys.path.
    """
    import infra_core.engine

    engine_dir = str(Path(infra_core.engine.__file__).parent)
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)

    # Pre-import to ensure sys.modules is populated before @patch evaluates
    import infra_core.engine.evolution_utils  # noqa: F401

    yield


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
    """临时 memory/system 目录"""
    root = tmp_path / "memory" / "system"
    root.mkdir(parents=True)
    return root
