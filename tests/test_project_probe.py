"""Tests for ProjectProbe and auto-fill logic.

Covers:
- Language detection (Python/JS/Go/Rust/mixed)
- Framework detection
- Project type detection
- Database detection
- Toolchain detection
- Git info detection
- README summary extraction
- Auto-fill tolerance on failure
- --no-auto-fill flag behavior
- Fill content correctness
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from memory_core.tools.init_project_memory import (
    fill_template_fields,
    init_project_memory,
    main,
    template_project_scope_md,
)


def _call_main(argv: list[str]) -> int:
    """Invoke init_project_memory.main() with patched sys.argv."""
    old_argv = sys.argv
    try:
        sys.argv = ["memory-init", *argv]
        return main()
    finally:
        sys.argv = old_argv


class TestProjectProbeBasic:
    """Test ProjectProbe on basic/minimal projects."""

    def test_empty_project_returns_empty_info(self, tmp_path: Path) -> None:
        """An empty directory should return empty ProjectInfo."""
        from memory_core.tools.project_probe import ProjectProbe

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        # All fields should be empty/default
        assert info.primary_language == ""
        assert info.framework == ""
        assert info.project_type == ""
        assert info.databases == []
        assert info.toolchain == []
        assert info.git_remote_url == ""
        assert info.git_branch == ""

    def test_python_project_detection(self, tmp_path: Path) -> None:
        """A Python project with pyproject.toml should detect Python."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n\n[tool.ruff]\n'
        )
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\nuvicorn\n")
        (tmp_path / "README.md").write_text("# MyApp\n\nA fast web API service.\n")

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert info.primary_language == "Python"
        assert info.framework == "FastAPI"

    def test_js_project_detection(self, tmp_path: Path) -> None:
        """A JavaScript/TypeScript project should detect JS/TS."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "my-web-app",
                "dependencies": {"express": "^4.0", "react": "^18.0"},
                "devDependencies": {"jest": "^29.0"}
            })
        )

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert info.primary_language == "JavaScript/TypeScript"
        assert info.framework in ("Express.js", "React")

    def test_go_project_detection(self, tmp_path: Path) -> None:
        """A Go project with go.mod should detect Go."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text('package main\n\nfunc main() {}')

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert info.primary_language == "Go"

    def test_rust_project_detection(self, tmp_path: Path) -> None:
        """A Rust project with Cargo.toml should detect Rust."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "myapp"\nversion = "0.1.0"\nedition = "2021"\n'
        )

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert info.primary_language == "Rust"

    def test_mixed_python_js_project(self, tmp_path: Path) -> None:
        """A mixed project should detect the dominant language."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "mixed"\n')
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "mixed", "dependencies": {"react": "^18.0"}})
        )
        # More Python config files should make Python win
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        (tmp_path / "setup.py").write_text('from setuptools import setup\n')

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert info.primary_language == "Python"

    def test_database_detection_from_docker_compose(self, tmp_path: Path) -> None:
        """Database keywords in docker-compose.yml should be detected."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "docker-compose.yml").write_text("""
version: '3'
services:
  db:
    image: postgres:15
  cache:
    image: redis:7
""")

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert "PostgreSQL" in info.databases
        assert "Redis" in info.databases

    def test_database_detection_from_env(self, tmp_path: Path) -> None:
        """Database keywords in .env should be detected."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / ".env").write_text("DATABASE_URL=postgresql://localhost:5432/mydb\n")

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert "PostgreSQL" in info.databases

    def test_toolchain_detection(self, tmp_path: Path) -> None:
        """CI and linter config files should be detected as toolchain."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / ".github").mkdir(parents=True)
        (tmp_path / ".github" / "workflows").mkdir()
        (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
        (tmp_path / "ruff.toml").write_text("line-length = 88\n")
        (tmp_path / "pytest.ini").write_text("[pytest]\n")

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        tool_names = [t["name"] for t in info.toolchain]
        assert "GitHub Actions" in tool_names
        assert "Ruff" in tool_names
        assert "pytest" in tool_names

    def test_git_info_detection(self, tmp_path: Path) -> None:
        """Git remote and branch should be detected."""
        from memory_core.tools.project_probe import ProjectProbe

        # Init as git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/org/test-repo.git"],
            cwd=tmp_path, capture_output=True,
        )
        # Create initial commit to have a branch
        (tmp_path / "README.md").write_text("# test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert "github.com" in info.git_remote_url
        assert info.git_branch != ""  # Now we have a branch

    def test_readme_summary_extraction(self, tmp_path: Path) -> None:
        """README.md first paragraph should be extracted."""
        from memory_core.tools.project_probe import ProjectProbe

        (tmp_path / "README.md").write_text("""# My Project

