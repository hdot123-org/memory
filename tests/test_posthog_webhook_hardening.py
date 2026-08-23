"""INFRA-524 回归测试：webhook-scripts 的 PostHog key 环境变量化防护。

PR #982 已将 4 个脚本的硬编码 phc_ key 迁移到 POSTHOG_API_KEY 环境变量
（trigger-ci-droid.sh / ci-timeout-watchdog.sh / trigger-error-droid.sh /
ci-failed.sh）。本文件守住两道防线，防止后续 sync 回填或重构把明文 key
带回公开仓库：

1. VAL-PH-WH-001: webhook-scripts/*.sh 不允许出现任何 phc_ 明文 key
2. VAL-PH-WH-002: 所有上报 posthog.com 的脚本必须带 POSTHOG_API_KEY 缺失守卫

注：memory_core/default_posthog_key.txt 是文档声明的公开默认 key（README），
不在 webhook-scripts 扫描范围内，由 test_posthog_client.py 单独覆盖。
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBHOOK_SCRIPTS_DIR = REPO_ROOT / "webhook-scripts"


def test_no_hardcoded_phc_in_webhook_scripts():
    """VAL-PH-WH-001: webhook-scripts 不得包含硬编码 phc_ key。"""
    result = subprocess.run(
        ["grep", "-r", "phc_", "webhook-scripts/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    # grep returns 1 if no matches, which is what we want
    assert result.returncode == 1, f"No webhook-scripts should contain hardcoded phc_ keys, found:\n{result.stdout}"


def test_webhook_scripts_posthog_guard():
    """VAL-PH-WH-002: 每个 PostHog 上报脚本必须有 POSTHOG_API_KEY 守卫。

    webhook-scripts/*.sh 中凡 posthog.com 的脚本，上报前必须检查
    POSTHOG_API_KEY，未设时跳过而非发送无效 payload（与 #982 既有
    缺失即跳过语义一致）。
    """
    senders = [p for p in WEBHOOK_SCRIPTS_DIR.glob("*.sh") if "posthog.com" in p.read_text(encoding="utf-8")]
    assert senders, "Expected at least one webhook script reporting to PostHog"

    missing_guard = [p.name for p in senders if "POSTHOG_API_KEY" not in p.read_text(encoding="utf-8")]
    assert not missing_guard, f"PostHog senders missing POSTHOG_API_KEY guard: {', '.join(sorted(missing_guard))}"
