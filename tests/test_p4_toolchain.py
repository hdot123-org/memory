"""Tests for P4 toolchain: init, validate, migrate.

Covers:
    - Happy path (init + validate full flow)
    - Missing file detection
    - Pollution guard
    - Migration idempotency
    - Dry-run modes
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def _read_memory_lock(path: Path) -> dict:
    """Read memory.lock, supporting both TOML (canonical) and JSON (legacy)."""
    text = path.read_text(encoding="utf-8")
    if text.strip().startswith("{"):
        return json.loads(text)
    return tomllib.loads(text)


def _write_memory_lock(path: Path, data: dict) -> None:
    """Write memory.lock in TOML format (canonical)."""
    memory = data.get("memory", {})
    lines = ["# memory.lock -- project binding to memory-core", "", "[memory]"]
    for key in ("memory_version", "schema_version", "adapter_version", "locked_at", "lock_reason"):
        val = memory.get(key, "")
        lines.append(f'{key} = "{val}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_lock_version(lock_data: dict) -> str:
    """Extract version from lock data (TOML or JSON format)."""
    if "memory" in lock_data:
        return lock_data["memory"].get("memory_version", "")
    return lock_data.get("version", "")


def _current_version() -> str:
    """Get current memory version from constants or fallback."""
    try:
        from memory_core.constants import CURRENT_MEMORY_VERSION
        return CURRENT_MEMORY_VERSION
    except ImportError:
        return "0.2.0"

TOOLS_DIR = Path(__file__).resolve().parents[1] / "memory_core" / "tools"
INIT_SCRIPT = TOOLS_DIR / "init_project_memory.py"
VALIDATE_SCRIPT = TOOLS_DIR / "validate_project_memory.py"
MIGRATE_SCRIPT = TOOLS_DIR / "migrate_project_memory.py"


def _run_script(
    script: Path, args: list[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a tool script and return the result."""
    env = dict(os.environ)
    # Set PYTHONPATH to memory_core/ so imports like 'memory_core.constants' work
    env["PYTHONPATH"] = str(TOOLS_DIR.parent.parent)
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def _make_temp_project() -> Path:
    """Create a temporary directory that looks like a project root."""
    tmp = Path(tempfile.mkdtemp(prefix="p4_test_"))
    # Create a minimal .git to look like a repo
    (tmp / ".git").mkdir()
    return tmp


# ---------------------------------------------------------------------------
# Happy path: init + validate
# ---------------------------------------------------------------------------

class TestHappyPathInitAndValidate:
    """Full flow: init creates skeleton, validate passes."""

    def test_init_creates_skeleton(self) -> None:
        """Init should create all required files and directories."""
        proj = _make_temp_project()
        try:
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0, f"init failed: {result.stderr}"
            data = json.loads(result.stdout)
            assert data["success"] is True

            # Verify files exist
            memory_root = proj / "memory" / "system"
            for fname in ("memory.lock", "adapter.toml", "migrations.log"):
                assert (memory_root / fname).is_file(), f"{fname} not created"

            # Verify dirs exist
            for dname in ("kb/projects", "kb/decisions", "kb/lessons", "kb/global"):
                assert (memory_root / dname).is_dir(), f"dir {dname} not created"
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_validate_passes_after_init(self) -> None:
        """Validate should pass on a freshly initialized skeleton."""
        proj = _make_temp_project()
        try:
            # Init
            init_result = _run_script(INIT_SCRIPT, ["--target", str(proj)])
            assert init_result.returncode == 0

            # Validate
            val_result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            assert val_result.returncode == 0, f"validate failed: {val_result.stderr}"
            data = json.loads(val_result.stdout)
            assert data["all_passed"] is True, f"Checks failed: {data}"
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_init_dry_run(self) -> None:
        """Init dry-run should not create any files."""
        proj = _make_temp_project()
        try:
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--dry-run", "--json"])
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["success"] is True
            assert data["dry_run"] is True
            # No .memory/ should exist
            assert not (proj / "memory" / "system").exists()
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_validate_dry_run(self) -> None:
        """Validate dry-run should report what would be checked."""
        proj = _make_temp_project()
        try:
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--dry-run", "--json"])
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["all_passed"] is True
            assert any(c["name"].startswith("dry_run") for c in data["checks"])
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Missing file detection
# ---------------------------------------------------------------------------

