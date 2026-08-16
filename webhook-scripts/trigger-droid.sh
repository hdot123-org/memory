#!/bin/bash
# trigger-droid.sh — Linear webhook → droid exec 异步触发器
# 由 adnanh/webhook 调用，立即返回 accepted，后台执行 droid + 回写 Linear
#
# 修复历史:
#   2026-08-01: 修复 LINEAR_API_KEY 后台获取失败、ISSUE_UUID 丢失、权限不足、成功未回写

set -uo pipefail

# === 参数 ===
ACTION="${1:-}"
TYPE="${2:-}"
ISSUE_REF="${3:-}"
ISSUE_UUID="${4:-}"
TEAM_KEY="${5:-}"
ISSUE_TITLE="${6:-}"

# === 配置 ===
WEBHOOK_BASE="/Users/busiji/.factory/webhook"
LOG_DIR="${WEBHOOK_BASE}/logs"
REPO_CONFIG="/Users/busiji/.factory/config/repositories.yml"

# === 日志 ===
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/trigger-${ISSUE_REF:-unknown}-${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# === Execution state sync (status files for dashboard) ===
STATUS_DIR="${WEBHOOK_BASE}/status"
mkdir -p "$STATUS_DIR" 2>/dev/null

# Atomic status file write (write-temp + rename)
_write_status() {
    local ref="$1"
    local json="$2"
    local status_file="${STATUS_DIR}/${ref}.json"
    local tmp_file="${status_file}.tmp"
    # Clean stale .tmp (m-4)
    rm -f "$tmp_file" 2>/dev/null
    # Write to temp
    echo "$json" > "$tmp_file" 2>/dev/null
    # Atomic rename (m-6: non-fatal on failure)
    if ! mv "$tmp_file" "$status_file" 2>/dev/null; then
        log "WARN: Status file write failed for $ref (continuing execution)"
        rm -f "$tmp_file" 2>/dev/null
    fi
}

# Start per-issue heartbeat (background loop)
_start_heartbeat() {
    local hb_ref="$1"
    local hb_pid_expected="$2"
    local hb_parent_pid="$3"
    local hb_status_file="${STATUS_DIR}/${hb_ref}.json"
    (
        while true; do
            sleep 30
            # C-2: Check parent alive — self-terminate if dead (orphan prevention)
            if ! kill -0 "$hb_parent_pid" 2>/dev/null; then
                break
            fi
            # FR-11 + status check: read status file, verify still running + PID matches
            # (self-terminate on mismatch or terminal state)
            /opt/homebrew/bin/python3 -c "
import json, sys, os
try:
    with open('$hb_status_file') as f:
        d = json.load(f)
    if d.get('status') != 'running':
        sys.exit(1)
    if str(d.get('pid', '')) != '$hb_pid_expected':
        sys.exit(1)
except:
    sys.exit(1)
" 2>/dev/null || break
            # Update heartbeat field atomically
            /opt/homebrew/bin/python3 -c "
import json, os, datetime
try:
    with open('$hb_status_file') as f:
        d = json.load(f)
    d['heartbeat'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    tmp = '$hb_status_file.tmp'
    with open(tmp, 'w') as f:
        json.dump(d, f)
    os.rename(tmp, '$hb_status_file')
except:
    pass
" 2>/dev/null
        done
    ) &
    HEARTBEAT_PID=$!
}

# Stop heartbeat
_stop_heartbeat() {
    if [ -n "${HEARTBEAT_PID:-}" ]; then
        kill "$HEARTBEAT_PID" 2>/dev/null || true
        wait "$HEARTBEAT_PID" 2>/dev/null || true
        unset HEARTBEAT_PID
    fi
}

# === M3: ECHO_DROID 启动警告 ===
if [ "${ECHO_DROID:-0}" = "1" ]; then
    log "⚠️ DRY-RUN MODE: ECHO_DROID=1 — all droid exec calls are no-ops"
fi

# === H5: PostHog 事件上报 (distinct_id=linear-webhook) ===
send_posthog_event() {
    local event_type="$1"
    local identifier="$2"
    local stage="$3"
    local detail="$4"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    curl -s -X POST "https://us.posthog.com/batch/" \
        -H "Content-Type: application/json" \
        -d "{
            \"api_key\": \"phc_o963uzVAku9jd4SB4tgV598LUu2oJQHKFBy3RKjtgAVs\",
            \"batch\": [{
                \"event\": \"linear_webhook_failure\",
                \"properties\": {
                    \"error_type\": \"$event_type\",
                    \"identifier\": \"$identifier\",
                    \"stage\": \"$stage\",
                    \"detail\": \"$detail\",
                    \"distinct_id\": \"linear-webhook\"
                },
                \"timestamp\": \"$timestamp\"
            }]
        }" >> "$LOG_FILE" 2>&1 || true
}

# === C6: with_timeout() — macOS 无 timeout 命令，纯 bash 实现 ===
with_timeout() {
    local timeout_sec=$1; shift
    local tmp_output
    tmp_output=$(mktemp)
    "$@" > "$tmp_output" 2>&1 &
    local pid=$!
    local elapsed=0
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 10; elapsed=$((elapsed + 10))
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null; sleep 5
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null
        fi
        wait "$pid" 2>/dev/null
        cat "$tmp_output"; rm -f "$tmp_output"; return 124
    fi
    wait "$pid" 2>/dev/null; local rc=$?
    cat "$tmp_output"; rm -f "$tmp_output"; return "$rc"
}

# === 获取 Linear API Key（通过 1Password MCP，无需 Touch ID） ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/op-mcp.sh"

LINEAR_API_KEY="${LINEAR_API_KEY:-}"
if [ -z "$LINEAR_API_KEY" ]; then
    LINEAR_API_KEY=$(op_get_field "$OP_VAULT_SEVER" "elgcm2nzfza2hjb3yffpkijj7y" "凭据" || true)
fi
if [ -n "$LINEAR_API_KEY" ]; then
    log "LINEAR_API_KEY: retrieved OK (${#LINEAR_API_KEY} chars)"
else
    log "WARN: LINEAR_API_KEY is empty — Linear comment writeback will fail"
    # H3: API Key missing sends PostHog alert
    send_posthog_event "api_key_missing" "${ISSUE_REF:-unknown}" "api_key" "MCP op_get_field returned empty"
fi

export LINEAR_API_KEY

# === ISSUE_UUID 回退解析（如果 webhook 未传 UUID，从 ISSUE_REF 解析） ===
resolve_issue_uuid() {
    local issue_ref="$1"
    if [ -z "$issue_ref" ] || [ -z "$LINEAR_API_KEY" ]; then
        echo ""
        return
    fi
    /opt/homebrew/bin/python3 -c "
import json, urllib.request, sys
query = '{ issue(id: \"%s\") { id } }' % '$issue_ref'
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': '$LINEAR_API_KEY', 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read().decode())
        print(d.get('data', {}).get('issue', {}).get('id', ''))
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null
}

