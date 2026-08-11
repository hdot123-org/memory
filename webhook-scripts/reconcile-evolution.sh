#!/usr/bin/env bash
# reconcile-evolution.sh — 拉取式对账，发现孤立的 evolution finding 并补触发
# 设计：push(webhook) + pull(本脚本) = 最终一致
#
# 核心逻辑：直接查询 Linear API（而非 GitHub Issue body），因为 Linear native
# sync 不会在 GitHub Issue body 中写入 Linear ref linkback。
#
# 调度：launchd 每小时的 :15 和 :45 运行（与 scanner cron :00/:30 错开 15 分钟）
# 串行：每次只补触发一个 Issue（per-team 锁保证串行，下一个 tick 再补）
set -euo pipefail

# === 配置 ===
SCRIPT_DIR="${HOME}/.factory/webhook/scripts"
WEBHOOK_BASE="${HOME}/.factory/webhook"
LOG_DIR="${WEBHOOK_BASE}/logs"
LOCK_DIR="${WEBHOOK_BASE}/locks"
STATUS_DIR="${WEBHOOK_BASE}/status"
REPO="hdot123/memory"
TEAM_KEY="INFRA"

mkdir -p "$LOG_DIR" 2>/dev/null

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/reconcile-${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# === 1. 解析 LINEAR_API_KEY（复用 trigger-droid.sh 的 op-mcp 机制）===
source "${SCRIPT_DIR}/lib/op-mcp.sh"

LINEAR_API_KEY="${LINEAR_API_KEY:-}"
if [ -z "$LINEAR_API_KEY" ]; then
    LINEAR_API_KEY=$(op_get_field "$OP_VAULT_SEVER" "elgcm2nzfza2hjb3yffpkijj7y" "凭据" || true)
fi

if [ -z "$LINEAR_API_KEY" ]; then
    log "ERROR: LINEAR_API_KEY is empty — cannot query Linear, aborting"
    exit 1
fi
export LINEAR_API_KEY

# === 2. 解析 TEAM_ID from repositories.yml ===
TEAM_ID=$(TEAM_KEY="$TEAM_KEY" /opt/homebrew/bin/python3 -c "
import yaml, os, sys
team_key = os.environ['TEAM_KEY']
with open(os.path.expanduser('~/.factory/config/repositories.yml')) as f:
    cfg = yaml.safe_load(f)
for td in cfg.get('teams', {}).values():
    if td.get('teamKey', '').upper() == team_key.upper():
        print(td.get('linearTeamId', ''))
        sys.exit(0)
print('')
" 2>/dev/null || echo "")

if [ -z "$TEAM_ID" ]; then
    log "ERROR: TEAM_ID not found for ${TEAM_KEY}, aborting"
    exit 1
fi

# === 3. 检查 per-team 锁是否空闲 ===
TEAM_LOCK="${LOCK_DIR}/l2d-team-${TEAM_KEY}.lock"
if [ -f "$TEAM_LOCK" ]; then
    LOCK_CONTENT=$(cat "$TEAM_LOCK" 2>/dev/null || echo "")
    if [ -n "$LOCK_CONTENT" ]; then
        LOCK_PID=$(echo "$LOCK_CONTENT" | cut -d: -f2)
        if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
            log "Team ${TEAM_KEY} droid still running (PID ${LOCK_PID}), skip reconciliation"
            exit 0
        else
            log "Team lock exists but PID ${LOCK_PID} is dead, proceeding"
        fi
    fi
fi

# === 4. 查询 Linear 中所有 evolution-found 且非终态的 Issue ===
# 查询 triage/backlog/unstarted 以及 started (In Progress) 状态。
# started 状态由 5t 超时保护处理，避免与刚启动的 droid 竞争。
LINEAR_ISSUES=$(TEAM_ID="$TEAM_ID" LINEAR_API_KEY="$LINEAR_API_KEY" /opt/homebrew/bin/python3 -c "
import json, urllib.request, os, sys, socket
socket.setdefaulttimeout(15)
team_id = os.environ['TEAM_ID']
api_key = os.environ['LINEAR_API_KEY']
query = '''{
    issues(
        filter: {
            team: { id: { eq: \"''' + team_id + '''\" } },
            labels: { name: { containsIgnoreCase: \"evolution-found\" } },
            state: { type: { in: [\"triage\", \"backlog\", \"unstarted\", \"started\"] } }
        },
        orderBy: createdAt,
        first: 50
    ) {
        nodes {
            id
            identifier
            title
            state { name type }
            updatedAt
        }
    }
}'''
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': api_key, 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
        nodes = d.get('data', {}).get('issues', {}).get('nodes', [])
        for n in nodes:
            ref = n.get('identifier', '')
            title = n.get('title', '').replace('|', '-')
            uuid = n.get('id', '')
            state = n.get('state', {}).get('name', '')
            updated_at = n.get('updatedAt', '')
            print(f'{uuid}|{ref}|{title}|{state}|{updated_at}')
except Exception as e:
    print('ERROR: ' + str(e), file=sys.stderr)
    sys.exit(1)
" 2>>"$LOG_FILE") || {
    log "ERROR: Linear API query failed, aborting"
    exit 1
}

ISSUE_COUNT=$(echo "$LINEAR_ISSUES" | grep -c '|' 2>/dev/null || true)
ISSUE_COUNT=${ISSUE_COUNT:-0}
ISSUE_COUNT=$(echo "$ISSUE_COUNT" | tr -d '[:space:]')
log "Found ${ISSUE_COUNT} non-terminal evolution-found issues in Linear"

# === 4b. 查询 Linear 中终态（Done/Cancelled）的 evolution-found Issue，关闭对应 GitHub Issue ===
TERMINAL_ISSUES=$(TEAM_ID="$TEAM_ID" LINEAR_API_KEY="$LINEAR_API_KEY" /opt/homebrew/bin/python3 -c "
import json, urllib.request, os, sys, socket
socket.setdefaulttimeout(15)
team_id = os.environ['TEAM_ID']
api_key = os.environ['LINEAR_API_KEY']
query = '''{
    issues(
        filter: {
            team: { id: { eq: \"''' + team_id + '''\" } },
            labels: { name: { containsIgnoreCase: \"evolution-found\" } },
            state: { type: { in: [\"completed\", \"canceled\"] } }
        },
        orderBy: createdAt,
        first: 50
    ) {
        nodes {
            identifier
            title
            state { name type }
        }
    }
}'''
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': api_key, 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
        nodes = d.get('data', {}).get('issues', {}).get('nodes', [])
        for n in nodes:
            ref = n.get('identifier', '')
            title = n.get('title', '').replace('|', '-')
            state = n.get('state', {}).get('name', '')
            print(f'{ref}|{title}|{state}')
except Exception as e:
    print('ERROR: ' + str(e), file=sys.stderr)
    sys.exit(1)
" 2>>"$LOG_FILE") || true

TERMINAL_COUNT=$(echo "$TERMINAL_ISSUES" | grep -c '|' 2>/dev/null || true)
TERMINAL_COUNT=${TERMINAL_COUNT:-0}
TERMINAL_COUNT=$(echo "$TERMINAL_COUNT" | tr -d '[:space:]')
log "Found ${TERMINAL_COUNT} terminal-state evolution-found issues in Linear"

if [ "$TERMINAL_COUNT" -gt 0 ]; then
    while IFS='|' read -r T_REF T_TITLE T_STATE; do
        [ -z "$T_REF" ] && continue
        log "Checking terminal ${T_REF}: ${T_TITLE} (state: ${T_STATE})"

        # 查找对应的 open GitHub Issue
        GH_ISSUE_JSON=$(gh issue list --repo "$REPO" --search "${T_REF}" --state open --json number --limit 1 2>/dev/null || echo "[]")
        GH_NUMBER=$(echo "$GH_ISSUE_JSON" | /opt/homebrew/bin/python3 -c "import json,sys; data=json.load(sys.stdin); print(data[0]['number'] if data else '')" 2>/dev/null || echo "")

        if [ -n "$GH_NUMBER" ]; then
            log "  ${T_REF}: closing GitHub Issue #${GH_NUMBER} (Linear state: ${T_STATE})"
            gh issue close "$GH_NUMBER" --repo "$REPO" \
                --comment "对应的 Linear Issue ${T_REF} 已处于终态（${T_STATE}），本 GitHub Issue 由 compensation-layer 清理关闭。" \
                2>>"$LOG_FILE" || log "  WARNING: failed to close GitHub Issue #${GH_NUMBER}"
        else
            log "  ${T_REF}: no open GitHub Issue found, skip"
        fi
    done <<< "$TERMINAL_ISSUES"
fi

if [ "$ISSUE_COUNT" -eq 0 ]; then
    log "Nothing to reconcile"
    exit 0
fi

# === 5. 对每个 Linear Issue 检查是否已有 PR 或正在处理 ===
TRIGGERED=0

while IFS='|' read -r ISSUE_UUID LINEAR_REF ISSUE_TITLE ISSUE_STATE ISSUE_UPDATED; do
    [ -z "$LINEAR_REF" ] && continue

    log "Checking ${LINEAR_REF}: ${ISSUE_TITLE} (state: ${ISSUE_STATE})"

    # 5t. 对 In Progress (started) 状态的 Issue 应用超时保护，避免与刚启动的 droid 竞争
    if echo "$ISSUE_STATE" | grep -q "进行"; then
        AGE_MIN=$(/opt/homebrew/bin/python3 -c "
from datetime import datetime, timezone
try:
    updated = datetime.fromisoformat('${ISSUE_UPDATED}'.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    age_min = int((now - updated).total_seconds() / 60)
    print(age_min)
except:
    print(9999)
" 2>/dev/null || echo "9999")

        STALE_THRESHOLD_MIN=45
        if [ "$AGE_MIN" -lt "$STALE_THRESHOLD_MIN" ]; then
            log "  ${LINEAR_REF}: In Progress but updated ${AGE_MIN}min ago (< ${STALE_THRESHOLD_MIN}min threshold), skip (timeout guard)"
            continue
        fi
        log "  ${LINEAR_REF}: In Progress and stale (${AGE_MIN}min > ${STALE_THRESHOLD_MIN}min threshold), checking for retrigger"
    fi

    # 5a. 检查是否有 open PR 引用该 Linear ref
    PR_FOUND=$(gh pr list --repo "$REPO" --search "${LINEAR_REF}" --state open --limit 5 --json number 2>/dev/null | /opt/homebrew/bin/python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")

    if [ "$PR_FOUND" -gt 0 ]; then
        log "  ${LINEAR_REF}: PR exists, skip"
        continue
    fi

    # 5a2. 检查 GitHub Issue 是否已关闭（若已关闭则跳过 droid 触发）
    GH_OPEN_JSON=$(gh issue list --repo "$REPO" --search "${LINEAR_REF}" --state open --json number --limit 1 2>/dev/null || echo "[]")
    GH_OPEN_COUNT=$(echo "$GH_OPEN_JSON" | /opt/homebrew/bin/python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")

    if [ "$GH_OPEN_COUNT" -eq 0 ]; then
        log "  ${LINEAR_REF}: GitHub Issue already closed (droid already processed), skip trigger"
        continue
    fi

    # 5b. 检查 per-issue 锁是否存在且 PID 存活
    ISSUE_LOCK="${LOCK_DIR}/l2d-${LINEAR_REF}.lock"
    if [ -f "$ISSUE_LOCK" ]; then
        ISSUE_LOCK_CONTENT=$(cat "$ISSUE_LOCK" 2>/dev/null || echo "")
        if [ -n "$ISSUE_LOCK_CONTENT" ]; then
            ISSUE_LOCK_PID=$(echo "$ISSUE_LOCK_CONTENT" | cut -d: -f2)
            if [ -n "$ISSUE_LOCK_PID" ] && kill -0 "$ISSUE_LOCK_PID" 2>/dev/null; then
                log "  ${LINEAR_REF}: per-issue lock held (PID ${ISSUE_LOCK_PID}), skip"
                continue
            else
                log "  ${LINEAR_REF}: per-issue lock stale (PID ${ISSUE_LOCK_PID} dead), marking for retrigger"
            fi
        fi
    fi

    # 5c. 检查状态文件是否正在运行
    STATUS_FILE="${STATUS_DIR}/${LINEAR_REF}.json"
    if [ -f "$STATUS_FILE" ]; then
        STATUS=$(/opt/homebrew/bin/python3 -c "
import json
try:
    d = json.load(open('$STATUS_FILE'))
    print(d.get('status', ''))
except:
    print('')
" 2>/dev/null || echo "")

        if [ "$STATUS" = "running" ]; then
            STATUS_PID=$(/opt/homebrew/bin/python3 -c "
import json
try:
    d = json.load(open('$STATUS_FILE'))
    print(d.get('pid', ''))
except:
    print('')
" 2>/dev/null || echo "")

            if [ -n "$STATUS_PID" ] && kill -0 "$STATUS_PID" 2>/dev/null; then
                log "  ${LINEAR_REF}: droid running (PID ${STATUS_PID}), skip"
                continue
            else
                log "  ${LINEAR_REF}: stale running status (PID dead), marking for retrigger"
            fi
        elif [ "$STATUS" = "completed" ]; then
            log "  ${LINEAR_REF}: already completed, skip"
            continue
        fi
    fi

    # 5d. 补触发
    log "  ${LINEAR_REF}: orphaned, triggering reconciliation"
    bash "${SCRIPT_DIR}/trigger-droid.sh" \
        "create" "Issue" "$LINEAR_REF" "$ISSUE_UUID" "$TEAM_KEY" "$ISSUE_TITLE" \
        >> "$LOG_FILE" 2>&1 || true

    TRIGGERED=1
    log "  Triggered ${LINEAR_REF}, stopping for this tick (serial execution)"
    break

done <<< "$LINEAR_ISSUES"

log "Reconciliation complete: triggered=${TRIGGERED}"
