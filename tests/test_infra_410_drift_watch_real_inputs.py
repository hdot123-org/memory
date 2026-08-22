"""INFRA-410: Forward drift watch must classify using real creation-path inputs.

三类误判的回归测试（Fix drift watch classification using real inputs and quotas）：
1. 同 tick 陈旧快照：open_issues 抓取于 issue 创建之前，本 tick 刚 create/reopen
   的 finding 不在快照里 → 必须通过 issued_keys 归入 ISSUE_EXISTS，而非 GHOST
2. 配额语义：创建路径是池切片（regular 多类别共享 max_issues_per_tick，溢出为
   severity 排序后尾部），类别计数近似会漏标（6+6>10 而各 ≤10）→ 必须
   用 _compute_quota_deferred_keys 的 per-finding 结果
3. reopen 上限抑制：合法防 churn 抑制 → 归入 SUPPRESSED，而非 GHOST
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from evolution_scanner import (  # noqa: E402
    Finding,
    _compute_quota_deferred_keys,
    _integrate_forward_drift_watch,
    _process_findings_with_reopen,
)
from evolution_utils import forward_drift_watch  # noqa: E402


def _make_finding(rule_id="RULE_A", location="src/a.py::L10", severity="warning", category="code_quality") -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        category=category,
        description=f"Test finding {rule_id}",
        location=location,
        evidence="test evidence",
    )


def _make_config(max_issues=10, self_audit=5, code_hygiene=5, severity_order=("critical", "warning", "info")) -> dict:
    return {
        "max_issues_per_tick": max_issues,
        "max_self_audit_issues_per_tick": self_audit,
        "max_code_hygiene_issues_per_tick": code_hygiene,
        "severity_order": list(severity_order),
    }


class TestIssuedKeysSameTick:
    """Bug #1: 同 tick 创建/reopen 的 issue 不在陈旧 open_issues 快照中。"""

    def test_issued_keys_prevent_false_ghost(self, capsys):
        """本 tick 刚获得 issue 的 finding（快照无记录）→ ISSUE_EXISTS 而非 GHOST。"""
        findings = [_make_finding("R1", "a.py::L1")]
        # Stale snapshot: fetched BEFORE issue creation — no entry for R1
        open_issues: list = []

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            issued_keys={("R1", "a.py::L1")},
        )
        captured = capsys.readouterr()
        assert "ISSUE_EXISTS=1" in captured.out
        assert "GHOST=0" in captured.out

    def test_without_issued_keys_stale_snapshot_is_ghost(self, capsys):
        """对照：不传 issued_keys 时同一输入判为 GHOST（证明修复的必要性）。"""
        findings = [_make_finding("R1", "a.py::L1")]
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=[],
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        assert "GHOST=1" in captured.out

    def test_process_findings_records_issued_keys(self, tmp_path):
        """_process_findings_with_reopen 通过 out-param 记录本 tick 获得_issue 的 keys。"""
        history_path = tmp_path / "findings_over_time.json"
        history_path.write_text('{"snapshots": [], "resolved_findings": []}')

        findings = [
            _make_finding("R1", "a.py::L1"),
            _make_finding("R2", "b.py::L2"),
        ]
        issued: set = set()
        with patch("evolution_scanner.create_issue", return_value=True) as mock_create:
            created = _process_findings_with_reopen(
                findings,
                quota=10,
                resolved_keys=set(),
                dedup_label="evolution-found",
                history_path=history_path,
                open_issues=[],
                issued_keys=issued,
            )
        assert created == 2
        assert mock_create.call_count == 2
        assert issued == {("R1", "a.py::L1"), ("R2", "b.py::L2")}

    def test_process_findings_records_reopen_success(self, tmp_path):
        """reopen 成功的 finding 也计入 issued_keys（它同样有 open issue）。"""
        history_path = tmp_path / "findings_over_time.json"
        history_path.write_text(
            json.dumps(
                {
                    "snapshots": [],
                    "resolved_findings": [
                        {
                            "rule_id": "R1",
                            "location": "a.py::L1",
                            "resolved_at": "2026-01-01T00:00:00Z",
                            "reopen_count": 0,
                        },
                    ],
                }
            )
        )
        closed_issues = [{"number": 42, "body": "**Rule ID**: R1\n**Location**: a.py::L1"}]

        finding = _make_finding("R1", "a.py::L1", severity="critical")
        issued: set = set()
        with (
            patch("evolution_scanner.subprocess.run") as mock_run,
            patch("evolution_scanner.create_issue") as mock_create,
        ):
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=json.dumps(closed_issues), stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            created = _process_findings_with_reopen(
                [finding],
                quota=10,
                resolved_keys={("R1", "a.py::L1")},
                dedup_label="evolution-found",
                history_path=history_path,
                open_issues=[],
                issued_keys=issued,
            )
        assert created == 0  # reopen not counted as create
        assert not mock_create.called
        assert issued == {("R1", "a.py::L1")}