# 如果 ISSUE_UUID 为空，尝试从 ISSUE_REF 解析
if [ -z "$ISSUE_UUID" ] && [ -n "$ISSUE_REF" ]; then
    log "ISSUE_UUID is empty, resolving from ISSUE_REF=${ISSUE_REF}..."
    ISSUE_UUID=$(resolve_issue_uuid "$ISSUE_REF")
    if [ -n "$ISSUE_UUID" ]; then
        log "ISSUE_UUID resolved: ${ISSUE_UUID}"
    else
        log "WARN: Failed to resolve ISSUE_UUID from ISSUE_REF"
        # M-LIN-5: UUID resolution failure sends PostHog
        send_posthog_event "uuid_resolution_failed" "${ISSUE_REF:-unknown}" "uuid_resolve" "Failed to resolve UUID from ISSUE_REF"
    fi
fi

# === ISSUE_REF 反向解析（从 UUID 查询 identifier/team/title） ===
# Comment webhook 事件只传 UUID 不传 REF，需要反向查询
resolve_issue_ref() {
    local issue_uuid="$1"
    if [ -z "$issue_uuid" ] || [ -z "$LINEAR_API_KEY" ]; then
        echo ""
        return
    fi
    /opt/homebrew/bin/python3 -c "
import json, urllib.request, sys
query = '{ issue(id: \"%s\") { identifier team { key } title } }' % '$issue_uuid'
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': '$LINEAR_API_KEY', 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read().decode())
        issue = d.get('data', {}).get('issue', {})
        identifier = issue.get('identifier', '')
        team_key = issue.get('team', {}).get('key', '')
        title = issue.get('title', '')
        print(f'{identifier}|{team_key}|{title}')
except Exception as e:
    print('||', file=sys.stderr)
" 2>/dev/null
}

# === PR_REF 解析（从 PR number 查询 PR 元数据） ===
# 用于 webhook 回写时获取 PR 信息（number, title, state, url, branch）
resolve_pr_ref() {
    local pr_number="$1"
    local github_repo="${2:-}"
    if [ -z "$pr_number" ]; then
        echo ""
        return
    fi
    local gh_args=(pr view "$pr_number" --json number,title,state,url,headRefName)
    if [ -n "$github_repo" ]; then
        gh_args+=(--repo "$github_repo")
    fi
    gh "${gh_args[@]}" --jq '"\(.number)|\(.title)|\(.state)|\(.url)|\(.headRefName)"' 2>/dev/null || echo ""
}

