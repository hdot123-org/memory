#!/bin/bash
# shellcheck disable=SC1091,SC2317,SC2054,SC2155,SC2329,SC2034
# trigger-ci-droid.sh — CI complete webhook → Sessions API 注入当前 session
# 由 adnanh/webhook 调用，立即返回 200，通过 Sessions API 注入消息到运行中的 session
#
# 机制：POST /api/v0/sessions/{session_id}/messages with computerId 路由到本地 daemon
# 参照：trigger-error-droid.sh 的异步模式和 fingerprint lock

set -uo pipefail

# === PostHog 事件上报 (lib/posthog.sh 统一实现) ===
POSTHOG_EVENT_NAME="ci_webhook_failure"
POSTHOG_DISTINCT_ID="ci-webhook"
# shellcheck source=/dev/null
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/posthog.sh"

# === 参数 ===
PR_NUMBER="${1:-}"
BRANCH="${2:-}"
SHA="${3:-}"
STATUS="${4:-}"

# === 配置（VAL-INJ-010: LOG_FILE 赋值先于任何 send_posthog_event）===
WEBHOOK_BASE="${WEBHOOK_BASE:-/Users/busiji/.factory/webhook}"
LOG_DIR="${WEBHOOK_BASE}/logs"
LOCK_DIR="${LOCK_DIR:-${WEBHOOK_BASE}/locks}"
SESSIONS_INDEX="${SESSIONS_INDEX:-${HOME}/.factory/sessions-index.json}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3}"
FLOCK_BIN="${FLOCK_BIN:-/opt/homebrew/bin/flock}"

# VAL-INJ-010: 提前赋值 LOG_FILE，确保 ci_invalid_pr_number 事件回执落盘
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/ci-complete-pr${PR_NUMBER:-unknown}-${TIMESTAMP}.log"
mkdir -p "$LOG_DIR" 2>/dev/null

