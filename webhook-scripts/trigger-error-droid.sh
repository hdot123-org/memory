#!/bin/bash
# trigger-error-droid.sh — PostHog webhook → droid exec 异步触发器
# 由 adnanh/webhook 调用，立即返回 accepted，后台执行 droid + error-gateway skill
#
# Fixes applied:
# - Dynamic repo routing via repositories.yml (no hardcoded paths)
# - Concurrent trigger protection via fingerprint lock files
# - Failure write-back: creates GitHub Issue if droid exec crashes

set -uo pipefail

# === 参数 ===
ERROR_TYPE="${1:-}"
METHOD="${2:-}"
FAILED_EVENT="${3:-}"
COUNT="${4:-}"
LAST_SEEN="${5:-}"

# === 配置 ===
WEBHOOK_BASE="/Users/busiji/.factory/webhook"
LOG_DIR="${WEBHOOK_BASE}/logs"
LOCK_DIR="${WEBHOOK_BASE}/locks"
REPO_CONFIG="/Users/busiji/.factory/config/repositories.yml"
GITHUB_REPO="${POSTHOG_GITHUB_REPO:-hdot123-org/memory}"

# === 日志 ===
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/error-trigger-${ERROR_TYPE:-unknown}-${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# === M3: ECHO_DROID 启动警告 ===
if [ "${ECHO_DROID:-0}" = "1" ]; then
    log "⚠️ DRY-RUN MODE: ECHO_DROID=1 — all droid exec calls are no-ops"
fi

# === C3: with_timeout() — macOS 无 timeout 命令，纯 bash 实现 ===
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

# === M-ERR-5: PostHog 事件上报 ===
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
                \"event\": \"error_webhook_failure\",
                \"properties\": {
                    \"error_type\": \"$event_type\",
                    \"identifier\": \"$identifier\",
                    \"stage\": \"$stage\",
                    \"detail\": \"$detail\",
                    \"distinct_id\": \"error-webhook\"
                },
                \"timestamp\": \"$timestamp\"
            }]
        }" >> "$LOG_FILE" 2>&1 || true
}

# === 仓库路由 (error 5 fix: no hardcoded paths) ===
route_repo() {
    local event_prefix="$1"

    # Strategy 1: Match failed_event prefix in repositories.yml
    if [ -f "$REPO_CONFIG" ]; then
        /opt/homebrew/bin/python3 -c "
import yaml, os
with open('$REPO_CONFIG') as f:
    cfg = yaml.safe_load(f)
# Search all teams for a repo whose paths match the event prefix
prefix = '${event_prefix}'.split('.')[0] if '${event_prefix}' else ''
for team in cfg.get('teams', {}).values():
    for repo in team.get('repos', []):
        repo_key = repo.get('repoKey', '')
        if prefix and prefix in repo_key:
            path = os.path.expanduser(repo.get('repoPath', ''))
            gh = repo.get('githubRepo', '')
            print(f'{path}|{gh}')
            exit(0)
# Default fallback
print(os.path.expanduser('~/memory') + '|hdot123-org/memory')
" 2>/dev/null && return
    fi

    # Strategy 2: Use CWD from hooks.json command-working-directory
    if [ -d "$(pwd)/.git" ]; then
        echo "$(pwd)|${GITHUB_REPO}"
        return
    fi

    # Strategy 3: Hardcoded fallback (last resort)
    echo "${HOME}/memory|hdot123-org/memory"
}

# === 并发保护 (M1: atomic flock + M2: PID liveness check) ===
FINGERPRINT="${ERROR_TYPE}:${METHOD}:${FAILED_EVENT}"
LOCK_FILE="${LOCK_DIR}/posthog-error-$(echo "$FINGERPRINT" | /usr/bin/sed 's/[^a-zA-Z0-9]/-/g').lock"

mkdir -p "$LOCK_DIR" 2>/dev/null

