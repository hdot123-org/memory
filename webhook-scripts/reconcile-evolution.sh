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

# 死锁出口 stale 阈值（architecture §3.2）：
# status=completed + sessionId 非空 + exitCode=0 而 Linear 停留非终态超过此阈值 → 推进终态
# 对齐 45 分钟量级（与现行 5t 超时保护一致）
DEADLOCK_STALE_THRESHOLD_MIN=45

# 死锁出口幂等 sentinel（HTML 隐藏评论，UI 不可见）
DEADLOCK_EXIT_SENTINEL_PREFIX="<!-- deadlock-exit "

mkdir -p "$LOG_DIR" 2>/dev/null

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/reconcile-${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# 锚点提取失败留痕（INFRA-357）：stderr 带时间戳写入 anchor-extract.log，
# 供事后 grep 退化痕迹；不影响调用方的 fail-closed 语义（空锚点照常 skip/block）
log_anchor_extract_err() {
    local target="$1" err_text="$2"
    [ -z "$err_text" ] && return 0
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] anchor-extract ${target}: ${line}" >> "${LOG_DIR}/anchor-extract.log"
    done <<< "$err_text"
}

# === 1. 解析 LINEAR_API_KEY（复用 trigger-droid.sh 的 op-mcp 机制）===
# shellcheck source=/dev/null
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

        # 查找对应的 open GitHub Issue（带 label 双闸）
        GH_ISSUE_JSON=$(gh issue list --repo "$REPO" --label evolution-found --state open --search "${T_REF}" --json number --limit 1 2>/dev/null || echo "[]")
        GH_NUMBER=$(echo "$GH_ISSUE_JSON" | /opt/homebrew/bin/python3 -c "import json,sys; data=json.load(sys.stdin); print(data[0]['number'] if data else '')" 2>/dev/null || echo "")

        if [ -n "$GH_NUMBER" ]; then
            # 锚点一致性校验（issue-flow.md §9.4）：提取评论中的 linear-linkback，必须 == T_REF
            # 失败留痕 anchor-extract.log（INFRA-357），fail-closed 语义不变
            ANCHOR_ERR="$(mktemp)"
            ANCHOR=$(/opt/homebrew/bin/python3 "${SCRIPT_DIR%/*}/scripts/extract_anchor.py" issue "$GH_NUMBER" "$REPO" 2>"$ANCHOR_ERR" || echo "")
            log_anchor_extract_err "issue#${GH_NUMBER}" "$(cat "$ANCHOR_ERR")"
            rm -f "$ANCHOR_ERR"
            if [ "$ANCHOR" = "$T_REF" ]; then
                log "  ${T_REF}: anchor consistent, closing GitHub Issue #${GH_NUMBER} (Linear state: ${T_STATE})"
                gh issue close "$GH_NUMBER" --repo "$REPO" \
                    --comment "对应的 Linear Issue ${T_REF} 已处于终态（${T_STATE}），本 GitHub Issue 由 compensation-layer 清理关闭。" \
                    2>>"$LOG_FILE" || log "  WARNING: failed to close GitHub Issue #${GH_NUMBER}"
            elif [ -z "$ANCHOR" ]; then
                log "  ${T_REF}: WARNING no anchor in GitHub Issue #${GH_NUMBER} — skip close (fail-closed, drift record)"
                # 漂移守望记录（issue-flow.md §9.4）
                echo "[$(date '+%Y-%d %H:%M:%S')] DRIFT: ${T_REF} GitHub Issue #${GH_NUMBER} missing anchor" >> "${LOG_DIR}/anchor-drift.log"
            else
                log "  ${T_REF}: WARNING anchor mismatch (expected ${T_REF}, got ${ANCHOR}) in GitHub Issue #${GH_NUMBER} — skip close (fail-closed)"
                # 漂移守望记录
                echo "[$(date '+%Y-%d %H:%M:%S')] DRIFT: ${T_REF} GitHub Issue #${GH_NUMBER} anchor mismatch (got ${ANCHOR})" >> "${LOG_DIR}/anchor-drift.log"
            fi
        else
            log "  ${T_REF}: no open GitHub Issue found, skip"
        fi
    done <<< "$TERMINAL_ISSUES"
fi