This is a web API service built with FastAPI.
It provides CRUD operations for user management.
And handles authentication and authorization.

## Getting Started

Install dependencies with pip.
""")

        probe = ProjectProbe(tmp_path)
        info = probe.probe()

        assert "web API service" in info.project_overview


class TestProjectProbeErrorTolerance:
    """Test that ProjectProbe tolerates errors gracefully."""

    def test_probe_never_raises_exception(self, tmp_path: Path) -> None:
        """ProjectProbe.probe() should never raise an exception."""
        from memory_core.tools.project_probe import ProjectProbe

        probe = ProjectProbe(tmp_path)
        # Should not raise
        info = probe.probe()
        assert isinstance(info.primary_language, str)

    def test_probe_handles_binary_files(self, tmp_path: Path) -> None:
        """Binary files should not crash detection."""
        from memory_core.tools.project_probe import ProjectProbe

        # Create a binary file that looks like a config file
        (tmp_path / "pyproject.toml").write_bytes(b'\x00\x01\x02\x03\xff\xfe')

        probe = ProjectProbe(tmp_path)
        info = probe.probe()
        # Should succeed without raising
        assert isinstance(info.primary_language, str)


class TestFillTemplateFields:
    """Test the fill_template_fields function."""

    def test_fill_project_scope(self) -> None:
        """fill_template_fields should fill project scope .md fields."""
        content, _ = template_project_scope_md("test-proj")

        from memory_core.tools.project_probe import ProjectInfo
        info = ProjectInfo(
            primary_language="Python",
            framework="FastAPI",
            databases=["PostgreSQL", "Redis"],
            project_overview="A web API service",
        )

        filled = fill_template_fields(content, info)
        assert "- 语言：Python" in filled
        assert "- 语言：（待填写）" not in filled
        assert "- 框架：FastAPI" in filled
        assert "- 数据库：PostgreSQL、Redis" in filled
        assert "A web API service" in filled
        assert "（待填写：项目简要描述）" not in filled

    def test_fill_with_none_project_info_is_noop(self) -> None:
        """fill_template_fields with None project_info should return content unchanged."""
        content, _ = template_project_scope_md("test-proj")
        filled = fill_template_fields(content, None)
        assert filled == content

class TestAutoFillIntegration:
    """Integration tests for auto-fill in init_project_memory."""

    def test_auto_fill_populates_project_scope(self, tmp_path: Path) -> None:
        """Auto-fill should populate project scope .md with tech stack."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
        (tmp_path / "requirements.txt").write_text("flask>=2.0\n")

        result = init_project_memory(tmp_path, scope="test-proj", auto_fill=True)
        assert result["success"] is True

        scope_md = tmp_path / "memory" / "kb" / "projects" / "test_proj.md"
        content = scope_md.read_text(encoding="utf-8")

        assert "- 语言：Python" in content

    def test_auto_fill_false_keeps_placeholders(self, tmp_path: Path) -> None:
        """auto_fill=False should keep all placeholders in project scope .md."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        result = init_project_memory(tmp_path, scope="test-proj", auto_fill=False)
        assert result["success"] is True

        scope_md = tmp_path / "memory" / "kb" / "projects" / "test_proj.md"
        content = scope_md.read_text(encoding="utf-8")
        assert "- 语言：（待填写）" in content

    def test_auto_fill_idempotent(self, tmp_path: Path) -> None:
        """Running init twice with auto_fill should not corrupt content."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        # First init
        result1 = init_project_memory(tmp_path, scope="test-proj", auto_fill=True)
        assert result1["success"] is True

        scope_md = tmp_path / "memory" / "kb" / "projects" / "test_proj.md"
        content1 = scope_md.read_text(encoding="utf-8")

        # Second init (should skip existing files)
        result2 = init_project_memory(tmp_path, scope="test-proj", auto_fill=True)
        assert result2["success"] is True

        content2 = scope_md.read_text(encoding="utf-8")
        # Content should be preserved
        assert content1 == content2
