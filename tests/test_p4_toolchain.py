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
            text = text.replace('version = "0.1.0"', 'version = "9.9.9"')
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
