#!/usr/bin/env bash
# write-pending-ci.sh - Write pending-ci.json for CI webhook routing
# Usage: scripts/write-pending-ci.sh <PR_NUMBER>
#
# Automatically extracts session_id from the latest .jsonl session file
# and writes it together with the PR number to pending-ci.json so the
# ci-complete webhook can route back to the current session.

set -euo pipefail

PR_NUMBER="${1:?Usage: write-pending-ci.sh <PR_NUMBER>}"

SESSIONS_DIR="$HOME/.factory/sessions/-Users-busiji-memory"
LOCKS_DIR="$HOME/.factory/webhook/locks"
OUTPUT_FILE="$LOCKS_DIR/pending-ci.json"

# Create locks directory if it doesn't exist
mkdir -p "$LOCKS_DIR"

# Extract session_id from the latest .jsonl file (pipe-free to avoid SIGPIPE with pipefail)
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

# Write pending-ci.json
cat > "$OUTPUT_FILE" <<EOF
{"session_id":"${SESSION_ID}","pr_number":"${PR_NUMBER}"}
EOF

echo "pending-ci.json written: session_id=$SESSION_ID, pr_number=$PR_NUMBER"
