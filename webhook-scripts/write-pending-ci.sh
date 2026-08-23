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

# === Env-overridable constants (M5: testability) ===
WEBHOOK_BASE="${WEBHOOK_BASE:-${HOME}/.factory/webhook}"
LOCKS_DIR="${LOCKS_DIR:-${WEBHOOK_BASE}/locks}"
SESSIONS_INDEX="${SESSIONS_INDEX:-${HOME}/.factory/sessions-index.json}"

# === PostHog 事件上报 (lib/posthog.sh 统一实现) ===
POSTHOG_EVENT_NAME="ci_webhook_failure"
POSTHOG_DISTINCT_ID="ci-webhook"
# shellcheck source=/dev/null
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/posthog.sh"

# Dynamic Python binary detection
PYTHON_BIN=${PYTHON_BIN:-$(command -v python3)}

# === F1: 选项解析框架 (--source session|scanner, --context <意图>) ===
SOURCE=""
CONTEXT=""
SOURCE_PROVIDED=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE="${2:-}"
      SOURCE_PROVIDED=true
      shift 2
      ;;
    --context)
      CONTEXT="${2:-}"
      shift 2
      ;;
    -*)
      echo "ERROR: Unknown option $1" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

PR_NUMBER="${1:?Usage: write-pending-ci.sh [--source session|scanner] [--context <意图>] <PR_NUMBER>}"

OUTPUT_FILE="$LOCKS_DIR/pending-ci-${PR_NUMBER}.json"

# source 合法性校验（fail-fast 先于写入，VAL-REG-004）
# 空字符串视为非法（VAL-REG-004: --source "" 必须 fail-fast）
if [[ "$SOURCE_PROVIDED" == "true" ]]; then
  case "$SOURCE" in
    session|scanner) ;;
    *)
      echo "ERROR: Invalid source '$SOURCE' (must be 'session' or 'scanner')" >&2
      exit 1
      ;;
  esac
fi

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

# === F1: Schema — M5 base fields + optional source/context ===
# Session selection is deferred to trigger-ci-droid.sh (event-time rebinding)
# VAL-REG-001/002/003: source/context 仅当显式传入时写入（旧式调用缺 source 键）
TMP_FILE="${OUTPUT_FILE}.tmp.$$"
"$PYTHON_BIN" -c "
import json, sys
data = {
    'pr_number': sys.argv[1],
    'cwd': sys.argv[2],
    'created_at': sys.argv[3]
}
# 仅当 --source 显式传入时写入（VAL-REG-002：旧式调用无 source 键）
if sys.argv[4]:  # SOURCE
    data['source'] = sys.argv[4]
if sys.argv[5]:  # CONTEXT
    data['context'] = sys.argv[5]
with open(sys.argv[6], 'w') as f:
    json.dump(data, f)
" "$PR_NUMBER" "$PROJECT_CWD" "$CREATED_AT" "$SOURCE" "$CONTEXT" "$TMP_FILE"

# Verify tmp file is valid JSON before mv
if ! "$PYTHON_BIN" -c "import json; json.load(open('$TMP_FILE'))" 2>/dev/null; then
  echo "ERROR: Generated pending file is not valid JSON. Aborting." >&2
  rm -f "$TMP_FILE"
  exit 1
fi

mv -f "$TMP_FILE" "$OUTPUT_FILE"

if [[ -n "$SOURCE" ]]; then
  echo "pending-ci-${PR_NUMBER}.json written (atomic, M5+F1 schema): pr_number=$PR_NUMBER, source=$SOURCE, created_at=$CREATED_AT, cwd=$PROJECT_CWD"
else
  echo "pending-ci-${PR_NUMBER}.json written (atomic, M5 schema): pr_number=$PR_NUMBER, created_at=$CREATED_AT, cwd=$PROJECT_CWD (no session_id — event-time rebinding)"
fi
