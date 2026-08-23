#!/usr/bin/env bash
# lib/posthog.sh — Unified PostHog event reporting for webhook scripts
# Source this file instead of defining send_posthog_event inline.
#
# Required caller setup (before sourcing or before first call):
#   POSTHOG_EVENT_NAME   — PostHog event name (e.g. "ci_webhook_failure")
#   POSTHOG_DISTINCT_ID  — distinct_id convention (e.g. "ci-webhook")
#
# Optional:
#   POSTHOG_DRY_RUN=1    — Print event JSON to stdout, do NOT send
#   POSTHOG_API_KEY      — API key from environment (skip if empty/unset)
#   PYTHON_BIN            — python3 binary path (auto-detected)
#   LOG_FILE              — Log output destination (default: /dev/null for curl)
#
# Usage:
#   send_posthog_event <error_type> <identifier> <stage> <detail>
#
# JSON is constructed via python3 to prevent shell injection.
# shellcheck disable=SC2034,SC2154

# Guard against double-sourcing
if [[ -n "${_POSTHOG_SH_LOADED:-}" ]]; then
    # shellcheck disable=SC2317
    return 0 2>/dev/null || true
fi
_POSTHOG_SH_LOADED=1

# Dynamic Python binary detection (macOS: /opt/homebrew/bin/python3, Linux: python3)
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 2>/dev/null || echo /opt/homebrew/bin/python3)}"

send_posthog_event() {
    local event_type="${1:-}"
    local identifier="${2:-}"
    local stage="${3:-}"
    local detail="${4:-}"

    # POSTHOG_DRY_RUN=1: print only, do not send (test isolation guard)
    if [[ "${POSTHOG_DRY_RUN:-0}" == "1" ]]; then
        echo "[POSTHOG_DRY_RUN] event=${POSTHOG_EVENT_NAME:-unset} distinct_id=${POSTHOG_DISTINCT_ID:-unset} error_type=$event_type identifier=$identifier stage=$stage detail=$detail"
        return 0
    fi

    # M4: PostHog key from environment; skip if not set
    if [[ -z "${POSTHOG_API_KEY:-}" ]]; then
        echo "[POSTHOG] Skipping event (no POSTHOG_API_KEY): ${event_type:-unknown}" >&2
        return 0
    fi

    # Validate required caller configuration
    if [[ -z "${POSTHOG_EVENT_NAME:-}" ]]; then
        echo "[POSTHOG] ERROR: POSTHOG_EVENT_NAME not set by caller, skipping event" >&2
        return 0
    fi
    if [[ -z "${POSTHOG_DISTINCT_ID:-}" ]]; then
        echo "[POSTHOG] ERROR: POSTHOG_DISTINCT_ID not set by caller, skipping event" >&2
        return 0
    fi

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Parameterized JSON construction via python3 (no shell string interpolation)
    local payload
    payload=$("${PYTHON_BIN}" -c "
import json, sys
print(json.dumps({
    'api_key': sys.argv[1],
    'batch': [{
        'event': sys.argv[2],
        'properties': {
            'error_type': sys.argv[3],
            'identifier': sys.argv[4],
            'stage': sys.argv[5],
            'detail': sys.argv[6],
            'distinct_id': sys.argv[7]
        },
        'timestamp': sys.argv[8]
    }]
}))" "$POSTHOG_API_KEY" "$POSTHOG_EVENT_NAME" "$event_type" "$identifier" "$stage" "$detail" "$POSTHOG_DISTINCT_ID" "$timestamp" 2>/dev/null)

    if [[ -z "$payload" ]]; then
        echo "[POSTHOG] ERROR: Failed to construct JSON payload for event: $event_type" >&2
        return 1
    fi

    curl -s -X POST "https://us.posthog.com/batch/" \
        -H "Content-Type: application/json" \
        -d "$payload" >> "${LOG_FILE:-/dev/null}" 2>&1 || true
}

# Variant: send_posthog_event_named — per-call event name override
# Usage: send_posthog_event_named <event_name> <error_type> <identifier> <stage> <detail>
# Use when a script sends multiple events with different PostHog event names
# (e.g., local_branch_cleanup.sh sends local_branch_cherry_failed, local_branch_orphan_content, etc.)
send_posthog_event_named() {
    local event_name="${1:-}"
    shift
    local saved_event_name="${POSTHOG_EVENT_NAME:-}"
    POSTHOG_EVENT_NAME="$event_name"
    send_posthog_event "$@"
    POSTHOG_EVENT_NAME="$saved_event_name"
}

# Variant: send_posthog_event_kv — accepts arbitrary key=value pairs as properties
# Usage: send_posthog_event_kv <event_type> key1=val1 key2=val2 ...
# Values must be valid JSON fragments (strings need quotes, numbers don't).
# Use this when properties are dynamic/variable rather than the standard 4 fields.
send_posthog_event_kv() {
    local event_type="${1:-}"
    shift
    # Remaining args are key=value pairs

    # POSTHOG_DRY_RUN=1: print only, do not send
    if [[ "${POSTHOG_DRY_RUN:-0}" == "1" ]]; then
        echo "[POSTHOG_DRY_RUN] event=${POSTHOG_EVENT_NAME:-unset} distinct_id=${POSTHOG_DISTINCT_ID:-unset} error_type=$event_type props=$*"
        return 0
    fi

    # M4: PostHog key from environment; skip if not set
    if [[ -z "${POSTHOG_API_KEY:-}" ]]; then
        echo "[POSTHOG] Skipping event (no POSTHOG_API_KEY): ${event_type:-unknown}" >&2
        return 0
    fi

    # Validate required caller configuration
    if [[ -z "${POSTHOG_EVENT_NAME:-}" ]]; then
        echo "[POSTHOG] ERROR: POSTHOG_EVENT_NAME not set by caller, skipping event" >&2
        return 0
    fi
    if [[ -z "${POSTHOG_DISTINCT_ID:-}" ]]; then
        echo "[POSTHOG] ERROR: POSTHOG_DISTINCT_ID not set by caller, skipping event" >&2
        return 0
    fi

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Build properties JSON from key=value pairs via python3 (safe construction)
    local payload
    payload=$("${PYTHON_BIN}" -c "
import json, sys
event_type = sys.argv[1]
event_name = sys.argv[2]
distinct_id = sys.argv[3]
api_key = sys.argv[4]
timestamp = sys.argv[5]
# Remaining args are key=value pairs
props = {}
for arg in sys.argv[6:]:
    if '=' in arg:
        k, v = arg.split('=', 1)
        # Try to parse as JSON (handles numbers, booleans, quoted strings)
        try:
            props[k] = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            props[k] = v
print(json.dumps({
    'api_key': api_key,
    'batch': [{
        'event': event_name,
        'properties': dict(props, distinct_id=distinct_id),
        'timestamp': timestamp,
        'error_type': event_type
    }]
}))
" "$event_type" "$POSTHOG_EVENT_NAME" "$POSTHOG_DISTINCT_ID" "$POSTHOG_API_KEY" "$timestamp" "$@" 2>/dev/null)

    if [[ -z "$payload" ]]; then
        echo "[POSTHOG] ERROR: Failed to construct JSON payload for event: $event_type" >&2
        return 1
    fi

    curl -s -X POST "https://us.posthog.com/batch/" \
        -H "Content-Type: application/json" \
        -d "$payload" >> "${LOG_FILE:-/dev/null}" 2>&1 || true
}
