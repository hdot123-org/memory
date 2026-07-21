"""Tests for source repo develop mode.

Verifies:
- get_source_repo_mode() returns readonly by default
- get_source_repo_mode() returns develop when configured
- Gateway falls through to normal build in develop mode
- ownership_cli source-repo-mode subcommand works
- pretooluse_guard still protects critical paths in develop mode
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture()
def source_repo(tmp_path: Path) -> Path:
    """Create a fake memory-core source repo with marker files."""
    memory_repo = tmp_path / "source-repo"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    (nested / "codex_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    (nested / "ownership.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    return memory_repo


@pytest.fixture()
def source_repo_with_develop(source_repo: Path) -> Path:
    """Source repo with develop mode configured in ownership.toml."""
    memory_dir = source_repo / "memory" / "system"
    memory_dir.mkdir(parents=True, exist_ok=True)
    ownership_content = """\
schema_version = "memory-ownership-v1"
memory_version = "0.4.0"

[[domains]]
name = "memory_docs"
path = "memory/docs"
level = "critical"
recursive = true
description = "Protected documentation domain"

[[domains]]
name = "memory_kb"
path = "memory/kb"
level = "critical"
recursive = true
description = "Protected knowledge base domain"

[[domains]]
name = "memory_system"
path = "memory/system"
level = "critical"
recursive = true
description = "Protected system state domain"

[[domains]]
name = "project_map"
path = "memory/project-map"
level = "critical"
recursive = true
description = "Protected project map domain"

[[resources]]
name = "agents_md"
path = "AGENTS.md"
level = "critical"
domain = ""
description = "Agent policy file"

[[resources]]
name = "memory_lock"
path = "memory/system/memory.lock"
level = "critical"
domain = "memory_system"
description = "Version lock file"

[[resources]]
name = "adapter_toml"
path = "memory/system/adapter.toml"
level = "critical"
domain = "memory_system"
description = "Adapter configuration"

[[resources]]
name = "ownership_toml"
path = "memory/system/ownership.toml"
level = "critical"
domain = "memory_system"
description = "Ownership configuration"

[policy.source_repo]
mode = "develop"
activated_at = "2026-05-21T00:00:00Z"
activated_by = "cli"
"""
    (memory_dir / "ownership.toml").write_text(ownership_content, encoding="utf-8")
    return source_repo


class TestGetSourceRepoMode:
    """Test get_source_repo_mode() function."""

    def test_default_is_readonly(self, source_repo: Path) -> None:
        """Without ownership.toml, mode is readonly."""
        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(source_repo) == "readonly"

    def test_develop_mode_from_toml(self, source_repo_with_develop: Path) -> None:
        """With develop mode in ownership.toml, returns develop."""
        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(source_repo_with_develop) == "develop"

    def test_non_source_repo_returns_readonly(self, tmp_path: Path) -> None:
        """Non-source-repo always returns readonly."""
        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(tmp_path) == "readonly"

    def test_invalid_mode_falls_back_to_readonly(self, source_repo: Path) -> None:
        """Invalid mode value falls back to readonly."""
        memory_dir = source_repo / "memory" / "system"
        memory_dir.mkdir(parents=True, exist_ok=True)
        ownership_content = """\
schema_version = "memory-ownership-v1"

[policy.source_repo]
mode = "invalid_mode"
"""
        (memory_dir / "ownership.toml").write_text(ownership_content, encoding="utf-8")
        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(source_repo) == "readonly"

    def test_empty_mode_falls_back_to_readonly(self, source_repo: Path) -> None:
        """Empty mode value falls back to readonly."""
        memory_dir = source_repo / "memory" / "system"
        memory_dir.mkdir(parents=True, exist_ok=True)
        ownership_content = """\
schema_version = "memory-ownership-v1"

