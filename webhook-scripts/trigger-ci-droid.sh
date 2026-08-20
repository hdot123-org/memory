#!/bin/bash
# shellcheck disable=SC1091,SC2317,SC2054,SC2155,SC2329
# trigger-ci-droid.sh — CI complete webhook → Sessions API 注入当前 session
# 由 adnanh/webhook 调用，立即返回 200，通过 Sessions API 注入消息到运行中的 session
#
# 机制：POST /api/v0/sessions/{session_id}/messages with computerId 路由到本地 daemon
# 参照：trigger-error-droid.sh 的异步模式和 fingerprint lock

set -uo pipefail

# === 参数 ===
PR_NUMBER="${1:-}"
BRANCH="${2:-}"
SHA="${3:-}"
STATUS="${4:-}"

# === 配置 ===
WEBHOOK_BASE="${WEBHOOK_BASE:-/Users/busiji/.factory/webhook}"
LOG_DIR="${WEBHOOK_BASE}/logs"
LOCK_DIR="${LOCK_DIR:-${WEBHOOK_BASE}/locks}"
PENDING_CI_FILE="${LOCK_DIR}/pending-ci-${PR_NUMBER}.json"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3}"
FLOCK_BIN="${FLOCK_BIN:-/opt/homebrew/bin/flock}"

# === PostHog 事件上报 ===
send_posthog_event() {
  local event_type="$1"
  local pr_number="$2"
  local stage="$3"
  local detail="$4"
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  curl -s -X POST "https://us.posthog.com/batch/" \
    -H "Content-Type: application/json" \
    -d "{
      \"api_key\": \"phc_o963uzVAku9jd4SB4tgV598LUu2oJQHKFBy3RKjtgAVs\",
      \"batch\": [{
        \"event\": \"ci_webhook_failure\",
        \"properties\": {
          \"error_type\": \"$event_type\",
          \"pr_number\": \"$pr_number\",
          \"stage\": \"$stage\",
          \"detail\": \"$detail\",
          \"distinct_id\": \"ci-webhook\"
        },
        \"timestamp\": \"$timestamp\"
      }]
    }" || true
}