# === 仓库路由 ===
# route_repo(team, issue_uuid) — smart multi-repo matching
# Priority 1: match issue's Linear project name against repos[].paths.when.projectNames
# Priority 2: repos marked default: true
# Priority 3: repos[0] (backward compat)
route_repo() {
    local team="$1"
    local issue_uuid="${2:-}"
    if [ ! -f "$REPO_CONFIG" ]; then
        echo ""
        return
    fi
    /opt/homebrew/bin/python3 -c "
import yaml, os, json, urllib.request, sys

REPO_CONFIG = '$REPO_CONFIG'
TEAM = '$team'
ISSUE_UUID = '$issue_uuid'
API_KEY = os.environ.get('LINEAR_API_KEY', '')

def get_issue_project_name(issue_uuid, api_key):
    \"\"\"Query Linear API for issue's project name. Returns None on failure.\"\"\"
    if not issue_uuid or not api_key:
        return None
    try:
        query = '{ issue(id: \"%s\") { project { name } } }' % issue_uuid
        req = urllib.request.Request(
            'https://api.linear.app/graphql',
            data=json.dumps({'query': query}).encode(),
            headers={'Authorization': api_key, 'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
            project = d.get('data', {}).get('issue', {}).get('project')
            if project:
                return project.get('name', '')
            return None
    except Exception:
        return None

with open(REPO_CONFIG) as f:
    cfg = yaml.safe_load(f)

for td in cfg.get('teams', {}).values():
    if td.get('teamKey', '').upper() != TEAM.upper():
        continue
    repos = td.get('repos', [])
    if not repos:
        break

    # Priority 1: Match by project name
    project_name = get_issue_project_name(ISSUE_UUID, API_KEY)
    if project_name:
        for repo in repos:
            for path_entry in repo.get('paths', []):
                when = path_entry.get('when', {})
                project_names = when.get('projectNames', [])
                if project_name in project_names:
                    print(os.path.expanduser(repo.get('repoPath', '')))
                    sys.exit(0)

    # Priority 2: Fall back to repos marked default: true
    for repo in repos:
        if repo.get('default', False):
            print(os.path.expanduser(repo.get('repoPath', '')))
            sys.exit(0)

    # Priority 3: Final fallback — repos[0] (backward compat)
    print(os.path.expanduser(repos[0].get('repoPath', '')))
    break
" 2>>"$LOG_FILE" || echo ""
}

# === 回写 Linear comment ===
write_linear_comment() {
    local issue_uuid="$1"
    local body="$2"
    if [ -z "$issue_uuid" ]; then
        log "WARN: Cannot write comment (ISSUE_UUID missing)"
        return 1
    fi
    if [ -z "$LINEAR_API_KEY" ]; then
        log "WARN: Cannot write comment (LINEAR_API_KEY missing)"
        return 1
    fi
    log "Writing comment to Linear issue $issue_uuid..."
    local tmpfile="/tmp/_linear_comment_$$.txt"
    echo "$body" > "$tmpfile"
    /opt/homebrew/bin/python3 /Users/busiji/.factory/webhook/scripts/write_comment.py \
        "$issue_uuid" "$LINEAR_API_KEY" "$tmpfile" >> "$LOG_FILE" 2>&1
    local rc=$?
    rm -f "$tmpfile"
    if [ "$rc" -eq 0 ]; then
        log "Linear comment written successfully."
    else
        log "ERROR: Linear comment write failed (rc=$rc)"
    fi
    return $rc
}

# ============================================================================
# Gate A: 状态门禁 — 阻止无 Droid session 记录的 Done 转换 (INFRA-67)
#
# 当 ACTION=update 且 issue 被移到 Done/Cancelled 时，检查是否有有效的 Droid session：
#   - state.type 非 completed/canceled → 保持原防风暴 skip 行为 (exit 0)
#   - 有有效 sessionId → 放行 (exit 0)
#   - 无有效 sessionId → 自动回退到 In Progress + 评论 + exit 1
#
# 错误处理：Linear API 调用失败时 fail-open (保持 skip)，不阻塞正常流程。
# ============================================================================
gate_check_done_transition() {
    # 1. 通过 Linear GraphQL 查询 issue 当前 state.type
    local state_type
    state_type=$(ISSUE_UUID="$ISSUE_UUID" LINEAR_API_KEY="$LINEAR_API_KEY" /opt/homebrew/bin/python3 -c "
import json, urllib.request, os, sys, socket
socket.setdefaulttimeout(15)
issue_uuid = os.environ['ISSUE_UUID']
api_key = os.environ['LINEAR_API_KEY']
if not issue_uuid or not api_key:
    sys.exit(0)
query = '{ issue(id: \"' + issue_uuid + '\") { state { name type } } }'
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': api_key, 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
        state = d.get('data', {}).get('issue', {}).get('state', {})
        print(state.get('type', ''))
except Exception:
    print('', file=sys.stderr)
    sys.exit(0)
" 2>>"$LOG_FILE") || state_type=""

    # 2. 只拦截 completed（已完成）。canceled（已取消）放行 — 取消是正常操作（重复、无效、测试清理），
    #    不需要 Droid session 记录。其他状态变更也保持原防风暴 skip 行为。
    if [ "$state_type" != "completed" ]; then
        log "SKIP: ACTION=update for Issue — metadata-only change (state.type=${state_type:-unknown}), not triggering Droid"
        exit 0
    fi

    log "GATE A: Detected Done transition for $ISSUE_REF (state.type=$state_type) — checking Droid session record"

    # 3. 检查 status 文件中是否有有效 sessionId
    local status_file="${STATUS_DIR}/${ISSUE_REF}.json"
    local has_valid_session
    has_valid_session=0
    if [ -f "$status_file" ]; then
        has_valid_session=$(/opt/homebrew/bin/python3 -c "
import json, sys
try:
    with open('$status_file') as f:
        d = json.load(f)
    sid = d.get('sessionId')
    if sid and str(sid).lower() not in ('none', 'null', ''):
        print(1)
    else:
        print(0)
except Exception:
    print(0)
" 2>/dev/null)
    fi

    # 4. 有有效 session → 放行
    if [ "${has_valid_session:-0}" = "1" ]; then
        log "GATE A PASS: $ISSUE_REF moved to Done with valid Droid session record — allowing transition"
        exit 0
    fi

    # 4.5. PR-merged override: 即使 Droid session 崩溃 (sessionId=null)，只要 PR 已合并就放行
    # 背景 (INFRA-243): Droid session 崩溃 (exitCode=1) 但 PR 仍成功创建并 merge 时，
    # GATE A 会无限阻塞 Done 转换（重复回退 Done→In Progress），造成死锁：
    #   - scanner 无法关闭 GitHub Issue（Linear 非终态）
    #   - Linear 原生 GitHub 集成重开 GitHub Issue（Linear 未 Done）
    # 检测到已合并 PR → 放行，打破死锁。
    # 失败处理：route_repo / git / gh 任一失败 → fall through 到 BLOCK（fail-closed）。
    local _override_repo_path
    _override_repo_path=$(route_repo "$TEAM_KEY" "$ISSUE_UUID" 2>>"$LOG_FILE")
    if [ -n "$_override_repo_path" ] && [ -d "$_override_repo_path/.git" ]; then
        local _override_gh_repo
        _override_gh_repo=$(git -C "$_override_repo_path" remote get-url origin 2>/dev/null | sed 's/.*github.com[:/]//' | sed 's/.git$//')
        if [ -n "$_override_gh_repo" ]; then
            local _merged_pr_json
            _merged_pr_json=$(gh pr list --repo "$_override_gh_repo" --state merged --search "$ISSUE_REF" --limit 1 --json number 2>/dev/null)
            if [ -n "$_merged_pr_json" ] && [ "$_merged_pr_json" != "[]" ]; then
                local _merged_pr_num
                _merged_pr_num=$(echo "$_merged_pr_json" | /opt/homebrew/bin/python3 -c "import json,sys; print(json.load(sys.stdin)[0]['number'])" 2>/dev/null)
                log "GATE A PASS (override): $ISSUE_REF moved to Done WITHOUT Droid session, but PR #${_merged_pr_num:-?} was merged in $_override_gh_repo — allowing transition"
                exit 0
            fi
        fi
    fi

    # 4.6. Sync-origin override (P0-3): GitHub close → Linear Done 同步
    # 场景：GitHub issue 被 PR 合并后自动关闭，Linear 同步触发 Done 转换
    # 检测：gh issue 已 closed 且 closed_at ≤ 10 分钟
    # 逻辑：证明 Done 是 GitHub close 的下游同步，非人工 Done → PASS
    # 失败处理：gh 查询失败 → fall through 到 BLOCK（fail-closed）
    local _sync_repo_path
    _sync_repo_path=$(route_repo "$TEAM_KEY" "$ISSUE_UUID" 2>>"$LOG_FILE")
    if [ -n "$_sync_repo_path" ] && [ -d "$_sync_repo_path/.git" ]; then
        local _sync_gh_repo
        _sync_gh_repo=$(git -C "$_sync_repo_path" remote get-url origin 2>/dev/null | sed 's/.*github.com[:/]//' | sed 's/.git$//')
        if [ -n "$_sync_gh_repo" ]; then
            local _sync_check_result
            _sync_check_result=$(gh issue list --repo "$_sync_gh_repo" --search "$ISSUE_REF" --state all --limit 1 --json number,state,closedAt 2>/dev/null | /opt/homebrew/bin/python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta

try:
    data = json.load(sys.stdin)
    if not data:
        sys.exit(0)  # no issue found, fall through to BLOCK
    
    issue = data[0]
    state = issue.get('state', '')
    closed_at_str = issue.get('closedAt', '')
    
    if state != 'CLOSED':
        sys.exit(0)  # issue still open, fall through to BLOCK
    
    if not closed_at_str:
        sys.exit(0)  # no closedAt timestamp, fall through to BLOCK
    
    # Parse GitHub ISO 8601 timestamp
    closed_at = datetime.fromisoformat(closed_at_str.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    diff_minutes = (now - closed_at).total_seconds() / 60
    
    # PASS if closed within 10 minutes
    if diff_minutes <= 10:
        print('PASS')
        sys.exit(0)
    else:
        sys.exit(0)  # closed too long ago, fall through to BLOCK
except Exception:
    sys.exit(0)  # any error, fall through to BLOCK
" 2>/dev/null)
            
            if [ "$_sync_check_result" = "PASS" ]; then
                log "GATE A PASS (sync-origin): $ISSUE_REF — GitHub issue closed ≤10min, Done is downstream sync"
                exit 0
            fi
        fi
    fi

    # 5. 无有效 session → 打回：回退到 In Progress + 评论
    log "GATE A BLOCK: $ISSUE_REF moved to Done WITHOUT Droid session record — reverting to In Progress"

    # 解析 IN_PROGRESS_STATE_ID（source 带幂等 guard，安全重复 source）
    source "${SCRIPT_DIR}/lib/linear-queue.sh"
    if linear_queue_init "$TEAM_KEY" "$ISSUE_UUID" "$LINEAR_API_KEY"; then
        if linear_move_to_in_progress "$ISSUE_UUID"; then
            log "GATE A: Reverted $ISSUE_REF to In Progress"
        else
            log "WARN: GATE A: Failed to revert $ISSUE_REF to In Progress"
        fi
    else
        log "WARN: GATE A: linear_queue_init failed — cannot auto-revert state"
    fi

    # 评论告知
    write_linear_comment "$ISSUE_UUID" "⛔ 状态门禁：未检测到 Droid 执行记录（session ID）。此任务必须通过 Droid 流程执行。已自动回退到「进行中」。" || \
        log "WARN: GATE A: Failed to write gate comment to Linear"

    send_posthog_event "gate_a_blocked" "$ISSUE_REF" "state_gate" "Done transition without Droid session"

    exit 1
}

# === H4: writeback failure → GitHub Issue fallback ===
create_github_fallback_issue() {
    local issue_ref="$1"
    local message_type="$2"  # "success" or "failure"
    local detail="$3"
    local repo_path="$4"
    
    # Derive GitHub repo from repo_path
    local github_repo=""
    if [ -d "$repo_path/.git" ]; then
        github_repo=$(git -C "$repo_path" remote get-url origin 2>/dev/null | sed 's/.*github.com[:/]//' | sed 's/.git$//')
    fi
    if [ -z "$github_repo" ]; then
        log "WARN: Cannot determine GitHub repo for fallback Issue"
        send_posthog_event "fallback_issue_failed" "$issue_ref" "github_fallback" "Cannot determine GitHub repo"
        return 1
    fi
    
    log "Creating GitHub Issue fallback for Linear writeback failure..."
    
    # Dedup check
    local existing
    existing=$(gh issue list --repo "$github_repo" --label "linear-writeback-fallback" \
        --state all --search "Linear 回写失败: $issue_ref" --limit 1 2>/dev/null)
    if [ -n "$existing" ]; then
        log "SKIP: Fallback Issue already exists for $issue_ref"
        return 0
    fi
    
    local body="## Linear 回写失败兜底

**Issue**: $issue_ref
**类型**: $message_type
**详情**: $detail
**时间**: $(date '+%Y-%m-%d %H:%M:%S')
**日志**: \`$LOG_FILE\`

---
此 Issue 由 trigger-droid.sh 自动创建（Linear comment writeback 失败）。
需要人工检查 Linear 回写状态。"

    gh issue create \
        --repo "$github_repo" \
        --title "Linear 回写失败: $issue_ref ($message_type)" \
        --body "$body" \
        --label "needs-triage,linear-writeback-fallback" >> "$LOG_FILE" 2>&1 || {
        # H4/LIN-007: Fallback Issue failure sends PostHog
        log "WARN: Failed to create fallback GitHub Issue"
        send_posthog_event "fallback_issue_failed" "$issue_ref" "github_fallback" "gh issue create failed for $issue_ref"
        return 1
    }
    log "GitHub Issue fallback created successfully"
    return 0
}

# === 主流程 ===
log "=== trigger-droid.sh started ==="
log "ACTION=$ACTION TYPE=$TYPE ISSUE_REF=$ISSUE_REF ISSUE_UUID=${ISSUE_UUID:-<empty>} TEAM=$TEAM_KEY"

# === ISSUE_REF 解析守卫 ===
# 如果 ISSUE_REF 和 ISSUE_UUID 都空 → 真正跳过
# 如果 ISSUE_REF 空但 ISSUE_UUID 存在 → 用 UUID 反查 identifier, team.key, title
# 如果 ISSUE_REF 存在 → 正常流程（可能仍需 UUID 反查，已在上方处理）
if [ -z "$ISSUE_REF" ] && [ -z "$ISSUE_UUID" ]; then
    log "ERROR: Both ISSUE_REF and ISSUE_UUID are empty, skipping"
    send_posthog_event "empty_issue_ref_and_uuid" "unknown" "validation" "ISSUE_REF and ISSUE_UUID both empty"
    exit 0
fi

if [ -z "$ISSUE_REF" ] && [ -n "$ISSUE_UUID" ]; then
    log "ISSUE_REF empty, resolving from UUID=$ISSUE_UUID via Linear API..."
    RESOLVED=$(resolve_issue_ref "$ISSUE_UUID")
    if [ -n "$RESOLVED" ]; then
        ISSUE_REF=$(echo "$RESOLVED" | cut -d'|' -f1)
        _RESOLVED_TEAM=$(echo "$RESOLVED" | cut -d'|' -f2)
        _RESOLVED_TITLE=$(echo "$RESOLVED" | cut -d'|' -f3)

        # 回填 TEAM_KEY（Comment webhook 事件中 TEAM 为空）
        if [ -z "$TEAM_KEY" ] && [ -n "$_RESOLVED_TEAM" ]; then
            TEAM_KEY="$_RESOLVED_TEAM"
        fi
        # 回填 ISSUE_TITLE（如未提供）
        if [ -z "$ISSUE_TITLE" ] && [ -n "$_RESOLVED_TITLE" ]; then
            ISSUE_TITLE="$_RESOLVED_TITLE"
        fi
    fi

    if [ -z "$ISSUE_REF" ]; then
        log "ERROR: Failed to resolve ISSUE_REF from UUID=$ISSUE_UUID"
        send_posthog_event "ref_resolution_failed" "$ISSUE_UUID" "ref_resolve" "Failed to resolve REF from UUID"
        exit 0
    fi
    log "Resolved: UUID=$ISSUE_UUID -> REF=$ISSUE_REF TEAM=$TEAM_KEY TITLE=${ISSUE_TITLE:0:60}"
fi

# === Team whitelist (补偿层): 只处理 INFRA 团队事件 ===
if [ -n "$TEAM_KEY" ] && [ "$TEAM_KEY" != "INFRA" ]; then
    log "SKIP: team whitelist filtered out team=$TEAM_KEY"
    exit 0
fi

# === Event type filter (补偿层): 跳过 remove/delete 事件 ===
if [ "$ACTION" = "remove" ] || [ "$ACTION" = "delete" ]; then
    log "SKIP: event type filtered (ACTION=$ACTION)"
    exit 0
fi

# === GAP-D (INFRA-180): 过滤所有 Comment.create 事件 ===
# Comment.create webhook 主要来自 GitHub/Linear 同步、bot 回写等系统行为，
# 不应触发完整 droid exec。INFRA-172 起初仅过滤 evolution-found 标签的 issue
# （scanner 噪音），INFRA-180 扩展为过滤全部 Comment.create，与脚本设计一致：
# 只在 Issue.create（新 Issue）和 resume（手动恢复）时触发 droid。
if [ "$TYPE" = "Comment" ] && [ "$ACTION" = "create" ]; then
    log "SKIP: GAP-D filtered Comment.create for ${ISSUE_REF:-<unknown>} (no droid exec on comment events)"
    exit 0
fi

# === ACTION=update 防风暴过滤 + Gate A 状态门禁 ===
# ACTION=update 在任何 Issue 修改时触发（改项目、改负责人、改标签、改优先级等），
# 这些元数据变更不应触发 Droid 执行。只允许 create（新 Issue）和 resume（手动恢复）。
# Gate A (INFRA-67): 如果是 Done/Cancelled 转换，检查是否有有效 Droid session 记录，
#   无记录则自动回退到 In Progress + 评论告知。
# 2026-08-03: 批量修改 issue 时触发了 webhook 风暴，10+ 个不必要的 Droid mission 同时启动
# 2026-08-06: Gate A — 杜绝无 Droid 执行记录的 Done 转换
if [ "$ACTION" = "update" ] && [ "$TYPE" = "Issue" ]; then
    gate_check_done_transition
fi

# FR-10: Validate ISSUE_REF format (path traversal prevention)
if ! echo "$ISSUE_REF" | grep -qE '^[A-Z]+-[0-9]+$'; then
    log "ERROR: Invalid ISSUE_REF format: '$ISSUE_REF' — must match ^[A-Z]+-[0-9]+$"
    exit 0
fi

# === 重複実行防止 (M1: atomic flock + M2: PID liveness check) ===
LOCK_DIR="${WEBHOOK_BASE}/locks"
LOCK_FILE="${LOCK_DIR}/l2d-${ISSUE_REF}.lock"
mkdir -p "$LOCK_DIR" 2>/dev/null

# M2: Advisory PID liveness check (observability only, NOT for reclaim-by-delete)
if [ -f "$LOCK_FILE" ]; then
    LOCK_CONTENT=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    LOCK_PID=$(echo "$LOCK_CONTENT" | cut -d: -f2)
    LOCK_TIMESTAMP=$(echo "$LOCK_CONTENT" | cut -d: -f1)

    # Validate timestamp: empty or non-numeric means corrupt lock file
    if [ -z "$LOCK_TIMESTAMP" ] || ! [[ "$LOCK_TIMESTAMP" =~ ^[0-9]+$ ]]; then
        log "WARN: Corrupt lock file for ${ISSUE_REF} (empty/invalid timestamp), will truncate and proceed"
        # Do NOT delete lock file - flock operates on inode, not filename
        # Truncate to allow fresh metadata write after flock acquisition
        : > "$LOCK_FILE"
    else
        # age>TTL check: cap at 1440min (24hr) max to prevent overflow display
        LOCK_AGE_SEC=$(( $(date +%s) - LOCK_TIMESTAMP ))
        if [ "$LOCK_AGE_SEC" -lt 0 ]; then LOCK_AGE_SEC=0; fi
        LOCK_AGE_MIN=$(( LOCK_AGE_SEC / 60 ))
        if [ "$LOCK_AGE_MIN" -gt 1440 ]; then LOCK_AGE_MIN=1440; fi

        if [ "$LOCK_AGE_MIN" -ge 60 ]; then
            log "WARN: Lock held for ${LOCK_AGE_MIN}min (possible hung process, age > 60min TTL)"
            send_posthog_event "lock_stale" "$ISSUE_REF" "dedup" "age=${LOCK_AGE_MIN}min"
            # If PID is dead, reclaim the lock instead of permanently blocking
            if [ -n "$LOCK_PID" ] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
                log "INFO: Stale lock PID $LOCK_PID is dead, will fall through to flock -n for ${ISSUE_REF}"
                # Do NOT rm lock file — flock operates on inode; deleting causes race
            else
                exit 0
            fi
        fi

        # PID liveness check (advisory only) — only reached if age < 60min
        if [ -f "$LOCK_FILE" ] && [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
            log "SKIP: Active lock for ${ISSUE_REF} (PID $LOCK_PID alive, age: ${LOCK_AGE_MIN}min). Already processing."
            send_posthog_event "lock_held" "$ISSUE_REF" "dedup" "PID alive"
            exit 0
        elif [ -f "$LOCK_FILE" ]; then
            # PID is dead — do NOT rm, just fall through to flock -n
            # flock -n will succeed if kernel released the lock, fail if subshell still running
            log "INFO: Previous holder PID ${LOCK_PID:-unknown} is dead (flock will reclaim if lock released)"
        fi
    fi
fi

# M1: Atomic lock acquisition with flock (append mode to avoid truncating holder metadata)
exec 200>>"$LOCK_FILE"
/opt/homebrew/bin/flock -n 200 || {
    log "SKIP: Lock held by another process (flock rejected)"
    send_posthog_event "lock_held" "$ISSUE_REF" "dedup" "flock rejected"
    exit 0
}
# Write holder metadata immediately after flock acquisition so M2 has fresh data
# on next invocation. Truncate (>) not append (>>) so stale metadata is replaced.
echo "$(date +%s):$$" > "$LOCK_FILE"

# === Per-team serialization (fd 201) ===
source "${SCRIPT_DIR}/lib/linear-queue.sh"

# Initialize Linear queue context (TEAM_ID, AGENT_UUID, IN_PROGRESS_STATE_ID)
if ! linear_queue_init "$TEAM_KEY" "$ISSUE_UUID" "$LINEAR_API_KEY"; then
    log "WARN: linear_queue_init failed — serialization uses flock only, no Linear visibility"
fi

TEAM_LOCK_FILE="${LOCK_DIR}/l2d-team-${TEAM_KEY}.lock"
exec 201>>"$TEAM_LOCK_FILE"
/opt/homebrew/bin/flock -n 201 || {
    log "SKIP: Team $TEAM_KEY is busy (another droid running). Issue $ISSUE_REF queued in Linear."
    send_posthog_event "team_lock_held" "$ISSUE_REF" "serialization" "team=$TEAM_KEY"
    exit 0
}
log "Acquired team lock for $TEAM_KEY"

# Move current issue to In Progress (visibility layer, non-blocking)
linear_move_to_in_progress "$ISSUE_UUID" || log "WARN: Failed to move $ISSUE_REF to In Progress"

# 仓库路由
REPO_PATH=$(route_repo "$TEAM_KEY" "$ISSUE_UUID")

if [ -z "$REPO_PATH" ] || [ ! -d "$REPO_PATH" ]; then
    log "ERROR: Cannot route team=$TEAM_KEY to valid repo (got: $REPO_PATH)"
    send_posthog_event "route_repo_failed" "$ISSUE_REF" "routing" "team=$TEAM_KEY repo=$REPO_PATH"
    write_linear_comment "$ISSUE_UUID" "Factory Droid 未能接单：无法将团队 \`$TEAM_KEY\` 路由到目标仓库。请确认 repositories.yml 配置。"
    # Lock file kept; flock released automatically on process exit
    exit 0
fi

log "Routed: team=$TEAM_KEY -> repo=$REPO_PATH"

# === 异步执行 ===
(
    # C7: EXIT trap inside subshell — fires on crash before writeback
    # Trap handler performs Linear writeback + PostHog + lock cleanup
    _subshell_cleanup() {
        local _exit_code=$?
        # If we crashed (non-zero exit) and haven't done writeback yet, do emergency writeback
        if [ "$_exit_code" -ne 0 ] && [ "${_WRITEBACK_DONE:-0}" != "1" ]; then
            log "CRASH: Subshell exiting with code $_exit_code before writeback completed"
            send_posthog_event "subshell_crash" "${_CURRENT_PROCESSING_REF:-$ISSUE_REF}" "subshell" "exit_code=$_exit_code"
            write_linear_comment "${_CURRENT_PROCESSING_UUID:-$ISSUE_UUID}" "Factory Droid 子进程异常退出 (exit=$_exit_code)。

**任务**: ${_CURRENT_PROCESSING_REF:-$ISSUE_REF}
**仓库**: $(basename "${_CURRENT_REPO_PATH:-$REPO_PATH}")
**日志**: \`${LOG_FILE}\`

请检查日志确认状态。" || {
                log "WARN: Crash writeback also failed"
                send_posthog_event "crash_writeback_failed" "${_CURRENT_PROCESSING_REF:-$ISSUE_REF}" "subshell" "writeback failed on crash"
            }
        fi
        # Stop any running heartbeat
        _stop_heartbeat
        # Fallback: if status file still says running, write failed
        if [ -n "${_CURRENT_PROCESSING_REF:-}" ] && [ -f "${STATUS_DIR}/${_CURRENT_PROCESSING_REF}.json" ]; then
            local _current_status
            _current_status=$(/opt/homebrew/bin/python3 -c "
import json
try:
    with open('${STATUS_DIR}/${_CURRENT_PROCESSING_REF}.json') as f:
        print(json.load(f).get('status', ''))
except:
    pass
" 2>/dev/null)
            if [ "$_current_status" = "running" ]; then
                local _fail_json
                _fail_json="$(/opt/homebrew/bin/python3 -c "
import json, datetime
print(json.dumps({
    'version': 1,
    'issueRef': '$_CURRENT_PROCESSING_REF',
    'status': 'failed',
    'sessionId': None,
    'completedAt': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'heartbeat': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'exitCode': $_exit_code,
    'prUrl': None
}))
")"
                _write_status "$_CURRENT_PROCESSING_REF" "$_fail_json"
                log "EXIT trap: wrote failed status for $_CURRENT_PROCESSING_REF (exit=$_exit_code)"
            fi
        fi
        # M-LIN-6: Lock file kept for flock consistency; flock released automatically on process exit
        # Do NOT delete lock file - would cause inode race condition with other processes
    }
    trap _subshell_cleanup EXIT

    # 子进程继承 LINEAR_API_KEY 和 ISSUE_UUID
    export LINEAR_API_KEY
    export ISSUE_UUID
    export ISSUE_REF

    # 覆盖 log 函数，只追加到日志文件
    log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

    # === Chain-trigger context variables for crash recovery ===
    _CURRENT_PROCESSING_REF="$ISSUE_REF"
    _CURRENT_PROCESSING_UUID="$ISSUE_UUID"
    _CURRENT_REPO_PATH="$REPO_PATH"
    _WRITEBACK_DONE=0

    # ========================================================================
    # process_one_issue(UUID, REF, TITLE, TEAM_KEY)
    #
    # Encapsulates single-issue processing: route → droid exec → writeback.
    # Used by both the triggering issue and chain-trigger loop.
    # Uses return (not exit) so the subshell continues after each issue.
    # ========================================================================
    process_one_issue() {
        local p_uuid="$1"
        local p_ref="$2"
        local p_title="$3"
        local p_team="$4"

        # Set current processing context for crash recovery
        _CURRENT_PROCESSING_REF="$p_ref"
        _CURRENT_PROCESSING_UUID="$p_uuid"
        _WRITEBACK_DONE=0

        log "--- process_one_issue started: $p_ref (team=$p_team) ---"

        # Write initial status file
        local p_subshell_pid
        p_subshell_pid=$(sh -c 'echo $PPID')
        local p_status_file="${STATUS_DIR}/${p_ref}.json"
        local p_init_json
        p_init_json="$(/opt/homebrew/bin/python3 -c "
import json, datetime
print(json.dumps({
    'version': 1,
    'issueRef': '$p_ref',
    'status': 'running',
    'pid': $p_subshell_pid,
    'sessionId': None,
    'startedAt': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'completedAt': None,
    'heartbeat': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'exitCode': None,
    'prUrl': None
}))
")"
        _write_status "$p_ref" "$p_init_json"
        log "Status file written: running (pid=$p_subshell_pid) for $p_ref"

        # Start per-issue heartbeat
        _start_heartbeat "$p_ref" "$p_subshell_pid" "$p_subshell_pid"
        log "Heartbeat started for $p_ref"

        # Route to repo using this issue's own team key
        local p_repo_path
        p_repo_path=$(route_repo "$p_team" "$p_uuid")
        if [ -z "$p_repo_path" ] || [ ! -d "$p_repo_path" ]; then
            log "ERROR: Cannot route team=$p_team to valid repo (got: $p_repo_path)"
            send_posthog_event "route_repo_failed" "$p_ref" "routing" "team=$p_team repo=$p_repo_path"
            write_linear_comment "$p_uuid" "Factory Droid 未能接单：无法将团队 \`$p_team\` 路由到目标仓库。请确认 repositories.yml 配置。"
            _WRITEBACK_DONE=1
            return 1
        fi
        log "Routed: team=$p_team -> repo=$p_repo_path"
        _CURRENT_REPO_PATH="$p_repo_path"

        # Build prompt with this issue's context
        local p_prompt="Linear 门铃触发。IssueRef=${p_ref}。Team=${p_team}。请按 linear-gateway skill 执行。

## Issue 上下文
- **Issue**: ${p_ref}
- **Title**: ${p_title}
- **Team**: ${p_team}
- **Action**: ${ACTION}
- **Trigger**: ${TYPE}

## 执行要求
1. 使用 Linear GraphQL API 拉取 Issue 完整详情（标题、描述、标签、评论）
2. 根据 repositories.yml 路由到目标仓库
3. 创建 feature 分支（分支名包含 ${p_ref}）
4. 执行代码变更
5. 运行验证（测试/构建/lint）
6. 提交并推送到 GitHub
7. 创建 PR（标题包含 ${p_ref}，body 包含 Fixes ${p_ref}）
8. 回写 Linear comment（中文）

## 重要约束
- 所有 commit 消息使用中文
- PR title 必须包含 ${p_ref}
- PR body 必须包含 Fixes ${p_ref}
- 不要手动设置 Linear issue 状态为 Done
"

        log "Launching droid exec for $p_ref..."

        # C5: cd failure triggers Linear writeback + PostHog
        cd "$p_repo_path" || {
            log "ERROR: cd $p_repo_path failed"
            send_posthog_event "cd_failed" "$p_ref" "droid_exec" "cd to $p_repo_path failed"
            write_linear_comment "$p_uuid" "Factory Droid cd 失败：无法进入仓库目录 \`$p_repo_path\`。

**任务**: ${p_ref}
**团队**: ${p_team}

请检查仓库路径配置。" || {
                log "WARN: cd-failure writeback also failed, creating GitHub Issue fallback"
                create_github_fallback_issue "$p_ref" "cd_failure" "cd $p_repo_path failed" "$p_repo_path" || \
                    send_posthog_event "cd_failure_fallback_failed" "$p_ref" "escalation" "all fallbacks failed"
            }
            _WRITEBACK_DONE=1
            return 1
        }

        # === Reliability hardening: integrity re-sign + stale mission cleanup ===
        # Memory integrity drift (hooks modify mutable log/audit files between sessions)
        # causes droid exec --mission to crash during orchestrator init because the
        # SessionStart hook reports SHA-256 mismatches. The resign CLI re-hashes ALL
        # signed files (including integrity-audit.jsonl) and writes a correct manifest.
        # Unlike memory-init --mode repair which only updates manifest metadata without
        # re-hashing existing files, this does a full re-sign via sign_project().
        if [ -d "$p_repo_path/memory/system" ] && [ -f "$p_repo_path/memory/system/manifest.json" ]; then
            if python3 -m memory_core.tools.memory_integrity_resign \
                --project-root "$p_repo_path" \
                --reason "pre-exec re-sign for ${p_ref}" \
                --force >/dev/null 2>&1; then
                log "Integrity manifest re-signed for $p_ref"
            else
                log "WARN: Integrity re-sign failed for $p_ref (continuing anyway)"
            fi
        fi
        # Clean stale "planning" state missions for this working directory.
        # Crashed --mission exec attempts leave orphaned mission dirs that never
        # progressed past planning; these accumulate and can interfere with new sessions.
        for _mission_sf in /Users/busiji/.factory/missions/*/state.json; do
            [ -f "$_mission_sf" ] || continue
            if python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
exit(0 if d.get('state')=='planning' and d.get('workingDirectory')==sys.argv[2] else 1)
" "$_mission_sf" "$p_repo_path" 2>/dev/null; then
                rm -rf "$(dirname "$_mission_sf")"
                log "Cleaned stale planning mission: $(basename "$(dirname "$_mission_sf")")"
            fi
        done

        # Run droid exec
        local p_droid_exit=0
        local p_droid_output

        if [ "$ACTION" = "resume" ] && [ -n "${RESUME_SESSION_ID:-}" ]; then
            # Resume mode: continue a previously interrupted Droid session
            log "RESUME MODE: Resuming session ${RESUME_SESSION_ID} for ${p_ref}"
            if [ "${ECHO_DROID:-0}" = "1" ]; then
                echo "[ECHO_DROID] Would run: droid exec -s ${RESUME_SESSION_ID} --auto high ... for $p_ref (team=$p_team)" >> "$LOG_FILE"
                p_droid_output='{"type":"result","session_id":"'"${RESUME_SESSION_ID}"'","result":"dry-run ok (resume)"}'
            else
                # C6: droid exec wrapped with 3600s timeout
                p_droid_output=$(with_timeout 3600 /Users/busiji/.local/bin/droid exec \
                    -s "$RESUME_SESSION_ID" \
                    --auto high \
                    --output-format json \
                    --tag "{\"name\":\"linear-gateway\",\"metadata\":{\"issueRef\":\"${p_ref}\",\"teamKey\":\"${p_team}\",\"triggerSource\":\"issue\",\"eventType\":\"Issue.${ACTION}\"}}" \
                    "继续处理 Linear Issue ${p_ref}。这是之前中断的任务，请检查之前的进度并继续。" 2>&1) || p_droid_exit=$?
            fi
        else
            # Start/default branch
            if [ "${ECHO_DROID:-0}" = "1" ]; then
                echo "[ECHO_DROID] Would run: droid exec --mission --auto high ... for $p_ref (team=$p_team)" >> "$LOG_FILE"
                p_droid_output='{"type":"result","session_id":"dry-run-session","result":"dry-run ok (start)"}'
            else
                # C6: droid exec wrapped with 3600s timeout
                p_droid_output=$(with_timeout 3600 /Users/busiji/.local/bin/droid exec \
                    --mission \
                    --auto high \
                    --output-format json \
                    --tag "{\"name\":\"linear-gateway\",\"metadata\":{\"issueRef\":\"${p_ref}\",\"teamKey\":\"${p_team}\",\"triggerSource\":\"issue\",\"eventType\":\"Issue.${ACTION}\"}}" \
                    "$p_prompt" 2>&1) || p_droid_exit=$?
            fi
        fi

        # Extract session_id from JSON output
        local p_session_id
        p_session_id=$(echo "$p_droid_output" | /opt/homebrew/bin/python3 -c "
import json, sys
try:
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        if d.get('type') == 'result' and 'session_id' in d:
            print(d['session_id'])
            break
except: pass
" 2>/dev/null)

        log "droid exec finished for $p_ref: exit=$p_droid_exit, session=${p_session_id:-unknown}"

        # === Retry on crash: mission init failures (exit=1, no session_id) ===
        # droid exec --mission can crash during orchestrator init if memory
        # integrity drifts between repair and session start, or due to transient
        # issues. Retry once with a fresh memory repair.
        if [ "$p_droid_exit" -ne 0 ] && [ -z "${p_session_id:-}" ] && [ "$ACTION" != "resume" ] && [ "${ECHO_DROID:-0}" != "1" ]; then
            log "First exec crashed (exit=$p_droid_exit, no session) — retrying with integrity re-sign..."
            if [ -d "$p_repo_path/memory/system" ]; then
                python3 -m memory_core.tools.memory_integrity_resign \
                    --project-root "$p_repo_path" \
                    --reason "retry re-sign for ${p_ref}" \
                    --force >/dev/null 2>&1 || true
            fi
            p_droid_exit=0
            p_droid_output=$(with_timeout 3600 /Users/busiji/.local/bin/droid exec \
                --mission \
                --auto high \
                --output-format json \
                --tag "{\"name\":\"linear-gateway\",\"metadata\":{\"issueRef\":\"${p_ref}\",\"teamKey\":\"${p_team}\",\"triggerSource\":\"issue\",\"eventType\":\"Issue.${ACTION}\"}}" \
                "$p_prompt" 2>&1) || p_droid_exit=$?
            # Re-extract session_id from retry output
            p_session_id=$(echo "$p_droid_output" | /opt/homebrew/bin/python3 -c "
import json, sys
try:
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        if d.get('type') == 'result' and 'session_id' in d:
            print(d['session_id'])
            break
except: pass
" 2>/dev/null)
            log "Retry exec finished for $p_ref: exit=$p_droid_exit, session=${p_session_id:-unknown}"
        fi

        # === 补偿层: GitHub Issue 自动关闭 (Linear 终态检测) ===
        # 查询 Linear Issue 状态，如果是终态 (completed/canceled)，关闭对应的 GitHub Issue
        if [ -n "${ECHO_DROID:-}" ] && [ "$ECHO_DROID" = "1" ]; then
            log "[ECHO_DROID] Would check Linear state for $p_ref and close GitHub Issue if terminal"
        else
            local p_linear_state_type
            p_linear_state_type=$(/opt/homebrew/bin/python3 -c "
import json, urllib.request, sys
query = '{ issue(id: \"$p_uuid\") { state { type } } }'
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': '$LINEAR_API_KEY', 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read().decode())
        state_type = d.get('data', {}).get('issue', {}).get('state', {}).get('type', '')
        print(state_type)
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null)

            if [ "$p_linear_state_type" = "completed" ] || [ "$p_linear_state_type" = "canceled" ]; then
                log "Linear state is terminal ($p_linear_state_type), checking for open GitHub Issue..."
                local p_github_repo=""
                p_github_repo=$(git -C "$p_repo_path" remote get-url origin 2>/dev/null | sed 's/.*github.com[:\/]//' | sed 's/.git$//')

                if [ -n "$p_github_repo" ]; then
                    local p_gh_issue_number
                    p_gh_issue_number=$(gh issue list --repo "$p_github_repo" --search "$p_ref" --state open --json number --limit 1 2>/dev/null | /opt/homebrew/bin/python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if data and len(data) > 0:
        print(data[0].get('number', ''))
except: pass
" 2>/dev/null)

                    if [ -n "$p_gh_issue_number" ]; then
                        local p_close_comment="对应的 Linear Issue ${p_ref} 已处于终态 (${p_linear_state_type})，自动关闭 GitHub Issue。"
                        log "Closing GitHub Issue #$p_gh_issue_number for $p_ref (state: $p_linear_state_type)"
                        gh issue close "$p_gh_issue_number" --repo "$p_github_repo" --comment "$p_close_comment" >> "$LOG_FILE" 2>&1 || {
                            log "WARN: Failed to close GitHub Issue #$p_gh_issue_number for $p_ref"
                        }
                    else
                        log "No open GitHub Issue found for $p_ref (or already closed)"
                    fi
                else
                    log "WARN: Could not determine GitHub repo from $p_repo_path"
                fi
            else
                log "Linear state is non-terminal ($p_linear_state_type), GitHub Issue left open"
            fi
        fi

        # SD-2: Stop heartbeat BEFORE writing terminal status (eliminates race)
        _stop_heartbeat
        log "Heartbeat stopped for $p_ref"

        # Capture exit code explicitly (m-3: don't rely on trap $?)
        local p_terminal_status
        if [ "$p_droid_exit" -eq 0 ]; then
            p_terminal_status="completed"
        else
            p_terminal_status="failed"
        fi

        # Read startedAt from current status file (preserve original start time)
        local p_started_at
        p_started_at=$(/opt/homebrew/bin/python3 -c "
import json
try:
    with open('$p_status_file') as f:
        print(json.load(f).get('startedAt',''))
except:
    pass
" 2>/dev/null)

        # Write terminal status file
        local SESSION_ID_FOR_JSON="${p_session_id:-}"
        local p_terminal_json
        p_terminal_json="$(/opt/homebrew/bin/python3 -c "
import json, datetime
sid = '$SESSION_ID_FOR_JSON' or None
print(json.dumps({
    'version': 1,
    'issueRef': '$p_ref',
    'status': '$p_terminal_status',
    'pid': $p_subshell_pid,
    'sessionId': sid,
    'startedAt': '$p_started_at',
    'completedAt': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'heartbeat': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'exitCode': $p_droid_exit,
    'prUrl': None
}))
")"
        _write_status "$p_ref" "$p_terminal_json"
        log "Status file written: $p_terminal_status (exit=$p_droid_exit) for $p_ref"

        # Extract result summary
        local p_result_text
        p_result_text=$(echo "$p_droid_output" | /opt/homebrew/bin/python3 -c "
import json, sys
try:
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        d = json.loads(line)
        if d.get('type') == 'result':
            print(d.get('result', '')[:800])
            break
except: pass
" 2>/dev/null)

        log "Result: ${p_result_text:0:500}"

        # H4: write_linear_comment failure → GitHub Issue fallback
        local p_result_msg
        if [ "$p_droid_exit" -ne 0 ]; then
            p_result_msg="Factory Droid 执行失败。

**任务**: ${p_ref}
**仓库**: $(basename "$p_repo_path")
**Mission**: ${p_session_id:-未知}

**错误摘要**:
\`\`\`
${p_result_text:-${p_droid_output:0:500}}
\`\`\`

请检查日志: \`${LOG_FILE}\`"
            send_posthog_event "droid_exec_failed" "$p_ref" "droid_exec" "exit_code=$p_droid_exit"
            write_linear_comment "$p_uuid" "$p_result_msg" || {
                log "WARN: Linear writeback failed, creating GitHub Issue fallback"
                send_posthog_event "linear_writeback_failed" "$p_ref" "linear_api" "droid_exit=$p_droid_exit"
                create_github_fallback_issue "$p_ref" "failure" "droid exit=$p_droid_exit" "$p_repo_path" || \
                    send_posthog_event "all_fallbacks_failed" "$p_ref" "escalation" "droid_exit=$p_droid_exit linear+issue+posthog all failed"
            }
        else
            p_result_msg="Factory Droid 执行完成。

**任务**: ${p_ref}
**仓库**: $(basename "$p_repo_path")
**Mission**: ${p_session_id:-未知}

**执行结果**:
\`\`\`
${p_result_text:-执行成功}
\`\`\`

**下一步**
- 查看 PR（如有）
- 等待 CI + Review
- 后续变更请在 Issue 下添加评论"
            write_linear_comment "$p_uuid" "$p_result_msg" || {
                log "WARN: Linear writeback failed, creating GitHub Issue fallback"
                send_posthog_event "linear_writeback_failed" "$p_ref" "linear_api" "success_writeback_failed"
                create_github_fallback_issue "$p_ref" "success" "droid completed" "$p_repo_path" || \
                    send_posthog_event "all_fallbacks_failed" "$p_ref" "escalation" "success writeback all failed"
            }
        fi
        _WRITEBACK_DONE=1
        log "--- process_one_issue completed: $p_ref ---"
        return 0
    }

    log "--- async droid exec started ---"
    log "ISSUE_UUID in subshell: ${ISSUE_UUID:-<empty>}"
    log "LINEAR_API_KEY in subshell: ${LINEAR_API_KEY:+OK (${#LINEAR_API_KEY} chars)}"

    # Process the triggering issue
    process_one_issue "$ISSUE_UUID" "$ISSUE_REF" "$ISSUE_TITLE" "$TEAM_KEY"

    # === Chain-trigger loop ===
    # After the triggering issue completes, query Linear for next queued same-team issue
    # delegated to Factory Agent. Process it, then repeat until queue is empty.
    log "CHAIN-TRIGGER: Checking for queued issues..."
    _last_picked_uuid=""
    while true; do
        next_line=$(linear_query_next_queued)
        if [ -z "$next_line" ]; then
            log "CHAIN-TRIGGER: Queue empty...exiting"
            break
        fi

        # Parse UUID|REF|TITLE|TEAM_KEY
        IFS='|' read -r n_uuid n_ref n_title n_team <<< "$next_line"

        if [ -z "${n_uuid:-}" ] || [ -z "${n_ref:-}" ]; then
            log "CHAIN-TRIGGER: WARN: Invalid query result '${next_line:-<empty>}', breaking"
            break
        fi

        # Repick guard: if same UUID as last iteration, move-to-in-progress likely failed
        if [ "$n_uuid" = "$_last_picked_uuid" ]; then
            log "CHAIN-TRIGGER: WARN: head-of-queue $n_ref unchanged (move-to-In-Progress likely failed). Breaking."
            break
        fi

        log "CHAIN-TRIGGER: Picking up $n_ref for team ${n_team:-$TEAM_KEY}"
        _last_picked_uuid="$n_uuid"
        linear_move_to_in_progress "$n_uuid" || log "WARN: Failed to move $n_ref to In Progress"

        process_one_issue "$n_uuid" "$n_ref" "${n_title:-}" "${n_team:-$TEAM_KEY}"

        log "CHAIN-TRIGGER: Finished attempt for $n_ref, checking for more..."
    done
    log "CHAIN-TRIGGER: All queued issues processed, exiting"

) >> "$LOG_FILE" 2>&1 &
SUBSHELL_PID=$!
# Store actual subshell PID in lock file (not main $$ which is always dead)
echo "$(date +%s):$SUBSHELL_PID" >&200

log "Background droid process started: PID=$SUBSHELL_PID"

# 立即返回
exit 0
