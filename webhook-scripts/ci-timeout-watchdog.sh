#!/bin/bash
# ci-timeout-watchdog.sh - TTL watchdog for pending CI notifications
# Scans ~/.factory/webhook/locks/pending-ci-*.json
# Phase A: If created_at > 30 minutes without injected_at, sends PostHog event and deletes file
# Phase B: If injected_at > 45 minutes and PR not merged, spawns fallback and deletes file
# Idempotent: safe to run multiple times

set -uo pipefail

# Dynamic Python binary detection (macOS: /opt/homebrew/bin/python3, Linux: python3)
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 2>/dev/null || echo /opt/homebrew/bin/python3)}"

# === Configuration ===
LOCKS_DIR="${LOCKS_DIR:-$HOME/.factory/webhook/locks}"
TTL_SECONDS=1800          # 30 minutes (Phase A)
INJECTION_TTL_SECONDS=2700 # 45 minutes (Phase B)

# === PostHog event reporting ===
send_posthog_event() {
  # POSTHOG_DRY_RUN=1: print only, do not send (test isolation guard)
  if [[ "${POSTHOG_DRY_RUN:-0}" == "1" ]]; then
    echo "[POSTHOG_DRY_RUN] Would send: event=$1 pr=$2 stage=$3 detail=$4"
    return 0
  fi
  local event_type="$1"
  local pr_number="$2"
  local stage="$3"
  local detail="$4"
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
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

# === Spawn fallback for lost messages ===
spawn_fallback() {
  local pr_num="$1"
  local ci_status="$2"
  local repo_path="$3"
  local lock_file="$LOCKS_DIR/ci-fallback-${pr_num}.lock"

  # Create fallback lock to prevent duplicate spawns (idempotent)
  # Only spawn if lock doesn't exist or is older than 1 hour
  if [ -f "$lock_file" ]; then
    local lock_age=$(( $(date +%s) - $(_portable_mtime "$lock_file") ))
    if [ "$lock_age" -lt 3600 ]; then
      echo "Fallback lock exists and is $lock_age seconds old, skipping duplicate spawn"
      return 0
    fi
    echo "Stale fallback lock ($lock_age seconds old), removing"
    rm -f "$lock_file"
  fi
  date +%Y%m%d-%H%M%S > "$lock_file"
  echo "Created fallback lock: $lock_file"

  echo "Spawning fallback session for PR #$pr_num (CI status: $ci_status)"

  # Determine if we need to spawn a droid session for branch cleanup
  # This is triggered when the main CI injection was lost
  local droid_bin="${DROID_BIN:-$(command -v droid || echo /usr/local/bin/droid)}"
  local prompt="CI webhook injection lost for PR #$pr_num (status: $ci_status). Repository: $repo_path. Please verify PR merge status and perform branch cleanup if needed: check if PR #$pr_num is merged, if so delete the remote branch and update local main branch. If not merged, investigate why."
  local tag="ci-fallback-$pr_num"

  # Dry-run guard: prevent real droid sessions during testing
  if [ "${ECHO_DROID:-0}" = "1" ]; then
    echo "[ECHO_DROID] Would run: $droid_bin exec --auto high --tag '$tag' '$prompt'"
    echo "Fallback session dry-run complete (ECHO_DROID=1)"
    return 0
  fi

  echo "Executing: $droid_bin exec --auto high --tag '$tag' '$prompt'"

  # Spawn new session in background (nohup preserves execution after webhook returns)
  nohup "$droid_bin" exec --auto high --tag "$tag" "$prompt" > /dev/null 2>&1 &
  local spawn_pid=$!

  # Brief delay + kill -0 probe to detect immediate spawn failure
  # (nohup ... & returns 0 immediately; $? is always 0 — previous dead code)
  sleep 2
  if ! kill -0 "$spawn_pid" 2>/dev/null; then
    # Process already exited — collect exit status if available
    wait "$spawn_pid" 2>/dev/null
    local spawn_exit=$?
    echo "ERROR: Failed to spawn fallback session (PID=$spawn_pid, exit=$spawn_exit)"
    send_posthog_event "ci_fallback_spawn_failed" "$pr_num" "fallback_spawn" "exit=$spawn_exit,pid=$spawn_pid"
    return 1
  fi

  echo "Fallback session spawned successfully (PID=$spawn_pid)"
}

# === Create locks directory if missing ===
if [ ! -d "$LOCKS_DIR" ]; then
  mkdir -p "$LOCKS_DIR"
  exit 0
fi

# === Scan pending-ci-*.json files ===
CURRENT_TIME=$(date +%s)

for pending_file in "$LOCKS_DIR"/pending-ci-*.json; do
  # Skip if no files match the pattern
  [ -f "$pending_file" ] || continue
  
  # Parse JSON to extract fields
  PR_NUMBER=$($PYTHON_BIN -c "
import json
try:
    with open('$pending_file') as f:
        print(json.load(f).get('pr_number', ''))
except:
    print('')
" 2>/dev/null)
  
  CREATED_AT=$($PYTHON_BIN -c "
import json
try:
    with open('$pending_file') as f:
        print(json.load(f).get('created_at', ''))
except:
    print('')
" 2>/dev/null)
  
  INJECTED_AT=$($PYTHON_BIN -c "
import json
try:
    with open('$pending_file') as f:
        print(json.load(f).get('injected_at', ''))
except:
    print('')
" 2>/dev/null)
  
  CWD=$($PYTHON_BIN -c "
import json
try:
    with open('$pending_file') as f:
        print(json.load(f).get('cwd', ''))
except:
    print('')
" 2>/dev/null)
  
  # Skip if parsing failed or fields are empty
  if [ -z "$PR_NUMBER" ] || [ -z "$CREATED_AT" ]; then
    continue
  fi
  
  # Calculate created_at age in seconds
  CREATED_EPOCH=$($PYTHON_BIN -c "
from datetime import datetime, timezone
import sys
try:
    created_at = '$CREATED_AT'
    # Parse ISO 8601 timestamp
    if created_at.endswith('Z'):
        created_at = created_at[:-1] + '+00:00'
    created_time = datetime.fromisoformat(created_at)
    print(int(created_time.timestamp()))
except Exception as e:
    print('0', file=sys.stderr)
    print('0')
" 2>/dev/null)
  
  # Skip if timestamp parsing failed
  if [ "$CREATED_EPOCH" = "0" ]; then
    continue
  fi
  
  CREATED_AGE_SECONDS=$((CURRENT_TIME - CREATED_EPOCH))
  
  # === Phase B: Check if injected but not consumed ===
  if [ -n "$INJECTED_AT" ]; then
    INJECTED_EPOCH=$($PYTHON_BIN -c "
from datetime import datetime, timezone
import sys
try:
    injected_at = '$INJECTED_AT'
    if injected_at.endswith('Z'):
        injected_at = injected_at[:-1] + '+00:00'
    injected_time = datetime.fromisoformat(injected_at)
    print(int(injected_time.timestamp()))
except Exception as e:
    print('0', file=sys.stderr)
    print('0')
" 2>/dev/null)
    
    if [ "$INJECTED_EPOCH" = "0" ]; then
      echo "Warning: Could not parse injected_at timestamp for PR #$PR_NUMBER, skipping Phase B"
      continue
    fi
    
    INJECTED_AGE_SECONDS=$((CURRENT_TIME - INJECTED_EPOCH))
    
    # Check if injected message was not consumed within 45 minutes
    if [ "$INJECTED_AGE_SECONDS" -gt "$INJECTION_TTL_SECONDS" ]; then
      INJECTED_AGE_MINUTES=$((INJECTED_AGE_SECONDS / 60))
      
      echo "Phase B: PR #$PR_NUMBER injected $INJECTED_AGE_MINUTES minutes ago but not consumed"
      
      # M3 (VAL-M3-001): Derive owner/repo from pending file's cwd for gh pr view -R
      # Without -R, gh pr view fails in non-git directories (e.g., plist WorkingDirectory)
      PR_REPO=""
      if [ -n "$CWD" ] && [ -d "$CWD" ]; then
        PR_REPO=$(git -C "$CWD" remote get-url origin 2>/dev/null \
          | /usr/bin/sed -E 's#^https?://[^/]+/##;s#^git@[^:]+:##;s#\.git$##' || true)
      fi

      # Check if PR is already merged (with -R when repo is derivable)
      if [ -n "$PR_REPO" ]; then
        PR_MERGED=$($PYTHON_BIN -c "
import subprocess, sys
try:
    result = subprocess.run(['gh', 'pr', 'view', '$PR_NUMBER', '-R', '$PR_REPO', '--json', 'state'],
                          capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout)
        print(data.get('state', 'UNKNOWN'))
    else:
        print('UNKNOWN')
except Exception as e:
    print(f'Error checking PR: {e}', file=sys.stderr)
    print('UNKNOWN')
" 2>/dev/null)
      else
        echo "Phase B: WARNING cannot derive owner/repo from cwd='$CWD', marking UNKNOWN"
        PR_MERGED="UNKNOWN"
      fi

      if [ "$PR_MERGED" = "MERGED" ]; then
        # PR is merged, message was consumed or branch cleanup will handle it
        echo "PR #$PR_NUMBER is already merged, cleaning up pending-ci file"
        rm -f "$pending_file"
      elif [ "$PR_MERGED" = "UNKNOWN" ]; then
        # M3 (VAL-M3-001): UNKNOWN = query failed — alert only, do NOT spawn
        # Spawning on UNKNOWN caused false fallback sessions when gh couldn't query
        echo "Phase B: PR #$PR_NUMBER query returned UNKNOWN (gh pr view failed), alerting only — no spawn"
        send_posthog_event "ci_pr_status_unknown" "$PR_NUMBER" "watchdog_phase_b" "gh_pr_view_failed,repo=${PR_REPO:-none}"
      else
        # OPEN or other non-merged state — injection was lost, spawn fallback
        echo "PR #$PR_NUMBER not merged (state: $PR_MERGED), spawning fallback"
        send_posthog_event "ci_injection_lost" "$PR_NUMBER" "watchdog_phase_b" "injected=${INJECTED_AGE_MINUTES}min, not consumed"
        spawn_fallback "$PR_NUMBER" "injection_lost" "$CWD"
        rm -f "$pending_file"
      fi
    fi
    
    # Skip Phase A if injected_at exists
    continue
  fi
  
  # === Phase A: Check if created but not injected ===
  if [ "$CREATED_AGE_SECONDS" -gt "$TTL_SECONDS" ]; then
    AGE_MINUTES=$((CREATED_AGE_SECONDS / 60))
    
    # Send PostHog timeout event
    send_posthog_event "ci_notification_timeout" "$PR_NUMBER" "watchdog_phase_a" "age=${AGE_MINUTES}min, not injected"
    
    # Spawn fallback for unprocessed CI
    echo "Phase A: PR #$PR_NUMBER pending for $AGE_MINUTES minutes, spawning fallback"
    spawn_fallback "$PR_NUMBER" "injection_timeout" "$CWD"
    
    # Delete stale file (idempotent)
    rm -f "$pending_file"
  fi
done

exit 0