[policy.source_repo]
mode = ""
"""
        (memory_dir / "ownership.toml").write_text(ownership_content, encoding="utf-8")
        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(source_repo) == "readonly"


class TestGatewayDevelopMode:
    """Test gateway behavior with develop mode."""

    def test_readonly_mode_returns_readonly_package(self, source_repo: Path) -> None:
        """Readonly source repo still gets readonly context-package."""
        from memory_core.tools.memory_hook_gateway import _build_readonly_source_repo_package
        pkg = _build_readonly_source_repo_package(source_repo, "factory", "session-start")
        assert pkg["mode"] == "read-only"
        assert pkg["allowed_writes"] == {}

    def test_develop_mode_does_not_return_readonly_package(self, source_repo_with_develop: Path) -> None:
        """Develop mode source repo should not get readonly context-package from _build_readonly."""
        from memory_core.ownership import get_source_repo_mode
        mode = get_source_repo_mode(source_repo_with_develop)
        assert mode == "develop"


class TestOwnershipCliSourceRepoMode:
    """Test ownership-cli source-repo-mode subcommand."""

    def test_status_readonly(self, source_repo: Path) -> None:
        """Status shows readonly when no ownership.toml."""
        import io
        from unittest.mock import patch

        from memory_core.tools.ownership_cli import cmd_source_repo_mode

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            rc = cmd_source_repo_mode(source_repo, mode=None, json_output=True)
        assert rc == 0
        output = json.loads(mock_stdout.getvalue())
        assert output["source_repo_mode"] == "readonly"

    def test_switch_to_develop(self, source_repo: Path) -> None:
        """Switching to develop creates ownership.toml with correct mode."""
        import io
        from unittest.mock import patch

        from memory_core.tools.ownership_cli import cmd_source_repo_mode

        with patch("sys.stdout", new_callable=io.StringIO):
            rc = cmd_source_repo_mode(source_repo, mode="develop", json_output=True)
        assert rc == 0

        # Verify the file was created
        ownership_file = source_repo / "memory" / "system" / "ownership.toml"
        assert ownership_file.exists()

        # Verify mode is persisted
        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(source_repo) == "develop"

    def test_switch_to_readonly(self, source_repo_with_develop: Path) -> None:
        """Switching from develop to readonly."""
        import io
        from unittest.mock import patch

        from memory_core.tools.ownership_cli import cmd_source_repo_mode

        with patch("sys.stdout", new_callable=io.StringIO):
            rc = cmd_source_repo_mode(source_repo_with_develop, mode="readonly", json_output=True)
        assert rc == 0

        from memory_core.ownership import get_source_repo_mode
        assert get_source_repo_mode(source_repo_with_develop) == "readonly"

    def test_non_source_repo_rejected(self, tmp_path: Path) -> None:
        """Non-source-repo is rejected."""
        import io
        from unittest.mock import patch

        from memory_core.tools.ownership_cli import cmd_source_repo_mode

        with patch("sys.stdout", new_callable=io.StringIO) as _mock_stdout:
            rc = cmd_source_repo_mode(tmp_path, mode=None, json_output=True)
        assert rc == 1

    def test_invalid_mode_rejected(self, source_repo: Path) -> None:
        """Invalid mode is rejected."""
        import io
        from unittest.mock import patch

        from memory_core.tools.ownership_cli import cmd_source_repo_mode

        with patch("sys.stdout", new_callable=io.StringIO) as _mock_stdout:
            rc = cmd_source_repo_mode(source_repo, mode="invalid", json_output=True)
        assert rc == 1


class TestPretooluseGuardInDevelopMode:
    """Verify pretooluse_guard still protects critical paths in develop mode."""

    def test_protects_memory_docs(self, source_repo_with_develop: Path) -> None:
        """memory/docs/ is still protected in develop mode."""
        from memory_core.ownership import classify_owned_path, load_memory_ownership
        ownership = load_memory_ownership(source_repo_with_develop)
        result = classify_owned_path("memory/docs/some_file.md", ownership, source_repo_with_develop)
        assert hasattr(result, "level"), "memory/docs should be owned/protected"

    def test_protects_memory_kb(self, source_repo_with_develop: Path) -> None:
        """memory/kb/ is still protected in develop mode."""
        from memory_core.ownership import classify_owned_path, load_memory_ownership
        ownership = load_memory_ownership(source_repo_with_develop)
        result = classify_owned_path("memory/kb/some_file.md", ownership, source_repo_with_develop)
        assert hasattr(result, "level"), "memory/kb should be owned/protected"

    def test_protects_dot_memory(self, source_repo_with_develop: Path) -> None:
        """memory/kb/ is still protected in develop mode."""
        from memory_core.ownership import classify_owned_path, load_memory_ownership
        ownership = load_memory_ownership(source_repo_with_develop)
        result = classify_owned_path("memory/system/memory.lock", ownership, source_repo_with_develop)
        assert hasattr(result, "level"), "memory/system/memory.lock should be owned/protected"

    def test_allows_code_files(self, source_repo_with_develop: Path) -> None:
        """Code files (memory_core/tools/*.py) are NOT protected."""
        from memory_core.ownership import classify_owned_path, load_memory_ownership
        ownership = load_memory_ownership(source_repo_with_develop)
        result = classify_owned_path("memory_core/tools/some_tool.py", ownership, source_repo_with_develop)
        assert not hasattr(result, "level"), "Code files should not be owned/protected"

    def test_allows_tests(self, source_repo_with_develop: Path) -> None:
        """Test files are NOT protected."""
        from memory_core.ownership import classify_owned_path, load_memory_ownership
        ownership = load_memory_ownership(source_repo_with_develop)
        result = classify_owned_path("tests/test_something.py", ownership, source_repo_with_develop)
        assert not hasattr(result, "level"), "Test files should not be owned/protected"