# M2: Advisory PID liveness check (observability only, NOT for reclaim-by-delete)
if [ -f "$LOCK_FILE" ]; then
    LOCK_CONTENT=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    LOCK_PID=$(echo "$LOCK_CONTENT" | cut -d: -f2)
    LOCK_TIMESTAMP=$(echo "$LOCK_CONTENT" | cut -d: -f1)

    # Validate timestamp: empty or non-numeric means corrupt lock file
    if [ -z "$LOCK_TIMESTAMP" ] || ! [[ "$LOCK_TIMESTAMP" =~ ^[0-9]+$ ]]; then
        log "WARN: Corrupt lock file for fingerprint '$FINGERPRINT' (empty/invalid timestamp), removing and proceeding"
        rm -f "$LOCK_FILE" 2>/dev/null
    else
        # age>TTL check: cap at 1440min (24hr) max to prevent overflow display
        LOCK_AGE_SEC=$(( $(date +%s) - LOCK_TIMESTAMP ))
        if [ "$LOCK_AGE_SEC" -lt 0 ]; then LOCK_AGE_SEC=0; fi
        LOCK_AGE_MIN=$(( LOCK_AGE_SEC / 60 ))
        if [ "$LOCK_AGE_MIN" -gt 1440 ]; then LOCK_AGE_MIN=1440; fi

        if [ "$LOCK_AGE_MIN" -ge 60 ]; then
            log "WARN: Lock held for ${LOCK_AGE_MIN}min (possible hung process, age > 60min TTL)"
            send_posthog_event "lock_stale" "$FINGERPRINT" "dedup" "age=${LOCK_AGE_MIN}min"
            # If PID is dead, reclaim the lock instead of permanently blocking
            if [ -n "$LOCK_PID" ] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
                log "INFO: Stale lock PID $LOCK_PID is dead, reclaiming lock for fingerprint '$FINGERPRINT'"
                rm -f "$LOCK_FILE" 2>/dev/null
            else
                exit 0
            fi
        fi

        # PID liveness check (advisory only) — only reached if age < 60min
        if [ -f "$LOCK_FILE" ] && [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
            log "SKIP: Active lock for fingerprint '$FINGERPRINT' (PID $LOCK_PID alive, age: ${LOCK_AGE_MIN}min). Already processing."
            send_posthog_event "lock_held" "$FINGERPRINT" "dedup" "PID alive"
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
    send_posthog_event "lock_held" "$FINGERPRINT" "dedup" "flock rejected"
    exit 0
}
# Placeholder removed; subshell PID written after backgrounding

