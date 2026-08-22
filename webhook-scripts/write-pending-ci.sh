#!/usr/bin/env bash
# write-pending-ci.sh - Write pending-ci-{PR_NUMBER}.json for CI webhook routing
# Usage: ~/.factory/webhook/scripts/write-pending-ci.sh <PR_NUMBER> [SESSION_ID]
#
# If SESSION_ID is provided, uses it directly (with probe validation).
# Otherwise, finds the orchestrator session from sessions-index.json (top-level
# mission-session with matching cwd). Writes pr_number and created_at to
# pending-ci-{PR_NUMBER}.json
#
# M3 hardening:
# - Atomic write via tmp+mv (prevents readers from seeing partial file)
# - Session probe before write: GET /sessions/{id}, 404 -> next mtime candidate
# - All candidates dead -> fail-fast exit (no dead-session pending written)
# - Deprecated mtime scan preserved with PostHog ci_write_deprecated_scan event

set -euo pipefail

PR_NUMBER="${1:?Usage: write-pending-ci.sh <PR_NUMBER> [SESSION_ID]}"
EXPLICIT_SESSION_ID="${2:-}"

LOCKS_DIR="$HOME/.factory/webhook/locks"
OUTPUT_FILE="$LOCKS_DIR/pending-ci-${PR_NUMBER}.json"
SESSIONS_INDEX="$HOME/.factory/sessions-index.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PostHog event reporting function
send_posthog_event() {
  # POSTHOG_DRY_RUN=1: print only, do not send
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
  # Skip if no API key configured
  if [ -z "${POSTHOG_API_KEY:-}" ]; then
    echo "[POSTHOG] Skipping event (no POSTHOG_API_KEY): $event_type" >&2
    return 0
  fi
  curl -s -X POST "https://us.posthog.com/batch/" \
    -H "Content-Type: application/json" \
    -d "{
      \"api_key\": \"${POSTHOG_API_KEY}\",
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

# Probe session liveness: GET /api/v0/sessions/{id}
# Returns 0 if session exists (HTTP 2xx), 1 if 404/not found, 2 if unreachable
# Usage: probe_session <session_id> <factory_token>
probe_session() {
  local sid="$1"
  local token="$2"
  local api_base="${FACTORY_API_BASE:-https://api.factory.ai/api/v0}"
  local probe_url="${api_base}/sessions/${sid}"

  local probe_response
  probe_response=$(curl -s -w "\n%{http_code}" -X GET "$probe_url" \
    -H "Authorization: Bearer $token" \
    --connect-timeout 10 --max-time 15 2>/dev/null) || probe_response=$'\n000'

  local probe_code
  probe_code=$(echo "$probe_response" | tail -n1)

  if [[ "$probe_code" =~ ^2 ]]; then
    return 0  # Session alive
  elif [ "$probe_code" = "404" ]; then
    return 1  # Session not found
  else
    return 2  # Unreachable / other error
  fi
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

# Get Factory token from 1Password MCP (reuses lib/op-mcp.sh pattern from trigger-ci-droid.sh)
get_factory_token() {
  if [ -n "${FACTORY_TOKEN:-}" ]; then
    echo "$FACTORY_TOKEN"
    return 0
  fi

  if [ -f "${SCRIPT_DIR}/lib/op-mcp.sh" ]; then
    # Define 1Password item reference (same as trigger-ci-droid.sh)
    local OP_ITEM_ID="d2da72sb27xfvekt6sbqag36zq"
    local OP_FIELD_LABEL="api"
    local OP_VAULT_SEVER="ozqqpvh5yvvxvyu64npq62a3ti"
    
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/lib/op-mcp.sh"
    local token
    token=$(op_get_field "$OP_VAULT_SEVER" "$OP_ITEM_ID" "$OP_FIELD_LABEL" 2>/dev/null || true)
    if [ -n "$token" ] && [[ "$token" =~ ^fk- ]]; then
      echo "$token"
      return 0
    fi
  fi
  return 1
}

# Create locks directory if it doesn't exist
mkdir -p "$LOCKS_DIR"

# Generate ISO 8601 timestamp
CREATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Dynamic Python binary detection
PYTHON_BIN=${PYTHON_BIN:-$(command -v python3)}

# Detect project root for cwd field (fallback for spawn_fallback)
PROJECT_CWD=""
if command -v git >/dev/null 2>&1; then
  PROJECT_CWD=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
fi

# === Session selection with probe validation ===
FACTORY_TOKEN="${FACTORY_TOKEN:-}"
if [ -n "$EXPLICIT_SESSION_ID" ]; then
  # Explicit session_id provided: probe it, fail-fast if dead
  SESSION_ID="$EXPLICIT_SESSION_ID"
  echo "Using explicit session_id: $SESSION_ID" >&2

  # Probe explicit session
  FACTORY_TOKEN=$(get_factory_token) || true
  if [ -n "$FACTORY_TOKEN" ]; then
    if probe_session "$SESSION_ID" "$FACTORY_TOKEN"; then
      echo "Probe OK: session $SESSION_ID is alive" >&2
    else
      PROBE_EXIT=$?
      if [ "$PROBE_EXIT" = "1" ]; then
        echo "ERROR: Explicit session $SESSION_ID does not exist (404). Refusing to write dead-session pending." >&2
        send_posthog_event "ci_write_probe_fail" "$PR_NUMBER" "write_probe" "explicit_session_404:$SESSION_ID"
        exit 1
      elif [ "$PROBE_EXIT" = "2" ]; then
        echo "ERROR: Probe unreachable for session $SESSION_ID (network/API error). Refusing to write unvalidated pending (fail-fast)." >&2
        send_posthog_event "ci_write_probe_fail" "$PR_NUMBER" "write_probe" "explicit_session_unreachable:$SESSION_ID"
        exit 1
      fi
    fi
  else
    echo "ERROR: Factory token unavailable. Cannot probe explicit session $SESSION_ID. Refusing to write unvalidated pending (fail-fast)." >&2
    send_posthog_event "ci_write_probe_fail" "$PR_NUMBER" "write_probe" "token_unavailable_for_explicit:$SESSION_ID"
    exit 1
  fi
else
  # No explicit session_id: detect project root and find from sessions-index
  if ! PROJECT_CWD_CHECK=$(git rev-parse --show-toplevel 2>/dev/null); then
    echo "ERROR: Not in a git repository. Run from a git project or provide SESSION_ID explicitly." >&2
    exit 1
  fi

  if [ ! -f "$SESSIONS_INDEX" ]; then
    echo "ERROR: sessions-index.json not found at $SESSIONS_INDEX" >&2
    exit 1
  fi

  # Get Factory token for probing
  FACTORY_TOKEN=$(get_factory_token) || true

  # Find orchestrator session candidates from sessions-index.json
  # Returns session IDs sorted by mtime descending (most recent first)
  CANDIDATE_SESSIONS=$("$PYTHON_BIN" -c "
import json, sys

with open('$SESSIONS_INDEX') as f:
    data = json.load(f)

entries = data.get('entries', [])
project_cwd = '$PROJECT_CWD_CHECK'

# Filter to top-level mission sessions with matching cwd
candidates = []
for e in entries:
    if e.get('cwd') != project_cwd:
        continue
    if 'callingSessionId' in e and e['callingSessionId'] is not None:
        continue  # Skip worker/subagent sessions
    tags = e.get('tags', [])
    tag_names = [t.get('name', '') for t in tags] if isinstance(tags, list) else []
    if 'mission-session' not in tag_names:
        continue
    # Check for orchestrator role in metadata
    for t in tags:
        if t.get('name') == 'mission-session':
            meta = t.get('metadata', {})
            if meta.get('role') == 'orchestrator':
                candidates.append(e)
                break

# Sort by mtime descending
candidates.sort(key=lambda x: x.get('mtime', 0), reverse=True)
for c in candidates:
    print(c['sessionId'])
" 2>/dev/null)

  if [ -n "$CANDIDATE_SESSIONS" ]; then
    # Probe candidates in mtime order, use first alive one
    SESSION_ID=""
    while IFS= read -r candidate; do
      [ -z "$candidate" ] && continue
      if [ -n "$FACTORY_TOKEN" ]; then
        if probe_session "$candidate" "$FACTORY_TOKEN"; then
          SESSION_ID="$candidate"
          echo "Probe OK: session $SESSION_ID is alive" >&2
          break
        else
          PROBE_EXIT=$?
          if [ "$PROBE_EXIT" = "1" ]; then
            echo "Session $candidate is dead (404), trying next candidate..." >&2
          else
            echo "Session $candidate probe unreachable, trying next candidate..." >&2
          fi
        fi
      else
        # No token: take first candidate (can't probe)
        SESSION_ID="$candidate"
        echo "WARN: Factory token unavailable, using first candidate without probe: $SESSION_ID" >&2
        break
      fi
    done <<< "$CANDIDATE_SESSIONS"

    if [ -z "$SESSION_ID" ]; then
      echo "ERROR: All candidate sessions are dead. Refusing to write dead-session pending (fail-fast)." >&2
      send_posthog_event "ci_write_all_sessions_dead" "$PR_NUMBER" "write_probe" "all_candidates_404"
      exit 1
    fi

    echo "Found orchestrator session from sessions-index.json: $SESSION_ID" >&2
  else
    # Fallback: mtime scan (deprecated)
    echo "WARNING: No orchestrator session found in sessions-index.json, falling back to mtime scan" >&2
    echo "DEPRECATION: mtime scan is deprecated and may select wrong session (e.g., worker instead of orchestrator)" >&2
    send_posthog_event "ci_write_deprecated_scan" "$PR_NUMBER" "session_select" "fallback_to_mtime_scan"

    SESSIONS_DIR="$HOME/.factory/sessions/-Users-busiji-memory"
    LATEST_JSONL=""
    latest_time=0
    for f in "$SESSIONS_DIR"/*.jsonl; do
      [ -f "$f" ] || continue
      t=$(_portable_mtime "$f")
      if [ "$t" -gt "$latest_time" ]; then
        latest_time=$t
        LATEST_JSONL="$f"
      fi
    done
    if [ -z "$LATEST_JSONL" ]; then
      echo "ERROR: No .jsonl session files found in $SESSIONS_DIR" >&2
      exit 1
    fi
    SESSION_ID=$(basename "$LATEST_JSONL" .jsonl)

    # Probe the mtime-scanned session if token available
    # BLK-M3-R1-1 fix: capture rc BEFORE branching.
    # Old pattern: `if ! probe_session ...; then PROBE_EXIT=$?` captures the negated
    # rc (always 0) — dead code.
    # Use `cmd || PROBE_EXIT=$?` to capture real rc without triggering set -e exit.
    if [ -n "$FACTORY_TOKEN" ]; then
      PROBE_EXIT=0
      probe_session "$SESSION_ID" "$FACTORY_TOKEN" || PROBE_EXIT=$?
      if [ "$PROBE_EXIT" = "0" ]; then
        echo "Probe OK: mtime-scanned session $SESSION_ID is alive" >&2
      elif [ "$PROBE_EXIT" = "1" ]; then
        echo "ERROR: mtime-scanned session $SESSION_ID is dead (404). No candidates left. Refusing to write dead-session pending." >&2
        send_posthog_event "ci_write_all_sessions_dead" "$PR_NUMBER" "write_probe" "mtime_scan_session_404"
        exit 1
      else
        echo "WARN: Probe unreachable for mtime-scanned session $SESSION_ID. Proceeding with caution." >&2
        send_posthog_event "ci_write_probe_unreachable" "$PR_NUMBER" "write_probe" "mtime_scan_unreachable:$SESSION_ID"
      fi
    fi
  fi
fi

# Use the PROJECT_CWD from earlier detection (or empty if not in git)
# Re-detect for the JSON payload field (in case we were in explicit-session mode)
if [ -z "${PROJECT_CWD:-}" ] && command -v git >/dev/null 2>&1; then
  PROJECT_CWD=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
fi

# === Atomic write: tmp+mv ===
TMP_FILE="${OUTPUT_FILE}.tmp.$$"
cat > "$TMP_FILE" <<EOF
{"session_id":"${SESSION_ID}","pr_number":"${PR_NUMBER}","created_at":"${CREATED_AT}","cwd":"${PROJECT_CWD}"}
EOF

# Verify tmp file is valid JSON before mv
if ! "$PYTHON_BIN" -c "import json; json.load(open('$TMP_FILE'))" 2>/dev/null; then
  echo "ERROR: Generated pending file is not valid JSON. Aborting." >&2
  rm -f "$TMP_FILE"
  exit 1
fi

mv -f "$TMP_FILE" "$OUTPUT_FILE"

echo "pending-ci-${PR_NUMBER}.json written (atomic): session_id=$SESSION_ID, pr_number=$PR_NUMBER, created_at=$CREATED_AT, cwd=$PROJECT_CWD"
