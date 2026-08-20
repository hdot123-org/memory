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

# === Spawn fallback for lost messages ===
spawn_fallback() {
  local pr_num="$1"
  local ci_status="$2"
  local repo_path="$3"
  local lock_file="$LOCKS_DIR/ci-fallback-${pr_num}.lock"

  # Create fallback lock to prevent duplicate spawns (idempotent)
  # Only spawn if lock doesn't exist or is older than 1 hour
  if [ -f "$lock_file" ]; then
    local lock_age=$(( $(date +%s) - $(stat -f '%m' "$lock_file" 2>/dev/null || stat -c '%Y' "$lock_file" 2>/dev/null || echo 0) ))
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
  local spawn_cmd="$HOME/.local/bin/droid --new-session --tag ci-fallback-$pr_num --command 'CI webhook injection lost for PR #$pr_num (status: $ci_status). Repository: $repo_path. Please verify PR merge status and perform branch cleanup if needed: check if PR #$pr_num is merged, if so delete the remote branch and update local main branch. If not merged, investigate why.'"

  # Dry-run guard: prevent real droid sessions during testing
  if [ "${ECHO_DROID:-0}" = "1" ]; then
    echo "[ECHO_DROID] Would spawn: $spawn_cmd"
    echo "Fallback session dry-run complete (ECHO_DROID=1)"
    return 0
  fi

  echo "Executing: $spawn_cmd"

  # Spawn new session in background
  nohup bash -c "$spawn_cmd" > /dev/null 2>&1 &

  echo "Fallback session spawned successfully"
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
      
      # Check if PR is already merged
      PR_MERGED=$($PYTHON_BIN -c "
import subprocess, sys
try:
    result = subprocess.run(['gh', 'pr', 'view', '$PR_NUMBER', '--json', 'state'], 
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
      
      if [ "$PR_MERGED" = "MERGED" ]; then
        # PR is merged, message was consumed or branch cleanup will handle it
        echo "PR #$PR_NUMBER is already merged, cleaning up pending-ci file"
        rm -f "$pending_file"
      else
        # PR not merged, injection was lost, spawn fallback
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
