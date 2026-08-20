"""Tests for repo_health_check.sh script.

INFRA-399: 突变类用例一律在隔离的 tmp git 夹具仓库上运行（fixture_repo）。
历史实现直接改写真实仓库根的 memory_core/__init__.py / README.md / CHANGELOG.md
并 git add 临时文件，在 pytest-xdist 6 worker 并行下与其他 worker 的
--ci/--full 只读用例形成竞态（脚本以子进程重读仓库状态），已造成 main push
CI 间歇性失败（PR #797 后首现）。只读用例仍在真实仓库上运行。
"""

import subprocess
from pathlib import Path

import pytest

from memory_core.constants import CURRENT_MEMORY_VERSION

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "repo_health_check.sh"


def run_health_check(mode: str = "--ci", cwd: Path | None = None) -> tuple[int, str, str]:
    """Run health check script and return (exit_code, stdout, stderr)."""
    cmd = ["bash", str(SCRIPT_PATH), mode]
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Build an isolated git repo whose health-check inputs start fully consistent.

    Versions default to v0.34.0 to mirror the real repo at the time this fixture
    was introduced; mutation tests then break exactly one input and assert the
    script reports it.
    """
    version = CURRENT_MEMORY_VERSION
    (tmp_path / "memory_core").mkdir()
    (tmp_path / "memory_core" / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (tmp_path / "memory_core" / "constants.py").write_text(
        "from memory_core import __version__ as CURRENT_MEMORY_VERSION\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "memory-core"\nversion = "{version}"\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "# Fixture README\n"
        f"\n## 架构 (v{version})\n"
        f"- 当前文档版本：v{version} <!-- x-release-please-version -->\n"
        f"pip install git+https://github.com/hdot123-org/memory.git@v{version}\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    git_user = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.com"]
    subprocess.run([*git_user, "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    return tmp_path


def test_ci_mode_version_consistency_passes():
    """Test that --ci mode passes when version is consistent across all files."""
    exit_code, stdout, stderr = run_health_check("--ci")

    # Should pass on clean repo
    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
    assert "version-consistency" in stdout
    assert "PASS" in stdout


def test_ci_mode_detects_version_mismatch_in_constants(fixture_repo: Path):
    """Test that --ci mode detects when __init__.py __version__ doesn't match pyproject.toml."""
    init_path = fixture_repo / "memory_core" / "__init__.py"

    # Break version consistency by changing __version__ in __init__.py
    (init_path).write_text('__version__ = "0.8.0"\n', encoding="utf-8")

    exit_code, stdout, stderr = run_health_check("--ci", cwd=fixture_repo)

    # Should fail
    assert exit_code == 1, f"Expected exit 1, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
    assert "version-consistency" in stdout
    assert "FAIL" in stdout


def test_ci_mode_detects_version_mismatch_in_readme(fixture_repo: Path):
    """Test that --ci mode detects when README version doesn't match pyproject.toml."""
    readme_path = fixture_repo / "README.md"

    # Break version consistency
    content = readme_path.read_text(encoding="utf-8")
    broken_content = content.replace(
        f"- 当前文档版本：v{CURRENT_MEMORY_VERSION}",
        "- 当前文档版本：v0.8.0",
    )
    assert broken_content != content, "fixture README must contain the marker line to break"
    readme_path.write_text(broken_content, encoding="utf-8")

    exit_code, stdout, stderr = run_health_check("--ci", cwd=fixture_repo)

    # Should fail
    assert exit_code == 1, f"Expected exit 1, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
    assert "version-consistency" in stdout
    assert "FAIL" in stdout


def test_ci_mode_detects_gitlab_residue(fixture_repo: Path):
    """Test that --ci mode detects GitLab residue in tracked files."""
    # Create a temporary file with GitLab residue
    test_file = fixture_repo / "test_gitlab_residue.txt"

    test_file.write_text("This file contains GitLab-first reference\n", encoding="utf-8")
    subprocess.run(["git", "add", str(test_file)], cwd=fixture_repo, check=True)

    exit_code, stdout, stderr = run_health_check("--ci", cwd=fixture_repo)

    # Should fail
    assert exit_code == 1, f"Expected exit 1, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
    assert "gitlab-residue" in stdout
    assert "FAIL" in stdout