# === 失败回写 (error 3 fix: write-back on droid exec failure) ===
create_failure_issue() {
    local err_output="$1"
    local session_id="${2:-unknown}"

    log "Creating failure GitHub Issue..."

    local body
    body="## PostHog 管道执行失败

**错误上下文**
- Error Type: \`$ERROR_TYPE\`
- Method: \`$METHOD\`
- Failed Event: \`$FAILED_EVENT\`
- Count: $COUNT

**执行信息**
- Droid Session: \`$session_id\`
- 失败时间: $(date '+%Y-%m-%d %H:%M:%S')
- 日志文件: \`$LOG_FILE\`

**错误输出**
\`\`\`
$(echo "$err_output" | head -20)
\`\`\`

---
此 Issue 由 trigger-error-droid.sh 自动创建（droid exec 执行失败）。
error-gateway skill 未能正常完成，需要人工介入。"

# C2: Dedup search before creating issue
    local existing
    existing=$(gh issue list --repo "$GITHUB_REPO" --label "posthog-error-sync" \
        --state all --search "crashed for $ERROR_TYPE" --limit 1 2>/dev/null)
    if [ -n "$existing" ]; then
        log "SKIP: Failure Issue already exists for $ERROR_TYPE"
        log "$existing"
        return 0
    fi

    gh issue create \
        --repo "$GITHUB_REPO" \
        --title "PostHog 管道失败: droid exec crashed for $ERROR_TYPE" \
        --body "$body" \
        --label "needs-triage,posthog-error-sync" >> "$LOG_FILE" 2>&1 || {
        # C4: Issue creation failure sends PostHog escalation
        log "WARN: Failed to create failure Issue (gh may not be authenticated)"
        send_posthog_event "issue_creation_failed" "$ERROR_TYPE" "github_issue" "gh issue create failed for $ERROR_TYPE"
    }
}

# === 主流程 ===
log "=== trigger-error-droid.sh started ==="
log "ERROR_TYPE=$ERROR_TYPE METHOD=$METHOD FAILED_EVENT=$FAILED_EVENT COUNT=$COUNT"
log "Fingerprint: $FINGERPRINT"

if [ -z "$ERROR_TYPE" ]; then
    # Alert-based trigger: error_type may be empty, check if this is an alert trigger
    TRIGGER_TYPE="${POSTHOG_TRIGGER_TYPE:-}"
    if [ "$TRIGGER_TYPE" = "alert" ]; then
        ERROR_TYPE="alert-trigger"
        METHOD="${METHOD:-unknown}"
        log "Alert-based trigger: error_type empty, using fallback. Trigger type: alert"
    else
        log "ERROR: ERROR_TYPE is empty and not an alert trigger, skipping"
        send_posthog_event "empty_error_type" "unknown" "validation" "ERROR_TYPE empty, not alert"
        rm -f "$LOCK_FILE"
        exit 0
    fi
fi

# Dynamic repo routing
ROUTE_RESULT=$(route_repo "$FAILED_EVENT")
REPO_PATH=$(echo "$ROUTE_RESULT" | cut -d'|' -f1)
GITHUB_REPO=$(echo "$ROUTE_RESULT" | cut -d'|' -f2)

if [ -z "$REPO_PATH" ] || [ ! -d "$REPO_PATH" ]; then
    log "ERROR: Routed repo path does not exist: $REPO_PATH"
    send_posthog_event "route_repo_failed" "$FINGERPRINT" "routing" "repo_path=$REPO_PATH not found"
    rm -f "$LOCK_FILE"
    exit 0
fi

log "Routed: failed_event=$FAILED_EVENT -> repo=$REPO_PATH github=$GITHUB_REPO"

# === 异步执行 ===
(
    # C1: EXIT trap inside subshell — fires when subshell exits, NOT when main shell exits
    # SC2064: single-quote the trap; $LOCK_FILE is inherited by the subshell and
    # expands at signal time, so the value at exit is what gets removed.
    trap 'rm -f "$LOCK_FILE" 2>/dev/null' EXIT

    # 覆盖 log 函数，只追加到日志文件，不使用 tee（避免双重写入）
    log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

    log "--- async droid exec started ---"

    PROMPT="PostHog 错误门铃触发。请按 error-gateway skill 执行。

## 错误上下文
- **Error Type**: ${ERROR_TYPE}
- **Method**: ${METHOD}
- **Failed Event**: ${FAILED_EVENT}
- **Count**: ${COUNT}
- **Last Seen**: ${LAST_SEEN}
- **GitHub Repo**: ${GITHUB_REPO}
- **Repo Path**: ${REPO_PATH}
- **Trigger Source**: PostHog webhook
- **Trigger Type**: ${POSTHOG_TRIGGER_TYPE:-event}

## ⚠️ 执行顺序要求
1. **先创建 GitHub Issue**（步骤 5），记录 Issue 编号
2. **然后才定位和修复代码**（步骤 6-7）
3. **创建 PR 时必须包含 Closes #<issue-number>**
4. **禁止在 Issue 创建前开始代码修改**

## ℹ️ Alert 触发说明
如果 Trigger Type 为 alert，则 error_type 和 method 可能为空。
请使用 PostHog MCP 查询 memory.error 事件的最新错误详情（步骤 2），
根据查询结果确定具体的 error_type 和 method。
"

    log "Launching droid exec..."
    cd "$REPO_PATH" || {
        log "ERROR: cd $REPO_PATH failed"
        send_posthog_event "cd_failed" "$ERROR_TYPE" "droid_exec" "cd to $REPO_PATH failed"
        create_failure_issue "cd failed: $REPO_PATH"
        exit 1
    }

    if [ "${ECHO_DROID:-0}" = "1" ]; then
        echo "[ECHO_DROID] Would run: with_timeout 1800 droid exec --auto high --output-format json --tag '{\"name\":\"error-gateway\",...}' \"<prompt>\"" >> "$LOG_FILE"
        DROID_OUTPUT='{"type":"result","session_id":"dry-run-session","result":"dry-run ok"}'
        DROID_EXIT=0
    else
        DROID_OUTPUT=$(with_timeout 1800 "${DROID_BIN:-$(command -v droid || echo /usr/local/bin/droid)}" exec \
            --auto high \
            --output-format json \
            --tag "{\"name\":\"error-gateway\",\"metadata\":{\"errorType\":\"${ERROR_TYPE}\",\"method\":\"${METHOD}\",\"failedEvent\":\"${FAILED_EVENT}\",\"count\":\"${COUNT}\",\"githubRepo\":\"${GITHUB_REPO}\",\"triggerSource\":\"posthog-webhook\"}}" \
            "$PROMPT" 2>&1) || DROID_EXIT=$?
    fi

    DROID_EXIT=${DROID_EXIT:-0}

    # 从 JSON 输出提取 session_id
    SESSION_ID=$(echo "$DROID_OUTPUT" | /opt/homebrew/bin/python3 -c "
import json, sys
try:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get('type') == 'result' and 'session_id' in d:
            print(d['session_id'])
            break
except:
    pass
" 2>/dev/null)

    log "droid exec finished with exit code: $DROID_EXIT, session_id: ${SESSION_ID:-unknown}"
    log "Output (first 500 chars): ${DROID_OUTPUT:0:500}"

    if [ "$DROID_EXIT" -ne 0 ]; then
        log "ERROR: droid exec failed with exit code $DROID_EXIT"
        log "Error output: ${DROID_OUTPUT:0:1000}"
        send_posthog_event "droid_exec_failed" "$ERROR_TYPE" "droid_exec" "exit_code=$DROID_EXIT"
        # Error 3 fix: write-back on failure
        create_failure_issue "$DROID_OUTPUT" "${SESSION_ID:-unknown}"
    fi

    log "--- async droid exec completed ---"

    # Release lock
    rm -f "$LOCK_FILE" 2>/dev/null

) >> "$LOG_FILE" 2>&1 &
SUBSHELL_PID=$!
# Store actual subshell PID in lock file (not main $$ which is always dead)
echo "$(date +%s):$SUBSHELL_PID" >&200

log "Background droid process started: PID=$SUBSHELL_PID"

# 立即返回
exit 0
