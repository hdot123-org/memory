#!/usr/bin/env bash
# write-pending-ci.sh - Write pending-ci-{PR_NUMBER}.json for CI webhook routing
# Usage: ~/.factory/webhook/scripts/write-pending-ci.sh <PR_NUMBER> [SESSION_ID]
#
# If SESSION_ID is provided, uses it directly. Otherwise, finds the orchestrator
# session from sessions-index.json (top-level mission-session with matching cwd).
# Writes session_id, pr_number, and created_at to pending-ci-{PR_NUMBER}.json

set -euo pipefail

PR_NUMBER="${1:?Usage: write-pending-ci.sh <PR_NUMBER> [SESSION_ID]}"
EXPLICIT_SESSION_ID="${2:-}"

LOCKS_DIR="$HOME/.factory/webhook/locks"
OUTPUT_FILE="$LOCKS_DIR/pending-ci-${PR_NUMBER}.json"
SESSIONS_INDEX="$HOME/.factory/sessions-index.json"

# PostHog event reporting function
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

# Create locks directory if it doesn't exist
mkdir -p "$LOCKS_DIR"

# Generate ISO 8601 timestamp
CREATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Dynamic Python binary detection
PYTHON_BIN=${PYTHON_BIN:-$(command -v python3)}

# If explicit session_id provided, use it directly (no git repo needed)
if [ -n "$EXPLICIT_SESSION_ID" ]; then
  SESSION_ID="$EXPLICIT_SESSION_ID"
  echo "Using explicit session_id: $SESSION_ID" >&2
else
  # Detect project root at runtime (not hardcoded)
  if ! PROJECT_CWD=$(git rev-parse --show-toplevel 2>/dev/null); then
    echo "ERROR: Not in a git repository. Run from a git project or provide SESSION_ID explicitly." >&2
    exit 1
  fi
  # Find orchestrator session from sessions-index.json
  # Criteria: cwd matches, callingSessionId is null (top-level), tags contain mission-session
  if [ ! -f "$SESSIONS_INDEX" ]; then
    echo "ERROR: sessions-index.json not found at $SESSIONS_INDEX" >&2
    exit 1
  fi

  SESSION_ID=$("$PYTHON_BIN" -c "
import json, sys

with open('$SESSIONS_INDEX') as f:
    data = json.load(f)

entries = data.get('entries', [])
project_cwd = '$PROJECT_CWD'

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

if not candidates:
    print('', file=sys.stderr)
    print('', file=sys.stdout)
    sys.exit(0)

# Take the most recent by mtime
candidates.sort(key=lambda x: x.get('mtime', 0), reverse=True)
print(candidates[0]['sessionId'])
" 2>/dev/null)

  if [ -z "$SESSION_ID" ]; then
    echo "WARNING: No orchestrator session found in sessions-index.json, falling back to mtime scan" >&2
    echo "DEPRECATION: mtime scan is deprecated and may select wrong session (e.g., worker instead of orchestrator)" >&2
    
    # Fallback: mtime scan (deprecated)
    SESSIONS_DIR="$HOME/.factory/sessions/-Users-busiji-memory"
    LATEST_JSONL=""
    latest_time=0
    for f in "$SESSIONS_DIR"/*.jsonl; do
      [ -f "$f" ] || continue
      t=$(stat -f '%m' "$f" 2>/dev/null || echo 0)
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
  else
    echo "Found orchestrator session from sessions-index.json: $SESSION_ID" >&2
  fi
fi

# Detect project root for cwd field (fallback for spawn_fallback)
PROJECT_CWD=""
if command -v git >/dev/null 2>&1; then
  PROJECT_CWD=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
fi

# Write pending-ci-{PR_NUMBER}.json with created_at timestamp and cwd
cat > "$OUTPUT_FILE" <<EOF
{"session_id":"${SESSION_ID}","pr_number":"${PR_NUMBER}","created_at":"${CREATED_AT}","cwd":"${PROJECT_CWD}"}
EOF

echo "pending-ci-${PR_NUMBER}.json written: session_id=$SESSION_ID, pr_number=$PR_NUMBER, created_at=$CREATED_AT, cwd=$PROJECT_CWD"
