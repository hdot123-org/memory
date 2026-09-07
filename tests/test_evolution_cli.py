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
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "status", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "status" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_status_json_output():
    """Test that status --json outputs valid JSON (D6)"""
    # Use temporary evolution root to avoid polluting production
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"MEMORY_CORE_EVOLUTION_ROOT": tmpdir, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "status", "--json"],
            capture_output=True,
            text=True,
            env=env,
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
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "status", "--bogus"], capture_output=True, text=True
    )

    # argparse should exit with code 2 for unknown arguments
    assert result.returncode == 2
    assert "error" in result.stderr.lower() or "unrecognized" in result.stderr.lower()


def test_backup_paths_command():
    """Test that backup-paths outputs existing memory directories"""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"MEMORY_CORE_EVOLUTION_ROOT": tmpdir, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "backup-paths"],
            capture_output=True,
            text=True,
            env=env,
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
        env = {"MEMORY_CORE_EVOLUTION_ROOT": tmpdir, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "backup-paths", "--json"],
            capture_output=True,
            text=True,
            env=env,
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
    result = subprocess.run([sys.executable, "-m", "memory_core.tools.evolve_cli"], capture_output=True, text=True)

    # Should exit with code 2 (usage error)
    assert result.returncode == 2
    # Should show help on stderr
    assert "usage" in result.stderr.lower() or "subcommand" in result.stderr.lower()


def test_global_kb_root_env_override():
    """Test that MEMORY_CORE_GLOBAL_KB_ROOT env overrides default"""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"MEMORY_CORE_GLOBAL_KB_ROOT": tmpdir, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}

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

        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert tmpdir in result.stdout


def test_script_bootstrap_from_root_cwd():
    """
    Test that evolve_cli.py can be called directly from cwd=/ (launchd environment).

    launchd runs with cwd=/ and no PYTHONPATH, so the script must bootstrap
    sys.path to find the memory_core package. This test verifies the bootstrap works.
    """
    # Derive script path relative to test file (no hardcoded /Users/ paths)
    test_file = Path(__file__).resolve()
    repo_root = test_file.parents[1]
    script_path = repo_root / "memory_core" / "tools" / "evolve_cli.py"

    # Call script directly from cwd=/ (simulating launchd environment)
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd="/",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, f"Script failed from cwd=/: {result.stderr}"
    assert "usage" in result.stdout.lower() or "memory-evolve" in result.stdout.lower()
    assert "run" in result.stdout  # Should list run subcommand


def _setup_dirty_git_repo(tmpdir: Path) -> None:
    """Helper: create a minimal git repo with fix/audit-round2 branch and dirty working tree."""
    # Init repo
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, check=True)

    # Create initial commit on main
    (tmpdir / "README.md").write_text("# Test KB\n")
    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True, check=True)

    # Create fix/audit-round2 branch with a commit
    subprocess.run(["git", "checkout", "-b", "fix/audit-round2"], cwd=tmpdir, capture_output=True, check=True)
    (tmpdir / "fix-file.md").write_text("# Fix content\n")
    subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "fix branch commit"], cwd=tmpdir, capture_output=True, check=True)

    # Go back to main and make the worktree dirty
    subprocess.run(["git", "checkout", "main"], cwd=tmpdir, capture_output=True, check=True)
    # Make dirty: create an untracked file
    (tmpdir / "dirty-file.md").write_text("# Dirty content from other session\n")


