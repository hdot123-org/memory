"""F1-routing: trigger-ci-droid.sh 分流路由测试

覆盖 VAL-REG-005 ~ VAL-REG-010：
- VAL-REG-005: scanner 来源静默清理（闭端口 + unset token 双变体）
- VAL-REG-006: scanner 路径零 PostHog 事件
- VAL-REG-007: 交叉校验不符 → 保守路径（保留文件 + anomaly 事件 + 无 fallback）
- VAL-REG-008: 缺 source 字段 → 默认 session + 记录恰一次
- VAL-REG-009: source=session 到达既有注入路径
- VAL-REG-010: 过期 scanner 文件同样静默清理

测试隔离：使用 ECHO_DROID=1 避免真实 droid exec，POSTHOG_DRY_RUN=1 避免真实事件。
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
TRIGGER_SCRIPT = REPO_ROOT / "webhook-scripts" / "trigger-ci-droid.sh"


def _make_env(tmp_path: Path, home_override: Path | None = None) -> dict:
    """构造测试环境变量"""
    env = os.environ.copy()

    # 隔离 webhook 目录
    webhook_base = tmp_path / "webhook"
    webhook_base.mkdir(exist_ok=True)
    env["WEBHOOK_BASE"] = str(webhook_base)

    locks_dir = tmp_path / "locks"
    locks_dir.mkdir(exist_ok=True)
    env["LOCK_DIR"] = str(locks_dir)

    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    env["LOG_DIR"] = str(log_dir)

    # 避免真实 API 调用
    env["FACTORY_API_BASE"] = "http://127.0.0.1:1"  # 闭端口
    if "FACTORY_TOKEN" in env:
        del env["FACTORY_TOKEN"]  # unset token

    # 避免真实 droid exec
    env["ECHO_DROID"] = "1"

    # 避免真实 PostHog 事件
    env["POSTHOG_DRY_RUN"] = "1"

    # 跨平台 Python
    env["PYTHON_BIN"] = sys.executable

    # HOME 隔离
    if home_override:
        env["HOME"] = str(home_override)

    return env


def _install_fake_gh_scanner(tmp_path: Path, env: dict) -> None:
    """Install a fake gh in PATH that returns scanner identity for cross-validation."""
    fake_gh_dir = tmp_path / "fake_gh_bin"
    fake_gh_dir.mkdir(exist_ok=True)
    fake_gh = fake_gh_dir / "gh"
    fake_gh.write_text('#!/bin/bash\necho \'{"author": {"login": "evolution-scanner[bot]"}, "labels": [{"name": "evolution-found"}]}\'\n')
    fake_gh.chmod(0o755)
    env["PATH"] = f"{fake_gh_dir}:{env.get('PATH', '')}"


def _install_fake_gh_human(tmp_path: Path, env: dict) -> None:
    """Install a fake gh in PATH that returns human identity (mismatch)."""
    fake_gh_dir = tmp_path / "fake_gh_human"
    fake_gh_dir.mkdir(exist_ok=True)
    fake_gh = fake_gh_dir / "gh"
    fake_gh.write_text('#!/bin/bash\necho \'{"author": {"login": "human-user"}, "labels": []}\'\n')
    fake_gh.chmod(0o755)
    env["PATH"] = f"{fake_gh_dir}:{env.get('PATH', '')}"


def _create_pending_file(locks_dir: Path, pr_number: int, source: str | None = None,
                         created_at: str | None = None) -> Path:
    """创建 pending-ci 测试文件"""
    data = {
        "pr_number": str(pr_number),
        "cwd": "/test/repo",
        "created_at": created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if source is not None:
        data["source"] = source

    file_path = locks_dir / f"pending-ci-{pr_number}.json"
    file_path.write_text(json.dumps(data))
    return file_path


class TestVAL_REG_005_Scanner_Silent_Cleanup:
    """VAL-REG-005: scanner 来源静默清理（闭端口 + unset token 双变体）"""

    def test_scanner_silent_cleanup_closed_port(self, tmp_path):
        """FACTORY_API_BASE=http://127.0.0.1:1（闭端口）下 scanner 来源静默清理"""
        env = _make_env(tmp_path)
        env["FACTORY_API_BASE"] = "http://127.0.0.1:1"  # 闭端口
        _install_fake_gh_scanner(tmp_path, env)  # gh 返回 scanner 身份

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4250
        pending_file = _create_pending_file(locks_dir, pr_number, source="scanner")

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：脚本成功退出
        assert result.returncode == 0, f"Script should exit 0, got {result.returncode}"

        # 验证：pending 文件被删除
        assert not pending_file.exists(), "Pending file should be deleted for scanner source"

        # 验证：无 fallback spawn（日志不含 "spawn_fallback" 函数调用）
        combined_output = result.stdout + result.stderr
        assert "spawn_fallback" not in combined_output, "Should not spawn fallback for scanner"

    def test_scanner_silent_cleanup_unset_token(self, tmp_path):
        """FACTORY_TOKEN unset 下 scanner 来源静默清理"""
        env = _make_env(tmp_path)
        if "FACTORY_TOKEN" in env:
            del env["FACTORY_TOKEN"]  # unset token
        _install_fake_gh_scanner(tmp_path, env)  # gh 返回 scanner 身份

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4251
        pending_file = _create_pending_file(locks_dir, pr_number, source="scanner")

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：脚本成功退出
        assert result.returncode == 0, f"Script should exit 0, got {result.returncode}"

        # 验证：pending 文件被删除
        assert not pending_file.exists(), "Pending file should be deleted for scanner source"


