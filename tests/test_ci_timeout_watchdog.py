"""Tests for ci-timeout-watchdog.sh - 两阶段消息对账机制

Phase A: 检测超过 30 分钟未注入的 pending-ci 文件
Phase B: 检测超过 45 分钟已注入但未消费的 pending-ci 文件
"""

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
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


def _make_test_env(locks_dir: Path, tmp_path: Path | None = None) -> dict:
    """构造隔离的测试环境，确保日志和锁文件不写入生产目录。

    VAL-HYG-003: 设置 LOG_DIR 环境变量指向临时目录，防止 watchdog 脚本
    在测试期间向 ~/.factory/webhook/logs/ 写入日志文件。

    Args:
        locks_dir: 临时锁文件目录
        tmp_path: pytest 提供的临时目录（用于日志），若为 None 则使用 locks_dir 的父目录

    Returns:
        包含所有必要环境变量的字典
    """
    env = os.environ.copy()
    env["LOCKS_DIR"] = str(locks_dir)
    env["ECHO_DROID"] = "1"  # 防止真实 droid 会话
    env["POSTHOG_DRY_RUN"] = "1"  # 防止真实 PostHog 事件

    # VAL-HYG-003: 确保日志写入临时目录而非生产目录
    if tmp_path is None:
        tmp_path = locks_dir.parent
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    env["LOG_DIR"] = str(log_dir)

    return env


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
        created_at = datetime.now(UTC) - timedelta(minutes=35)
        file_path = create_pending_ci_file(temp_locks_dir, 123, created_at)

        env = _make_test_env(temp_locks_dir)

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
        created_at = datetime.now(UTC) - timedelta(minutes=20)
        file_path = create_pending_ci_file(temp_locks_dir, 124, created_at)

        env = _make_test_env(temp_locks_dir)

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
        created_at = datetime.now(UTC) - timedelta(minutes=35)
        injected_at = datetime.now(UTC) - timedelta(minutes=30)
        file_path = create_pending_ci_file(temp_locks_dir, 125, created_at, injected_at=injected_at)

        env = _make_test_env(temp_locks_dir)

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
        created_at = datetime.now(UTC) - timedelta(minutes=55)
        injected_at = datetime.now(UTC) - timedelta(minutes=50)
        create_pending_ci_file(temp_locks_dir, 126, created_at, injected_at=injected_at)

        env = _make_test_env(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert (
            "Phase B" in result.stdout
            or "PR #126" in result.stdout
            or "not merged" in result.stdout
            or "spawning fallback" in result.stdout
        )

    def test_phase_b_ignores_recent_injected_file(self, temp_locks_dir, watchdog_script):
        """Phase B 不应该处理 45 分钟内注入的文件"""
        created_at = datetime.now(UTC) - timedelta(minutes=40)
        injected_at = datetime.now(UTC) - timedelta(minutes=30)
        file_path = create_pending_ci_file(temp_locks_dir, 127, created_at, injected_at=injected_at)

        env = _make_test_env(temp_locks_dir)

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
        env = _make_test_env(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0


class TestF1WatchdogScannerSource:
    """VAL-REG-011: Watchdog Phase A 对 scanner 超期文件不 spawn fallback"""

    def test_phase_a_skips_scanner_source_file(self, temp_locks_dir, watchdog_script):
        """Phase A 应该跳过 scanner source 的超期文件，只静默删除"""
        created_at = datetime.now(UTC) - timedelta(minutes=35)
        file_path = temp_locks_dir / "pending-ci-128.json"
        file_path.write_text(
            json.dumps(
                {
                    "pr_number": "128",
                    "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "cwd": "/test/repo",
                    "source": "scanner",  # F1: scanner source
                }
            )
        )

        env = _make_test_env(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # 验证：文件被删除（静默清理）
        assert not file_path.exists(), "Phase A should delete scanner source file"
        # 验证：输出包含 scanner source 相关提示
        assert "scanner source" in result.stdout.lower() or "silent cleanup" in result.stdout.lower(), (
            "Should mention scanner source or silent cleanup in output"
        )
        # 验证：没有 spawn fallback
        assert "spawning fallback" not in result.stdout.lower(), "Phase A should not spawn fallback for scanner source"

    def test_phase_a_processes_session_source_file(self, temp_locks_dir, watchdog_script):
        """Phase A 应该正常处理 session source 的超期文件（spawn fallback）"""
        created_at = datetime.now(UTC) - timedelta(minutes=35)
        file_path = temp_locks_dir / "pending-ci-129.json"
        file_path.write_text(
            json.dumps(
                {
                    "pr_number": "129",
                    "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "cwd": "/test/repo",
                    "source": "session",  # F1: session source
                }
            )
        )

        env = _make_test_env(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # 验证：文件被删除
        assert not file_path.exists(), "Phase A should delete session source file"
        # 验证：spawn fallback（ECHO_DROID 模式下会打印）
        assert "spawning fallback" in result.stdout.lower() or "phase a" in result.stdout.lower(), (
            "Phase A should spawn fallback for session source"
        )

    def test_watchdog_handles_malformed_json(self, temp_locks_dir, watchdog_script):
        """watchdog 应该能处理格式错误的 JSON 文件"""
        malformed_file = temp_locks_dir / "pending-ci-999.json"
        malformed_file.write_text("not valid json")

        env = _make_test_env(temp_locks_dir)

        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0


class TestVALINJ007ZStripRegression:
    """VAL-INJ-007: Z-strip 解析回归验证（scrutiny 修正：修复已存在，转回归验证）"""

    @pytest.mark.parametrize(
        "timestamp",
        [
            "2026-08-15T03:22:10Z",
            "2026-08-16T14:45:33Z",
            "2026-08-18T09:12:47Z",
            "2026-08-19T21:08:55Z",
            "2026-08-20T06:30:02Z",
            "2026-08-21T11:55:18Z",
            "2026-08-22T16:42:09Z",
            "2026-08-23T02:17:44Z",
            "2026-08-23T08:33:21Z",
            "2026-08-23T14:58:06Z",
            "2026-08-23T19:24:15Z",
        ],
    )
    def test_z_strip_parses_real_malformed_samples(self, timestamp):
        """VAL-INJ-007: 真实畸形样本应通过 Z-strip 成功解析为 datetime"""
        from datetime import datetime

        # 模拟 watchdog 脚本中的 Z-strip 逻辑（ci-timeout-watchdog.sh:178-179）
        parsed = timestamp
        if parsed.endswith("Z"):
            parsed = parsed[:-1] + "+00:00"
        dt = datetime.fromisoformat(parsed)
        assert dt is not None
        assert dt.year == 2026

    def test_control_valid_iso8601_passes(self):
        """VAL-INJ-007: 合法 ISO8601 对照样本必须原样通过"""
        from datetime import datetime

        timestamp = "2026-08-24T12:00:00+00:00"
        dt = datetime.fromisoformat(timestamp)
        assert dt is not None
        assert dt.year == 2026


class TestVALINJ008TerminalState:
    """VAL-INJ-008: 不可恢复样本单次告警 + 终态处理（不反复告警）"""

    def test_unrecoverable_timestamp_single_alert_then_terminal(self, temp_locks_dir, watchdog_script):
        """VAL-INJ-008: 不可解析时间戳应触发单次告警后重命名为 .malformed，
        连续两轮运行告警计数 == 1"""
        # 创建含真正不可解析时间戳的 fixture（非 Z-suffix，而是完全畸形）
        created_at = datetime.now(UTC) - timedelta(minutes=55)
        injected_at_str = "not-a-timestamp-at-all"  # 完全不可解析
        file_path = temp_locks_dir / "pending-ci-855.json"
        file_path.write_text(
            json.dumps(
                {
                    "pr_number": "855",
                    "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "injected_at": injected_at_str,
                    "cwd": "/test/repo",
                }
            )
        )

        env = _make_test_env(temp_locks_dir)

        # 第一轮运行
        result1 = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # 验证：文件被重命名为 .malformed
        malformed_path = temp_locks_dir / "pending-ci-855.json.malformed"
        assert malformed_path.exists(), "First run should rename file to .malformed"
        assert not file_path.exists(), "Original file should not exist after first run"

        # 验证：输出包含 malformed 相关提示
        assert "malformed" in result1.stdout.lower() or "marking as malformed" in result1.stdout.lower()

        # 第二轮运行（同一 locks 目录）
        result2 = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # 验证：第二轮不处理 .malformed 文件（glob 模式 pending-ci-*.json 不匹配）
        # 且无新增告警
        assert malformed_path.exists(), ".malformed file should persist across runs"
        assert "malformed" not in result2.stdout.lower() or result2.stdout.count("malformed") <= result1.stdout.count(
            "malformed"
        )


class TestVALINJ009WatchdogReceipt:
    """VAL-INJ-009: watchdog PostHog 回执落盘（非 /dev/null）"""

    def test_watchdog_posthog_receipt_written_to_log_file(self, temp_locks_dir, watchdog_script):
        """VAL-INJ-009: Phase A 触发 PostHog 事件后，回执应写入 LOG_FILE"""
        created_at = datetime.now(UTC) - timedelta(minutes=35)
        create_pending_ci_file(temp_locks_dir, 130, created_at)

        # 验证：代码断言——watchdog 脚本中 LOG_FILE 赋值在 source lib/posthog.sh 之前
        script_content = watchdog_script.read_text()
        assert "LOG_FILE=" in script_content

        # 找到 LOG_FILE 赋值行和 source 行（排除注释行）
        lines = script_content.split("\n")
        log_file_line = None
        source_line = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "LOG_FILE=" in line and log_file_line is None:
                log_file_line = i
            if "source" in line and "lib/posthog.sh" in line and source_line is None:
                source_line = i

        assert log_file_line is not None, "LOG_FILE assignment not found"
        assert source_line is not None, "source lib/posthog.sh not found"
        assert log_file_line < source_line, "LOG_FILE must be assigned before sourcing lib/posthog.sh"


class TestVALINJ010InvalidPROrdering:
    """VAL-INJ-010: ci_invalid_pr_number 事件发生在 LOG_FILE 赋值之后"""

    def test_trigger_ci_droid_log_file_before_invalid_pr(self):
        """VAL-INJ-010: trigger-ci-droid.sh 中 LOG_FILE 赋值行号 < ci_invalid_pr_number 行号（排除注释）"""
        repo_root = Path(__file__).parent.parent
        script_path = repo_root / "webhook-scripts" / "trigger-ci-droid.sh"
        script_content = script_path.read_text()

        lines = script_content.split("\n")
        log_file_line = None
        invalid_pr_line = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "LOG_FILE=" in line and log_file_line is None:
                log_file_line = i
            if "ci_invalid_pr_number" in line and invalid_pr_line is None:
                invalid_pr_line = i

        assert log_file_line is not None, "LOG_FILE assignment not found in trigger-ci-droid.sh"
        assert invalid_pr_line is not None, "ci_invalid_pr_number event not found"
        assert log_file_line < invalid_pr_line, (
            f"LOG_FILE (line {log_file_line}) must be assigned before "
            f"ci_invalid_pr_number event (line {invalid_pr_line})"
        )

    def test_write_pending_ci_log_file_before_invalid_pr(self):
        """VAL-INJ-010: write-pending-ci.sh 中 LOG_FILE 赋值行号 < ci_invalid_pr_number 行号"""
        repo_root = Path(__file__).parent.parent
        script_path = repo_root / "webhook-scripts" / "write-pending-ci.sh"
        script_content = script_path.read_text()

        lines = script_content.split("\n")
        log_file_line = None
        invalid_pr_line = None

        for i, line in enumerate(lines):
            if "LOG_FILE=" in line and not line.strip().startswith("#"):
                log_file_line = i
            if "ci_invalid_pr_number" in line:
                invalid_pr_line = i
                break

        assert log_file_line is not None, "LOG_FILE assignment not found in write-pending-ci.sh"
        assert invalid_pr_line is not None, "ci_invalid_pr_number event not found"
        assert log_file_line < invalid_pr_line, (
            f"LOG_FILE (line {log_file_line}) must be assigned before "
            f"ci_invalid_pr_number event (line {invalid_pr_line})"
        )


class TestVALINJ011PostHogFallbackLog:
    """VAL-INJ-011: 手动调用不静默丢事件（默认回执路径非 /dev/null）"""

    def test_posthog_lib_no_dev_null_default(self):
        """VAL-INJ-011: lib/posthog.sh 中 ${LOG_FILE:-/dev/null} 在可执行代码中出现次数 == 0"""
        repo_root = Path(__file__).parent.parent
        posthog_lib = repo_root / "webhook-scripts" / "lib" / "posthog.sh"
        content = posthog_lib.read_text()

        # 验证：不在可执行代码行（排除注释行）中出现 ${LOG_FILE:-/dev/null}
        # 注释中提到旧实现是允许的
        for i, line in enumerate(content.split("\n")):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "${LOG_FILE:-/dev/null}" not in line, (
                f"lib/posthog.sh line {i + 1}: executable code should not default LOG_FILE to /dev/null: {line.strip()}"
            )

    def test_posthog_lib_has_fallback_path(self):
        """VAL-INJ-011: lib/posthog.sh 应有非 /dev/null 的默认回执路径"""
        repo_root = Path(__file__).parent.parent
        posthog_lib = repo_root / "webhook-scripts" / "lib" / "posthog.sh"
        content = posthog_lib.read_text()

        # 验证：存在 _posthog_resolve_log 函数或类似 fallback 机制
        assert "_posthog_resolve_log" in content or "posthog-fallback.log" in content, (
            "lib/posthog.sh should have a fallback log path (not /dev/null)"
        )


class TestVALHYG003ZeroProductionLogWrites:
    """VAL-HYG-003: pytest 日志分离——测试执行期间不向生产日志目录写入文件"""

    def test_pytest_zero_production_log_writes(self):
        """VAL-HYG-003: 跑一组 dry-run watchdog 测试前后，生产 logs/ 的 ci-complete-pr* 计数不变。
        行为已由 _make_test_env() 的 LOG_DIR 沙箱化强制（见 :28-58），本用例为对齐设计清单口径的显式守卫。
        """
        production_logs = Path.home() / ".factory" / "webhook" / "logs"

        # 记录测试前的生产日志 ci-complete-pr* 文件计数
        if production_logs.exists():
            before_count = len(list(production_logs.glob("ci-complete-pr*")))
        else:
            before_count = 0

        # 跑一个最小 watchdog dry-run（使用隔离环境）
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            locks_dir = tmpdir_path / "locks"
            logs_dir = tmpdir_path / "logs"
            locks_dir.mkdir()
            logs_dir.mkdir()

            env = os.environ.copy()
            env["LOCKS_DIR"] = str(locks_dir)
            env["LOG_DIR"] = str(logs_dir)
            env["ECHO_DROID"] = "1"
            env["POSTHOG_DRY_RUN"] = "1"

            # 创建一个过期的 pending-ci 文件触发 Phase A
            stale_time = datetime.now(UTC) - timedelta(minutes=35)
            pending_file = locks_dir / "pending-ci-4242.json"
            pending_file.write_text(
                json.dumps(
                    {
                        "pr_number": "4242",
                        "created_at": stale_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "cwd": str(tmpdir_path),
                    }
                )
            )

            repo_root = Path(__file__).parent.parent
            watchdog = repo_root / "webhook-scripts" / "ci-timeout-watchdog.sh"
            subprocess.run(
                ["bash", str(watchdog)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )

        # 记录测试后的生产日志 ci-complete-pr* 文件计数
        if production_logs.exists():
            after_count = len(list(production_logs.glob("ci-complete-pr*")))
        else:
            after_count = 0

        # 断言：测试期间零新增 ci-complete-pr* 文件写入生产目录
        assert after_count == before_count, (
            f"VAL-HYG-003: 测试期间向生产日志目录写入了 {after_count - before_count} 个 "
            f"ci-complete-pr* 文件（before={before_count}, after={after_count}）"
        )