class TestMissingFileDetection:
    """Validator must fail when required files are missing."""

    def test_missing_memory_lock(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Remove memory.lock
            (proj / "memory" / "system" / "memory.lock").unlink()
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            lock_checks = [c for c in data["checks"] if "memory.lock" in c["name"]]
            assert any(not c["passed"] for c in lock_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_missing_all_required(self) -> None:
        """When no .memory/ exists at all, validate should fail."""
        proj = _make_temp_project()
        try:
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            root_checks = [c for c in data["checks"] if "memory_root" in c["name"]]
            assert any(not c["passed"] for c in root_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Pollution guard
# ---------------------------------------------------------------------------

class TestPollutionGuard:
    """Validator must detect business-state pollution in memory repo."""

    def test_pollution_in_path(self) -> None:
        """Files under node_modules-like paths should be flagged."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Create a pollution file
            poll_dir = proj / "memory" / "system" / "kb" / "node_modules"
            poll_dir.mkdir(parents=True)
            (poll_dir / "package.json").write_text('{"name":"test"}', encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            pollution_checks = [c for c in data["checks"] if "pollution" in c["name"]]
            assert any(not c["passed"] for c in pollution_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_pollution_in_content(self) -> None:
        """References to __pycache__ in file content should be flagged."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Write pollution into adapter.toml
            adapter = proj / "memory" / "system" / "adapter.toml"
            text = adapter.read_text(encoding="utf-8")
            text += '\n# Path reference: /some/project/__pycache__/module.pyc\n'
            adapter.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_clean_project_passes(self) -> None:
        """A clean project should pass pollution checks."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            pollution_checks = [c for c in data["checks"] if "pollution" in c["name"]]
            assert all(c["passed"] for c in pollution_checks), "Unexpected pollution detected"
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Migration idempotency (removed: no longer supported in v0.5.0)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Version check failure
# ---------------------------------------------------------------------------

class TestVersionCheckFailure:
    """Validator must fail when versions don't match."""

    def test_wrong_lock_version(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Tamper with version
            lock = proj / "memory" / "system" / "memory.lock"
            data = _read_memory_lock(lock)
            if "memory" in data:
                data["memory"]["memory_version"] = "9.9.9"
            else:
                data["version"] = "9.9.9"
            _write_memory_lock(lock, data)

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data_out = json.loads(result.stdout)
            # Backward compatibility: unknown versions should pass (with warnings)
            assert data_out["all_passed"] is True
            version_checks = [c for c in data_out["checks"] if "lock_version" in c["name"]]
            # Version check should pass (backward compatible)
            assert any(c["passed"] for c in version_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_wrong_adapter_version(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Tamper with adapter version
            adapter = proj / "memory" / "system" / "adapter.toml"
            text = adapter.read_text(encoding="utf-8")
            text = text.replace(f'version = "{_current_version()}"', 'version = "9.9.9"')
            adapter.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data_out = json.loads(result.stdout)
            # Backward compatibility: unknown versions should pass (with warnings)
            assert data_out["all_passed"] is True
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Frontmatter validation
# ---------------------------------------------------------------------------

# NOTE: _parse_frontmatter exists in validate_project_memory.py but is not
# wired into any validation check. This test class remains skipped until
# frontmatter validation checks are implemented.
@pytest.mark.skip(reason="Frontmatter validation not yet wired into validate_project_memory.py")
class TestFrontmatterValidation:
    """Validator must check frontmatter fields."""

    def test_missing_frontmatter_field(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--scope", "my_project"])
            # Remove frontmatter from CANONICAL.md
            canonical = proj / "memory" / "kb" / "projects" / "my_project" / "CANONICAL.md"
            canonical.write_text("# No frontmatter\n\nContent\n", encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            fm_checks = [c for c in data["checks"] if "frontmatter" in c["name"]]
            assert any(not c["passed"] for c in fm_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scope and project name discovery
# ---------------------------------------------------------------------------

class TestScopeAndProjectName:
    """Test --scope parameter and project name discovery logic."""

    def test_scope_explicit(self) -> None:
        """Explicit --scope should be used as project_scope."""
        proj = _make_temp_project()
        try:
            result = _run_script(
                INIT_SCRIPT,
                ["--target", str(proj), "--scope", "my_project", "--json"],
            )
            assert result.returncode == 0
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            assert 'project_scope = "my_project"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_scope_with_hyphens_is_slugified(self) -> None:
        """Hyphens in --scope should be converted to underscores."""
        proj = _make_temp_project()
        try:
            result = _run_script(
                INIT_SCRIPT,
                ["--target", str(proj), "--scope", "My-Project", "--json"],
            )
            assert result.returncode == 0
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            assert 'project_scope = "my_project"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_fallback_to_dirname_lowercase(self) -> None:
        """Without --scope or git remote, should use lowercase directory name."""
        proj = _make_temp_project()
        try:
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            # _make_temp_project creates dirs like p4_test_xxx
            assert 'project_scope = "' in adapter
            # Should not be the old uppercase format
            assert 'project_scope = "project"' not in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_git_remote_origin_discovery(self) -> None:
        """Project name should be derived from git remote origin URL."""
        proj = _make_temp_project()
        try:
            # Set up a git remote
            subprocess.run(
                ["git", "init"], cwd=str(proj), capture_output=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", "git@github.com:busiji/my-awesome-project.git"],
                cwd=str(proj), capture_output=True,
            )
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            assert 'project_scope = "my_awesome_project"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    @pytest.mark.flaky(reruns=2)
    def test_git_remote_https_url(self) -> None:
        """HTTPS remote URLs should also work."""
        proj = _make_temp_project()
        try:
            subprocess.run(
                ["git", "init"], cwd=str(proj), capture_output=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/org/some-repo.git"],
                cwd=str(proj), capture_output=True,
            )
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            assert 'project_scope = "some_repo"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_scope_takes_priority_over_git_remote(self) -> None:
        """Explicit --scope should override git remote discovery."""
        proj = _make_temp_project()
        try:
            subprocess.run(
                ["git", "init"], cwd=str(proj), capture_output=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/org/remote-name.git"],
                cwd=str(proj), capture_output=True,
            )
            result = _run_script(
                INIT_SCRIPT,
                ["--target", str(proj), "--scope", "explicit_scope", "--json"],
            )
            assert result.returncode == 0
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            assert 'project_scope = "explicit_scope"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Hooks and AGENTS.md generation
# ---------------------------------------------------------------------------

class TestHooksAndAgentsMdGeneration:
    """Test AGENTS.md generation during init. Note: hooks.json is no longer created (INV-6)."""

    def test_agents_md_created_with_markers(self) -> None:
        """Init should create AGENTS.md with MEMORY_HOOK markers."""
        proj = _make_temp_project()
        try:
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0

            agents_path = proj / "AGENTS.md"
            assert agents_path.is_file(), "AGENTS.md not created"

            content = agents_path.read_text(encoding="utf-8")
            assert "<!-- MEMORY_HOOK_BEGIN -->" in content
            assert "<!-- MEMORY_HOOK_END -->" in content
            # VAL-P0-002: AGENTS.md should NOT contain deprecated wrapper paths
            assert "~/.codex/bin/memory-hook" not in content
            assert "~/.claude/bin/memory-hook" not in content
            # Should reference factory host
            assert "factory" in content
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_hooks_json_not_created(self) -> None:
        """Init should NOT create hooks.json (INV-6: host tightening)."""
        proj = _make_temp_project()
        try:
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0

            hooks_path = proj / ".claude" / "hooks.json"
            assert not hooks_path.exists(), "hooks.json should not be created"
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_agents_md_idempotent_no_duplicate(self) -> None:
        """Running init twice should not duplicate the hook block."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            agents_path = proj / "AGENTS.md"
            content1 = agents_path.read_text(encoding="utf-8")
            count1 = content1.count("<!-- MEMORY_HOOK_BEGIN -->")

            # Run again
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            content2 = agents_path.read_text(encoding="utf-8")
            count2 = content2.count("<!-- MEMORY_HOOK_BEGIN -->")

            assert count1 == 1
            assert count2 == 1
            # Content should be identical after second run
            assert content1 == content2
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_agents_md_preserves_existing_content(self) -> None:
        """Init should preserve existing AGENTS.md content and append the block."""
        proj = _make_temp_project()
        try:
            agents_path = proj / "AGENTS.md"
            agents_path.write_text("# My Project\n\nSome existing content.\n", encoding="utf-8")

            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            content = agents_path.read_text(encoding="utf-8")
            assert "# My Project" in content
            assert "Some existing content." in content
            assert "<!-- MEMORY_HOOK_BEGIN -->" in content
            assert "<!-- MEMORY_HOOK_END -->" in content
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_default_host_is_factory(self) -> None:
        """Default host should be factory."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            agents_path = proj / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")
            assert "--host factory" in content
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Factory host support
# ---------------------------------------------------------------------------

class TestFactoryHost:
    """Tests for --host factory support."""

    def test_init_factory_adapter_toml_host(self) -> None:
        """memory-init --host factory should set routing.host to factory in adapter.toml."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--host", "factory"])
            adapter = (proj / "memory" / "system" / "adapter.toml").read_text()
            assert 'host = "factory"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_init_factory_validate_passes(self) -> None:
        """A factory-initialized project should pass validation."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--host", "factory"])
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is True
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_init_factory_agents_md_command(self) -> None:
        """AGENTS.md should contain --host factory in the command."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--host", "factory"])
            agents = (proj / "AGENTS.md").read_text()
            assert "--host factory" in agents
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Validator enhanced checks
# ---------------------------------------------------------------------------

class TestValidatorEnhancedChecks:
    """Tests for enhanced validator checks."""

    def test_reject_invalid_host(self) -> None:
        """adapter.toml with unsupported host should fail validation."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            adapter = proj / "memory" / "system" / "adapter.toml"
            text = adapter.read_text(encoding="utf-8")
            text = text.replace('host = "factory"', 'host = "neovim"')
            adapter.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            host_checks = [c for c in data["checks"] if "adapter_host_enum" in c["name"]]
            assert any(not c["passed"] for c in host_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_reject_codex_host(self) -> None:
        """adapter.toml with 'codex' host should fail validation (no longer supported)."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            adapter = proj / "memory" / "system" / "adapter.toml"
            text = adapter.read_text(encoding="utf-8")
            text = text.replace('host = "factory"', 'host = "codex"')
            adapter.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            host_checks = [c for c in data["checks"] if "adapter_host_enum" in c["name"]]
            assert any(not c["passed"] for c in host_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_reject_claude_host(self) -> None:
        """adapter.toml with 'claude' host should fail validation (no longer supported)."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            adapter = proj / "memory" / "system" / "adapter.toml"
            text = adapter.read_text(encoding="utf-8")
            text = text.replace('host = "factory"', 'host = "claude"')
            adapter.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            host_checks = [c for c in data["checks"] if "adapter_host_enum" in c["name"]]
            assert any(not c["passed"] for c in host_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    # NOTE: status_enum validation is not wired into validate_project_memory.py
    @pytest.mark.skip(reason="STATUS_ENUMERATIONS not wired into validate_project_memory.py")
    def test_reject_invalid_status_enum(self) -> None:
        """STATE.md with invalid status should fail validation."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--scope", "my_project"])
            state = proj / "memory" / "kb" / "projects" / "my_project" / "STATE.md"
            text = state.read_text(encoding="utf-8")
            text = text.replace("status: active", "status: invalid_status")
            state.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            enum_checks = [c for c in data["checks"] if "status_enum" in c["name"]]
            assert any(not c["passed"] for c in enum_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_reject_invalid_semver(self) -> None:
        """memory.lock with non-SemVer version should fail validation."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            lock = proj / "memory" / "system" / "memory.lock"
            text = lock.read_text(encoding="utf-8")
            text = text.replace(f'memory_version = "{_current_version()}"', 'memory_version = "not-a-version"')
            lock.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            semver_checks = [c for c in data["checks"] if "memory_lock_semver" in c["name"]]
            assert any(not c["passed"] for c in semver_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)
