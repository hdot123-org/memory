"""GATE A §4.6 sync-origin override 的标签盲区回归测试（INFRA-536 / #1000 振荡）.

背景（2026-08-24 事故链）：
- heartbeat resolve_cleared_alerts() 自愈关闭 GitHub #1000（label: evolution-heartbeat）
- Linear 原生集成将 INFRA-536 同步为 Done
- trigger-droid.sh GATE A 触发，§4.6 sync-origin override 查询
  `gh issue list --label evolution-found`，#1000 无该标签 → 候选列表不可见
- GATE A BLOCK → 回滚 Linear → GitHub issue 被 reopen → 每 2h 振荡一次

修复（锚点统一方案，与 §4.5 一致）：
- §4.6 查询移除 `--label evolution-found` 过滤，锚点一致性（linear-linkback 提取）
  作为唯一判别器。heartbeat 自愈 close 与 scanner auto_close_resolved 均为合法来源。

本测试采用源码断言模式（与 test_deadlock_exit_retrigger.py 一致）：
断言脚本关键行为片段存在/不存在，防止标签过滤回归。
"""

from pathlib import Path

import pytest

SCRIPT_RELATIVE_PATH = Path("webhook-scripts/trigger-droid.sh")


def _load_script(repo_root: Path) -> str:
    script_path = repo_root / SCRIPT_RELATIVE_PATH
    if not script_path.exists():
        pytest.skip(f"trigger-droid.sh not found at {script_path}")
    return script_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def repo_root() -> Path:
    """定位仓库根目录（tests/ 的上一级）。"""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def script_content(repo_root: Path) -> str:
    return _load_script(repo_root)


class TestSyncOriginLabelBlindspot:
    """§4.6 sync-origin override 不得用标签做信任边界。"""

    def test_sync_origin_query_drops_label_filter(self, script_content: str):
        """greenPath: §4.6 查询不携带 --label evolution-found。

        查询必须覆盖全部 issue（--state all），由锚点一致性判别，
        否则 evolution-heartbeat 等非 evolution-found 标签的合法 close
        会被 GATE A 误判（redEvidence: #1000 三轮 close→reopen 振荡）。
        """
        lines = script_content.splitlines()
        query_lines = [line for line in lines if "gh issue list" in line and "--json number,state,closedAt" in line]
        assert query_lines, "§4.6 必须存在 gh issue list 查询（number,state,closedAt）"

        for line in query_lines:
            assert "--label evolution-found" not in line, (
                "§4.6 sync-origin 查询禁止携带 --label evolution-found："
                "标签过滤使 heartbeat 自愈 close（evolution-heartbeat 标签）"
                "对 GATE A 不可见，导致 Done 回滚与 close→reopen 振荡（#1000/INFRA-536）"
            )

    def test_sync_origin_anchor_check_present(self, script_content: str):
        """greenPath: 锚点一致性判别仍然存在且必经。

        移除标签过滤后，锚点（linear-linkback 提取）成为唯一判别器，
        该检查必须保留：extract_anchor.py 失败 → fail-closed（anchor mismatch → continue）。
        """
        assert "extract_anchor.py', 'issue'" in script_content, (
            "§4.6 必须调用 extract_anchor.py issue 提取锚点做一致性校验"
        )
        assert "anchor == target_ref" in script_content, "锚点比对逻辑必须存在"
        assert "GATE A PASS (sync-origin)" in script_content, "PASS 分支必须存在且可区分"
        assert "GATE A BLOCK (sync-origin)" in script_content, "BLOCK 分支必须存在且可区分"

    def test_sync_origin_ten_minute_window_kept(self, script_content: str):
        """greenPath: 10 分钟时间窗语义保留（防御陈旧 close 误放行）。"""
        assert "diff_minutes > 10" in script_content, "closed_at ≤ 10min 时间窗必须保留"

    def test_heartbeat_comment_pattern_untargeted(self, script_content: str):
        """greenPath: 脚本不得针对 heartbeat 🩹 自愈评论做特殊放行。

        修复依赖锚点一致性而非评论指纹；若未来引入评论指纹放行，
        应视为设计回归（伪造评论可绕过 GATE A）。
        """
        assert "🩹" not in script_content, "禁止以 🩹 评论指纹作为 GATE A 放行依据（锚点统一方案：伪造评论可绕过）"
