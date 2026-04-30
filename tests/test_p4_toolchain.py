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

TOOLS_DIR = Path(__file__).resolve().parents[1] / "workspace" / "tools"
INIT_SCRIPT = TOOLS_DIR / "init_project_memory.py"
VALIDATE_SCRIPT = TOOLS_DIR / "validate_project_memory.py"
MIGRATE_SCRIPT = TOOLS_DIR / "migrate_project_memory.py"


def _run_script(
    script: Path, args: list[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a tool script and return the result."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(TOOLS_DIR)
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
            memory_root = proj / ".memory"
            for fname in ("memory.lock", "adapter.toml", "CANONICAL.md",
                          "PLAN.md", "STATE.md", "TASKS.md", "migrations.log"):
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
            assert not (proj / ".memory").exists()
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
            (proj / ".memory" / "memory.lock").unlink()
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
            lock_checks = [c for c in data["checks"] if "memory.lock" in c["name"]]
            assert any(not c["passed"] for c in lock_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_missing_canonical(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            (proj / ".memory" / "CANONICAL.md").unlink()
            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data = json.loads(result.stdout)
            assert data["all_passed"] is False
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
            poll_dir = proj / ".memory" / "kb" / "node_modules"
            poll_dir.mkdir()
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
            # Write pollution into CANONICAL.md
            canonical = proj / ".memory" / "CANONICAL.md"
            text = canonical.read_text(encoding="utf-8")
            text += "\nPath reference: /some/project/__pycache__/module.pyc\n"
            canonical.write_text(text, encoding="utf-8")

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
# Migration idempotency
# ---------------------------------------------------------------------------

class TestMigrationIdempotency:
    """Migration tool behavior tests."""

    def test_migrate_dry_run(self) -> None:
        """Migration dry-run should not modify files."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Downgrade version to 0.1.0 so we can test the 0.1.0->0.2.0 migration
            lock_path = proj / ".memory" / "memory.lock"
            lock_data = json.loads(lock_path.read_text())
            lock_data["version"] = "0.1.0"
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
            adapter_path = proj / ".memory" / "adapter.toml"
            adapter_text = adapter_path.read_text(encoding="utf-8")
            adapter_text = adapter_text.replace('version = "0.2.0"', 'version = "0.1.0"')
            adapter_path.write_text(adapter_text, encoding="utf-8")

            result = _run_script(
                MIGRATE_SCRIPT,
                ["--target", str(proj), "--from", "0.1.0", "--to", "0.2.0", "--dry-run", "--json"],
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["success"] is True
            assert data["dry_run"] is True

            # Verify lock file still says 0.1.0
            lock = json.loads((proj / ".memory" / "memory.lock").read_text())
            assert lock["version"] == "0.1.0"
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_migrate_actual(self) -> None:
        """Actual migration should update version and log it."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Downgrade version to 0.1.0 so we can test the 0.1.0->0.2.0 migration
            lock_path = proj / ".memory" / "memory.lock"
            lock_data = json.loads(lock_path.read_text())
            lock_data["version"] = "0.1.0"
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
            adapter_path = proj / ".memory" / "adapter.toml"
            adapter_text = adapter_path.read_text(encoding="utf-8")
            adapter_text = adapter_text.replace('version = "0.2.0"', 'version = "0.1.0"')
            adapter_path.write_text(adapter_text, encoding="utf-8")

            result = _run_script(
                MIGRATE_SCRIPT,
                ["--target", str(proj), "--from", "0.1.0", "--to", "0.2.0", "--json"],
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["success"] is True

            # Verify lock file updated
            lock = json.loads((proj / ".memory" / "memory.lock").read_text())
            assert lock["version"] == "0.2.0"

            # Verify migrations.log has entry
            log = (proj / ".memory" / "migrations.log").read_text()
            assert "0.1.0" in log
            assert "0.2.0" in log
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_migrate_no_path(self) -> None:
        """Migration with no available path should fail."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            result = _run_script(
                MIGRATE_SCRIPT,
                ["--target", str(proj), "--from", "9.9.9", "--to", "0.2.0", "--json"],
            )
            data = json.loads(result.stdout)
            assert data["success"] is False
            assert len(data["errors"]) > 0
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_migrate_version_mismatch(self) -> None:
        """Migration with wrong --from version should fail."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            result = _run_script(
                MIGRATE_SCRIPT,
                ["--target", str(proj), "--from", "0.0.1", "--to", "0.2.0", "--json"],
            )
            data = json.loads(result.stdout)
            assert data["success"] is False
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


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
            lock = proj / ".memory" / "memory.lock"
            data = json.loads(lock.read_text())
            data["version"] = "9.9.9"
            lock.write_text(json.dumps(data, indent=2), encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data_out = json.loads(result.stdout)
            assert data_out["all_passed"] is False
            version_checks = [c for c in data_out["checks"] if "lock_version" in c["name"]]
            assert any(not c["passed"] for c in version_checks)
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_wrong_adapter_version(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Tamper with adapter version
            adapter = proj / ".memory" / "adapter.toml"
            text = adapter.read_text(encoding="utf-8")
            text = text.replace('version = "0.2.0"', 'version = "9.9.9"')
            adapter.write_text(text, encoding="utf-8")

            result = _run_script(VALIDATE_SCRIPT, ["--target", str(proj), "--json"])
            data_out = json.loads(result.stdout)
            assert data_out["all_passed"] is False
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Frontmatter validation
# ---------------------------------------------------------------------------

class TestFrontmatterValidation:
    """Validator must check frontmatter fields."""

    def test_missing_frontmatter_field(self) -> None:
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            # Remove frontmatter from CANONICAL.md
            canonical = proj / ".memory" / "CANONICAL.md"
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
            adapter = (proj / ".memory" / "adapter.toml").read_text()
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
            adapter = (proj / ".memory" / "adapter.toml").read_text()
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
            adapter = (proj / ".memory" / "adapter.toml").read_text()
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
            adapter = (proj / ".memory" / "adapter.toml").read_text()
            assert 'project_scope = "my_awesome_project"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

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
            adapter = (proj / ".memory" / "adapter.toml").read_text()
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
            adapter = (proj / ".memory" / "adapter.toml").read_text()
            assert 'project_scope = "explicit_scope"' in adapter
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)


# ---------------------------------------------------------------------------
# Hooks and AGENTS.md generation
# ---------------------------------------------------------------------------

class TestHooksAndAgentsMdGeneration:
    """Test .claude/hooks.json and AGENTS.md generation during init."""

    def test_hooks_json_created_with_4_events(self) -> None:
        """Init should create .claude/hooks.json with 4 hook events."""
        proj = _make_temp_project()
        try:
            result = _run_script(INIT_SCRIPT, ["--target", str(proj), "--json"])
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["success"] is True

            hooks_path = proj / ".claude" / "hooks.json"
            assert hooks_path.is_file(), "hooks.json not created"

            hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
            assert "hooks" in hooks_data
            assert len(hooks_data["hooks"]) == 4

            # Verify all expected events are present
            events = {h["event"] for h in hooks_data["hooks"]}
            assert events == {"SessionStart", "UserPromptSubmit", "Notification", "Stop"}

            # Verify each hook has command and stdin
            for hook in hooks_data["hooks"]:
                assert "command" in hook
                assert "memory-hook-gateway" in hook["command"]
                assert hook.get("stdin") is True
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

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
            assert "memory_hook_gateway" in content
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

    def test_hooks_json_idempotent_no_duplicate(self) -> None:
        """Running init twice should not duplicate hook entries."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            hooks_path = proj / ".claude" / "hooks.json"
            data1 = json.loads(hooks_path.read_text(encoding="utf-8"))
            count1 = len(data1["hooks"])

            # Run again
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            data2 = json.loads(hooks_path.read_text(encoding="utf-8"))
            count2 = len(data2["hooks"])

            assert count1 == 4
            assert count2 == 4
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_host_claude_generates_hooks_json(self) -> None:
        """--host claude should generate hooks.json with claude host in commands."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--host", "claude", "--json"])
            hooks_path = proj / ".claude" / "hooks.json"
            data = json.loads(hooks_path.read_text(encoding="utf-8"))

            for hook in data["hooks"]:
                assert "--host claude" in hook["command"]
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_host_codex_generates_agents_md(self) -> None:
        """--host codex should generate AGENTS.md with codex host."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj), "--host", "codex", "--json"])
            agents_path = proj / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")
            assert "--host codex" in content
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

    def test_hooks_json_merges_with_existing_hooks(self) -> None:
        """Init should append memory hooks to existing hooks.json without removing others."""
        proj = _make_temp_project()
        try:
            hooks_path = proj / ".claude" / "hooks.json"
            existing = {
                "hooks": [
                    {"event": "CustomEvent", "command": "custom-cmd", "stdin": False}
                ]
            }
            hooks_path.parent.mkdir(parents=True, exist_ok=True)
            hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            data = json.loads(hooks_path.read_text(encoding="utf-8"))

            # Should have original + 4 memory hooks
            assert len(data["hooks"]) == 5
            custom_hooks = [h for h in data["hooks"] if h["event"] == "CustomEvent"]
            assert len(custom_hooks) == 1
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)

    def test_default_host_is_codex(self) -> None:
        """Default host should be codex."""
        proj = _make_temp_project()
        try:
            _run_script(INIT_SCRIPT, ["--target", str(proj)])
            agents_path = proj / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")
            assert "--host codex" in content
        finally:
            import shutil
            shutil.rmtree(proj, ignore_errors=True)