# PR_NUMBER 前置校验（必须在路径拼接前）
if [[ ! "$PR_NUMBER" =~ ^[1-9][0-9]*$ ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Invalid PR_NUMBER='$PR_NUMBER' (must match ^[1-9][0-9]*$)"
  send_posthog_event "ci_invalid_pr_number" "${PR_NUMBER:-empty}" "validation" "format_error"
  exit 0
fi

# === 配置（后续字段依赖 PR_NUMBER 合法性）===
PENDING_CI_FILE="${LOCK_DIR}/pending-ci-${PR_NUMBER}.json"

# Cross-platform mtime (macOS stat -f %m / GNU stat -c %Y)
# Conditional assignment avoids GNU stdout leak into $() capture
# (GNU stat treats -f as --file-system, leaking fs-listing stdout)
_portable_mtime() {
    local _f="$1" _ts
    if ! _ts=$(stat -f %m "$_f" 2>/dev/null); then
        _ts=$(stat -c %Y "$_f" 2>/dev/null || echo 0)
    fi
    printf '%s' "$_ts"
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

  # F3 VAL-INJ-005: Fallback prompt includes gh pr view step for context retrieval
  # This ensures the fallback session fetches PR state/checks before acting,
  # rather than being triggered with bare context.
  local PROMPT="CI 完成通知（fallback 路径）：PR #${pr_num} 状态为 ${ci_status}。
1. 先执行 \`gh pr view ${pr_num} --json state,statusCheckRollup\` 获取 PR 上下文
2. 若 CI 全绿（state=OPEN, statusCheckRollup 全部 success）→ 合并 PR
3. 若 CI 红 → 分析失败原因，修复后 push 重跑
4. 若 PR 已关闭 → 清理分支
铁律：禁止静默关 PR——关闭前必须写评论说明原因，评论失败则本轮不关"
  local TAG="{\"name\":\"ci-gateway\",\"metadata\":{\"pr_number\":\"${pr_num}\",\"status\":\"${ci_status}\"}}"

  log "FALLBACK: Spawning droid exec for PR #${pr_num} (repo: ${repo_path})"

  if [ "${ECHO_DROID:-0}" = "1" ]; then
    echo "[ECHO_DROID] Would run: droid exec --auto high --tag '${TAG}' '${PROMPT}'" >> "$LOG_FILE"
    log "[ECHO_DROID] Fallback droid exec command printed (dry-run)"
  else
    (cd "$repo_path" && with_timeout 3600 "${DROID_BIN:-$(command -v droid || echo /usr/local/bin/droid)}" exec --auto high \
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
# VAL-INJ-010: LOG_FILE 已在文件顶部提前赋值（在 PR_NUMBER 校验之前）
# 这里只定义 log 函数

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
        FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$FALLBACK_LOCK") ))
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
# M5: session_id is now optional (new schema: {pr_number, cwd, created_at})
# Old schema with session_id still works (backward compat)
#
# INFRA-527 修复：空 session_id 占位符
# 旧实现按 `{session_id} {pr_number} ...` 单行拼接，session_id 为空时 python 输出
# 前导空格，bash read 的 IFS 默认剥离所有空白，导致字段整体左移错位：
# SESSION_ID=pr_number、PENDING_PR=created_at —— 新 schema 100% 误报 ci_pr_mismatch。
# 占位符 "-" 保证 read 永远对齐 4 个字段，随后归一化为空字符串。
read -r SESSION_ID PENDING_PR CREATED_AT PENDING_CWD < <($PYTHON_BIN -c "
import json, sys
try:
    with open('$PENDING_CI_FILE') as f:
        data = json.load(f)
    session_id = data.get('session_id') or '-'  # M5: null/missing → placeholder keeps read aligned
    pr_number = data.get('pr_number', '-')
    created_at = data.get('created_at', '-')
    cwd = data.get('cwd', '-')
    print(f'{session_id} {pr_number} {created_at} {cwd}')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    print('- - - -')
" 2>>"$LOG_FILE")

# Normalize placeholders to empty (missing optional fields keep legacy behavior)
[ "$SESSION_ID" = "-" ] && SESSION_ID=""
[ "$CREATED_AT" = "-" ] && CREATED_AT=""
[ "$PENDING_CWD" = "-" ] && PENDING_CWD=""

# Check for corrupted JSON (parser failed to extract any fields)
if [ -z "$PENDING_PR" ] || [ "$PENDING_PR" = "-" ]; then
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

# === F1: Extract source field for routing ===
PENDING_SOURCE=$($PYTHON_BIN -c "
import json, sys
try:
    with open('$PENDING_CI_FILE') as f:
        data = json.load(f)
    print(data.get('source', ''))
except Exception as e:
    print('', file=sys.stderr)
    print('')
" 2>>"$LOG_FILE")

# === F1: Weak cross-validation for scanner source ===
# VAL-REG-007: Verify scanner identity via gh pr view (author/labels)
# Returns: 0=pass, 1=mismatch, 2=unexecutable (gh unavailable/failed)
verify_scanner_identity() {
    local pr_num="$1"

    # Check if gh CLI is available
    if ! command -v gh &>/dev/null; then
        log "WARN: gh CLI not available for scanner cross-validation"
        return 2
    fi

    # Derive owner/repo from PENDING_CWD for -R flag (VAL-REG-007 fix: without -R,
    # gh falls back to CWD which is not the PR's repo, so verification always fails)
    local repo_slug=""
    if [[ -n "$PENDING_CWD" && -d "$PENDING_CWD/.git" ]]; then
        repo_slug=$(git -C "$PENDING_CWD" remote get-url origin 2>/dev/null | \
            sed -E 's#^https://[^/]+/##; s#^git@[^:]+:##; s#\.git$##' || true)
    fi
    local repo_flag=""
    if [[ -n "$repo_slug" ]]; then
        repo_flag="-R $repo_slug"
        log "DEBUG: verify_scanner_identity using repo=$repo_slug (from PENDING_CWD)"
    else
        log "WARN: Could not derive repo from PENDING_CWD='$PENDING_CWD', gh pr view may fail"
    fi

    # Fetch PR metadata (author + labels)
    local pr_data
    # shellcheck disable=SC2086  # repo_flag is intentionally unquoted (empty or "-R owner/repo")
    if ! pr_data=$(gh pr view "$pr_num" $repo_flag --json author,labels 2>&1); then
        log "WARN: gh pr view failed for PR #$pr_num: $pr_data"
        return 2
    fi

    # Extract author login
    local author
    author=$($PYTHON_BIN -c "
import json, sys
try:
    data = json.loads('''$pr_data''')
    print(data.get('author', {}).get('login', ''))
except:
    print('')
" 2>>"$LOG_FILE")

    # Check for scanner-related labels (e.g., "scanner", "evolution-scanner")
    local has_scanner_label
    has_scanner_label=$($PYTHON_BIN -c "
import json, sys
try:
    data = json.loads('''$pr_data''')
    labels = [l.get('name', '').lower() for l in data.get('labels', [])]
    print('yes' if any('scanner' in l for l in labels) else 'no')
except:
    print('no')
" 2>>"$LOG_FILE")

    # Heuristic: author must be a bot/automation account OR PR must have scanner label
    # For now, accept any PR that either has scanner label or is authored by known bot accounts
    if [ "$has_scanner_label" = "yes" ]; then
        log "Scanner identity verified: PR #$pr_num has scanner-related label"
        return 0
    fi

    # Check for known scanner/bot accounts (placeholder - expand as needed)
    case "$author" in
        *scanner*|*bot*|*automation*|github-actions|evolution[bot])
            log "Scanner identity verified: PR #$pr_num authored by $author (bot account)"
            return 0
            ;;
    esac

    # Mismatch: PR doesn't look like it came from scanner
    log "WARN: Scanner cross-validation failed for PR #$pr_num (author=$author, scanner_label=$has_scanner_label)"
    return 1
}

# === F1: Source-based routing ===
# VAL-REG-005/006/007/008/010: Scanner source gets silent cleanup
if [ "$PENDING_SOURCE" = "scanner" ]; then
    # Check if expired first (VAL-REG-010: expired scanner also silent cleanup)
    if [ -n "$CREATED_AT" ]; then
        IS_EXPIRED=$($PYTHON_BIN -c "
from datetime import datetime, timezone, timedelta
import sys
try:
    created_at = '$CREATED_AT'
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
    print('no', file=sys.stderr)
    print('no')
" 2>>"$LOG_FILE")
    else
        IS_EXPIRED="no"
    fi

    # VAL-REG-010: Expired scanner files skip cross-validation and go straight to silent cleanup
    if [ "$IS_EXPIRED" = "yes" ]; then
        log "Source=scanner detected (expired), performing silent cleanup (no cross-validation needed)"
        rm -f "$PENDING_CI_FILE"
        exit 0
    fi

    # Weak cross-validation (VAL-REG-007) - only for non-expired scanner files
    verify_scanner_identity "$PR_NUMBER"
    CROSS_VALIDATION_RC=$?

    if [ "$CROSS_VALIDATION_RC" -eq 1 ]; then
        # VAL-REG-007: Positive evidence of mismatch, conservative path
        log "ERROR: Source=scanner but cross-validation failed for PR #$PR_NUMBER — conservative path (keep file, no fallback)"
        send_posthog_event "ci_scanner_source_mismatch" "$PR_NUMBER" "cross_validation" "PR #$PR_NUMBER does not match scanner identity"
        # Keep the file, don't spawn fallback, exit cleanly
        exit 0
    elif [ "$CROSS_VALIDATION_RC" -eq 2 ]; then
        # VAL-REG-007b (D2 ruling): gh unavailable → conservative path
        # Rationale: session file mislabeled as scanner + gh恰好不可用时，
        # 静默清理会删除 session PR 救援通道，违背不变量 2。
        # 保守代价仅为文件滞留 ≤2h，由过期路径 VAL-REG-010 兜底。
        log "ERROR: Source=scanner but cross-validation unexecutable (gh unavailable) for PR #$PR_NUMBER — conservative path (keep file, anomaly event, no fallback)"
        send_posthog_event "ci_scanner_source_unverifiable" "$PR_NUMBER" "cross_validation" "gh unavailable for PR #$PR_NUMBER"
        # Keep the file, don't spawn fallback, exit cleanly
        exit 0
    else
        # VAL-REG-005/006: Validation passed, silent cleanup
        log "Source=scanner detected, cross-validation passed, performing silent cleanup (no fallback/events)"
        rm -f "$PENDING_CI_FILE"
        exit 0
    fi
fi

# VAL-REG-008: Missing source field → default to session + log once
if [ -z "$PENDING_SOURCE" ]; then
    log "unknown-source defaulted to session (legacy M5 schema)"
    # Record event exactly once (no idempotency lock needed — this log line runs once per invocation)
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
            FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$FALLBACK_LOCK") ))
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

log "Pending PR from file: $PENDING_PR"

# === M5: Event-time session rebinding ===
# If SESSION_ID is present (old schema), probe it first.
# If missing or dead, do event-time rebinding from sessions-index.json.
if [ -n "$SESSION_ID" ]; then
    log "Extracted session_id (old schema): $SESSION_ID — probing..."
    # We'll probe this session below; if probe fails we'll rebind.
    : # probe happens after token retrieval (line ~361)
else
    log "No session_id in pending file (M5 schema) — will do event-time rebinding"
fi

# === 幂等保护：fingerprint lock ===
# M5: Use resolved session_id (from rebinding) or PR-based key to avoid null collision
FINGERPRINT_KEY="${SESSION_ID:-rebinding}:${PR_NUMBER}"
FINGERPRINT="$FINGERPRINT_KEY"
LOCK_FILE="${LOCK_DIR}/ci-complete-$(echo "$FINGERPRINT" | /usr/bin/sed 's/[^a-zA-Z0-9]/-/g').lock"

mkdir -p "$LOCK_DIR" 2>/dev/null

# Secondary stale lock check (timestamp-based, for locks older than 60min)
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$LOCK_FILE") ))
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

# === F3 Branch A: Check sessions-index freshness ===
# Cross-verifies if a session is actually alive despite probe 404.
# Returns "1" if session exists in index with mtime < max_age_hours, "0" otherwise.
# Rationale: Factory API may return 404 for sessions that are alive in sessions-index
# (daemon idle/timeout/platform delay). Probe 404 ≠ session death.
check_sessions_index_fresh() {
    local session_id="$1"
    local index_file="$2"
    local max_age_hours="${3:-72}"
    
    if [ ! -f "$index_file" ]; then
        echo "0"
        return
    fi
    
    # Pass variables as sys.argv to avoid quoting issues
    $PYTHON_BIN -c "
import json, sys, time
try:
    index_file = sys.argv[1]
    target_session_id = sys.argv[2]
    max_age_sec = float(sys.argv[3]) * 3600
    with open(index_file) as f:
        data = json.load(f)
    now = time.time()
    for entry in data.get('entries', []):
        if entry.get('sessionId') == target_session_id:
            mtime = entry.get('mtime', 0)
            # Normalize: if mtime is in milliseconds (> 1e12), convert to seconds
            if mtime > 1e12:
                mtime = mtime / 1000.0
            age = now - mtime
            if age < max_age_sec:
                print('1')  # fresh
                sys.exit(0)
            else:
                print('0')  # stale
                sys.exit(0)
    print('0')  # not found
except Exception as e:
    print('0')  # error = treat as stale
" "$index_file" "$session_id" "$max_age_hours" 2>>"$LOG_FILE"
}

# === M5: Event-time session selection function ===
# Queries sessions-index.json to find active orchestrator sessions for the given cwd.
# Returns the most recent session_id (by mtime) that matches the criteria.
# Criteria: cwd exact match + mission-session tag with role=orchestrator + callingSessionId=null
select_session_at_event_time() {
    local target_cwd="$1"
    local index_file="$2"

    if [ ! -f "$index_file" ]; then
        log "ERROR: sessions-index.json not found at $index_file"
        return 1
    fi

    $PYTHON_BIN -c "
import json, sys
try:
    with open('$index_file') as f:
        data = json.load(f)
    target_cwd = '$target_cwd'
    candidates = []
    for entry in data.get('entries', []):
        # Filter: exact cwd match
        if entry.get('cwd') != target_cwd:
            continue
        # Filter: callingSessionId must be null (orchestrator sessions)
        if entry.get('callingSessionId') is not None:
            continue
        # Filter: must have mission-session tag with role=orchestrator
        has_orch_tag = False
        for tag in entry.get('tags', []):
            if tag.get('name') == 'mission-session':
                metadata = tag.get('metadata', {})
                if metadata.get('role') == 'orchestrator':
                    has_orch_tag = True
                    break
        if not has_orch_tag:
            continue
        # Collect candidate
        candidates.append({
            'sessionId': entry.get('sessionId'),
            'mtime': entry.get('mtime', 0)
        })
    # Sort by mtime descending (most recent first)
    candidates.sort(key=lambda x: x['mtime'], reverse=True)
    # Return top candidate's sessionId
    if candidates:
        print(candidates[0]['sessionId'])
        sys.exit(0)
    else:
        sys.exit(1)
except Exception as e:
    print(f'ERROR in select_session_at_event_time: {e}', file=sys.stderr)
    sys.exit(2)
" 2>>"$LOG_FILE"
}

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

# === M5: Event-time session selection ===
# Determine which session to target:
# 1. If SESSION_ID is present (old schema), probe it first. If dead, do event-time rebinding.
# 2. If SESSION_ID is empty (new schema), do event-time rebinding immediately.
# 3. If rebinding finds a live session, skip to injection (no redundant probe).
# 4. If all candidates fail, mark rebinding_failed and fallback.

SESSION_PROBED=""  # Track if we've already probed the final SESSION_ID

if [ -n "$SESSION_ID" ]; then
    log "Old schema detected (session_id present): $SESSION_ID — probing first"
    PROBE_URL="${FACTORY_API_BASE}/sessions/${SESSION_ID}"
    PROBE_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$PROBE_URL" \
        -H "Authorization: Bearer $FACTORY_TOKEN" \
        --connect-timeout 10 --max-time 15 2>>"$LOG_FILE") || PROBE_RESPONSE=$'\n000'
    PROBE_CODE=$(echo "$PROBE_RESPONSE" | tail -n1)
    
    if [[ "$PROBE_CODE" =~ ^2 ]]; then
        log "Session $SESSION_ID is alive (probe HTTP $PROBE_CODE), using it"
        SESSION_PROBED="1"
    elif [ "$PROBE_CODE" = "404" ]; then
        # F3 Branch A: 404 ≠ death — cross-check sessions-index freshness
        INDEX_FRESH=$(check_sessions_index_fresh "$SESSION_ID" "$SESSIONS_INDEX" 72)
        if [ "$INDEX_FRESH" = "1" ]; then
            log "WARN: Probe 404 but sessions-index shows recent activity for $SESSION_ID, attempting POST anyway"
            SESSION_PROBED="1"
            PROBE_CODE="200"  # Treat as alive for downstream flow
        else
            log "Session $SESSION_ID is dead (probe HTTP $PROBE_CODE, index stale/missing), attempting event-time rebinding"
            SESSION_ID=""  # Clear for rebinding
        fi
    else
        # 5xx/000 — probe unavailable ≠ death; still treat as candidate
        log "Session $SESSION_ID probe unavailable (probe HTTP $PROBE_CODE), using it anyway"
        SESSION_PROBED="1"
        PROBE_CODE="200"  # Treat as alive for downstream flow
    fi
fi

if [ -z "$SESSION_ID" ]; then
    log "Attempting event-time session selection for cwd=$PENDING_CWD"
    SELECTED_SESSION=$(select_session_at_event_time "$PENDING_CWD" "$SESSIONS_INDEX" 2>>"$LOG_FILE")
    SELECT_RC=$?
    
    if [ $SELECT_RC -eq 0 ] && [ -n "$SELECTED_SESSION" ]; then
        log "Selected session via event-time rebinding: $SELECTED_SESSION"
        # Probe the selected session
        PROBE_URL="${FACTORY_API_BASE}/sessions/${SELECTED_SESSION}"
        PROBE_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$PROBE_URL" \
            -H "Authorization: Bearer $FACTORY_TOKEN" \
            --connect-timeout 10 --max-time 15 2>>"$LOG_FILE") || PROBE_RESPONSE=$'\n000'
        PROBE_CODE=$(echo "$PROBE_RESPONSE" | tail -n1)
        
        if [[ "$PROBE_CODE" =~ ^2 ]]; then
            log "Selected session $SELECTED_SESSION is alive (probe HTTP $PROBE_CODE)"
            SESSION_ID="$SELECTED_SESSION"
            SESSION_PROBED="1"
        elif [ "$PROBE_CODE" = "404" ]; then
            # F3 Branch A: 404 ≠ death — cross-check sessions-index freshness
            INDEX_FRESH=$(check_sessions_index_fresh "$SELECTED_SESSION" "$SESSIONS_INDEX" 72)
            if [ "$INDEX_FRESH" = "1" ]; then
                log "WARN: Probe 404 but sessions-index shows recent activity for $SELECTED_SESSION, attempting POST anyway"
                SESSION_ID="$SELECTED_SESSION"
                SESSION_PROBED="1"
            else
                log "Selected session $SELECTED_SESSION is dead (probe HTTP $PROBE_CODE, index stale/missing), marking rebinding_failed"
            fi
        else
            log "Selected session $SELECTED_SESSION probe unavailable (probe HTTP $PROBE_CODE), attempting POST anyway"
            SESSION_ID="$SELECTED_SESSION"
            SESSION_PROBED="1"
        fi
    else
        log "No candidates found in sessions-index for cwd=$PENDING_CWD"
    fi
fi

# If no live session found after rebinding, go directly to fallback
if [ -z "$SESSION_ID" ]; then
    log "ERROR: No live session available (event-time rebinding exhausted), going to fallback"
    
    # Mark pending file with rebinding_failed
    if [ -f "$PENDING_CI_FILE" ]; then
        log "Marking pending file with rebinding_failed"
        $PYTHON_BIN -c "
import json
try:
    with open('$PENDING_CI_FILE', 'r') as f:
        data = json.load(f)
    data['rebinding_failed'] = '$(date -u +"%Y-%m-%dT%H:%M:%SZ")'
    data['rebinding_reason'] = 'all_candidates_dead'
    with open('$PENDING_CI_FILE', 'w') as f:
        json.dump(data, f)
except Exception as e:
    print(f'Failed to mark pending file: {e}')
" 2>>"$LOG_FILE" || true
    fi
    
    # Go to fallback
    send_posthog_event "ci_probe_failed_session_not_found" "$PR_NUMBER" "probe" "all_rebinding_candidates_dead"
    rm -f "$LOCK_FILE"
    exec 200>&-
    FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
    if [ -f "$FALLBACK_LOCK" ]; then
        FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$FALLBACK_LOCK") ))
        if [ "$FALLBACK_LOCK_AGE_SEC" -lt 0 ]; then FALLBACK_LOCK_AGE_SEC=0; fi
        FALLBACK_LOCK_AGE=$(( FALLBACK_LOCK_AGE_SEC / 60 ))
        if [ "$FALLBACK_LOCK_AGE" -gt 1440 ]; then FALLBACK_LOCK_AGE=1440; fi
        if [ "$FALLBACK_LOCK_AGE" -lt 60 ]; then
            log "SKIP: Fallback already triggered for PR #${PR_NUMBER} (rebinding dedup, lock age: ${FALLBACK_LOCK_AGE}min < 60min)"
            exit 0
        else
            log "WARN: Stale fallback lock (${FALLBACK_LOCK_AGE}min > 60min), removing and proceeding"
            rm -f "$FALLBACK_LOCK"
        fi
    fi
    echo "$TIMESTAMP" > "$FALLBACK_LOCK" || {
        log "ERROR: Failed to write fallback lock $FALLBACK_LOCK"
        send_posthog_event "ci_fallback_lock_write_failed" "$PR_NUMBER" "fallback_lock" "rebinding path"
    }
    log "Created fallback lock: $FALLBACK_LOCK"
    FALLBACK_REPO="${PENDING_CWD:-$SCRIPT_CWD}"
    # Mark pending file with fallback_dispatched
    if [ -f "$PENDING_CI_FILE" ]; then
        $PYTHON_BIN -c "
import json
try:
    with open('$PENDING_CI_FILE', 'r') as f:
        data = json.load(f)
    data['fallback_dispatched_at'] = '$(date -u +"%Y-%m-%dT%H:%M:%SZ")'
    data['fallback_reason'] = 'rebinding_exhausted'
    with open('$PENDING_CI_FILE', 'w') as f:
        json.dump(data, f)
except Exception as e:
    print(f'Failed to mark pending file: {e}')
" 2>>"$LOG_FILE" || true
    fi
    spawn_fallback "$PR_NUMBER" "${STATUS:-rebinding_failed}" "$FALLBACK_REPO"
    exit 0
fi

# Update fingerprint lock with resolved session_id
FINGERPRINT_KEY="${SESSION_ID}:${PR_NUMBER}"
log "Final fingerprint key: $FINGERPRINT_KEY (SESSION_ID=$SESSION_ID)"

# Skip redundant probe if we already probed during rebinding
if [ "$SESSION_PROBED" != "1" ]; then
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
else
    log "Skipping redundant probe (already probed during rebinding)"
    PROBE_CODE="200"  # Pretend probe succeeded to skip the 404 check below
fi

# 探活失败判定：
# - 404 JSON 响应（Session does not exist）→ 检查 sessions-index 新鲜度（F3 Branch A）
#   - 若 index 显示 72h 内活跃 → 仍尝试 POST（API 暂时不可达 ≠ 会话死亡）
#   - 若 index 过期/缺失 → 走 fallback
# - 5xx 或 000（连接失败）→ 探活不可用，仍尝试 POST（不阻塞注入）
# - 200 或其他 → 会话存在，继续 POST 注入
if [ "$PROBE_CODE" = "404" ]; then
    # F3 Branch A: Cross-check sessions-index before judging death
    INDEX_FRESH=$(check_sessions_index_fresh "$SESSION_ID" "$SESSIONS_INDEX" 72)
    
    if [ "$INDEX_FRESH" = "1" ]; then
        # Index shows recent activity → attempt POST despite 404
        log "WARN: Probe 404 but sessions-index shows recent activity for $SESSION_ID, attempting POST anyway"
        # Continue to POST injection (same as 5xx/000 path)
    else
        # Index stale/missing → check if this is API-level 404
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
            log "PROBE FAILED: Session does not exist (404 JSON, index stale/missing), going to fallback"
            send_posthog_event "ci_probe_failed_session_not_found" "$PR_NUMBER" "probe" "session_id=$SESSION_ID"
            
            # 直接走 fallback，不烧 POST 重试
            rm -f "$LOCK_FILE"
            exec 200>&-
            FALLBACK_LOCK="${LOCK_DIR}/ci-fallback-${PR_NUMBER}.lock"
            if [ -f "$FALLBACK_LOCK" ]; then
                FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$FALLBACK_LOCK") ))
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
            # M1: 标记 pending 文件（不删除，保留审计轨迹）
            if [ -f "$PENDING_CI_FILE" ]; then
                $PYTHON_BIN -c "
import json
try:
    with open('$PENDING_CI_FILE', 'r') as f:
        data = json.load(f)
    data['fallback_dispatched_at'] = '$(date -u +"%Y-%m-%dT%H:%M:%SZ")'
    data['fallback_reason'] = 'probe_404'
    with open('$PENDING_CI_FILE', 'w') as f:
        json.dump(data, f)
except Exception as e:
    print(f'Failed to mark pending file: {e}')
" 2>>"$LOG_FILE" || true
            fi
            spawn_fallback "$PR_NUMBER" "${STATUS:-probe_failed}" "$FALLBACK_REPO"
            exit 0
        fi
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
    if [[ "$HTTP_CODE" =~ ^2 ]] || [[ "$HTTP_CODE" =~ ^4 ]]; then
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
if [[ "$HTTP_CODE" =~ ^2 ]]; then
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
            FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$FALLBACK_LOCK") ))
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
        # M1: 标记 pending 文件（不删除，保留审计轨迹）
        if [ -f "$PENDING_CI_FILE" ]; then
            $PYTHON_BIN -c "
import json
try:
    with open('$PENDING_CI_FILE', 'r') as f:
        data = json.load(f)
    data['fallback_dispatched_at'] = '$(date -u +"%Y-%m-%dT%H:%M:%SZ")'
    data['fallback_reason'] = '4xx'
    with open('$PENDING_CI_FILE', 'w') as f:
        json.dump(data, f)
except Exception as e:
    print(f'Failed to mark pending file: {e}')
" 2>>"$LOG_FILE" || true
        fi
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
                FALLBACK_LOCK_AGE_SEC=$(( $(date +%s) - $(_portable_mtime "$FALLBACK_LOCK") ))
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
            # M1: 标记 pending 文件（不删除，保留审计轨迹）
            if [ -f "$PENDING_CI_FILE" ]; then
                $PYTHON_BIN -c "
import json
try:
    with open('$PENDING_CI_FILE', 'r') as f:
        data = json.load(f)
    data['fallback_dispatched_at'] = '$(date -u +"%Y-%m-%dT%H:%M:%SZ")'
    data['fallback_reason'] = '5xx_exhausted'
    with open('$PENDING_CI_FILE', 'w') as f:
        json.dump(data, f)
except Exception as e:
    print(f'Failed to mark pending file: {e}')
" 2>>"$LOG_FILE" || true
            fi
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
