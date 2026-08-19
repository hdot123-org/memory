"""Tests for ci-timeout-watchdog.sh - 两阶段消息对账机制

Phase A: 检测超过 30 分钟未注入的 pending-ci 文件
Phase B: 检测超过 45 分钟已注入但未消费的 pending-ci 文件
"""
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def temp_locks_dir():
    """创建临时 locks 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def watchdog_script():
    """获取 watchdog 脚本路径"""
    repo_root = Path(__file__).parent.parent
    return repo_root / "webhook-scripts" / "ci-timeout-watchdog.sh"


def create_pending_ci_file(
    locks_dir: Path,
    pr_number: int,
    created_at: datetime,
    injected_at: datetime | None = None,
    message_id: str | None = None,
):
    """创建 pending-ci 文件"""
    def format_timestamp(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    data = {
        "session_id": "test-session-id",
        "pr_number": str(pr_number),
        "created_at": format_timestamp(created_at),
        "cwd": "/test/repo",
    }
    if injected_at is not None:
        data["injected_at"] = format_timestamp(injected_at)
    if message_id is not None:
        data["message_id"] = message_id

    file_path = locks_dir / f"pending-ci-{pr_number}.json"
    file_path.write_text(json.dumps(data))
    return file_path


class TestPhaseAReconciliation:
    """Phase A: 检测未注入的过期文件"""

    def test_phase_a_detects_stale_uninjected_file(self, temp_locks_dir, watchdog_script):
        """Phase A 应该检测超过 30 分钟未注入的 pending-ci 文件"""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        file_path = create_pending_ci_file(temp_locks_dir, 123, created_at)

        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert not file_path.exists(), "Phase A should delete stale uninjected file"
        assert "Phase A" in result.stdout or "PR #123" in result.stdout

    def test_phase_a_ignores_recent_file(self, temp_locks_dir, watchdog_script):
        """Phase A 不应该删除 30 分钟内的文件"""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        file_path = create_pending_ci_file(temp_locks_dir, 124, created_at)

        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert file_path.exists(), "Phase A should not delete recent file"

    def test_phase_a_ignores_file_with_injected_at(self, temp_locks_dir, watchdog_script):
        """Phase A 应该跳过已注入的文件（由 Phase B 处理）"""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        injected_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        file_path = create_pending_ci_file(
            temp_locks_dir, 125, created_at, injected_at=injected_at
        )

        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert file_path.exists(), "Phase A should skip files with injected_at"


class TestPhaseBReconciliation:
    """Phase B: 检测已注入但未消费的文件"""

    def test_phase_b_detects_stale_injected_file(self, temp_locks_dir, watchdog_script):
        """Phase B 应该检测超过 45 分钟已注入但未消费的文件"""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=55)
        injected_at = datetime.now(timezone.utc) - timedelta(minutes=50)
        create_pending_ci_file(
            temp_locks_dir, 126, created_at, injected_at=injected_at
        )

        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert "Phase B" in result.stdout or "PR #126" in result.stdout or \
               "not merged" in result.stdout or "spawning fallback" in result.stdout

    def test_phase_b_ignores_recent_injected_file(self, temp_locks_dir, watchdog_script):
        """Phase B 不应该处理 45 分钟内注入的文件"""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=40)
        injected_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        file_path = create_pending_ci_file(
            temp_locks_dir, 127, created_at, injected_at=injected_at
        )

        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert file_path.exists(), "Phase B should not process recent injected files"


class TestWatchdogIdempotency:
    """幂等性和边界条件测试"""

    def test_watchdog_handles_empty_directory(self, temp_locks_dir, watchdog_script):
        """watchdog 应该能处理空的 locks 目录"""
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0

    def test_watchdog_handles_malformed_json(self, temp_locks_dir, watchdog_script):
        """watchdog 应该能处理格式错误的 JSON 文件"""
        malformed_file = temp_locks_dir / "pending-ci-999.json"
        malformed_file.write_text("not valid json")

        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