# === Process timeout wrapper (macOS has no `timeout` command) ===
with_timeout() {
    local timeout_sec=$1; shift
    local tmp_output=$(mktemp)
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

# === Fallback: spawn droid exec (previously --mission; dropped 2026-08-16, PR #741) ===
# Used when Sessions API injection fails (4xx) or pending-ci file is missing.
# Derives repo path from pending-ci cwd field (if available) or script's CWD.
SCRIPT_CWD="$(pwd)"

spawn_fallback() {
  local pr_num="$1"
  local ci_status="$2"
  local repo_path="${3:-$SCRIPT_CWD}"

  local PROMPT="CI 完成通知：PR #${pr_num} 状态为 ${ci_status}。如果 CI 通过请检查并合并此 PR。"
  local TAG="{\"name\":\"ci-gateway\",\"metadata\":{\"pr_number\":\"${pr_num}\",\"status\":\"${ci_status}\"}}"

  log "FALLBACK: Spawning droid exec for PR #${pr_num} (repo: ${repo_path})"

  if [ "${ECHO_DROID:-0}" = "1" ]; then
    echo "[ECHO_DROID] Would run: droid exec --auto high --tag '${TAG}' '${PROMPT}'" >> "$LOG_FILE"
    log "[ECHO_DROID] Fallback droid exec command printed (dry-run)"
  else
    (cd "$repo_path" && with_timeout 3600 /Users/busiji/.local/bin/droid exec --auto high \
        --tag "$TAG" "$PROMPT" >> "$LOG_FILE" 2>&1) || {
      log "WARN: Fallback droid exec exited with error"
      send_posthog_event "ci_fallback_failed" "$pr_num" "fallback_exec" "droid exec failed"
    } &
  fi
}

# 1Password 配置
OP_ITEM_ID="d2da72sb27xfvekt6sbqag36zq"
OP_FIELD_LABEL="api"

# Factory Sessions API 配置
FACTORY_API_BASE="${FACTORY_API_BASE:-https://api.factory.ai/api/v0}"
COMPUTER_ID="d6cf2cd1-a7b8-4aad-a71f-ca89c90d2c33"

# === 日志 ===
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/ci-complete-pr${PR_NUMBER:-unknown}-${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# === ECHO_DROID startup warning ===
if [ "${ECHO_DROID:-0}" = "1" ]; then
    mkdir -p "$LOG_DIR" 2>/dev/null
    log "⚠️ DRY-RUN MODE: ECHO_DROID=1 — all droid exec calls are no-ops"
fi

# === 参数验证 ===
if [ -z "$PR_NUMBER" ]; then
    mkdir -p "$LOG_DIR" 2>/dev/null
    log "ERROR: PR_NUMBER parameter is empty"
    send_posthog_event "ci_empty_pr_number" "none" "validation" "PR_NUMBER parameter empty"
    exit 0
fi

log "=== trigger-ci-droid.sh started ==="
log "PR_NUMBER=$PR_NUMBER BRANCH=$BRANCH SHA=$SHA STATUS=$STATUS"

# === 检查 pending-ci-{PR_NUMBER}.json ===
if [ ! -f "$PENDING_CI_FILE" ]; then
    log "WARN: pending-ci-${PR_NUMBER}.json not found at $PENDING_CI_FILE"
    # PR-based ephemeral lock (60min TTL) to prevent duplicate fallback spawns on webhook retries
    FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
    mkdir -p "$LOCK_DIR" 2>/dev/null
    if [ -f "$FALLBACK_LOCK" ]; then
        FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$FALLBACK_LOCK" 2>/dev/null || stat -c %Y "$FALLBACK_LOCK" 2>/dev/null || echo 0) ))
        if [ "$FALLBACK_LOCK_AGE_SEC" -lt 0 ]; then FALLBACK_LOCK_AGE_SEC=0; fi
        FALLBACK_LOCK_AGE=$(( FALLBACK_LOCK_AGE_SEC / 60 ))
        if [ "$FALLBACK_LOCK_AGE" -gt 1440 ]; then FALLBACK_LOCK_AGE=1440; fi
        if [ "$FALLBACK_LOCK_AGE" -lt 60 ]; then
            log "SKIP: Fallback already triggered for PR #${PR_NUMBER} (lock age: ${FALLBACK_LOCK_AGE}min < 60min)"
            exit 0
        else
            log "WARN: Stale fallback lock (${FALLBACK_LOCK_AGE}min > 60min), removing and proceeding"
            rm -f "$FALLBACK_LOCK"
        fi
    fi
    echo "$TIMESTAMP" > "$FALLBACK_LOCK" || {
        log "ERROR: Failed to write fallback lock $FALLBACK_LOCK"
        send_posthog_event "ci_fallback_lock_write_failed" "$PR_NUMBER" "fallback_lock" "missing-pending-ci path"
    }
    log "Created fallback lock: $FALLBACK_LOCK"
    log "Triggering fallback: spawning droid exec for PR #${PR_NUMBER}"
    spawn_fallback "$PR_NUMBER" "${STATUS:-unknown}"
    exit 0
fi

log "Reading pending-ci-${PR_NUMBER}.json..."

# 读取 session_id、pr_number、created_at 和 cwd（从 pending-ci-{PR_NUMBER}.json）
read -r SESSION_ID PENDING_PR CREATED_AT PENDING_CWD < <($PYTHON_BIN -c "
import json, sys
try:
    with open('$PENDING_CI_FILE') as f:
        data = json.load(f)
    session_id = data.get('session_id', '')
    pr_number = data.get('pr_number', '')
    created_at = data.get('created_at', '')
    cwd = data.get('cwd', '')
    print(f'{session_id} {pr_number} {created_at} {cwd}')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    print('    ')
" 2>>"$LOG_FILE")

# Check for corrupted JSON (parser failed to extract any fields)
if [ -z "$SESSION_ID" ] && [ -z "$PENDING_PR" ]; then
    log "ERROR: Failed to parse pending-ci JSON — quarantining corrupted file"
    mv "$PENDING_CI_FILE" "${PENDING_CI_FILE}.corrupted.$(date +%s)"
    send_posthog_event "ci_corrupted_json" "$PR_NUMBER" "parse" "JSON parse failed"
    spawn_fallback "$PR_NUMBER" "${STATUS:-unknown}" "${PENDING_CWD:-$SCRIPT_CWD}"
    exit 0
fi

# === PR 号校验 ===
if [ "$PENDING_PR" != "$PR_NUMBER" ]; then
    log "ERROR: PR number mismatch! File contains PR #$PENDING_PR but webhook triggered for PR #$PR_NUMBER"
    send_posthog_event "ci_pr_mismatch" "$PR_NUMBER" "pr_validation" "file=$PENDING_PR arg=$PR_NUMBER"
    exit 0
fi

# Check if pending-ci-{PR_NUMBER}.json is expired (older than 2 hours)
if [ -n "$CREATED_AT" ]; then
    EXPIRED=$($PYTHON_BIN -c "
from datetime import datetime, timezone, timedelta
import sys
try:
    created_at = '$CREATED_AT'
    # Parse ISO 8601 timestamp
    if created_at.endswith('Z'):
        created_at = created_at[:-1] + '+00:00'
    created_time = datetime.fromisoformat(created_at)
    now = datetime.now(timezone.utc)
    age = now - created_time
    if age > timedelta(hours=2):
        print('yes')
    else:
        print('no')
except Exception as e:
    print(f'ERROR parsing created_at: {e}', file=sys.stderr)
    print('no')  # Don't reject if parsing fails
" 2>>"$LOG_FILE")
    
    if [ "$EXPIRED" = "yes" ]; then
        log "ERROR: pending-ci-${PR_NUMBER}.json is expired (created_at: $CREATED_AT, older than 2 hours)"
        log "Cleaning up stale pending-ci-${PR_NUMBER}.json to prevent retry loop"
        rm -f "$PENDING_CI_FILE"
        # PR-based ephemeral lock to prevent duplicate fallback spawns on retries
        FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
        mkdir -p "$LOCK_DIR" 2>/dev/null
        if [ -f "$FALLBACK_LOCK" ]; then
            FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$FALLBACK_LOCK" 2>/dev/null || stat -c %Y "$FALLBACK_LOCK" 2>/dev/null || echo 0) ))
            if [ "$FALLBACK_LOCK_AGE_SEC" -lt 0 ]; then FALLBACK_LOCK_AGE_SEC=0; fi
            FALLBACK_LOCK_AGE=$(( FALLBACK_LOCK_AGE_SEC / 60 ))
            if [ "$FALLBACK_LOCK_AGE" -gt 1440 ]; then FALLBACK_LOCK_AGE=1440; fi
            if [ "$FALLBACK_LOCK_AGE" -lt 60 ]; then
                log "SKIP: Fallback already triggered for expired PR #${PR_NUMBER} (lock age: ${FALLBACK_LOCK_AGE}min < 60min)"
                exit 0
            else
                log "WARN: Stale fallback lock (${FALLBACK_LOCK_AGE}min > 60min), removing and proceeding"
                rm -f "$FALLBACK_LOCK"
            fi
        fi
        echo "$TIMESTAMP" > "$FALLBACK_LOCK" || {
            log "ERROR: Failed to write fallback lock $FALLBACK_LOCK"
            send_posthog_event "ci_fallback_lock_write_failed" "$PR_NUMBER" "fallback_lock" "expired-pending-ci path"
        }
        send_posthog_event "ci_expired_pending_ci" "$PR_NUMBER" "expiry" "pending-ci older than 2 hours, created_at=$CREATED_AT"
        log "Created fallback lock: $FALLBACK_LOCK"
        log "Triggering fallback: spawning droid exec for expired PR #${PR_NUMBER}"
        spawn_fallback "$PR_NUMBER" "${STATUS:-unknown}"
        exit 0
    else
        log "pending-ci-${PR_NUMBER}.json is fresh (created_at: $CREATED_AT)"
    fi
else
    log "WARNING: pending-ci-${PR_NUMBER}.json missing created_at field (legacy format)"
fi

if [ -z "$SESSION_ID" ]; then
    log "ERROR: Failed to extract session_id from pending-ci-${PR_NUMBER}.json"
    send_posthog_event "ci_session_id_empty" "$PR_NUMBER" "parse" "session_id empty"
    exit 0
fi

log "Extracted session_id: $SESSION_ID"
log "Pending PR from file: $PENDING_PR"

# === 幂等保护：fingerprint lock ===
FINGERPRINT="${SESSION_ID}:${PR_NUMBER}"
LOCK_FILE="${LOCK_DIR}/ci-complete-$(echo "$FINGERPRINT" | /usr/bin/sed 's/[^a-zA-Z0-9]/-/g').lock"

mkdir -p "$LOCK_DIR" 2>/dev/null

# Secondary stale lock check (timestamp-based, for locks older than 60min)
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$LOCK_FILE" 2>/dev/null || stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
    if [ "$LOCK_AGE_SEC" -lt 0 ]; then LOCK_AGE_SEC=0; fi
    LOCK_AGE_MIN=$(( LOCK_AGE_SEC / 60 ))
    if [ "$LOCK_AGE_MIN" -gt 1440 ]; then LOCK_AGE_MIN=1440; fi
    if [ "$LOCK_AGE_MIN" -ge 60 ]; then
        log "WARN: Stale lock found (${LOCK_AGE_MIN}min > 60min), removing and proceeding"
        rm -f "$LOCK_FILE"
    fi
fi

# Atomic lock acquisition via flock (M1)
exec 200>"$LOCK_FILE"
$FLOCK_BIN -n 200 || {
    log "SKIP: Lock held by another process for fingerprint '$FINGERPRINT'"
    send_posthog_event "ci_lock_held" "$PR_NUMBER" "dedup" "flock rejected"
    exit 0
}

# Write timestamp:PID to lock file (M-CI-7: check return value)
if ! echo "$TIMESTAMP:$$" >&200; then
    log "ERROR: Failed to write to lock file $LOCK_FILE"
    send_posthog_event "ci_lock_write_failed" "$PR_NUMBER" "lock" "echo failed"
    exit 1
fi
log "Created lock file: $LOCK_FILE"

# === 从 1Password MCP 读取 Factory token ===
if [ -z "${FACTORY_TOKEN:-}" ]; then
    log "Reading Factory token from 1Password MCP..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "${SCRIPT_DIR}/lib/op-mcp.sh" ]; then
        source "${SCRIPT_DIR}/lib/op-mcp.sh"
        FACTORY_TOKEN=$(op_get_field "$OP_VAULT_SEVER" "$OP_ITEM_ID" "$OP_FIELD_LABEL" || true)
    else
        log "WARNING: op-mcp.sh not found, FACTORY_TOKEN must be set in environment"
    fi
else
    log "Using FACTORY_TOKEN from environment"
fi

if [ -z "$FACTORY_TOKEN" ]; then
    log "ERROR: Failed to read Factory token from 1Password"
    send_posthog_event "ci_token_read_failed" "$PR_NUMBER" "auth" "1Password read failed"
    rm -f "$LOCK_FILE"
    exit 0
fi

# 验证 token 格式（应以 fk- 开头）
if [[ ! "$FACTORY_TOKEN" =~ ^fk- ]]; then
    log "ERROR: Factory token does not start with 'fk-' prefix"
    send_posthog_event "ci_token_format_error" "$PR_NUMBER" "auth" "Token missing fk- prefix"
    rm -f "$LOCK_FILE"
    exit 0
fi

log "Factory token retrieved successfully (prefix: ${FACTORY_TOKEN:0:10}...)"

# === 探活：GET /api/v0/sessions/{id} 检查会话是否活跃 ===
# 实测结论（2026-08-20）：
# - GET /api/v0/sessions/{id} 端点存在，返回 JSON 格式错误（非 HTML 404 页面）
# - 不存在的会话返回 {"detail":"Session does not exist","status":404,...}
# - 不存在的路由返回 HTML 404 页面（Next.js 默认）
# - 结论：端点可用，可用于注入前探活，避免向挂起的 daemon 烧重试
PROBE_URL="${FACTORY_API_BASE}/sessions/${SESSION_ID}"
log "Probing session liveness: GET $PROBE_URL"

PROBE_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$PROBE_URL" \
    -H "Authorization: Bearer $FACTORY_TOKEN" \
    --connect-timeout 10 --max-time 15 2>>"$LOG_FILE") || PROBE_RESPONSE=$'\n000'

PROBE_BODY=$(echo "$PROBE_RESPONSE" | sed '$ d')
PROBE_CODE=$(echo "$PROBE_RESPONSE" | tail -n1)

log "Probe HTTP Response Code: $PROBE_CODE"

# 探活失败判定：
# - 404 JSON 响应（Session does not exist）→ 会话不存在，直接走 fallback
# - 5xx 或 000（连接失败）→ 探活不可用，仍尝试 POST（不阻塞注入）
# - 200 或其他 → 会话存在，继续 POST 注入
if [ "$PROBE_CODE" = "404" ]; then
    # 检查是否为 API 级别的 404（JSON 响应含 "Session does not exist"）
    echo "$PROBE_BODY" | $PYTHON_BIN -c "
import json, sys
try:
    input_data = sys.stdin.read()
    data = json.loads(input_data)
    detail = data.get('detail', '')
    if 'Session does not exist' in detail:
        sys.exit(0)
    sys.exit(1)
except Exception as e:
    sys.exit(1)
" 2>>"$LOG_FILE"
    PROBE_CHECK_EXIT=$?
    if [ "$PROBE_CHECK_EXIT" = "0" ]; then
        log "PROBE FAILED: Session does not exist (404 JSON), skipping POST retries and going directly to fallback"
        send_posthog_event "ci_probe_failed_session_not_found" "$PR_NUMBER" "probe" "session_id=$SESSION_ID"
        # 直接走 fallback，不烧 POST 重试
        rm -f "$LOCK_FILE"
        exec 200>&-
        FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
        if [ -f "$FALLBACK_LOCK" ]; then
            FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$FALLBACK_LOCK" 2>/dev/null || stat -c %Y "$FALLBACK_LOCK" 2>/dev/null || echo 0) ))
            if [ "$FALLBACK_LOCK_AGE_SEC" -lt 0 ]; then FALLBACK_LOCK_AGE_SEC=0; fi
            FALLBACK_LOCK_AGE=$(( FALLBACK_LOCK_AGE_SEC / 60 ))
            if [ "$FALLBACK_LOCK_AGE" -gt 1440 ]; then FALLBACK_LOCK_AGE=1440; fi
            if [ "$FALLBACK_LOCK_AGE" -lt 60 ]; then
                log "SKIP: Fallback already triggered for PR #${PR_NUMBER} (probe dedup, lock age: ${FALLBACK_LOCK_AGE}min < 60min)"
                exit 0
            else
                log "WARN: Stale fallback lock (${FALLBACK_LOCK_AGE}min > 60min), removing and proceeding"
                rm -f "$FALLBACK_LOCK"
            fi
        fi
        echo "$TIMESTAMP" > "$FALLBACK_LOCK" || {
            log "ERROR: Failed to write fallback lock $FALLBACK_LOCK"
            send_posthog_event "ci_fallback_lock_write_failed" "$PR_NUMBER" "fallback_lock" "probe path"
        }
        log "Created fallback lock: $FALLBACK_LOCK"
        FALLBACK_REPO="${PENDING_CWD:-$SCRIPT_CWD}"
        spawn_fallback "$PR_NUMBER" "${STATUS:-probe_failed}" "$FALLBACK_REPO"
        exit 0
    fi
fi

# 探活失败（5xx/000/其他）不阻塞 POST，仍尝试注入
if [[ "$PROBE_CODE" =~ ^5 ]] || [ "$PROBE_CODE" = "000" ]; then
    log "WARN: Probe unavailable (HTTP $PROBE_CODE), proceeding with POST injection anyway"
fi

# === 构造注入消息 ===
# 消息内容需要包含 pr_number 和 CI 通过指示
if [ "$STATUS" = "passed" ] || [ "$STATUS" = "success" ]; then
    INJECT_TEXT="CI 全绿，请合并 PR #${PR_NUMBER}。分支: ${BRANCH:-unknown}, SHA: ${SHA:-unknown}"
else
    INJECT_TEXT="CI 状态更新: PR #${PR_NUMBER} 状态为 ${STATUS:-unknown}。分支: ${BRANCH:-unknown}, SHA: ${SHA:-unknown}"
fi

log "Injecting message: $INJECT_TEXT"

# === POST 到 Sessions API（带 5xx 重试）===
API_URL="${FACTORY_API_BASE}/sessions/${SESSION_ID}/messages"

log "POSTing to $API_URL with computerId=$COMPUTER_ID"

# 重试参数（可通过环境变量覆盖以加速测试）
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_DELAY="${RETRY_DELAY:-10}"

# 使用 curl POST，捕获 HTTP 响应码和 body（5xx 自动重试）
ATTEMPT=0
HTTP_CODE="000"
HTTP_BODY=""

while [ "$ATTEMPT" -lt "$MAX_RETRIES" ]; do
    ATTEMPT=$((ATTEMPT + 1))
    log "Attempt $ATTEMPT/$MAX_RETRIES..."

    HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL" \
        -H "Authorization: Bearer $FACTORY_TOKEN" \
        -H "Content-Type: application/json" \
        --connect-timeout 15 --max-time 45 \
        -d "{
            \"text\": \"$INJECT_TEXT\",
            \"computerId\": \"$COMPUTER_ID\"
        }" 2>>"$LOG_FILE") || HTTP_RESPONSE=$'\n000'

    HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '$ d')
    HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -n1)

    log "HTTP Response Code: $HTTP_CODE"
    log "HTTP Response Body: $HTTP_BODY"

    # 成功或 4xx 客户端错误，不需要重试
    if [ "$HTTP_CODE" = "200" ] || [[ "$HTTP_CODE" =~ ^4 ]]; then
        break
    fi

    # 5xx 错误，等待后重试
    if [[ "$HTTP_CODE" =~ ^5 ]] || [ "$HTTP_CODE" = "000" ]; then
        if [ "$ATTEMPT" -lt "$MAX_RETRIES" ]; then
            log "Server error (HTTP $HTTP_CODE), retrying in ${RETRY_DELAY}s..."
            sleep "$RETRY_DELAY"
            RETRY_DELAY=$((RETRY_DELAY * 2))
        fi
    fi
done

# === 检查 API 响应 ===
if [ "$HTTP_CODE" = "200" ]; then
    # 验证响应包含 messageId
    MESSAGE_ID=$(echo "$HTTP_BODY" | $PYTHON_BIN -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('messageId', ''))
except:
    print('')
" 2>>"$LOG_FILE")

    if [ -n "$MESSAGE_ID" ]; then
        log "SUCCESS: Message injected with messageId=$MESSAGE_ID"
        
        # 不删除 pending-ci-{PR_NUMBER}.json，改为标记 injected_at 用于对账
        # 修复 daemon-hung session 问题：消息已发送但目标 session 空闲无法消费
        # ci-timeout-watchdog.sh 会在 45 分钟后检查 injected_at，若 PR 仍未合并则触发清理
        INJECTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        $PYTHON_BIN << PYEOF 2>>"$LOG_FILE"
import json
with open('$PENDING_CI_FILE', 'r') as f:
    data = json.load(f)
data['injected_at'] = '$INJECTED_AT'
data['message_id'] = '$MESSAGE_ID'
with open('$PENDING_CI_FILE', 'w') as f:
    json.dump(data, f)
PYEOF
        log "Marked pending-ci-${PR_NUMBER}.json with injected_at=$INJECTED_AT (will be cleaned up by watchdog if PR not merged in 45min)"
    else
        log "WARN: HTTP 200 but no messageId in response"
        send_posthog_event "ci_no_message_id" "$PR_NUMBER" "factory_api" "HTTP 200 without messageId"
    fi
else
    log "ERROR: API call failed with HTTP $HTTP_CODE"
    log "Response body: $HTTP_BODY"
    
    # Report failure to PostHog
    send_posthog_event "ci_inject_failed" "$PR_NUMBER" "factory_api" "HTTP $HTTP_CODE"
    
    # 不清除 lock，让下次重试（如果是临时错误）
    # 但如果是 4xx 错误（如 404 session 不存在），应该清除 lock
    if [[ "$HTTP_CODE" =~ ^4 ]]; then
        log "Client error (4xx), removing lock and triggering fallback"
        rm -f "$LOCK_FILE"
        # Close fd 200 to prevent lock leak on unlinked inode
        exec 200>&-
        # H2: 4xx fallback dedup lock (same 60min TTL as missing-pending-ci path)
        FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
        if [ -f "$FALLBACK_LOCK" ]; then
            FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$FALLBACK_LOCK" 2>/dev/null || stat -c %Y "$FALLBACK_LOCK" 2>/dev/null || echo 0) ))
            if [ "$FALLBACK_LOCK_AGE_SEC" -lt 0 ]; then FALLBACK_LOCK_AGE_SEC=0; fi
            FALLBACK_LOCK_AGE=$(( FALLBACK_LOCK_AGE_SEC / 60 ))
            if [ "$FALLBACK_LOCK_AGE" -gt 1440 ]; then FALLBACK_LOCK_AGE=1440; fi
            if [ "$FALLBACK_LOCK_AGE" -lt 60 ]; then
                log "SKIP: Fallback already triggered for PR #${PR_NUMBER} (4xx dedup, lock age: ${FALLBACK_LOCK_AGE}min < 60min)"
                exit 0
            else
                log "WARN: Stale fallback lock (${FALLBACK_LOCK_AGE}min > 60min), removing and proceeding"
                rm -f "$FALLBACK_LOCK"
            fi
        fi
        echo "$TIMESTAMP" > "$FALLBACK_LOCK" || {
            log "ERROR: Failed to write fallback lock $FALLBACK_LOCK"
            send_posthog_event "ci_fallback_lock_write_failed" "$PR_NUMBER" "fallback_lock" "echo failed"
        }
        log "Created fallback lock: $FALLBACK_LOCK"
        # Use cwd from pending-ci file if available, otherwise script CWD
        FALLBACK_REPO="${PENDING_CWD:-$SCRIPT_CWD}"
        spawn_fallback "$PR_NUMBER" "$STATUS" "$FALLBACK_REPO"
    else
        log "Server error (5xx), keeping lock for potential retry"
        # TD-DR-03: 5xx 重试耗尽后同步降级，不再只留锁等 watchdog 30min
        if [ "$ATTEMPT" -ge "$MAX_RETRIES" ]; then
            log "WARN: All $MAX_RETRIES retries exhausted (last HTTP $HTTP_CODE), triggering synchronous fallback"
            send_posthog_event "injection_daemon_504" "$PR_NUMBER" "factory_api" "HTTP $HTTP_CODE after $MAX_RETRIES retries"
            # 标记锁文件为已走 fallback 路径（防 watchdog 重复补救）
            echo "$TIMESTAMP:fallback" >&200
            # 复用 4xx 的去重逻辑（60min TTL 防风暴）
            FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
            if [ -f "$FALLBACK_LOCK" ]; then
                FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$FALLBACK_LOCK" 2>/dev/null || stat -c %Y "$FALLBACK_LOCK" 2>/dev/null || echo 0) ))
                if [ "$FALLBACK_LOCK_AGE_SEC" -lt 0 ]; then FALLBACK_LOCK_AGE_SEC=0; fi
                FALLBACK_LOCK_AGE=$(( FALLBACK_LOCK_AGE_SEC / 60 ))
                if [ "$FALLBACK_LOCK_AGE" -gt 1440 ]; then FALLBACK_LOCK_AGE=1440; fi
                if [ "$FALLBACK_LOCK_AGE" -lt 60 ]; then
                    log "SKIP: Fallback already triggered for PR #${PR_NUMBER} (5xx dedup, lock age: ${FALLBACK_LOCK_AGE}min < 60min)"
                    exit 0
                else
                    log "WARN: Stale fallback lock (${FALLBACK_LOCK_AGE}min > 60min), removing and proceeding"
                    rm -f "$FALLBACK_LOCK"
                fi
            fi
            echo "$TIMESTAMP" > "$FALLBACK_LOCK" || {
                log "ERROR: Failed to write fallback lock $FALLBACK_LOCK"
                send_posthog_event "ci_fallback_lock_write_failed" "$PR_NUMBER" "fallback_lock" "5xx path"
            }
            log "Created fallback lock: $FALLBACK_LOCK"
            FALLBACK_REPO="${PENDING_CWD:-$SCRIPT_CWD}"
            spawn_fallback "$PR_NUMBER" "$STATUS" "$FALLBACK_REPO"
        fi
    fi
    exit 0
fi

# === 清理 ===
log "CI complete notification processed successfully"

log "=== trigger-ci-droid.sh completed ==="

# 保持 lock 文件（60 分钟内防止重复触发）
# lock 会在 60 分钟后自动过期

exit 0