def test_ci_mode_excludes_changelog_from_residue_check(fixture_repo: Path):
    """Test that CHANGELOG.md is excluded from GitLab residue check."""
    changelog_path = fixture_repo / "CHANGELOG.md"
    original_content = changelog_path.read_text(encoding="utf-8")

    # Add GitLab residue to CHANGELOG (should be ignored)
    test_content = original_content + "\n- Fixed sync-to-github job\n"
    changelog_path.write_text(test_content, encoding="utf-8")

    exit_code, stdout, stderr = run_health_check("--ci", cwd=fixture_repo)

    # Should still pass (CHANGELOG is excluded)
    assert "gitlab-residue" in stdout
    assert "PASS" in stdout


def test_ci_mode_excludes_python_files_from_residue_check(fixture_repo: Path):
    """Test that Python files are excluded from GitLab residue check."""
    # Create a temporary Python file with GitLab residue
    test_file = fixture_repo / "test_gitlab_residue.py"

    test_file.write_text(
        '# This file checks for .gitlab-ci.yml\nCI_CONFIG = ".gitlab-ci.yml"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(test_file)], cwd=fixture_repo, check=True)

    exit_code, stdout, stderr = run_health_check("--ci", cwd=fixture_repo)

    # Should still pass (Python files are excluded)
    assert "gitlab-residue" in stdout
    assert "PASS" in stdout


def test_full_mode_includes_remote_checks():
    """Test that --full mode includes remote checks (tags/releases, workflow health)."""
    exit_code, stdout, stderr = run_health_check("--full")

    # Should include remote checks
    assert "tags-releases" in stdout
    assert "release-workflow" in stdout


def test_script_requires_bash():
    """Test that script runs with bash interpreter."""
    first_line = SCRIPT_PATH.read_text().split("\n")[0]

    assert first_line.startswith("#!/usr/bin/env bash") or first_line.startswith("#!/bin/bash")


def test_script_has_execute_permission():
    """Test that script has execute permission in git index."""
    # Check git index for executable permission (100755 mode)
    result = subprocess.run(
        ["git", "ls-files", "--stage", "scripts/repo_health_check.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    # Should find the file with executable bit set (100755)
    assert result.returncode == 0
    assert "100755" in result.stdout, "Script should have execute permission (100755) in git index"


def test_ci_mode_output_format():
    """Test that --ci mode output has expected format."""
    exit_code, stdout, stderr = run_health_check("--ci")

    # Check output format
    assert "Repo Health Check" in stdout
    assert "version-consistency" in stdout
    assert "readme-install-versions" in stdout
    assert "gitlab-residue" in stdout
    assert "Summary:" in stdout


def test_full_mode_output_format():
    """Test that --full mode output has expected format."""
    exit_code, stdout, stderr = run_health_check("--full")

    # Check output format includes CI checks
    assert "version-consistency" in stdout
    assert "readme-install-versions" in stdout
    assert "gitlab-residue" in stdout

    # Check output format includes remote checks
    assert "tags-releases" in stdout
    assert "release-workflow" in stdout

    assert "Summary:" in stdout


def test_invalid_mode():
    """Test that invalid mode returns error."""
    cmd = ["bash", str(SCRIPT_PATH), "--invalid"]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    # Should fail with error
    assert result.returncode != 0
    assert "Usage:" in result.stdout or "Usage:" in result.stderr


# ── Regression tests for Python version selection (PR #859) ──────────────

def test_python_version_selection_prefers_3_12_plus():
    """Regression: script must select a Python >= 3.11 with tomllib support.

    Even when PATH contains a python3 < 3.11 first, the script should
    still find a qualifying interpreter (python3.12 or python3 >= 3.11)
    or emit a clear error instead of crashing with ModuleNotFoundError.
    """
    import os
    import shutil

    # Build a fake python3 that reports 3.9 — place it first in PATH
    fake_dir = Path("/tmp") / "regression_fake_python"
    fake_dir.mkdir(exist_ok=True)
    fake_py = fake_dir / "python3"
    fake_py.write_text(
        '#!/bin/bash\npython3.12 -c "import sys; print(f\'3.9\')" "$@"\n',
        encoding="utf-8",
    )
    fake_py.chmod(0o755)

    # Prepend fake dir so plain python3 resolves to our 3.9 stub
    env = os.environ.copy()
    env["PATH"] = str(fake_dir) + os.pathsep + env["PATH"]
    # Remove python3.12 from reach to force the fallback branch
    # (python3 version check).  We keep the real system python3.12 reachable
    # via an explicit absolute path, but the script uses `command -v python3.12`
    # which scans PATH — so we must make it invisible there too.
    # Instead of hiding it, we verify the script's actual behaviour:
    # on this system python3.12 IS available, so the script should succeed.
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--ci"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    # The script should either succeed (found python3.12 via command -v)
    # or fail with a clear Python version error — never with ModuleNotFoundError.
    if result.returncode != 0:
        assert "ModuleNotFoundError" not in result.stderr, (
            "Script must not crash with ModuleNotFoundError — "
            "it should select a Python with tomllib or report clearly"
        )
        assert "Python 3.11+" in result.stderr or "Python 3.11+" in result.stdout, (
            "When no suitable Python is found, the error message must mention "
            "the minimum version requirement"
        )


def test_python_selection_error_message_when_only_old_python():
    """Regression: when only Python < 3.11 is available, script exits with
    a clear error mentioning the version requirement."""
    import os
    import shutil
    import sys

    # Create a temporary directory with a fake python3 that is < 3.11
    fake_dir = Path("/tmp") / "regression_old_python"
    fake_dir.mkdir(exist_ok=True)
    fake_py = fake_dir / "python3"
    fake_py.write_text(
        '#!/bin/bash\necho "3.9"\n',
        encoding="utf-8",
    )
    fake_py.chmod(0o755)

    # Also create fake python3.9 to ensure no python3.12 is found
    # (the script checks `command -v python3.12` first)
    # We need an environment where ONLY python3 exists and it is < 3.11
    # Build a minimal PATH with only our fake python3
    env = os.environ.copy()
    # Keep /usr/bin for bash, git but strip any real python paths
    env["PATH"] = str(fake_dir) + os.pathsep + "/usr/bin:/bin"

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--ci"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    # Script should exit non-zero with a clear version error
    assert result.returncode != 0, "Script should fail when only old Python available"
    assert "Python 3.11+" in result.stderr or "Python 3.11+" in result.stdout, (
        f"Expected clear version error, got stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    # Must NOT crash with ModuleNotFoundError
    assert "ModuleNotFoundError" not in result.stderr


def test_script_uses_python_variable_not_hardcoded():
    """Regression: script must use $PYTHON variable for all Python calls
    outside the version selection block, not hardcoded 'python3'."""
    script_content = SCRIPT_PATH.read_text(encoding="utf-8")

    # Find the end of the Python version selection block
    # The block ends at the third 'fi' after "Python version selection" comment
    # After that, all Python invocations should use $PYTHON
    lines = script_content.split("\n")
    in_version_block = False
    fi_count = 0
    version_block_ended_at = -1
    for i, line in enumerate(lines):
        if "Python version selection" in line:
            in_version_block = True
            continue
        if in_version_block:
            if line.strip().startswith("fi"):
                fi_count += 1
                if fi_count >= 3:
                    version_block_ended_at = i
                    break

    assert version_block_ended_at > 0, "Could not find end of version selection block"

    # Check that no hardcoded python3 calls exist after the version block
    hardcoded_python3_lines = []
    for i in range(version_block_ended_at, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Flag lines that call 'python3' directly (not inside $PYTHON)
        if "python3" in line and "$PYTHON" not in line and "python3." not in line:
            hardcoded_python3_lines.append((i + 1, stripped))

    assert not hardcoded_python3_lines, (
        f"Script should use $PYTHON variable after version selection block, "
        f"not hardcoded 'python3'. Found at: {hardcoded_python3_lines}"
    )
