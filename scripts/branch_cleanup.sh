#!/usr/bin/env bash
# Branch cleanup: delete orphan branches with PR protection
# Usage:
#   bash scripts/branch_cleanup.sh --scheduled     # Daily sweep (24h threshold)
#   bash scripts/branch_cleanup.sh --immediate <branch-name>  # PR-close trigger (only this branch)
set -euo pipefail

# Parse arguments
MODE=""
TARGET_BRANCH=""

if [[ $# -eq 0 ]]; then
  echo "Error: No mode specified."
  echo "Usage: $0 --scheduled | --immediate <branch-name>"
  exit 1
fi

case "$1" in
  --scheduled)
    MODE="scheduled"
    ;;
  --immediate)
    MODE="immediate"
    if [[ $# -lt 2 ]]; then
      echo "Error: --immediate mode requires a branch name argument."
      echo "Usage: $0 --immediate <branch-name>"
      exit 1
    fi
    TARGET_BRANCH="$2"
    ;;
  *)
    echo "Error: Invalid mode '$1'."
    echo "Usage: $0 --scheduled | --immediate <branch-name>"
    exit 1
    ;;
esac

# Initialize tracking arrays
DELETED_BRANCHES=()
PROTECTED_BRANCHES=()

# Get cutoff as epoch seconds for reliable comparison (24 hours ago)
CUTOFF_EPOCH=$(date -u -d '24 hours ago' '+%s' 2>/dev/null || date -u -v-24H '+%s')

echo "=== Branch Cleanup Script ==="
echo "Mode: $MODE"
echo "Cutoff epoch: $CUTOFF_EPOCH ($(date -u -d "@$CUTOFF_EPOCH" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -r "$CUTOFF_EPOCH" '+%Y-%m-%dT%H:%M:%SZ'))"
echo ""

# Determine which branches to process
if [[ "$MODE" == "immediate" ]]; then
  # IMMEDIATE MODE: Process ONLY the specified branch
  echo "Immediate mode: processing only branch '$TARGET_BRANCH'"

  # Check if branch exists
  if ! git rev-parse --verify "origin/$TARGET_BRANCH" >/dev/null 2>&1; then
    echo "Branch '$TARGET_BRANCH' not found on remote. Nothing to do."
    echo "deleted_count=0"
    echo "protected_count=0"
    exit 0
  fi

  # Never delete main
  if [[ "$TARGET_BRANCH" == "main" ]]; then
    echo "ERROR: Cannot delete main branch."
    echo "deleted_count=0"
    echo "protected_count=0"
    exit 1
  fi

  BRANCHES="$TARGET_BRANCH"
else
  # SCHEDULED MODE: Process all non-main branches
  echo "Scheduled mode: processing all non-main branches"

  # Get all remote branches except main
  # || true prevents set -e + pipefail from exiting when grep finds no matches
  BRANCHES=$(git branch -r | grep -v 'origin/main' | grep -v 'HEAD' | sed 's|origin/||' | xargs) || true

  if [[ -z "$BRANCHES" ]]; then
    echo "No branches found (besides main). Nothing to clean."
    echo "deleted_count=0"
    echo "protected_count=0"
    exit 0
  fi
fi

echo "Checking branches: $BRANCHES"
echo ""

# Process each branch
for BRANCH in $BRANCHES; do
  echo "--- Checking branch: $BRANCH ---"

  # Never delete main (safety check)
  if [[ "$BRANCH" == "main" ]]; then
    echo "  Skipping main branch (protected)."
    continue
  fi

  # Fetch all PRs for this branch in one API call
  if ! ALL_PRS=$(gh pr list --head "$BRANCH" --state all --json number,state 2>/dev/null); then
    echo "  API error checking PRs for $BRANCH, skipping (fail-closed)."
    continue
  fi

  # Count PRs by state: OPEN, CLOSED (not merged)
  OPEN_PR_COUNT=$(echo "$ALL_PRS" | jq '[.[] | select(.state == "OPEN")] | length')
  CLOSED_NOT_MERGED_COUNT=$(echo "$ALL_PRS" | jq '[.[] | select(.state == "CLOSED")] | length')

  # Skip if has open PR
  if [[ "$OPEN_PR_COUNT" != "0" ]]; then
    echo "  Has open PR ($OPEN_PR_COUNT), skipping."
    continue
  fi

  # Safety check: count commits in branch but not in main (2-dot range).
  # These are the commits that would be lost if the branch is deleted.
  UNIQUE_COUNT=$(git rev-list --count "origin/main..origin/$BRANCH" 2>/dev/null || echo "0")

  # Protect branches with unmerged unique commits from CLOSED (not merged) PRs.
  # These branches contain code that was never merged and would be lost if deleted.
  if [[ "$UNIQUE_COUNT" -gt 0 ]] && [[ "$CLOSED_NOT_MERGED_COUNT" -gt 0 ]]; then
    echo "  ⚠️  PROTECTED: branch has $UNIQUE_COUNT unique commit(s) and $CLOSED_NOT_MERGED_COUNT CLOSED (not merged) PR(s) — would lose unmerged code."
    PROTECTED_BRANCHES+=("$BRANCH ($UNIQUE_COUNT unique commits)")
    continue
  fi

  # Get last commit date for this branch as epoch seconds
  if ! LAST_COMMIT_EPOCH=$(git log -1 --format='%ct' "origin/$BRANCH" 2>/dev/null); then
    echo "  Could not get last commit date, skipping."
    continue
  fi

  if [[ -z "$LAST_COMMIT_EPOCH" ]]; then
    echo "  Could not get last commit date, skipping."
    continue
  fi

  LAST_COMMIT_DATE=$(date -u -d "@$LAST_COMMIT_EPOCH" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -r "$LAST_COMMIT_EPOCH" '+%Y-%m-%dT%H:%M:%SZ')

  # Determine if branch should be deleted
  SHOULD_DELETE=false

  if [[ "$MODE" == "immediate" ]]; then
    # IMMEDIATE MODE: No age check, delete if no open PR
    echo "  Immediate mode: orphan branch with no open PR, deleting."
    SHOULD_DELETE=true
  else
    # SCHEDULED MODE: Check age threshold (24h)
    if [[ "$LAST_COMMIT_EPOCH" -lt "$CUTOFF_EPOCH" ]]; then
      echo "  No open PR and last commit ($LAST_COMMIT_DATE) is older than 24h."
      SHOULD_DELETE=true
    else
      echo "  Last commit ($LAST_COMMIT_DATE) is within 24h, skipping."
    fi
  fi

  # Delete branch if eligible
  if [[ "$SHOULD_DELETE" == "true" ]]; then
    echo "  Deleting branch: $BRANCH"

    # Delete remote branch
    if git push origin --delete "$BRANCH" 2>/dev/null; then
      echo "  Branch deleted successfully."
      DELETED_BRANCHES+=("$BRANCH")
    else
      echo "  Failed to delete branch (may already be deleted)."
    fi
  fi

  echo ""
done

# Output results
DELETED_COUNT=${#DELETED_BRANCHES[@]}
PROTECTED_COUNT=${#PROTECTED_BRANCHES[@]}

echo "deleted_count=$DELETED_COUNT"
echo "protected_count=$PROTECTED_COUNT"

if [[ "$DELETED_COUNT" -gt 0 ]]; then
  echo ""
  echo "Deleted $DELETED_COUNT branch(es):"
  printf '%s\n' "${DELETED_BRANCHES[@]}"
fi

if [[ "$PROTECTED_COUNT" -gt 0 ]]; then
  echo ""
  echo "Protected $PROTECTED_COUNT branch(es) with unmerged unique commits:"
  printf '%s\n' "${PROTECTED_BRANCHES[@]}"
fi

if [[ "$DELETED_COUNT" -eq 0 ]] && [[ "$PROTECTED_COUNT" -eq 0 ]]; then
  echo ""
  echo "No orphan branches to delete."
fi
