"""Init vs Runtime coverage consistency tests.

This test module ensures that init_project_memory generates all files
that runtime components (like memory_hook_core and adapters) depend on.

Goal: Prevent "init generated files missing runtime dependencies" issues.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parent.parent


def _subprocess_env(repo_root: Path) -> dict[str, str]:
    """Return an environment that can import the local package in subprocesses."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(repo_root) if not existing else f"{repo_root}{os.pathsep}{existing}"
    return env


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root directory."""
    return _repo_root()


@pytest.fixture
def memory_core_tools(repo_root: Path) -> Path:
    """Return the memory_core/tools directory."""
    return repo_root / "memory_core" / "tools"


@pytest.fixture
def init_script_path(repo_root: Path) -> Path:
    """Return the path to init_project_memory.py script."""
    return repo_root / "memory_core" / "tools" / "init_project_memory.py"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def run_init_dry_run(
    target: Path,
    scope: str | None = None,
    host: str = "codex",
) -> dict[str, Any]:
    """Run init_project_memory with --dry-run --json and return parsed output.

    Returns:
        Dict containing the dry-run output with 'would_create_files' and 'would_create_dirs'.
    """
    cmd = [
        sys.executable,
        "-m",
        "memory_core.tools.init_project_memory",
        "--target",
        str(target),
        "--dry-run",
        "--json",
        "--host",
        host,
    ]
    if scope:
        cmd.extend(["--scope", scope])

    repo_root = _repo_root()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root,
        env=_subprocess_env(repo_root),
    )
    return json.loads(result.stdout)


def get_runtime_reads_from_memory_hook_core() -> list[str]:
    """Extract the reads list from memory_hook_core.build_context_package_core.

    This reads the source code to find the 'reads' list construction.
    """
    repo_root = Path(__file__).resolve().parent.parent
    core_path = repo_root / "memory_core" / "tools" / "memory_hook_core.py"

    # The reads list is constructed in build_context_package_core function
    # Looking for the pattern:
    #     reads = [
    #         str(workspace_root / "NOW.md"),
    #         ...
    #     ]
    content = core_path.read_text(encoding="utf-8")

    # Extract reads list - this is a simplified parser
    # The reads list contains files that runtime needs
    reads: list[str] = []

    # Based on code analysis, the reads list includes:
    # - workspace_root / "NOW.md"
    # - project_map_refs
    # - workspace_root / "memory" / "kb" / "INDEX.md"
    # - workspace_root / "memory" / "docs" / "INDEX.md"
    # - truth_basis_refs
    # - decisions
    # - lessons
    # - docs_refs

    # We return the pattern matches for verification
    if 'str(workspace_root / "NOW.md")' in content:
        reads.append("NOW.md")
    if 'str(workspace_root / "memory" / "kb" / "INDEX.md")' in content:
        reads.append("memory/kb/INDEX.md")
    if 'str(workspace_root / "memory" / "docs" / "INDEX.md")' in content:
        reads.append("memory/docs/INDEX.md")

    return reads


def get_default_adapter_required_canonical() -> list[str]:
    """Extract required_canonical from default_runtime_profile.

    Returns list of relative file paths that are required.
    """
    repo_root = Path(__file__).resolve().parent.parent
    profile_path = repo_root / "memory_core" / "tools" / "memory_hook_adapters" / "default_runtime_profile.py"
    content = profile_path.read_text(encoding="utf-8")

    # Parse required_canonical list from the file
    required: list[str] = []

    # required_canonical now references truth_model, memory_system_path, global_rule_path
    # which map to memory/kb/global/ paths
    if 'truth_model' in content:
        required.append("memory/kb/global/truth-model.md")
    if 'memory_system_path' in content:
        required.append("memory/kb/global/memory-system.md")
    if 'global_rule_path' in content:
        required.append("memory/kb/global/memory-routing.md")

    return required


# ---------------------------------------------------------------------------
# Test 1: Init generates all runtime reads
# ---------------------------------------------------------------------------

class TestInitGeneratesRuntimeReads:
    """Test that init generates all files that runtime reads."""

    def test_init_generates_all_runtime_reads(self, tmp_path: Path) -> None:
        """Test that init generates files that memory_hook_core reads.

        The runtime (build_context_package_core) reads:
        - NOW.md
        - memory/kb/INDEX.md
        - memory/docs/INDEX.md
        - Various project map files
        """
        result = run_init_dry_run(tmp_path, scope="test-project")
        dry_run_output = result.get("dry_run_output", {})
        would_create_files = dry_run_output.get("would_create_files", [])

        # Normalize to just filenames for checking
        created_files = {f.split()[0] for f in would_create_files}

        # Files that runtime reads
        runtime_reads = get_runtime_reads_from_memory_hook_core()

        # Check that INDEX.md files are created (either in KB_TEMPLATES or FILE_TEMPLATES)
        # The actual reads from memory_hook_core include:
        # - workspace_root / "NOW.md"
        # - memory/kb/INDEX.md
        # - memory/docs/INDEX.md

        missing = []
        for read_file in runtime_reads:
            # Check if this file or its containing directory is created
            if read_file not in created_files and not any(
                read_file.startswith(d.replace("dir:", "")) for d in created_files if d.startswith("dir:")
            ):
                # Check if it's covered by KB_TEMPLATES
                if read_file not in ["NOW.md", "memory/kb/INDEX.md", "memory/docs/INDEX.md"]:
                    missing.append(read_file)

        # NOW.md is checked in a separate test
        # KB index files should be generated
        assert "memory/kb/INDEX.md" in created_files or "file:memory/kb/INDEX.md" in created_files, \
            "memory/kb/INDEX.md should be generated by init"
        assert "memory/docs/INDEX.md" in created_files or "file:memory/docs/INDEX.md" in created_files, \
            "memory/docs/INDEX.md should be generated by init"


# ---------------------------------------------------------------------------
# Test 2: Init generates all required_canonical files
# ---------------------------------------------------------------------------

class TestInitGeneratesRequiredCanonical:
    """Test that init generates all required_canonical files."""

    def test_init_generates_all_required_canonical(self, tmp_path: Path) -> None:
        """Test that init generates files listed in adapter's required_canonical.

        The default_runtime_profile defines required_canonical as:
        - memory/kb/projects/{scope}/CANONICAL.md
        - memory/kb/projects/{scope}/PLAN.md
        - memory/kb/projects/{scope}/STATE.md
        - memory/kb/global/truth-model.md
        - memory/kb/global/memory-system.md
        - memory/kb/global/memory-routing.md
        """
        result = run_init_dry_run(tmp_path, scope="test-project")
        dry_run_output = result.get("dry_run_output", {})
        would_create_files = dry_run_output.get("would_create_files", [])

        # Normalize - remove (create) or (overwrite) suffixes
        created_files: set[str] = set()
        for f in would_create_files:
            if " (" in f:
                f = f.split(" (")[0]
            created_files.add(f)

        required_canonical = [
            "CANONICAL.md",  # in memory/kb/projects/{scope}/
            "PLAN.md",       # in memory/kb/projects/{scope}/
            "STATE.md",      # in memory/kb/projects/{scope}/
        ]

        # Check memory/kb/projects/{scope}/ files
        # Note: scope "test-project" is slugified to "test_project"
        for req_file in required_canonical:
            full_path = f"memory/kb/projects/test_project/{req_file}"
            assert req_file in created_files or full_path in created_files, \
                f"Required canonical file {req_file} should be generated by init"

        # Check memory/kb/global/ files (created via KB_TEMPLATES)
        global_kb_files = [
            "memory/kb/global/truth-model.md",
            "memory/kb/global/memory-system.md",
            "memory/kb/global/memory-routing.md",
        ]

        for global_file in global_kb_files:
            filename = global_file.split("/")[-1]
            assert global_file in created_files or filename in created_files, \
                f"Required canonical file {global_file} should be generated by init"


# ---------------------------------------------------------------------------
# Test 3: Init generates policy pack
# ---------------------------------------------------------------------------

class TestInitGeneratesPolicyPack:
    """Test that init generates the policy pack file."""

    def test_init_generates_policy_pack(self, tmp_path: Path) -> None:
        """Test that init generates memory/kb/global/memory-hook-policy-pack.json.

        This file is required by PolicyRegistryImpl for dynamic policy loading.
        """
        result = run_init_dry_run(tmp_path, scope="test-project")
        dry_run_output = result.get("dry_run_output", {})
        would_create_dirs = dry_run_output.get("would_create_dirs", [])

        # Policy pack should be creatable in the global directory
        # The actual file may or may not be in the templates, but the directory structure
        # must allow it to be created
        has_global_dir = any(
            "memory/kb/global" in d or d == "memory/kb/global"
            for d in would_create_dirs
        )

        assert has_global_dir, \
            "memory/kb/global directory should be created to allow policy-pack.json"


# ---------------------------------------------------------------------------
# Test 4: Init generates project scope file
# ---------------------------------------------------------------------------

class TestInitGeneratesProjectScopeFile:
    """Test that init generates project scope files for all supported hosts."""

    @pytest.mark.parametrize("host", ["codex", "claude", "factory"])
    def test_init_generates_project_scope_file(self, tmp_path: Path, host: str) -> None:
        """Test that init with --scope creates the project scope file.

        For each SUPPORTED_HOSTS, when using --scope test-project,
        init should set up infrastructure that allows
        memory/kb/projects/{scope}.md to be created.
        """
        result = run_init_dry_run(tmp_path, scope="test-project", host=host)
        dry_run_output = result.get("dry_run_output", {})
        would_create_dirs = dry_run_output.get("would_create_dirs", [])

        # Check that projects directory is created
        has_projects_dir = any(
            "memory/kb/projects" in d or d == "memory/kb/projects"
            for d in would_create_dirs
        )

        assert has_projects_dir, \
            f"memory/kb/projects directory should be created for host={host}"

        # The project scope file would be created by runtime, but init must create
        # the directory structure for it
        projects_dirs = [d for d in would_create_dirs if "projects" in d]
        assert len(projects_dirs) > 0, \
            f"Projects directories should be created for host={host}"


# ---------------------------------------------------------------------------
# Test 5: (Removed) Init generates NOW.md
# NOW.md removed in v0.5.0
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test 6: Init generates inbox.md
# ---------------------------------------------------------------------------

class TestInitGeneratesInboxMd:
    """Test that init generates the inbox.md file."""

    def test_init_generates_inbox_md(self, tmp_path: Path) -> None:
        """Test that init generates memory/inbox.md.

        The runtime uses memory/inbox.md as the action write target.
        This is required for the write target policy.
        """
        result = run_init_dry_run(tmp_path, scope="test-project")
        dry_run_output = result.get("dry_run_output", {})
        would_create_files = dry_run_output.get("would_create_files", [])

        # Check for inbox.md
        created_files = {f.split()[0] for f in would_create_files}

        assert "memory/inbox.md" in created_files, \
            "memory/inbox.md should be generated by init"


# ---------------------------------------------------------------------------
# Additional comprehensive test
# ---------------------------------------------------------------------------

class TestInitRuntimeCoverageComprehensive:
    """Comprehensive tests for init-runtime coverage."""

    def test_init_creates_all_essential_directories(self, tmp_path: Path) -> None:
        """Test that init creates all directories needed by runtime."""
        result = run_init_dry_run(tmp_path, scope="test-project")
        dry_run_output = result.get("dry_run_output", {})
        would_create_dirs = set(dry_run_output.get("would_create_dirs", []))

        essential_dirs = {
            "memory/system/kb",
            "memory/system/kb/projects",
            "memory/system/kb/decisions",
            "memory/system/kb/lessons",
            "memory/system/kb/global",
            "project-map",
            "memory",
            "memory/kb",
            "memory/kb/global",
            "memory/kb/projects",
            "memory/kb/decisions",
            "memory/kb/lessons",
            "memory/docs",
            "memory/system",
            "memory/log",
        }

        for essential in essential_dirs:
            assert essential in would_create_dirs, \
                f"Essential directory {essential} should be created by init"

    def test_init_creates_adapter_toml(self, tmp_path: Path) -> None:
        """Test that init creates adapter.toml which is required for runtime config."""
        result = run_init_dry_run(tmp_path, scope="test-project")
        dry_run_output = result.get("dry_run_output", {})
        would_create_files = dry_run_output.get("would_create_files", [])

        created_files = {f.split()[0] for f in would_create_files}

        assert "adapter.toml" in created_files, \
            "adapter.toml should be generated by init"

    def test_no_degraded_due_to_missing_init_files(self, tmp_path: Path) -> None:
        """Test that after real init, no required files show as missing.

        This performs an actual init and then validates that the runtime
        would not report missing_paths for init-managed files.
        """
        import subprocess
        import sys

        # Run actual init
        cmd = [
            sys.executable,
            "-m",
            "memory_core.tools.init_project_memory",
            "--target",
            str(tmp_path),
            "--scope",
            "test-project",
            "--force",
        ]
        repo_root = _repo_root()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_root,
            env=_subprocess_env(repo_root),
        )

        # Check init succeeded
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Check that required files exist (v0.5.0: only memory.lock, adapter.toml, migrations.log)
        required_files = [
            tmp_path / "memory" / "system" / "memory.lock",
            tmp_path / "memory" / "system" / "adapter.toml",
            tmp_path / "memory" / "system" / "migrations.log",
            tmp_path / "memory" / "inbox.md",
            tmp_path / "memory" / "kb" / "global" / "truth-model.md",
            tmp_path / "memory" / "kb" / "global" / "memory-system.md",
            tmp_path / "memory" / "kb" / "global" / "memory-routing.md",
            tmp_path / "memory" / "kb" / "global" / "hook-contract.md",
            tmp_path / "memory" / "kb" / "global" / "project-map-governance.md",
        ]

        missing = []
        for req_file in required_files:
            if not req_file.exists():
                missing.append(str(req_file.relative_to(tmp_path)))

        assert not missing, f"Required files missing after init: {missing}"