def test_gk_ensure_dirty_root_without_flag_aborts():
    """
    D8 default: dirty root + no --adopt-dirty → exit 1, worktree preserved.
    Verifies VAL-SED-004 backward compatibility.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        _setup_dirty_git_repo(tmpdir_path)

        # Verify dirty before running gk-ensure
        status_before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=tmpdir_path, capture_output=True, text=True, check=True
        )
        assert status_before.stdout.strip(), "Precondition: repo should be dirty"
        assert "dirty-file.md" in status_before.stdout

        # Run gk-ensure WITHOUT --adopt-dirty
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "gk-ensure", "--global-kb-root", tmpdir],
            capture_output=True,
            text=True,
        )

        # Should exit 1
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}. stderr={result.stderr}"

        # Worktree should still be dirty (unchanged)
        status_after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=tmpdir_path, capture_output=True, text=True, check=True
        )
        assert status_after.stdout.strip(), "Postcondition: worktree should still be dirty"
        assert "dirty-file.md" in status_after.stdout

        # Should still be on main branch (not switched)
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=tmpdir_path, capture_output=True, text=True, check=True
        )
        assert branch.stdout.strip() == "main"


def test_gk_ensure_dirty_root_with_adopt_flag_commits_and_continues():
    """
    --adopt-dirty: dirty root → git add -A + commit → worktree clean → continue merge.
    Verifies the new maintenance mode works end-to-end.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        _setup_dirty_git_repo(tmpdir_path)

        # Run gk-ensure WITH --adopt-dirty
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.evolve_cli",
                "gk-ensure",
                "--global-kb-root",
                tmpdir,
                "--adopt-dirty",
            ],
            capture_output=True,
            text=True,
        )

        # Should exit 0 (adopted dirty + merged)
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}. stderr={result.stderr}"

        # Worktree should be clean now
        status_after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=tmpdir_path, capture_output=True, text=True, check=True
        )
        assert not status_after.stdout.strip(), f"Worktree should be clean, but got: {status_after.stdout}"

        # The dirty file should have been committed (check git log)
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"], cwd=tmpdir_path, capture_output=True, text=True, check=True
        )
        assert "维护" in log.stdout or "采纳脏工作区" in log.stdout, f"Expected maintenance commit in log: {log.stdout}"

        # Should be on main branch
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=tmpdir_path, capture_output=True, text=True, check=True
        )
        assert branch.stdout.strip() == "main", f"Should be on main, got {branch.stdout.strip()}"

        # The dirty file content should still exist (preserved, not lost)
        assert (tmpdir_path / "dirty-file.md").exists(), "dirty-file.md should be preserved after adopt"
        assert (tmpdir_path / "dirty-file.md").read_text() == "# Dirty content from other session\n", (
            "File content should be preserved verbatim"
        )


# ===== 回归守卫：mcp-secret 子命令存在性（1ff55d9 merge 丢块热修） =====

EXPECTED_SUBCOMMANDS = {"run", "status", "backup-paths", "gk-ensure", "mcp-secret"}


def test_subcommand_set_complete():
    """回归守卫：--help 输出必须恰含五个子命令（任何 merge 丢块或多出子命令必红）"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--help failed: {result.stderr}"
    help_text = result.stdout

    # 恰含等值断言：子命令集合必须精确等于期望集合
    # 任何缺失或多余子命令都意味着回归或意外变更
    missing_commands = []
    for cmd in EXPECTED_SUBCOMMANDS:
        if cmd not in help_text:
            missing_commands.append(cmd)

    # 检查是否有多余的子命令
    import re

    # 过滤出子命令区域（在 "commands:" 之后）
    commands_section = re.search(r"commands:\s*\n((?:\s+\S+\s+.*\n)+)", help_text)
    if commands_section:
        actual_commands = set(re.findall(r"^\s+(\S+)", commands_section.group(1), re.MULTILINE))
        extra_commands = actual_commands - EXPECTED_SUBCOMMANDS
    else:
        extra_commands = set()

    assert not missing_commands, f"子命令缺失: {missing_commands}（merge 丢块回归）"
    assert not extra_commands, f"子命令多余: {extra_commands}（意外变更）"


def test_mcp_secret_subcommand_smoke_module_entry():
    """D1 双入口 smoke：python3 -m 入口的 mcp-secret --help 可达"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "mcp-secret", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"mcp-secret --help failed: {result.stderr}"
    assert "op_ref" in result.stdout or "op://" in result.stdout
    assert "--length-only" in result.stdout


