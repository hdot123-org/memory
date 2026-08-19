#!/usr/bin/env bash
# Auto-merge triage script (INFRA-416)
# Classifies PRs by mergeable state and mergeStateStatus.
#
# Input:  JSON array of PRs via stdin (gh pr view/list --json number,mergeable,mergeStateStatus)
# Output: JSON with 4 categories: mergeable, behind, conflicting, unknown
# Exit:   always 0 (triage never fails workflow)
#
# Modes:
#   default         classify stdin, emit full JSON
#   --get-action N  classify stdin, emit the single action for PR number N
#                   (merge|update-branch|notify|skip; exit 0; empty input
#                   also emits skip — triage must never fail the workflow)
#
# Classification precedence (one PR falls into exactly one category):
#   CONFLICTING          -> conflicting  (action: notify)
#   mergeStateStatus=BEHIND -> behind    (action: update-branch)
#   mergeable=MERGEABLE  -> mergeable    (action: merge)
#   everything else      -> unknown      (action: skip)
# Note: a BEHIND PR with conflicts reports mergeable=CONFLICTING; DIRTY
# wins over BEHIND so we never blind-merge a conflicting PR.

set -euo pipefail

GET_ACTION_PR=""

if [[ "${1:-}" == "--get-action" ]]; then
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 [--get-action PR_NUMBER]" >&2
    echo '{"mergeable":[],"behind":[],"conflicting":[],"unknown":[]}'
    exit 0
  fi
  GET_ACTION_PR="$2"
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--get-action PR_NUMBER]" >&2
  echo '{"mergeable":[],"behind":[],"conflicting":[],"unknown":[]}'
  exit 0
fi

EMPTY_RESULT='{"mergeable":[],"behind":[],"conflicting":[],"unknown":[]}'

# Classify PRs and add action fields.
# `jq -e` would swallow the classification on unexpected shapes; plain jq
# with a fallback keeps triage total (empty result on any malformed input).
classify() {
  jq '
    def action_for(cat):
      if cat == "mergeable" then "merge"
      elif cat == "behind" then "update-branch"
      elif cat == "conflicting" then "notify"
      else empty
      end;
    {
      conflicting: [.[] | select(.mergeable == "CONFLICTING")],
      behind: [.[] | select(.mergeable != "CONFLICTING" and .mergeStateStatus == "BEHIND")],
      mergeable: [.[] | select(.mergeable == "MERGEABLE" and .mergeStateStatus != "BEHIND")],
      unknown: [.[] | select(
        (.mergeable == "UNKNOWN") or
        (.mergeable != "MERGEABLE" and .mergeable != "CONFLICTING" and .mergeStateStatus != "BEHIND")
      )]
    }
    | to_entries
    | map(. as $entry | .value = [.value[] | . + {action: (action_for($entry.key) // "skip")}])
    | from_entries
  ' 2>/dev/null || echo "$EMPTY_RESULT"
}

# Read JSON from stdin
input=$(cat)

# Handle empty or invalid JSON
if ! echo "$input" | jq empty 2>/dev/null; then
  echo "Invalid or empty JSON input, returning empty triage result" >&2
  if [[ -n "$GET_ACTION_PR" ]]; then
    echo "skip"
  else
    echo "$EMPTY_RESULT"
  fi
  exit 0
fi

TRIAGE_RESULT=$(echo "$input" | classify)

if [[ -n "$GET_ACTION_PR" ]]; then
  echo "$TRIAGE_RESULT" | jq -r --argjson pr "$GET_ACTION_PR" '
    if ([.behind[] | select(.number == $pr)] | length) > 0 then .behind[] | select(.number == $pr) | .action
    elif ([.conflicting[] | select(.number == $pr)] | length) > 0 then .conflicting[] | select(.number == $pr) | .action
    elif ([.mergeable[] | select(.number == $pr)] | length) > 0 then .mergeable[] | select(.number == $pr) | .action
    else "skip"
    end
  '
  exit 0
fi

echo "$TRIAGE_RESULT"
