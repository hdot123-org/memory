#!/usr/bin/env bash
# extract_anchor.sh - Extract linear-linkback anchor from GitHub issue/PR comments
# Wrapper for scripts/extract_anchor.py (Python implementation)
#
# Usage: extract_anchor.sh <issue|pr> <number> <repo>
# Returns: INFRA-xxx identifier or empty string
# Exit code: 0 on success (even if no anchor found), 1 on error
#
# Architecture: §3.1 镜像锚点（Tier2b anchor 正则限定 linkback 评论内第一处）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Validate arguments
if [ $# -ne 3 ]; then
    echo "Usage: $0 <issue|pr> <number> <repo>" >&2
    exit 1
fi

TARGET_TYPE="$1"
NUMBER="$2"
REPO="$3"

# Call Python implementation
exec /opt/homebrew/bin/python3 "$REPO_ROOT/scripts/extract_anchor.py" "$TARGET_TYPE" "$NUMBER" "$REPO"