def test_mcp_secret_subcommand_smoke_console_entry():
    """D1 双入口 smoke：memory-evolve console script 的 mcp-secret --help 可达

    注意：console script 是安装时生成的，worktree 测试时可能指向旧代码。
    若 console script 不含 mcp-secret（worktree 未重装），不再自 skip——丢块症状必须红。
    """
    result = subprocess.run(
        ["memory-evolve", "mcp-secret", "--help"],
        capture_output=True,
        text=True,
    )
    # 不再自 skip：console script 指向旧代码是丢块症状，必须报错让 CI 失败
    assert result.returncode == 0, (
        f"console script mcp-secret --help failed (可能指向旧代码未重装，丢块症状): {result.stderr}"
    )
    assert "op_ref" in result.stdout or "op://" in result.stdout
    assert "--length-only" in result.stdout


def test_mcp_secret_no_op_ref_exits_2():
    """mcp-secret 无 op_ref 参数 → exit 2（argparse nargs='?' 但 handler 校验）"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "mcp-secret"],
        capture_output=True,
        text=True,
    )
    # handler 检查 op_ref 为空时 exit 2
    assert result.returncode == 2, f"Expected exit 2, got {result.returncode}. stderr={result.stderr}"


def test_mcp_secret_invalid_mcp_config_exits_1():
    """mcp-secret 指向不存在的 mcp.json → exit 1"""
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # 指向不存在的 HOME 使 mcp.json 读不到
        env = os.environ.copy()
        env["HOME"] = tmpdir
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "mcp-secret", "op://vault/item/field"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}. stderr={result.stderr}"
        assert "1password-connect" in result.stderr or "mcp.json" in result.stderr


def test_mcp_secret_length_only_mask_output():
    """
    --length-only 掩码模式测试（round-1 发现该测试名虚构从未编写）

    验证：
    1. stdout 仅包含数字（密钥长度）
    2. stdout 不包含任何密钥值字符（零密钥泄露）
    3. 输出为单行纯数字
    """
    import json as _json
    import os
    import socket

    # 动态读取 MCP 端点（BOUNDARY 4.3 零硬编码 IP）
    from pathlib import Path as _Path
    from urllib.parse import urlparse

    def _get_mcp_host_port():
        mcp_path = _Path.home() / ".factory" / "mcp.json"
        try:
            data = _json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", data)
            entry = servers.get("1password-connect", {})
            url = entry.get("url", "")
            if not url:
                return None
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not host:
                return None
            return (host, port)
        except (OSError, ValueError, KeyError):
            return None

    endpoint = _get_mcp_host_port()
    if endpoint is None:
        pytest.skip("MCP 配置不可读，无法测试真实密钥解析")

    try:
        sock = socket.create_connection(endpoint, timeout=2)
        sock.close()
    except (TimeoutError, OSError):
        pytest.skip(f"MCP 端点 {endpoint[0]}:{endpoint[1]} 不可达，无法测试真实密钥解析")

    # 临时移除 AXONHUB_API_KEY 环境变量，强制走 MCP 路径
    env = os.environ.copy()
    env.pop("AXONHUB_API_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "memory_core.tools.evolve_cli",
            "mcp-secret",
            "op://ozqqpvh5yvvxvyu64npq62a3ti/arh3eyylx2snevicwvb3px7iui/api_key",
            "--length-only",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, f"命令失败: {result.stderr}"

    stdout = result.stdout.strip()

    # 验证 1: stdout 仅包含数字
    assert stdout.isdigit(), f"--length-only 输出应为纯数字，实际: {stdout!r}"

    # 验证 2: 输出为单行
    assert "\n" not in stdout, f"--length-only 应为单行输出，实际包含换行: {stdout!r}"

    # 验证 3: 长度值在合理范围内（真实密钥为 67 字符）
    length = int(stdout)
    assert 50 <= length <= 100, f"密钥长度 {length} 不在合理范围 [50, 100]"

    # 验证 4: stdout 不包含常见密钥字符（零泄露）
    # 真实密钥通常包含 base64 字符、特殊符号等
    # 我们验证输出仅包含数字，不包含其他字符
    assert stdout == str(length), "输出应严格等于长度值的字符串表示"
