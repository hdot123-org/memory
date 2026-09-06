"""
Tests for memory_core.tools.evolve_cli - CLI skeleton
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest


def test_status_command_exists():
    """Test that status subcommand is recognized"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "status", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "status" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_status_json_output():
    """Test that status --json outputs valid JSON (D6)"""
    # Use temporary evolution root to avoid polluting production
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "MEMORY_CORE_EVOLUTION_ROOT": tmpdir,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        }
        
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "status", "--json"],
            capture_output=True,
            text=True,
            env=env
        )
        
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Should be valid JSON
        try:
            data = json.loads(result.stdout)
            assert "projects" in data
            assert "last_run" in data
            assert "pending_count" in data
            
            # projects should be a list
            assert isinstance(data["projects"], list)
            
            # Each project should have git_root and health
            for proj in data["projects"]:
                assert "git_root" in proj
                assert "health" in proj
                assert proj["health"] in ["active_kb", "no_kb", "missing"]
        except json.JSONDecodeError as e:
            pytest.fail(f"stdout is not valid JSON: {e}\nstdout: {result.stdout}")


def test_status_bogus_arg_exit_2():
    """Test that unknown arguments exit with code 2 (argparse)"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "status", "--bogus"],
        capture_output=True,
        text=True
    )
    
    # argparse should exit with code 2 for unknown arguments
    assert result.returncode == 2
    assert "error" in result.stderr.lower() or "unrecognized" in result.stderr.lower()


def test_backup_paths_command():
    """Test that backup-paths outputs existing memory directories"""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "MEMORY_CORE_EVOLUTION_ROOT": tmpdir,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        }
        
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "backup-paths"],
            capture_output=True,
            text=True,
            env=env
        )
        
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Each line should be a path ending with /memory
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if line.strip():  # skip empty lines
                assert line.endswith("/memory") or line.endswith("\\memory")
                # Path should exist on disk
                assert Path(line).exists()


def test_backup_paths_json_output():
    """Test that backup-paths --json outputs valid JSON array"""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "MEMORY_CORE_EVOLUTION_ROOT": tmpdir,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        }
        
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "backup-paths", "--json"],
            capture_output=True,
            text=True,
            env=env
        )
        
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Should be valid JSON array
        try:
            data = json.loads(result.stdout)
            assert isinstance(data, list)
            
            # Each element should be a string path
            for path in data:
                assert isinstance(path, str)
                assert path.endswith("/memory") or path.endswith("\\memory")
        except json.JSONDecodeError as e:
            pytest.fail(f"stdout is not valid JSON: {e}\nstdout: {result.stdout}")


def test_no_command_shows_help():
    """Test that running without subcommand shows help"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli"],
        capture_output=True,
        text=True
    )
    
    # Should exit with code 2 (usage error)
    assert result.returncode == 2
    # Should show help on stderr
    assert "usage" in result.stderr.lower() or "subcommand" in result.stderr.lower()


def test_global_kb_root_env_override():
    """Test that MEMORY_CORE_GLOBAL_KB_ROOT env overrides default"""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "MEMORY_CORE_GLOBAL_KB_ROOT": tmpdir,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        }
        
        # Test that get_global_kb_root() respects the env
        code = f"""
import sys, os
# Use relative path from current working directory
sys.path.insert(0, os.getcwd())
from memory_core.tools.global_kb_init import get_global_kb_root
from pathlib import Path
root = get_global_kb_root()
print(root)
assert str(root) == '{tmpdir}', f"Expected {tmpdir}, got {{root}}"
"""
        
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env
        )
        
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert tmpdir in result.stdout