class TestVAL_REG_006_Scanner_Zero_PostHog:
    """VAL-REG-006: scanner 路径零 PostHog 事件"""

    def test_scanner_zero_posthog_noise(self, tmp_path):
        """scanner 来源路径不触发任何 PostHog 事件（POSTHOG_DRY_RUN 日志无 ci_ 前缀事件）"""
        env = _make_env(tmp_path)
        _install_fake_gh_scanner(tmp_path, env)  # gh 返回 scanner 身份

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4252
        _create_pending_file(locks_dir, pr_number, source="scanner")

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：日志中无 PostHog 事件发送记录
        combined_output = result.stdout + result.stderr
        # PostHog dry-run 模式会打印 "[DRY-RUN] Would send PostHog event: <event_name>"
        assert "Would send PostHog event" not in combined_output, \
            "Scanner path should not trigger any PostHog events"

        # 验证：无 ci_ 前缀事件（保守路径的 anomaly 事件除外，但 scanner 通过时不应触发）
        ci_events = [line for line in combined_output.split("\n")
                     if "ci_" in line and "PostHog" in line]
        assert len(ci_events) == 0, \
            f"Scanner path should not trigger ci_* events, found: {ci_events}"


class TestVAL_REG_007_Scanner_Cross_Validation_Mismatch:
    """VAL-REG-007: 交叉校验不符 → 保守路径"""

    def test_scanner_cross_validation_mismatch(self, tmp_path):
        """交叉校验不符：文件保留 + anomaly 记录 + 无 fallback"""
        env = _make_env(tmp_path)

        # 注入假 gh 命令，返回非 scanner 身份的 PR 元数据
        fake_gh_dir = tmp_path / "fake_gh"
        fake_gh_dir.mkdir()
        fake_gh = fake_gh_dir / "gh"
        fake_gh.write_text("""#!/bin/bash
# 模拟 gh pr view 返回非 scanner 身份的 PR
echo '{"author": {"login": "human-user"}, "labels": []}'
""")
        fake_gh.chmod(0o755)

        # 将假 gh 加入 PATH
        env["PATH"] = f"{fake_gh_dir}:{env.get('PATH', '')}"

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4253
        pending_file = _create_pending_file(locks_dir, pr_number, source="scanner")

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：脚本成功退出
        assert result.returncode == 0, f"Script should exit 0, got {result.returncode}"

        # 验证：文件保留（保守路径不删除）
        assert pending_file.exists(), "Pending file should be kept on cross-validation mismatch"

        # 验证：anomaly 事件被记录（日志包含 ci_scanner_source_mismatch）
        combined_output = result.stdout + result.stderr
        assert "ci_scanner_source_mismatch" in combined_output or "cross-validation failed" in combined_output.lower(), \
            "Should log anomaly event on cross-validation mismatch"

        # 验证：无 fallback spawn
        assert "spawn_fallback" not in combined_output, "Should not spawn fallback on mismatch"

    def test_scanner_cross_validation_gh_unavailable(self, tmp_path):
        """gh 不可用时走保守路径（D2 裁决）：保留文件 + anomaly 事件 + 无 fallback"""
        env = _make_env(tmp_path)

        # 保留基本命令但排除 gh：使用系统路径但创建空 gh 覆盖
        # 不能清空 PATH，否则 dirname/date 等命令也找不到
        empty_gh_dir = tmp_path / "empty_gh"
        empty_gh_dir.mkdir()
        # 将空目录放在 PATH 前面，但不覆盖整个 PATH
        env["PATH"] = f"{empty_gh_dir}:{env.get('PATH', '/usr/bin:/bin')}"
        # 确保没有 gh 命令可用（空目录里没有 gh）

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4254
        pending_file = _create_pending_file(locks_dir, pr_number, source="scanner")

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：脚本成功退出
        assert result.returncode == 0, f"Script should exit 0, got {result.returncode}"

        # 验证：文件保留（D2 裁决：保守路径，不删除）
        # 理由：session 文件误标 scanner + gh 恰好不可用时，
        # 静默清理会删除 session PR 救援通道，违背不变量 2
        assert pending_file.exists(), "Pending file should be kept when gh unavailable (conservative path D2)"

        # 验证：anomaly 事件被记录
        combined_output = result.stdout + result.stderr
        assert "ci_scanner_source_unverifiable" in combined_output or "cross-validation unexecutable" in combined_output.lower(), \
            "Should log anomaly event when gh unavailable (conservative path)"

        # 验证：无 fallback spawn
        assert "spawn_fallback" not in combined_output, "Should not spawn fallback when gh unavailable"


