#!/usr/bin/env bash
# Auto-merge triage script
# Classifies PRs by mergeable state and mergeStateStatus
# Input: JSON array of PRs via stdin
# Output: JSON with 4 categories: mergeable, behind, conflicting, unknown
# Exit: always 0 (triage never fails workflow)

set -euo pipefail

# Read JSON from stdin
input=$(cat)

# Handle empty or invalid JSON
if ! echo "$input" | jq empty 2>/dev/null; then
    echo '{"mergeable":[],"behind":[],"conflicting":[],"unknown":[]}'
    exit 0
fi

# Classify PRs and add action fields
echo "$input" | jq '
  {
    mergeable: [.[] | select(.mergeable == "MERGEABLE" and .mergeStateStatus != "BEHIND") | . + {action: "merge"}],
    behind: [.[] | select(.mergeStateStatus == "BEHIND") | . + {action: "update-branch"}],
    conflicting: [.[] | select(.mergeable == "CONFLICTING") | . + {action: "notify"}],
    unknown: [.[] | select(.mergeable == "UNKNOWN" or (.mergeable != "MERGEABLE" and .mergeable != "CONFLICTING" and .mergeStateStatus != "BEHIND"))]
  }
' 2>/dev/null || echo '{"mergeable":[],"behind":[],"conflicting":[],"unknown":[]}'