# === GAP-A (INFRA-174): GitHub→Linear 反向对账 — 检测 Linear 同步失败 ===
# 当 Linear native GitHub 集成同步失败（API 限流、集成故障）时，evolution scanner
# 创建的 GitHub Issue 在 Linear 中无对应记录，Linear webhook 永不触发、droid 永不处理。
# 本节通过反向对账（GitHub→Linear）检测孤立 Issue 并补偿创建 Linear Issue。
#
# 注意：必须在下面的 ISSUE_COUNT==0 提前退出检查之前执行 —— 孤立 Issue 意味着
# Linear 无记录，ISSUE_COUNT 可能为 0，否则会跳过本节。
GAP_A_THRESHOLD_MIN=30

GH_EVOLUTION_ISSUES=$(gh issue list --repo "$REPO" --label evolution-found --state open \
    --json number,title,createdAt --limit 50 2>>"$LOG_FILE" || echo "[]")

GH_EVOLUTION_COUNT=$(echo "$GH_EVOLUTION_ISSUES" | /opt/homebrew/bin/python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")
GH_EVOLUTION_COUNT=$(echo "$GH_EVOLUTION_COUNT" | tr -d '[:space:]')

if [ "$GH_EVOLUTION_COUNT" -gt 0 ]; then
    log "GAP-A: checking ${GH_EVOLUTION_COUNT} open evolution-found GitHub issues for Linear sync"

    # 构建 Linear 标题集合（来自 $LINEAR_ISSUES 的第 3 字段，临时文件避免 subshell 传递问题）
    LINEAR_TITLES_TMP=$(mktemp 2>/dev/null || echo "/tmp/gap-a-linear-titles.$$")
    echo "$LINEAR_ISSUES" | awk -F'|' 'NF>=3 {print $3}' > "$LINEAR_TITLES_TMP" 2>/dev/null || true

    # 检测第一个孤立 Issue：无 linear-linkback + 标题不在 Linear + age > 阈值
    GAP_A_ORPHAN=$(LINEAR_TITLES_TMP="$LINEAR_TITLES_TMP" REPO="$REPO" \
        GAP_A_THRESHOLD_MIN="$GAP_A_THRESHOLD_MIN" \
        /opt/homebrew/bin/python3 -c "
import json, os, subprocess, sys
from datetime import datetime, timezone

# 从 stdin 读取 GitHub issues JSON
try:
    issues = json.load(sys.stdin)
except Exception:
    issues = []

threshold = int(os.environ.get('GAP_A_THRESHOLD_MIN', '30'))
now = datetime.now(timezone.utc)

repo = os.environ.get('REPO', '')
titles_path = os.environ.get('LINEAR_TITLES_TMP', '')
linear_titles = set()
try:
    with open(titles_path) as f:
        linear_titles = {line.strip() for line in f if line.strip()}
except Exception:
    pass

def has_linkback(number):
    try:
        r = subprocess.run(
            ['gh', 'issue', 'view', str(number), '--repo', repo,
             '--json', 'comments', '--jq', '.comments[].body'],
            capture_output=True, text=True, timeout=15
        )
        return 'linear-linkback' in (r.stdout or '')
    except Exception:
        # 查询失败时保守视为已有 linkback，避免误补偿
        return True

for issue in issues:
    title = issue.get('title', '')
    number = issue.get('number')
    created = issue.get('createdAt', '')
    if number is None or not title:
        continue
    try:
        ca = datetime.fromisoformat(created.replace('Z', '+00:00'))
        age_min = (now - ca).total_seconds() / 60
    except Exception:
        continue
    if age_min <= threshold:
        continue
    if title in linear_titles:
        continue
    if has_linkback(number):
        continue
    # 找到孤立 Issue，输出 number<TAB>title
    print(f'{number}\t{title}')
    break
" <<< "$GH_EVOLUTION_ISSUES" 2>>"$LOG_FILE" || echo "")

    rm -f "$LINEAR_TITLES_TMP" 2>/dev/null || true

    if [ -n "$GAP_A_ORPHAN" ]; then
        O_NUMBER=$(echo "$GAP_A_ORPHAN" | cut -f1)
        O_TITLE=$(echo "$GAP_A_ORPHAN" | cut -f2-)
        log "GAP-A: orphan detected — GitHub Issue #${O_NUMBER} has no Linear sync, compensating"

        # 补偿创建 Linear Issue（解析 evolution-found 标签 → issueCreate → 回写评论）
        GAP_A_RESULT=$(TEAM_ID="$TEAM_ID" LINEAR_API_KEY="$LINEAR_API_KEY" \
            O_NUMBER="$O_NUMBER" O_TITLE="$O_TITLE" REPO="$REPO" \
            /opt/homebrew/bin/python3 -c "
import json, os, sys, urllib.request

team_id = os.environ['TEAM_ID']
api_key = os.environ['LINEAR_API_KEY']
o_number = os.environ['O_NUMBER']
o_title = os.environ['O_TITLE']
repo = os.environ['REPO']
gh_url = f'https://github.com/{repo}/issues/{o_number}'

def gql(query, variables=None):
    payload = {'query': query}
    if variables:
        payload['variables'] = variables
    req = urllib.request.Request(
        'https://api.linear.app/graphql',
        data=json.dumps(payload).encode(),
        headers={'Authorization': api_key, 'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

# 1. 解析 evolution-found 标签 ID
label_query = '''query (\$tid: String!) {
    team(id: \$tid) {
        labels(filter: { name: { eq: \"evolution-found\" } }) {
            nodes { id name }
        }
    }
}'''
label_data = gql(label_query, {'tid': team_id})
nodes = label_data.get('data', {}).get('team', {}).get('labels', {}).get('nodes', [])
label_id = nodes[0]['id'] if nodes else None

# 2. 创建 Linear Issue
desc = (
    f'## Compensation 创建（GAP-A / INFRA-174）\\n\\n'
    f'Linear native GitHub 集成未能自动同步此 Issue，由 reconcile-evolution.sh 反向对账补偿创建。\\n\\n'
    f'**GitHub Issue**: {gh_url}\\n'
    f'**Title**: {o_title}\\n\\n'
    f'请参考 GitHub Issue 获取完整 finding 详情。'
)
create_mut = '''mutation (\$tid: String!, \$title: String!, \$desc: String!, \$labels: [String!]) {
    issueCreate(input: {
        teamId: \$tid,
        title: \$title,
        description: \$desc,
        labelIds: \$labels
    }) {
        issue { id identifier url }
    }
}'''
create_vars = {'tid': team_id, 'title': o_title, 'desc': desc, 'labels': [label_id] if label_id else []}
create_data = gql(create_mut, create_vars)
issue_node = create_data.get('data', {}).get('issueCreate', {}).get('issue', {})
if not issue_node:
    errs = create_data.get('errors', [])
    print('ERROR: ' + json.dumps(errs, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)

linear_uuid = issue_node['id']
linear_ref = issue_node['identifier']

# 3. 回写评论关联 GitHub Issue
comment_mut = '''mutation (\$iid: String!, \$body: String!) {
    commentCreate(input: { issueId: \$iid, body: \$body }) {
        comment { id }
    }
}'''
comment_body = f'GitHub Issue: {gh_url}（补偿创建，Linear 集成同步失败）'
gql(comment_mut, {'iid': linear_uuid, 'body': comment_body})

print(f'{linear_ref}|{linear_uuid}')
" 2>>"$LOG_FILE" || echo "")

        if [ -n "$GAP_A_RESULT" ]; then
            log "GAP-A: created Linear Issue ${GAP_A_RESULT} for GitHub #${O_NUMBER} (next tick will trigger droid)"
        else
            log "GAP-A: WARNING — Linear issue creation failed for GitHub #${O_NUMBER}"
        fi
    else
        log "GAP-A: no orphaned GitHub issues detected"
    fi
else
    log "GAP-A: no open evolution-found GitHub issues to check"
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
            # === 死锁出口（architecture §3.2，VAL-DLK-001/002/004/005）===
            # 条件：status=completed + sessionId 非空 + exitCode=0 + Linear 非终态超 stale 阈值
            # 动作：推进 Linear 终态 + 三要素证据评论 + 幂等 sentinel
            DEADLOCK_EXIT_DONE=$(/opt/homebrew/bin/python3 -c "
import json
try:
    d = json.load(open('$STATUS_FILE'))
    sid = d.get('sessionId')
    ec = d.get('exitCode')
    if sid and str(sid).lower() not in ('none', 'null', '') and ec == 0:
        print('yes')
    else:
        print('no')
except:
    print('no')
" 2>/dev/null || echo "no")

            if [ "$DEADLOCK_EXIT_DONE" = "yes" ]; then
                # 检查 Linear updatedAt 是否超过 stale 阈值
                LINEAR_AGE_MIN=$(/opt/homebrew/bin/python3 -c "
from datetime import datetime, timezone
try:
    updated = datetime.fromisoformat('${ISSUE_UPDATED}'.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    age_min = int((now - updated).total_seconds() / 60)
    print(age_min)
except:
    print(0)
" 2>/dev/null || echo "0")

                if [ "$LINEAR_AGE_MIN" -ge "$DEADLOCK_STALE_THRESHOLD_MIN" ]; then
                    # 检查幂等 sentinel（是否已执行过出口）
                    # LINEAR_API_KEY 已在脚本顶部 export，子进程自动继承
                    SENTINEL_EXISTS=$(/opt/homebrew/bin/python3 -c "
import json, urllib.request, os, sys, socket
socket.setdefaulttimeout(15)
api_key = os.environ['LINEAR_API_KEY']
issue_uuid = '$ISSUE_UUID'
sentinel_prefix = '$DEADLOCK_EXIT_SENTINEL_PREFIX'
if not api_key or not issue_uuid:
    print('no')
    sys.exit(0)
query = '{ issue(id: \"' + issue_uuid + '\") { comments { nodes { body } } } }'
req = urllib.request.Request(
    'https://api.linear.app/graphql',
    data=json.dumps({'query': query}).encode(),
    headers={'Authorization': api_key, 'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
        nodes = d.get('data', {}).get('issue', {}).get('comments', {}).get('nodes', [])
        for n in nodes:
            body = n.get('body', '')
            if sentinel_prefix in body:
                print('yes')
                sys.exit(0)
        print('no')
except Exception:
    print('no')
" 2>>"$LOG_FILE" || echo "no")

                    if [ "$SENTINEL_EXISTS" = "yes" ]; then
                        log "  ${LINEAR_REF}: deadlock exit already executed (sentinel found), skip (VAL-DLK-005 idempotent)"
                        continue
                    fi

                    # 执行死锁出口：推进 Linear 终态 + 三要素证据评论
                    # LINEAR_API_KEY 已在脚本顶部 export，子进程自动继承
                    DEADLOCK_RESULT=$(ISSUE_UUID="$ISSUE_UUID" \
                        LINEAR_REF="$LINEAR_REF" STATUS_FILE="$STATUS_FILE" \
                        DEADLOCK_EXIT_SENTINEL_PREFIX="$DEADLOCK_EXIT_SENTINEL_PREFIX" \
                        /opt/homebrew/bin/python3 -c "
import json, urllib.request, os, sys, socket
socket.setdefaulttimeout(15)
api_key = os.environ['LINEAR_API_KEY']
issue_uuid = os.environ['ISSUE_UUID']
linear_ref = os.environ['LINEAR_REF']
status_file = os.environ['STATUS_FILE']
sentinel_prefix = os.environ['DEADLOCK_EXIT_SENTINEL_PREFIX']

# 1. 查询 In Progress state ID for this team
def gql(query, variables=None):
    payload = {'query': query}
    if variables:
        payload['variables'] = variables
    req = urllib.request.Request(
        'https://api.linear.app/graphql',
        data=json.dumps(payload).encode(),
        headers={'Authorization': api_key, 'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

# 查询 team 的 completed state
team_query = '''query {
    teams(first: 1) {
        nodes {
            id
            states {
                nodes { id name type }
            }
        }
    }
}'''
team_data = gql(team_query)
completed_state_id = None
for team in team_data.get('data', {}).get('teams', {}).get('nodes', []):
    for state in team.get('states', {}).get('nodes', []):
        if state.get('type') == 'completed':
            completed_state_id = state['id']
            break
    if completed_state_id:
        break

if not completed_state_id:
    print('ERROR: no completed state found')
    sys.exit(1)

# 2. 读取 status 文件证据
with open(status_file) as f:
    status_data = json.load(f)
session_id = status_data.get('sessionId', '')
exit_code = status_data.get('exitCode', '')

# 3. 推进 Linear 到 completed
move_mut = '''mutation (\$issueId: String!, \$stateId: String!) {
    issueUpdate(id: \$issueId, input: { stateId: \$stateId }) {
        success
    }
}'''
move_result = gql(move_mut, {'issueId': issue_uuid, 'stateId': completed_state_id})
if not move_result.get('data', {}).get('issueUpdate', {}).get('success'):
    print('ERROR: failed to move to completed')
    sys.exit(1)

# 4. 写三要素证据评论（含幂等 sentinel）
comment_body = f'''{sentinel_prefix}{linear_ref} sessionId={session_id} exitCode=0 -->
死锁出口：session 已完成（sessionId={session_id}，exitCode={exit_code}），Linear 停留非终态超 stale 阈值，由 reconcile 推进终态。
- **INFRA ref**: {linear_ref}
- **Status 依据**: status=completed, sessionId={session_id}, exitCode={exit_code}
- **动作**: Linear state → completed（reconcile deadlock exit）'''

comment_mut = '''mutation (\$issueId: String!, \$body: String!) {
    commentCreate(input: { issueId: \$issueId, body: \$body }) {
        comment { id }
    }
}'''
gql(comment_mut, {'issueId': issue_uuid, 'body': comment_body})

print('OK')
" 2>>"$LOG_FILE" || echo "FAIL")

                    if [ "$DEADLOCK_RESULT" = "OK" ]; then
                        log "  ${LINEAR_REF}: DEADLOCK EXIT executed — Linear pushed to completed (session=${SESSION_ID_FOR_LOG:-unknown}, exitCode=0, stale=${LINEAR_AGE_MIN}min)"
                        # 记录到 drift log 供取证
                        echo "[$(date '+%Y-%d %H:%M:%S')] DEADLOCK_EXIT: ${LINEAR_REF} uuid=${ISSUE_UUID} stale=${LINEAR_AGE_MIN}min" >> "${LOG_DIR}/anchor-drift.log"
                    else
                        log "  ${LINEAR_REF}: WARNING deadlock exit failed (${DEADLOCK_RESULT}), will retry next tick"
                    fi
                    continue
                else
                    log "  ${LINEAR_REF}: completed but Linear not yet stale (${LINEAR_AGE_MIN}min < ${DEADLOCK_STALE_THRESHOLD_MIN}min threshold), skip"
                    continue
                fi
            else
                log "  ${LINEAR_REF}: already completed (no valid session/exitCode), skip"
                continue
            fi
        fi
    fi

    # 5d. 补触发前置双验证（architecture §3.3，VAL-DRF-005）
    # 前提：镜像 issue 仍 OPEN 且 finding 仍存在（status 文件存在）
    # 不满足 → 不派发，转关闭评估或记录
    RETRIGGER_OK=1

    # 验证 1：镜像 issue 仍 OPEN
    RETRIGGER_GH_CHECK=$(gh issue list --repo "$REPO" --label evolution-found --state open \
        --search "${LINEAR_REF}" --json number --limit 1 2>/dev/null || echo "[]")
    RETRIGGER_GH_COUNT=$(echo "$RETRIGGER_GH_CHECK" | /opt/homebrew/bin/python3 -c \
        "import json,sys; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")
    if [ "$RETRIGGER_GH_COUNT" -eq 0 ]; then
        log "  ${LINEAR_REF}: retrigger BLOCKED — no open GitHub mirror issue (VAL-DRF-005)"
        RETRIGGER_OK=0
    fi

    # 验证 2：status 文件存在（finding 仍被追踪）
    if [ "$RETRIGGER_OK" -eq 1 ] && [ ! -f "${STATUS_DIR}/${LINEAR_REF}.json" ]; then
        log "  ${LINEAR_REF}: retrigger BLOCKED — no status file (E4 形态，VAL-DRF-005)"
        # 转关闭评估：issue open + finding 消失（无 status 文件）→ 记录漂移
        echo "[$(date '+%Y-%d %H:%M:%S')] DRIFT: ${LINEAR_REF} retrigger blocked — status file missing (E4)" >> "${LOG_DIR}/anchor-drift.log"
        RETRIGGER_OK=0
    fi

    if [ "$RETRIGGER_OK" -eq 0 ]; then
        continue
    fi

    log "  ${LINEAR_REF}: orphaned, triggering reconciliation"
    bash "${SCRIPT_DIR}/trigger-droid.sh" \
        "create" "Issue" "$LINEAR_REF" "$ISSUE_UUID" "$TEAM_KEY" "$ISSUE_TITLE" \
        >> "$LOG_FILE" 2>&1 || true

    TRIGGERED=1
    log "  Triggered ${LINEAR_REF}, stopping for this tick (serial execution)"
    break

done <<< "$LINEAR_ISSUES"

log "Reconciliation complete: triggered=${TRIGGERED}"
