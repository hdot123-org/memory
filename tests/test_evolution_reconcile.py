"""Tests for GitHub→Linear 反向补偿工具 (INFRA-175 / GAP-B).

覆盖场景：
  1. extract_linear_ref 解析 linkback 评论 / 无 linkback 返回 None。
  2. reconcile 非终态 Linear Issue → 关闭并留言。
  3. reconcile 已终态 Linear Issue → 跳过。
  4. reconcile 无 linkback → no_ref。
  5. reconcile 无关闭 Issue → 空结果。
  6. close_linear_issue 通过 urllib 发起正确的 mutation。

所有 Linear/GitHub 写操作均通过 mock 完成，不触碰真实 API。
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for import (与既有 evolution 测试一致)
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import evolution_reconcile  # noqa: E402


# ---------------------------------------------------------------------------
# 辅助：构造 gh subprocess 结果 / urllib urlopen 伪上下文管理器
# ---------------------------------------------------------------------------
def _gh_result(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _urlopen_cm(data: dict) -> MagicMock:
    """构造一个形如 ``with urlopen(...) as resp`` 的伪上下文管理器。"""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read = MagicMock(return_value=json.dumps(data).encode("utf-8"))
    return cm


# ---------------------------------------------------------------------------
# extract_linear_ref
# ---------------------------------------------------------------------------
def test_extract_linear_ref_with_linkback():
    """linkback 评论存在 → 返回 INFRA-191。"""
    comments_payload = {
        "comments": [
            {
                "body": (
                    "<!-- linear-linkback --> "
                    '<p><a href="https://linear.app/jtoom/issue/INFRA-191">'
                    "INFRA-191</a></p>"
                )
            },
            {"body": "some unrelated comment"},
        ]
    }
    with patch("evolution_reconcile.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(comments_payload))
        ref = evolution_reconcile.extract_linear_ref(123, "hdot123/memory")

    assert ref == "INFRA-191"


def test_extract_linear_ref_no_linkback():
    """无 linkback 评论 → 返回 None。"""
    comments_payload = {"comments": [{"body": "普通评论，无标记"}]}
    with patch("evolution_reconcile.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(comments_payload))
        ref = evolution_reconcile.extract_linear_ref(456, "hdot123/memory")

    assert ref is None


def test_extract_linear_ref_no_comments():
    """无任何评论 → 返回 None。"""
    with patch("evolution_reconcile.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps({"comments": []}))
        ref = evolution_reconcile.extract_linear_ref(789, "hdot123/memory")

    assert ref is None


# ---------------------------------------------------------------------------
# gh_json
# ---------------------------------------------------------------------------
def test_gh_json_success_returns_parsed_list():
    """gh 成功且输出 list JSON → 返回解析后的 list。"""
    with patch("evolution_reconcile.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps([{"number": 1}]))
        result = evolution_reconcile.gh_json(
            ["issue", "list", "--json", "number"], "hdot123/memory"
        )

    assert result == [{"number": 1}]


def test_gh_json_failure_raises():
    """gh 退出码非 0 → 抛 RuntimeError。"""
    with patch("evolution_reconcile.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(stdout="", returncode=1, stderr="boom")
        try:
            evolution_reconcile.gh_json(["issue", "view", "1"], "hdot123/memory")
        except RuntimeError as e:
            assert "boom" in str(e)
        else:
            raise AssertionError("RuntimeError not raised")


def test_gh_json_empty_list_command_returns_empty_list():
    """list 类命令空输出 → 返回 []。"""
    with patch("evolution_reconcile.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(stdout="")
        result = evolution_reconcile.gh_json(
            ["issue", "list", "--json", "number"], "hdot123/memory"
        )

    assert result == []


# ---------------------------------------------------------------------------
# linear_request + close_linear_issue (urllib 层)
# ---------------------------------------------------------------------------
def test_linear_request_parses_data():
    """linear_request 返回 data 字段。"""
    resp = {"data": {"team": {"id": "T1"}}}
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm(resp)
        data = evolution_reconcile.linear_request("query{}", "key", {"id": "T1"})

    assert data == {"team": {"id": "T1"}}


def test_linear_request_raises_on_graphql_errors():
    """响应含 errors → 抛 RuntimeError。"""
    resp = {"errors": [{"message": "not found"}]}
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm(resp)
        try:
            evolution_reconcile.linear_request("query{}", "key")
        except RuntimeError:
            pass
        else:
            raise AssertionError("RuntimeError not raised")


def test_close_linear_issue_issues_update_and_comment():
    """close_linear_issue 依次发起 issueUpdate + commentCreate。"""
    responses = [
        _urlopen_cm({"data": {"issueUpdate": {"success": True, "issue": {"id": "I1"}}}}),
        _urlopen_cm({"data": {"commentCreate": {"success": True}}}),
    ]
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.side_effect = responses
        evolution_reconcile.close_linear_issue(
            "I1", "STATE-DONE", "key", "closing comment"
        )

    assert mock_open.call_count == 2
    # 校验两次请求的 query 内容
    first_req = mock_open.call_args_list[0].args[0]
    second_req = mock_open.call_args_list[1].args[0]
    first_body = json.loads(first_req.data.decode("utf-8"))
    second_body = json.loads(second_req.data.decode("utf-8"))
    assert "issueUpdate" in first_body["query"]
    assert first_body["variables"] == {"id": "I1", "stateId": "STATE-DONE"}
    assert "commentCreate" in second_body["query"]
    assert second_body["variables"] == {"iid": "I1", "body": "closing comment"}


def test_close_linear_issue_raises_when_update_fails():
    """issueUpdate success=False → 抛 RuntimeError，不发起 commentCreate。"""
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm(
            {"data": {"issueUpdate": {"success": False}}}
        )
        try:
            evolution_reconcile.close_linear_issue(
                "I1", "STATE-DONE", "key", "closing comment"
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("RuntimeError not raised")

    assert mock_open.call_count == 1  # 仅 issueUpdate，未进入 commentCreate


# ---------------------------------------------------------------------------
# get_team_done_state_id / get_linear_issue
# ---------------------------------------------------------------------------
def test_get_team_done_state_id_returns_completed():
    """返回 type==completed 的状态 ID。"""
    resp = {
        "data": {
            "team": {
                "states": {
                    "nodes": [
                        {"id": "S1", "name": "进行中", "type": "started"},
                        {"id": "DONE-ID", "name": "已完成", "type": "completed"},
                    ]
                }
            }
        }
    }
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm(resp)
        state_id = evolution_reconcile.get_team_done_state_id("TEAM", "key")

    assert state_id == "DONE-ID"


def test_get_team_done_state_id_none_when_no_completed():
    """无 completed 状态 → 返回 None。"""
    resp = {
        "data": {
            "team": {
                "states": {
                    "nodes": [
                        {"id": "S1", "name": "进行中", "type": "started"},
                    ]
                }
            }
        }
    }
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm(resp)
        state_id = evolution_reconcile.get_team_done_state_id("TEAM", "key")

    assert state_id is None


def test_get_linear_issue_returns_issue():
    """返回 Issue 字典。"""
    resp = {
        "data": {
            "issue": {
                "id": "UUID-1",
                "identifier": "INFRA-175",
                "state": {"name": "进行中", "type": "started"},
            }
        }
    }
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm(resp)
        issue = evolution_reconcile.get_linear_issue("INFRA-175", "key")

    assert issue["identifier"] == "INFRA-175"
    assert issue["state"]["type"] == "started"


def test_get_linear_issue_none_when_missing():
    """Issue 不存在 → 返回 None。"""
    with patch("evolution_reconcile.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_cm({"data": {"issue": None}})
        issue = evolution_reconcile.get_linear_issue("INFRA-999", "key")

    assert issue is None


# ---------------------------------------------------------------------------
# reconcile 编排（patch 顶层 helper，聚焦编排逻辑）
# ---------------------------------------------------------------------------
def _start_reconcile_mocks(
    closed_issues,
    ref_map,
    done_state_id="DONE-ID",
    linear_issues=None,
):
    """启动一组 reconcile 依赖的 mock。

    返回 ``(patchers, mocks)``：
      - patchers: list，用于测试结束后 ``.stop()``。
      - mocks: dict，键 list_closed / done_state / extract / get_issue / close。
    """
    linear_issues = linear_issues or {}

    def _extract(number, repo):
        return ref_map.get(number)

    def _get_issue(ref, api_key):
        return linear_issues.get(ref)

    patchers = [
        patch(
            "evolution_reconcile.list_closed_evolution_issues",
            return_value=closed_issues,
        ),
        patch(
            "evolution_reconcile.get_team_done_state_id",
            return_value=done_state_id,
        ),
        patch("evolution_reconcile.extract_linear_ref", side_effect=_extract),
        patch("evolution_reconcile.get_linear_issue", side_effect=_get_issue),
        patch("evolution_reconcile.close_linear_issue"),
    ]
    started = [p.start() for p in patchers]
    mocks = {
        "list_closed": started[0],
        "done_state": started[1],
        "extract": started[2],
        "get_issue": started[3],
        "close": started[4],
    }
    return patchers, mocks


def test_reconcile_closes_non_terminal():
    """非终态 Linear Issue → 关闭并留言，ref 进入 closed_linear。"""
    closed = [{"number": 101, "title": "T", "closedAt": "2026-01-01"}]
    linear_issues = {
        "INFRA-101": {
            "id": "UUID-101",
            "identifier": "INFRA-101",
            "state": {"name": "进行中", "type": "started"},
        }
    }
    patchers, mocks = _start_reconcile_mocks(closed, {101: "INFRA-101"}, linear_issues=linear_issues)
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary["checked"] == 1
    assert summary["closed_linear"] == ["INFRA-101"]
    assert summary["already_terminal"] == []
    assert summary["no_ref"] == []
    assert summary["errors"] == []

    # close_linear_issue 应被以 (issue_uuid, done_state_id, api_key, comment) 调用
    mocks["close"].assert_called_once()
    args, kwargs = mocks["close"].call_args
    assert args[0] == "UUID-101"
    assert args[1] == "DONE-ID"
    assert args[2] == "key"
    comment = args[3]
    assert "hdot123/memory#101" in comment
    assert "INFRA-175" in comment


def test_reconcile_skips_already_terminal():
    """已终态（completed）Linear Issue → 不关闭，ref 进入 already_terminal。"""
    closed = [{"number": 202, "title": "T", "closedAt": "2026-01-01"}]
    linear_issues = {
        "INFRA-202": {
            "id": "UUID-202",
            "identifier": "INFRA-202",
            "state": {"name": "已完成", "type": "completed"},
        }
    }
    patchers, mocks = _start_reconcile_mocks(closed, {202: "INFRA-202"}, linear_issues=linear_issues)
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary["checked"] == 1
    assert summary["closed_linear"] == []
    assert summary["already_terminal"] == ["INFRA-202"]
    assert summary["errors"] == []

    mocks["close"].assert_not_called()


def test_reconcile_skips_canceled_terminal():
    """canceled 也是终态 → 跳过。"""
    closed = [{"number": 303, "title": "T", "closedAt": "2026-01-01"}]
    linear_issues = {
        "INFRA-303": {
            "id": "UUID-303",
            "identifier": "INFRA-303",
            "state": {"name": "已取消", "type": "canceled"},
        }
    }
    patchers, mocks = _start_reconcile_mocks(closed, {303: "INFRA-303"}, linear_issues=linear_issues)
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary["already_terminal"] == ["INFRA-303"]
    assert summary["closed_linear"] == []
    mocks["close"].assert_not_called()


def test_reconcile_no_linkback():
    """无 linkback 评论 → 无 Linear 调用，number 进入 no_ref。"""
    closed = [{"number": 404, "title": "T", "closedAt": "2026-01-01"}]
    patchers, mocks = _start_reconcile_mocks(closed, {404: None})
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary["checked"] == 1
    assert summary["no_ref"] == [404]
    assert summary["closed_linear"] == []
    assert summary["errors"] == []

    mocks["get_issue"].assert_not_called()
    mocks["close"].assert_not_called()


def test_reconcile_no_closed_issues():
    """无关闭 Issue → 空结果，无任何 Linear 调用。"""
    patchers, mocks = _start_reconcile_mocks([], {})
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary == {
        "checked": 0,
        "closed_linear": [],
        "already_terminal": [],
        "no_ref": [],
        "errors": [],
    }
    mocks["get_issue"].assert_not_called()
    mocks["close"].assert_not_called()


def test_reconcile_no_done_state_returns_error():
    """无 completed 状态 → 返回错误，不处理任何 Issue。"""
    patchers, mocks = _start_reconcile_mocks(
        [{"number": 1, "title": "T", "closedAt": "x"}], {1: "INFRA-1"},
        done_state_id=None,
    )
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary["checked"] == 0
    assert summary["errors"], "should contain an error"
    assert "completed-type state" in summary["errors"][0]
    # list_closed_evolution_issues 不应被调用（提前返回）
    mocks["list_closed"].assert_not_called()


def test_reconcile_records_error_when_close_fails():
    """close_linear_issue 抛错 → 记录到 errors，不进入 closed_linear。"""
    closed = [{"number": 1, "title": "T", "closedAt": "x"}]
    linear_issues = {
        "INFRA-1": {
            "id": "UUID-1",
            "identifier": "INFRA-1",
            "state": {"name": "进行中", "type": "started"},
        }
    }
    patchers, mocks = _start_reconcile_mocks(
        closed, {1: "INFRA-1"}, linear_issues=linear_issues
    )
    mocks["close"].side_effect = RuntimeError("linear down")
    try:
        summary = evolution_reconcile.reconcile(
            "hdot123/memory", "evolution-found", "TEAM", "key"
        )
    finally:
        for p in patchers:
            p.stop()

    assert summary["closed_linear"] == []
    assert summary["errors"], "should record the failure"
    assert "INFRA-1" in summary["errors"][0]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_missing_api_key_returns_1():
    """缺少 LINEAR_API_KEY → 返回 1，不调用 reconcile。"""
    env = {"LINEAR_API_KEY": ""}
    with patch.dict("os.environ", env, clear=False), \
            patch("evolution_reconcile.reconcile") as mock_reconcile, \
            patch("builtins.print") as mock_print:
        rc = evolution_reconcile.main()

    assert rc == 1
    mock_reconcile.assert_not_called()
    mock_print.assert_called()
    args, kwargs = mock_print.call_args
    assert kwargs.get("file") is not None  # 输出到 stderr


def test_main_success_returns_0_and_prints_summary():
    """有 API Key → 调用 reconcile，打印汇总，返回 0。"""
    env = {
        "LINEAR_API_KEY": "key",
        "EVOLUTION_REPO": "hdot123/memory",
        "EVOLUTION_TEAM_ID": "TEAM",
        "EVOLUTION_DEDUP_LABEL": "evolution-found",
    }
    fake_summary = {
        "checked": 0,
        "closed_linear": [],
        "already_terminal": [],
        "no_ref": [],
        "errors": [],
    }
    with patch.dict("os.environ", env, clear=False), \
            patch("evolution_reconcile.reconcile", return_value=fake_summary) as mock_reconcile, \
            patch("builtins.print"):
        rc = evolution_reconcile.main()

    assert rc == 0
    mock_reconcile.assert_called_once_with(
        "hdot123/memory", "evolution-found", "TEAM", "key"
    )