class TestVAL_REG_008_Missing_Source_Default_Session:
    """VAL-REG-008: 缺 source 字段 → 默认 session + 记录恰一次"""

    def test_missing_source_defaulted_session(self, tmp_path):
        """缺 source 字段的 legacy 文件被默认到 session + 日志记录恰一次"""
        env = _make_env(tmp_path)

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4255
        # 创建不含 source 字段的 legacy 文件
        _create_pending_file(locks_dir, pr_number, source=None)

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：日志记录 default 信息
        combined_output = result.stdout + result.stderr
        default_logs = [line for line in combined_output.split("\n")
                        if "unknown-source defaulted to session" in line]
        assert len(default_logs) == 1, \
            f"Should log 'unknown-source defaulted to session' exactly once, found {len(default_logs)} times"

        # 验证：继续走既有 session 路径（不删除文件，尝试注入）
        pending_file = locks_dir / f"pending-ci-{pr_number}.json"
        # 由于闭端口，注入会失败，但文件应保留（不进入 scanner 清理路径）
        assert pending_file.exists(), "Legacy file should not be deleted by scanner routing"


class TestVAL_REG_009_Session_Source_Reaches_Injection:
    """VAL-REG-009: source=session 到达既有注入路径"""

    def test_session_source_reaches_injection_path(self, tmp_path):
        """source=session 文件到达既有注入路径（不进入 scanner 清理）"""
        env = _make_env(tmp_path)

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4256
        pending_file = _create_pending_file(locks_dir, pr_number, source="session")

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：文件未被删除（session 路径保留文件，尝试注入）
        assert pending_file.exists(), "Session source file should not be deleted by scanner routing"

        # 验证：日志不包含 scanner 清理信息
        combined_output = result.stdout + result.stderr
        assert "silent cleanup" not in combined_output.lower(), \
            "Session source should not enter scanner silent cleanup path"

        # 验证：尝试注入（由于闭端口会失败，但应有注入相关日志）
        # 此处不验证注入成功，只验证未进入 scanner 路径


class TestVAL_REG_010_Expired_Scanner_Silent_Cleanup:
    """VAL-REG-010: 过期 scanner 文件同样静默清理"""

    def test_expired_scanner_silent_cleanup(self, tmp_path):
        """过期 scanner 文件走静默清理而非 expiry fallback 路径"""
        env = _make_env(tmp_path)

        locks_dir = Path(env["LOCK_DIR"])
        pr_number = 4257
        # 创建过期的 scanner 文件（created_at 3 小时前）
        expired_at = (datetime.now(UTC) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pending_file = _create_pending_file(locks_dir, pr_number, source="scanner", created_at=expired_at)

        result = subprocess.run(
            [str(TRIGGER_SCRIPT), str(pr_number)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # 验证：脚本成功退出
        assert result.returncode == 0, f"Script should exit 0, got {result.returncode}"

        # 验证：文件被删除（静默清理）
        assert not pending_file.exists(), "Expired scanner file should be silently deleted"

        # 验证：无 expiry fallback 事件（不进入过期路径）
        combined_output = result.stdout + result.stderr
        assert "ci_expired_pending_ci" not in combined_output, \
            "Expired scanner file should not trigger expiry fallback event"

        # 验证：无 fallback spawn
        assert "spawn_fallback" not in combined_output, \
            "Expired scanner file should not spawn fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
