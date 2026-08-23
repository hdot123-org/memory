#!/usr/bin/env bash
# shellcheck disable=SC2034
# write-pending-ci.sh - Write pending-ci-{PR_NUMBER}.json for CI webhook routing
# Usage: ~/.factory/webhook/scripts/write-pending-ci.sh <PR_NUMBER>
#
# M5 event-time rebinding: New schema {pr_number, cwd, created_at}
# - session_id is NO LONGER written (session selection deferred to trigger-ci-droid.sh)
# - trigger-ci-droid.sh does event-time session selection at CI-complete time
#
# Backward compat: old pending files with session_id still work (trigger reads both)
#
# Env-overridable constants (for testing without /tmp copy + sed):
#   LOCKS_DIR     - directory for pending-ci files (default: ~/.factory/webhook/locks)
#   WEBHOOK_BASE  - base webhook directory (default: ~/.factory/webhook)
#   SESSIONS_INDEX - sessions-index.json path (default: ~/.factory/sessions-index.json)

set -euo pipefail

PR_NUMBER="${1:?Usage: write-pending-ci.sh <PR_NUMBER>}"

# === Env-overridable constants (M5: testability) ===
WEBHOOK_BASE="${WEBHOOK_BASE:-${HOME}/.factory/webhook}"
LOCKS_DIR="${LOCKS_DIR:-${WEBHOOK_BASE}/locks}"
SESSIONS_INDEX="${SESSIONS_INDEX:-${HOME}/.factory/sessions-index.json}"

OUTPUT_FILE="$LOCKS_DIR/pending-ci-${PR_NUMBER}.json"

# === PostHog 事件上报 (lib/posthog.sh 统一实现) ===
POSTHOG_EVENT_NAME="ci_webhook_failure"
POSTHOG_DISTINCT_ID="ci-webhook"
# shellcheck source=/dev/null
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/posthog.sh"

# Dynamic Python binary detection
PYTHON_BIN=${PYTHON_BIN:-$(command -v python3)}

# PR_NUMBER must be a positive integer (mirror trigger-ci-droid.sh consumer guard)
if [[ ! "$PR_NUMBER" =~ ^[1-9][0-9]*$ ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Invalid PR_NUMBER='$PR_NUMBER' (must match ^[1-9][0-9]*$)"
  send_posthog_event "ci_invalid_pr_number" "${PR_NUMBER:-empty}" "validation" "format_error"
  exit 1
fi

# Create locks directory if it doesn't exist
mkdir -p "$LOCKS_DIR"

# Detect project root for cwd field
if ! PROJECT_CWD=$(git rev-parse --show-toplevel 2>/dev/null); then
  echo "ERROR: Not in a git repository. Run from a git project." >&2
  exit 1
fi

# Generate ISO 8601 timestamp (UTC)
CREATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# === M5: New schema — write pr_number + cwd + created_at only ===
# Session selection is deferred to trigger-ci-droid.sh (event-time rebinding)
TMP_FILE="${OUTPUT_FILE}.tmp.$$"
"$PYTHON_BIN" -c "
import json, sys
data = {
    'pr_number': sys.argv[1],
    'cwd': sys.argv[2],
    'created_at': sys.argv[3]
}
with open(sys.argv[4], 'w') as f:
    json.dump(data, f)
" "$PR_NUMBER" "$PROJECT_CWD" "$CREATED_AT" "$TMP_FILE"

# Verify tmp file is valid JSON before mv
if ! "$PYTHON_BIN" -c "import json; json.load(open('$TMP_FILE'))" 2>/dev/null; then
  echo "ERROR: Generated pending file is not valid JSON. Aborting." >&2
  rm -f "$TMP_FILE"
  exit 1
fi

mv -f "$TMP_FILE" "$OUTPUT_FILE"

echo "pending-ci-${PR_NUMBER}.json written (atomic, M5 schema): pr_number=$PR_NUMBER, created_at=$CREATED_AT, cwd=$PROJECT_CWD (no session_id — event-time rebinding)"