class TestPoolQuotaSemantics:
    """Bug #2: 配额判定必须用真实池切片语义，而非类别计数近似。"""

    def test_shared_regular_pool_quota_defers_tail(self):
        """regular 池多类别共享配额：6 catA + 6 catB，quota=10 → 溢出 2 个尾部 finding。

        类别计数近似：catA(6)≤10 且 catB(6)≤10 → 无 defer（漏标）。
        真实池语义：池总长 12 > 10 → severity 排序尾部 2 个被 defer。
        """
        config = _make_config(max_issues=10)
        # Sort by severity: critical(1) < warning(2) < info(3); tail = 2 info findings
        deduped = (
            [_make_finding(f"CRIT{i}", f"c.py::L{i}", severity="critical", category="catA") for i in range(1)]
            + [_make_finding(f"WARN{i}", f"w.py::L{i}", severity="warning", category="catA") for i in range(5)]
            + [_make_finding(f"WARNB{i}", f"wb.py::L{i}", severity="warning", category="catB") for i in range(4)]
            + [_make_finding(f"INFO{i}", f"i.py::L{i}", severity="info", category="catB") for i in range(2)]
        )
        deferred = _compute_quota_deferred_keys(deduped, [], config, gh_failed=False)
        # Pool has 12 findings, quota=10 → the 2 info findings (sorted tail) deferred
        assert deferred == {("INFO0", "i.py::L0"), ("INFO1", "i.py::L1")}

    def test_category_count_approximation_would_miss_this(self):
        """红证据：旧 _compute_quota_exhausted 的类别计数在此场景返回空 dict。"""
        # Same scenario: 6 catA + 6 catB, quota=10 → each category count (6) <= 10
        # → category-level dict would be {} (no deferral detected)
        deduped = [_make_finding(f"A{i}", f"a.py::L{i}", category="catA") for i in range(6)] + [
            _make_finding(f"B{i}", f"b.py::L{i}", category="catB") for i in range(6)
        ]
        # The real pool semantics catches it:
        config = _make_config(max_issues=10)
        deferred = _compute_quota_deferred_keys(deduped, [], config, gh_failed=False)
        assert len(deferred) == 2  # 12 - 10 = 2 tail findings deferred

    def test_critical_regression_slice_counts_separately(self):
        """critical_regressions 是独立切片（同样 max_issues_per_tick），溢出进 defer。"""
        config = _make_config(max_issues=2)
        criticals = [_make_finding(f"C{i}", f"c.py::L{i}", severity="critical") for i in range(4)]
        deferred = _compute_quota_deferred_keys([], criticals, config, gh_failed=False)
        assert deferred == {("C2", "c.py::L2"), ("C3", "c.py::L3")}

    def test_self_audit_pool_independent(self):
        """self_audit 池独立配额：regular 溢出不影响 self_audit。"""
        config = _make_config(max_issues=2, self_audit=5)
        deduped = [_make_finding(f"A{i}", f"a.py::L{i}", category="code_quality") for i in range(4)] + [
            _make_finding(f"S{i}", f"s.py::L{i}", category="evolution_self_audit") for i in range(3)
        ]
        deferred = _compute_quota_deferred_keys(deduped, [], config, gh_failed=False)
        # regular pool: 4 findings, quota=2 → 2 deferred (all code_quality)
        # self_audit pool: 3 <= 5 → none deferred
        assert deferred == {("A2", "a.py::L2"), ("A3", "a.py::L3")}

    def test_gh_failed_returns_empty(self):
        """gh 失败时创建路径未执行 → 无 defer 记录（分类另由 P2-A 兜底）。"""
        config = _make_config(max_issues=1)
        deduped = [_make_finding(f"A{i}", f"a.py::L{i}") for i in range(3)]
        assert _compute_quota_deferred_keys(deduped, [], config, gh_failed=True) == set()

    def test_quota_deferred_keys_classified_quota_pending(self, capsys):
        """defer 的 finding 在分类中归 QUOTA_PENDING 而非 GHOST。"""
        findings = [
            _make_finding("R1", "a.py::L1"),
            _make_finding("R2", "b.py::L2"),
        ]
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=[],
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            quota_deferred_keys={("R2", "b.py::L2")},
        )
        captured = capsys.readouterr()
        assert "QUOTA_PENDING=1" in captured.out
        # R1 has no issue and no reason → still GHOST (watch remains meaningful)
        assert "GHOST=1" in captured.out


