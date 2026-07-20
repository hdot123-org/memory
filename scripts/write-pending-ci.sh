#!/usr/bin/env bash
# write-pending-ci.sh - Write pending-ci.json for CI webhook routing
# Usage: scripts/write-pending-ci.sh <PR_NUMBER> [SESSION_ID]
#
# If SESSION_ID is provided, uses it directly. Otherwise, finds the orchestrator
# session from sessions-index.json (top-level mission-session with matching cwd).
# Writes session_id, pr_number, and created_at to pending-ci.json.

set -euo pipefail

PR_NUMBER="${1:?Usage: write-pending-ci.sh <PR_NUMBER> [SESSION_ID]}"
EXPLICIT_SESSION_ID="${2:-}"

LOCKS_DIR="$HOME/.factory/webhook/locks"
OUTPUT_FILE="$LOCKS_DIR/pending-ci.json"
SESSIONS_INDEX="$HOME/.factory/sessions-index.json"
PROJECT_CWD="/Users/busiji/memory"

# Create locks directory if it doesn't exist
mkdir -p "$LOCKS_DIR"

# Generate ISO 8601 timestamp
CREATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# If explicit session_id provided, use it directly
if [ -n "$EXPLICIT_SESSION_ID" ]; then
  SESSION_ID="$EXPLICIT_SESSION_ID"
  echo "Using explicit session_id: $SESSION_ID" >&2
else
  # Find orchestrator session from sessions-index.json
  # Criteria: cwd matches, callingSessionId is null (top-level), tags contain mission-session
  if [ ! -f "$SESSIONS_INDEX" ]; then
    echo "ERROR: sessions-index.json not found at $SESSIONS_INDEX" >&2
    exit 1
  fi

  SESSION_ID=$(/opt/homebrew/bin/python3 -c "
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
    if e.get('callingSessionId') is not None:
        continue  # Skip worker/subagent sessions
    tags = e.get('tags', [])
    tag_names = [t.get('name', '') for t in tags] if isinstance(tags, list) else []
    if 'mission-session' not in tag_names:
        continue
    candidates.append(e)

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

# Write pending-ci.json with created_at timestamp
cat > "$OUTPUT_FILE" <<EOF
{"session_id":"${SESSION_ID}","pr_number":"${PR_NUMBER}","created_at":"${CREATED_AT}"}
EOF

echo "pending-ci.json written: session_id=$SESSION_ID, pr_number=$PR_NUMBER, created_at=$CREATED_AT"
