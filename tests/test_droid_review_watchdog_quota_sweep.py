"""droid-review-watchdog quota-sweep 自愈结构测试（2026-08-19 PR #852）。

回归保护：BYOK 429 配额耗尽自愈（quota-sweep job）的关键属性。
背景：PR #850 实证 Bailian 配额打穿时 review exit 1，job log 只有
无差别 "exited with code 1"，真实 429 签名只在 debug artifact 的
session transcript 里；且配额未恢复时立即 rerun 无意义。quota-sweep
以 schedule 扫描 + artifact 检测 + 恢复窗口 + attempt 限界实现自愈。

这些断言防止自愈逻辑被静默移除或弱化（如去掉恢复窗口导致 rerun
风暴、去掉 attempt 限界导致无限重试）。
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
WATCHDOG_PATH = REPO_ROOT / ".github/workflows/droid-review-watchdog.yml"


def _load() -> dict:
    return yaml.safe_load(WATCHDOG_PATH.read_text())


def _quota_sweep_run() -> str:
    data = _load()
    steps = data["jobs"]["quota-sweep"]["steps"]
    return steps[0]["run"]


class TestQuotaSweepJobStructure:
    """quota-sweep job 的存在性与触发配置。"""

    def test_quota_sweep_job_exists(self):
        """quota-sweep job 必须存在（429 自愈入口）。"""
        assert "quota-sweep" in _load()["jobs"]

    def test_schedule_trigger_present(self):
        """schedule 每 30 分钟触发（配额恢复探测窗口）。"""
        on_block = _load()[True]  # yaml 把 `on:` 解析为 True
        assert "schedule" in on_block
        crons = [c["cron"] for c in on_block["schedule"]]
        assert "*/30 * * * *" in crons

    def test_quota_sweep_gated_on_schedule_event(self):
        """quota-sweep 只在 schedule 事件运行，workflow_run 不误入
        （配额耗尽时立即 rerun 无意义，必须走恢复窗口）。"""
        assert _load()["jobs"]["quota-sweep"]["if"] == "github.event_name == 'schedule'"

    def test_workflow_run_trigger_preserved(self):
        """原有 workflow_run 双触发源（self-heal-rerun / cancel-on-ci-fail）不受影响。"""
        on_block = _load()[True]
        assert "workflow_run" in on_block
        names = on_block["workflow_run"]["workflows"]
        assert "Droid Auto Review" in names
        assert "CI" in names


class TestQuotaSweepDetectionLogic:
    """429 检测与防风暴关键属性。"""

    def test_artifact_signature_grep(self):
        """检测必须 grep transcript 的 quota exceeded 签名（job log 无此特征）。"""
        run = _quota_sweep_run()
        assert "quota exceeded" in run
        assert ".factory/sessions/" in run

    def test_recovery_window_30min(self):
        """run 结束满 30 分钟（1800s）才 rerun——配额恢复窗口。"""
        run = _quota_sweep_run()
        assert "1800" in run
        assert "-lt 1800" in run

    def test_attempt_limit_3(self):
        """run_attempt < 3 限界防 rerun 风暴（与 self-heal-rerun 一致）。"""
        run = _quota_sweep_run()
        assert '"$ATTEMPT" -ge 3' in run

    def test_rerun_uses_failed_jobs_api(self):
        """rerun 必须走 rerun-failed-jobs API（终态 run 才可用）。"""
        run = _quota_sweep_run()
        assert "rerun-failed-jobs" in run

    def test_scan_window_6h(self):
        """扫描窗口 6 小时（配额周期量级），不追历史。"""
        run = _quota_sweep_run()
        assert "6 hours ago" in run

    def test_fail_closed_no_conclusion_change(self):
        """门禁语义：脚本只请求 rerun，不写 check 结论、不绕过门禁。"""
        run = _quota_sweep_run()
        # 不存在任何 check 结论改写 API
        for forbidden in ("check-runs", "annotations", "--admin"):
            assert forbidden not in run


class TestExistingJobsPreserved:
    """原有 watchdog 职责不受影响。"""

    def test_self_heal_rerun_preserved(self):
        """self-heal-rerun（503 自愈）保留且限界不变。"""
        data = _load()
        assert "self-heal-rerun" in data["jobs"]
        assert data["jobs"]["self-heal-rerun"]["if"].count("run_attempt < 3") == 1

    def test_cancel_on_ci_fail_preserved(self):
        """cancel-on-ci-fail（CI 红取消烧钱 review）保留。"""
        assert "cancel-on-ci-fail" in _load()["jobs"]

    def test_timeout_minutes_bounded(self):
        """quota-sweep 有 timeout 上界（防 sweep 自身挂死）。"""
        assert _load()["jobs"]["quota-sweep"]["timeout-minutes"] <= 15