class TestReopenLimitSuppression:
    """Bug #3: reopen 上限抑制的 finding 归 SUPPRESSED 而非 GHOST。"""

    def test_suppressed_reopen_keys_prevent_false_ghost(self, capsys):
        findings = [_make_finding("R1", "a.py::L1")]
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=[],
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            suppressed_reopen_keys={("R1", "a.py::L1")},
        )
        captured = capsys.readouterr()
        assert "SUPPRESSED=1" in captured.out
        assert "GHOST=0" in captured.out

    def test_process_findings_records_suppressed_reopen_keys(self, tmp_path):
        """reopen 上限抑制路径记录到 suppressed_reopen_keys out-param。"""
        history_path = tmp_path / "findings_over_time.json"
        history_path.write_text(
            json.dumps(
                {
                    "snapshots": [],
                    "resolved_findings": [
                        {
                            "rule_id": "R1",
                            "location": "a.py::L1",
                            "resolved_at": "2026-01-01T00:00:00Z",
                            "reopen_count": 3,
                        },
                    ],
                }
            )
        )
        finding = _make_finding("R1", "a.py::L1", severity="critical")
        issued: set = set()
        suppressed: set = set()
        with patch("evolution_scanner.create_issue") as mock_create:
            created = _process_findings_with_reopen(
                [finding],
                quota=10,
                resolved_keys={("R1", "a.py::L1")},
                dedup_label="evolution-found",
                history_path=history_path,
                open_issues=[],
                issued_keys=issued,
                suppressed_reopen_keys=suppressed,
            )
        assert created == 0
        assert not mock_create.called
        assert issued == set()
        assert suppressed == {("R1", "a.py::L1")}


class TestForwardDriftWatchPerFindingQuota:
    """forward_drift_watch 的 per-finding quota_deferred_keys 优先级。"""

    def test_deferred_key_takes_precedence_over_category_dict(self):
        """quota_deferred_keys 命中 → QUOTA_PENDING，即使 quota_exhausted 为空。"""
        records = forward_drift_watch(
            findings=[_make_finding("R1", "a.py::L1", category="code_quality")],
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={},  # category-level says nothing
            issue_excluded_categories=set(),
            quota_deferred_keys={("R1", "a.py::L1")},
        )
        assert records[0].status == "QUOTA_PENDING"
        assert records[0].reason == "pool_quota_deferred"

    def test_non_deferred_same_category_not_quota_pending(self):
        """同类别未被 defer 的 finding 不因类别近似被误标（per-finding 精度）。"""
        records = forward_drift_watch(
            findings=[
                _make_finding("R1", "a.py::L1", category="code_quality"),  # deferred
                _make_finding("R2", "b.py::L2", category="code_quality"),  # within quota
            ],
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={},  # absent — per-finding keys are authoritative
            issue_excluded_categories=set(),
            quota_deferred_keys={("R1", "a.py::L1")},
        )
        status_map = {r.finding_key: r.status for r in records}
        assert status_map[("R1", "a.py::L1")] == "QUOTA_PENDING"
        # R2 got an issue within quota... but no snapshot entry in this unit test,
        # so without issued_keys it is GHOST — classification stays honest
        assert status_map[("R2", "b.py::L2")] == "GHOST"

    def test_category_fallback_still_works_without_keys(self):
        """不传 quota_deferred_keys 时旧的类别级判定保持不变（向后兼容）。"""
        records = forward_drift_watch(
            findings=[_make_finding("R1", "a.py::L1", category="code_quality")],
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={"code_quality": True},
            issue_excluded_categories=set(),
        )
        assert records[0].status == "QUOTA_PENDING"
        assert records[0].reason == "category_quota_exhausted:code_quality"
