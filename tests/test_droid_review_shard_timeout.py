"""droid-review shard 超时预算回归测试（2026-08-25 PR #1027 三连超时）。

回归保护：review-shard job 的 timeout-minutes 必须由 SHARD_TIMEOUT_MINUTES
repo 变量驱动。背景：PR #1027 实证 BYOM 链路（Qwen 3.7 Plus）单轮延迟
1-8 分钟、完整审查需 13-15 轮模型交互，硬编码 timeout-minutes: 30 导致
三次确定性超时（session transcript 证实模型被杀时仍在活跃产出，非卡死），
且超时取消不匹配 watchdog 的 503/429 自愈特征，rerun 无法恢复。

变量驱动与其他预算层一致（Layer 2 DROID_REVIEW_TIMEOUT_MINUTES、
Layer 3 SHARD_MAX_FILES/SHARD_MAX_LINES、Layer 4 SHARD_MAX_PARALLEL），
可在线调参无需改 workflow。
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/droid-review.yml"
PROMPT_PATH = REPO_ROOT / ".github/review/shard-review-prompt.md"


def _load() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


class TestShardTimeoutVariableDriven:
    """review-shard 超时必须由 SHARD_TIMEOUT_MINUTES 变量驱动。"""

    def test_shard_timeout_uses_variable(self):
        """timeout-minutes 引用 SHARD_TIMEOUT_MINUTES（禁止回到硬编码）。"""
        timeout = _load()["jobs"]["review-shard"]["timeout-minutes"]
        assert "SHARD_TIMEOUT_MINUTES" in timeout

    def test_shard_timeout_default_fallback(self):
        """变量缺失时回退默认值 45（> 30，覆盖 PR #1027 实测的审查时长）。"""
        timeout = _load()["jobs"]["review-shard"]["timeout-minutes"]
        assert "'45'" in timeout or '"45"' in timeout

    def test_shard_timeout_default_below_aggregation_layer(self):
        """Layer 1 默认值必须低于 Layer 2 聚合路径预算（45 < 90），
        保证聚合 job 仍有余量收集 shard 结果。"""
        shard_timeout = _load()["jobs"]["review-shard"]["timeout-minutes"]
        agg_timeout = _load()["jobs"]["droid-review"]["timeout-minutes"]
        shard_default = int(shard_timeout.split("'")[1])
        agg_default = int(agg_timeout.split("'")[1])
        assert shard_default < agg_default

    def test_workflow_contracts_preserved(self):
        """三大契约不被破坏：workflow 名 / 聚合 job 名 / artifact 前缀。"""
        data = _load()
        assert data["name"] == "Droid Auto Review"
        assert "droid-review" in data["jobs"]
        # artifact 前缀出现在 review-shard 的 upload step
        shard_steps_text = yaml.safe_dump(data["jobs"]["review-shard"]["steps"])
        assert "droid-review-debug-" in shard_steps_text

    def test_prompt_no_hardcoded_minutes(self):
        """prompt 模板不再硬编码 30 分钟数字（超时值由 workflow 层统一管理）。"""
        content = PROMPT_PATH.read_text()
        assert "30-minute" not in content
        assert "maximum of 30" not in content
