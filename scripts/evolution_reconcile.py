"""GitHub→Linear 反向补偿工具 (INFRA-175 / GAP-B).

背景
----
evolution scanner (`scripts/evolution_utils.py::auto_close_resolved`) 在 finding
解决后关闭对应的 GitHub Issue，并依赖 Linear 原生 GitHub 集成把这次关闭同步到
对应 Linear Issue。当同步失败时，Linear Issue 永久卡在「进行中」等非终态，形成
僵尸 Issue。

`~/.factory/webhook/scripts/reconcile-evolution.sh` 的 §4b 只处理 Linear→GitHub
方向（Linear Issue 终态 → 关闭对应 open GitHub Issue）。本模块补齐反向方向：

    GitHub→Linear 反向补偿 (GAP-B / INFRA-175)
    已关闭的 GitHub evolution-found Issue → 通过 `<!-- linear-linkback -->` 评论
    定位对应 Linear Issue → 若 Linear Issue 仍非终态，通过 Linear API 关闭并留言。

幂等性：仅处理非终态 Linear Issue；已处于 completed/canceled 终态的 Issue 会被跳过，
后续运行不会重复操作。

安全约束：本工具仅通过 Linear GraphQL API 读取/写入，不对 GitHub 执行任何写操作。
测试通过 mock subprocess + urllib 覆盖，禁止在生产前对真实 Linear 执行。
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
LINEAR_API_URL = "https://api.linear.app/graphql"

# INFRA team UUID (verified)
DEFAULT_TEAM_ID = "6f378ffa-2cc9-4c5d-a131-efc7fba06485"
DEFAULT_REPO = "hdot123/memory"
DEFAULT_LABEL = "evolution-found"

# Linear 终态类型：completed / canceled 视为已关闭，跳过
TERMINAL_STATE_TYPES = ("completed", "canceled")

# 提取 Linear 标识符，如 INFRA-191
LINEAR_REF_RE = re.compile(r"([A-Z]+-\d+)")

# ---------------------------------------------------------------------------
# GraphQL 查询模板（verified working）
# ---------------------------------------------------------------------------
TEAM_STATES_QUERY = (
    "query($id:String!){ team(id:$id){ states{ nodes{ id name type } } } }"
)
ISSUE_QUERY = (
    "query($id:String!){ issue(id:$id){ id identifier state{ name type } } }"
)
ISSUE_UPDATE_MUTATION = (
    "mutation($id:String!,$stateId:String!){"
    " issueUpdate(id:$id,input:{stateId:$stateId}){"
    " success issue{ id state{ name type } } } }"
)
COMMENT_CREATE_MUTATION = (
    "mutation($iid:String!,$body:String!){"
    " commentCreate(input:{issueId:$iid,body:$body}){ success } }"
)

# 关闭时附加的可追溯评论（中文）
CLOSING_COMMENT_TEMPLATE = (
    "GitHub Issue {repo}#{num} 已关闭（evolution finding 已解决），"
    "本 Linear Issue 由 GitHub→Linear 反向补偿层（INFRA-175）关闭。"
)


# ---------------------------------------------------------------------------
# GitHub 操作（subprocess + gh，遵循 evolution_utils.py 既有模式）
# ---------------------------------------------------------------------------
def gh_json(args: list[str], repo: str) -> Any:
    """运行 `gh` 子命令并返回解析后的 JSON。

    Args:
        args: 传给 `gh` 的参数（不含 `--repo`）。
        repo: GitHub 仓库（owner/name）。

    Returns:
        解析后的 JSON（list 或 dict）。当 stdout 为空时，list 类命令返回 ``[]``，
        其余返回 ``{}``。

    Raises:
        RuntimeError: gh 退出码非 0。
    """
    cmd = ["gh"] + args + ["--repo", repo]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"gh command failed: {' '.join(cmd)}\nstderr: {result.stderr}"
        )
    stdout = result.stdout.strip()
    if not stdout:
        return [] if "list" in args else {}
    return json.loads(stdout)


def list_closed_evolution_issues(repo: str, label: str) -> list[dict[str, Any]]:
    """列出最近关闭的 evolution-found GitHub Issue。

    Returns:
        Issue 字典列表，字段：number, title, closedAt。
    """
    data = gh_json(
        [
            "issue", "list",
            "--search", f"label:{label}",
            "--state", "closed",
            "--limit", "50",
            "--json", "number,title,closedAt",
        ],
        repo,
    )
    return data if isinstance(data, list) else []


def extract_linear_ref(issue_number: Any, repo: str) -> str | None:
    """从 GitHub Issue 评论中提取 Linear 标识符。

    扫描 issue 的所有评论，寻找包含 ``linear-linkback`` 标记的评论，从中正则
    提取首个 ``([A-Z]+-\\d+)`` 标识符。未找到返回 None。

    Args:
        issue_number: GitHub Issue 编号。
        repo: GitHub 仓库（owner/name）。

    Returns:
        Linear 标识符（如 ``INFRA-191``）或 None。
    """
    data = gh_json(
        ["issue", "view", str(issue_number), "--json", "comments"],
        repo,
    )
    comments = data.get("comments", []) if isinstance(data, dict) else []
    for comment in comments:
        body = comment.get("body", "") or ""
        if "linear-linkback" in body:
            match = LINEAR_REF_RE.search(body)
            if match:
                return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Linear GraphQL 操作（urllib，遵循「无第三方依赖」原则）
# ---------------------------------------------------------------------------
def linear_request(
    query: str, api_key: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    """向 Linear GraphQL endpoint 发起 POST 请求。

    Args:
        query: GraphQL 查询/变更字符串。
        api_key: Linear API Key。
        variables: 查询变量。

    Returns:
        响应 JSON 的 ``data`` 字段。

    Raises:
        RuntimeError: HTTP 错误或响应包含 GraphQL ``errors``。
    """
    payload = json.dumps(
        {"query": query, "variables": variables or {}}
    ).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_API_URL,
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
    data = json.loads(body)
    if "errors" in data:
        raise RuntimeError(f"Linear API errors: {data['errors']}")
    result: dict[str, Any] = data.get("data", {})
    return result


def get_team_done_state_id(team_id: str, api_key: str) -> str | None:
    """查询团队工作流状态，返回 ``type == completed`` 的状态 ID。

    Args:
        team_id: Linear team UUID。
        api_key: Linear API Key。

    Returns:
        completed 类型状态 ID，未找到返回 None。
    """
    data = linear_request(TEAM_STATES_QUERY, api_key, {"id": team_id})
    states = (
        data.get("team", {}).get("states", {}).get("nodes", [])
    )
    for state in states:
        if state.get("type") == "completed":
            state_id: str | None = state.get("id")
            return state_id
    return None


def get_linear_issue(identifier: str, api_key: str) -> dict[str, Any] | None:
    """按标识符（如 INFRA-175）获取 Linear Issue。

    Returns:
        Issue 字典（含 id, identifier, state{name,type}）或 None。
    """
    data = linear_request(ISSUE_QUERY, api_key, {"id": identifier})
    issue = data.get("issue")
    return issue if issue else None


def close_linear_issue(
    issue_id: str, state_id: str, api_key: str, comment: str
) -> None:
    """将 Linear Issue 流转到终态并附加可追溯评论。

    Args:
        issue_id: Linear Issue 内部 UUID。
        state_id: 目标 completed 状态 ID。
        api_key: Linear API Key。
        comment: 关闭时附加的评论。

    Raises:
        RuntimeError: issueUpdate 或 commentCreate 失败。
    """
    update_result = linear_request(
        ISSUE_UPDATE_MUTATION, api_key, {"id": issue_id, "stateId": state_id}
    )
    if not update_result.get("issueUpdate", {}).get("success"):
        raise RuntimeError(
            f"issueUpdate did not succeed for {issue_id}: {update_result}"
        )
    comment_result = linear_request(
        COMMENT_CREATE_MUTATION, api_key, {"iid": issue_id, "body": comment}
    )
    if not comment_result.get("commentCreate", {}).get("success"):
        raise RuntimeError(
            f"commentCreate did not succeed for {issue_id}: {comment_result}"
        )


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------
def reconcile(repo: str, label: str, team_id: str, api_key: str) -> dict[str, Any]:
    """GitHub→Linear 反向补偿编排。

    流程：
        1. 解析团队 completed 状态 ID。
        2. 列出最近关闭的 evolution-found GitHub Issue。
        3. 对每个 Issue，通过 linkback 评论提取 Linear 标识符。
        4. 获取 Linear Issue 状态；非终态则关闭并留言。

    Args:
        repo: GitHub 仓库（owner/name）。
        label: evolution 去重标签。
        team_id: Linear team UUID。
        api_key: Linear API Key。

    Returns:
        汇总字典::

            {
              "checked": int,
              "closed_linear": [refs],
              "already_terminal": [refs],
              "no_ref": [issue_numbers],
              "errors": [...],
            }
    """
    summary: dict[str, Any] = {
        "checked": 0,
        "closed_linear": [],
        "already_terminal": [],
        "no_ref": [],
        "errors": [],
    }

    done_state_id = get_team_done_state_id(team_id, api_key)
    if not done_state_id:
        summary["errors"].append(
            f"No completed-type state found for team {team_id}"
        )
        return summary

    issues = list_closed_evolution_issues(repo, label)
    for issue in issues:
        summary["checked"] += 1
        number = issue.get("number")
        ref = extract_linear_ref(number, repo)
        if not ref:
            summary["no_ref"].append(number)
            continue

        try:
            linear_issue = get_linear_issue(ref, api_key)
        except Exception as e:  # noqa: BLE001 - 记录错误继续处理后续 Issue
            summary["errors"].append(f"Failed to fetch Linear issue {ref}: {e}")
            continue

        if not linear_issue:
            summary["errors"].append(f"Linear issue not found: {ref}")
            continue

        state_type = (linear_issue.get("state") or {}).get("type")
        if state_type in TERMINAL_STATE_TYPES:
            summary["already_terminal"].append(ref)
            continue

        comment = CLOSING_COMMENT_TEMPLATE.format(repo=repo, num=number)
        try:
            close_linear_issue(
                linear_issue["id"], done_state_id, api_key, comment
            )
            summary["closed_linear"].append(ref)
        except Exception as e:  # noqa: BLE001 - 记录错误继续处理后续 Issue
            summary["errors"].append(f"Failed to close Linear issue {ref}: {e}")

    return summary


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def main() -> int:
    """CLI 入口：从环境变量读取配置并执行 reconcile。

    环境变量：
        LINEAR_API_KEY        (必填) Linear API Key。
        EVOLUTION_TEAM_ID     (默认 INFRA team UUID)。
        EVOLUTION_REPO        (默认 hdot123/memory)。
        EVOLUTION_DEDUP_LABEL (默认 evolution-found)。

    Returns:
        0 成功；1 缺少 API Key。
    """
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print(
            "Error: LINEAR_API_KEY environment variable is required",
            file=sys.stderr,
        )
        return 1

    team_id = os.environ.get("EVOLUTION_TEAM_ID", DEFAULT_TEAM_ID)
    repo = os.environ.get("EVOLUTION_REPO", DEFAULT_REPO)
    label = os.environ.get("EVOLUTION_DEDUP_LABEL", DEFAULT_LABEL)

    summary = reconcile(repo, label, team_id, api_key)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
