#!/usr/bin/env bash
# shellcheck disable=SC2034
# CI failed webhook handler
set -uo pipefail

LOG_DIR="/Users/busiji/.factory/webhook/logs"
LOG_FILE="$LOG_DIR/ci-failed-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"
}

# === PostHog 事件上报 (lib/posthog.sh 统一实现) ===
POSTHOG_EVENT_NAME="ci_failed_mcp_failure"
POSTHOG_DISTINCT_ID="ci-webhook"
# shellcheck source=/dev/null
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/posthog.sh"

log "CI failed hook triggered: pipeline=$CI_PIPELINE_ID project=$CI_PROJECT branch=$CI_BRANCH sha=$CI_SHA"

# Write comment to Linear issue about CI failure (triggers Droid via Linear webhook)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/op-mcp.sh"
LINEAR_API_KEY=$(op_get_field "$OP_VAULT_SEVER" "elgcm2nzfza2hjb3yffpkijj7y" "凭据" || true)

if [ -z "$LINEAR_API_KEY" ]; then
    log "ERROR: Linear API key not found"
    send_posthog_event "mcp_key_retrieval_failed" "${CI_PIPELINE_ID:-unknown}" "auth" "MCP: op_get_field returned empty"
    exit 1
fi

# Get issue ID from Linear
ISSUE_ID=$(curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ issue(id: \"f023acdf-71d9-4121-8edf-a9ed8c7c05f7\") { id } }"}' 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('issue',{}).get('id',''))" 2>/dev/null)

if [ -z "$ISSUE_ID" ]; then
    log "ERROR: Could not find Linear issue"
    exit 1
fi

log "Found Linear issue ID: $ISSUE_ID"

# Write comment to Linear (this triggers the Linear webhook -> trigger-droid.sh -> Droid)
COMMENT_BODY="⚠️ CI 流水线失败，请修复。\n\nPipeline: $CI_PIPELINE_ID\n分支: $CI_BRANCH\nMR: https://gitlab.exa.edu.kg/infra/memory-core/-/merge_requests/41"

curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"mutation { commentCreate(input: { issueId: \\\"$ISSUE_ID\\\", body: \\\"$COMMENT_BODY\\\" }) { success } }\"}" >> "$LOG_FILE" 2>&1

log "Comment posted to Linear issue INFRA-5"

log "CI failed hook completed"
