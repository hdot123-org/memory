#!/usr/bin/env bash
# Branch cleanup tracking-issue manager (INFRA-385)
#
# Deduplicates the "Branch cleanup" tracking issues created by the
# branch-cleanup workflow. Before INFRA-385 every scheduled run that ended
# with protected branches opened a NEW issue, so a permanently protected
# branch (e.g. content landed via a different PR and then evolved on main)
# generated one duplicate issue per run (every 5 hours).
#
# Contract:
#   * Zero actionable items  -> auto-close the tracking issue (resolved)
#   * Same actionable items  -> NO new issue, NO duplicate comment
#   * Changed actionable items -> update the single tracking issue in place
#       - added items   -> comment on the existing issue
#       - deleted items -> comment
#       - removed protected items -> comment (+ auto-close when empty)
#   * At most ONE open tracking issue exists at any time; pre-INFRA-385
#     duplicate open issues are closed with a pointer to the active tracker.
#
# Usage (from the branch-cleanup workflow):
#   bash scripts/branch_cleanup_issue.sh \
#     --deleted /tmp/deleted_branches.txt \
#     --protected /tmp/protected_branches.txt \
#     --run-url <workflow run url> --run-date "<YYYY-MM-DD HH:MM UTC>"
#
# Input files may be missing or empty when the corresponding list is empty.
# Exit code is always 0: notification failures must not fail the workflow
# (branch cleanup itself has already run at this point).
set -euo pipefail

LABELS="automation,branch-cleanup"
# Unique marker for the single reusable tracking issue (INFRA-385). HTML
# comments are rendered invisibly on GitHub, so the marker does not clutter
# the issue body.
MARKER="<!-- branch-cleanup-tracker -->"

DELETED_FILE=""
PROTECTED_FILE=""
RUN_URL=""
RUN_DATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deleted)
      DELETED_FILE="$2"
      shift 2
      ;;
    --protected)
      PROTECTED_FILE="$2"
      shift 2
      ;;
    --run-url)
      RUN_URL="$2"
      shift 2
      ;;
    --run-date)
      RUN_DATE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 --deleted <file> --protected <file> --run-url <url> --run-date <date>" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$DELETED_FILE" || -z "$PROTECTED_FILE" || -z "$RUN_URL" || -z "$RUN_DATE" ]]; then
  echo "Error: --deleted, --protected, --run-url and --run-date are all required." >&2
  exit 1
fi

# Read a branch-list file into a newline-separated string (may be empty).
# Nonexistent files are treated as empty lists.
read_list() {
  local file="$1"
  if [[ -f "$file" ]]; then
    grep -v '^[[:space:]]*$' "$file" || true
  fi
}

DELETED_ITEMS=$(read_list "$DELETED_FILE")
PROTECTED_ITEMS=$(read_list "$PROTECTED_FILE")

DELETED_COUNT=$(echo -n "$DELETED_ITEMS" | grep -c . || true)
PROTECTED_COUNT=$(echo -n "$PROTECTED_ITEMS" | grep -c . || true)

if [[ "$DELETED_COUNT" -gt 0 ]]; then
  echo "deleted_branches:"
  echo "$DELETED_ITEMS"
fi
if [[ "$PROTECTED_COUNT" -gt 0 ]]; then
  echo "protected_branches:"
  echo "$PROTECTED_ITEMS"
fi
echo "deleted_count=$DELETED_COUNT protected_count=$PROTECTED_COUNT"

# ---------------------------------------------------------------------------
# Find the single open tracking issue via its unique marker. We search for
# the marker's stable prefix because GitHub's text search splits
# "<!-- branch-cleanup-tracker -->" into words.
# ---------------------------------------------------------------------------
TRACKER_URL=""
LABELED=""

# shellcheck disable=SC2016  # marker must reach gh search verbatim
SEARCH_RESULT=$(gh search issues '"branch-cleanup-tracker"' --state open --json repository,url --limit 100 2>/dev/null || true)

if [[ -n "$SEARCH_RESULT" && "$SEARCH_RESULT" != "[]" ]]; then
  OURS=$(echo "$SEARCH_RESULT" | jq -r --arg repo "$GH_REPO_KEY" '[.[] | select(.repository == $repo)] | .[0].url // ""')
  if [[ -n "$OURS" ]]; then
    TRACKER_URL="$OURS"
  fi
fi

# Always resolve this repository's labeled open issues (fallback tracker
# resolution AND duplicate detection share the result).
# shellcheck disable=SC2016
LABELED=$(gh search issues --repo "$GH_REPO_KEY" 'label:branch-cleanup' --state open --json url --limit 100 2>/dev/null || true)
if [[ -z "$TRACKER_URL" && -n "$LABELED" && "$LABELED" != "[]" ]]; then
  TRACKER_URL=$(echo "$LABELED" | jq -r '.[0].url // ""')
fi

gh_view_field() {
  gh issue view "$1" --json body --jq "$2" 2>/dev/null || echo ""
}

gh_close_with_comment() {
  gh issue close "$1" --comment "$2" 2>/dev/null || true
}

# Strip the markdown bullet/backticks from a tracked entry line, producing
# the same "branch (N unique commits)" string PROTECTED_ITEMS contains.
entry_of() {
  # shellcheck disable=SC2016
  sed -E 's/^- `([^`]+)`$/\1/' <<<"$1"
}

# Resolve a tracking-issue URL to its plain issue number (gh issue subcommands
# accept both, but a plain number keeps logs and mock tests unambiguous).
# grep exits 1 on no-match, which under `set -e -o pipefail` inside a command
# substitution would abort the script — normalize to an empty string instead.
issue_number_of() {
  local num
  num=$(echo "$1" | grep -oE '[0-9]+$') || num=""
  echo "$num"
}

# Close duplicate open branch-cleanup issues (pre-INFRA-385 leftovers) that
# are not the active tracker. No-op when the tracker is the only open one.
close_duplicate_trackers() {
  if [[ -z "$LABELED" || "$LABELED" == "[]" || -z "$TRACKER_NUMBER" ]]; then
    return 0
  fi
  local dupes dupe_url dupe_number
  dupes=$(echo "$LABELED" | jq -r '.[].url' | grep -vE "/$TRACKER_NUMBER$" || true)
  if [[ -z "$dupes" ]]; then
    return 0
  fi
  while IFS= read -r dupe_url; do
    [[ -z "$dupe_url" ]] && continue
    echo "Closing duplicate tracking issue $dupe_url"
    dupe_number=$(issue_number_of "$dupe_url")
    gh_close_with_comment "$dupe_number" \
"Duplicate branch-cleanup tracking issue: superseded by $TRACKER_URL (run of $RUN_DATE, $RUN_URL). Closing.

$MARKER"
  done <<< "$dupes"
}

TRACKER_NUMBER=$(issue_number_of "$TRACKER_URL")

# ---------------------------------------------------------------------------
# Nothing actionable: close the tracking issue as resolved, if any.
# ---------------------------------------------------------------------------
if [[ "$DELETED_COUNT" -eq 0 && "$PROTECTED_COUNT" -eq 0 ]]; then
  if [[ -n "$TRACKER_URL" ]]; then
    echo "No actionable branches: closing tracking issue $TRACKER_URL"
    gh_close_with_comment "$TRACKER_NUMBER" \
"All branch-cleanup items resolved (run of $RUN_DATE, $RUN_URL). Closing this tracking issue.

$MARKER"
    echo "issue_action=closed"
  else
    echo "No actionable branches and no open tracking issue. Nothing to do."
    echo "issue_action=none"
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Build the report section for the current run.
# ---------------------------------------------------------------------------
REPORT="**Run date:** $RUN_DATE
**Deleted branches:** $DELETED_COUNT
**Protected branches:** $PROTECTED_COUNT
**Workflow run:** $RUN_URL
"
if [[ "$DELETED_COUNT" -gt 0 ]]; then
  REPORT+=$'\n'"### Deleted branches"$'\n'$'\n'
  while IFS= read -r branch; do
    REPORT+="- \`$branch\`"$'\n'
  done <<< "$DELETED_ITEMS"
fi
if [[ "$PROTECTED_COUNT" -gt 0 ]]; then
  REPORT+=$'\n'"### 🛡️ Protected branches (unmerged unique commits)"$'\n'$'\n'
  REPORT+="These branches were protected from deletion because they contain unique commits not in main and their PR was closed without merging:"$'\n'$'\n'
  while IFS= read -r branch; do
    REPORT+="- \`$branch\`"$'\n'
  done <<< "$PROTECTED_ITEMS"
fi

# Extract "- `branch (N unique commits)`" entries from a tracking-issue body.
get_protected_from_body() {
  local body="$1"
  # Emit full entry lines (`- \`branch (N unique commits)\``) verbatim so the
  # tracked set compares equal to PROTECTED_ITEMS entries from this run.
  # Tolerate the plain branch form (`- \`branch\``) for hand-written lists.
  # grep exits 1 on no-match — normalize so the script survives `set -e`.
  # shellcheck disable=SC2016  # $ anchors are regex, not expansions
  grep -oE '^- `[^`]+( \([0-9]+ unique commits\))?`$' <<<"$body" || true
}

if [[ -z "$TRACKER_URL" ]]; then
  # -----------------------------------------------------------------------
  # No open tracking issue: create the single reusable one.
  # -----------------------------------------------------------------------
  echo "Creating tracking issue"
  BODY="## Automated Branch Cleanup (tracking)

$REPORT
---
*This tracking issue is managed by the [Branch Cleanup]($RUN_URL) workflow; it is updated in place instead of one issue per run ($MARKER).*"
  gh label create automation --force >/dev/null 2>&1 || true
  gh label create branch-cleanup --force >/dev/null 2>&1 || true
  gh issue create \
    --title "Branch cleanup tracking" \
    --body "$BODY" \
    --label "$LABELS" >/dev/null
  echo "issue_action=created"
  exit 0
fi

# ---------------------------------------------------------------------------
# Tracking issue exists: diff the protected lists.
# ---------------------------------------------------------------------------
TRACKER_BODY=$(gh_view_field "$TRACKER_NUMBER" '.body')
CURRENT_PROTECTED="$PROTECTED_ITEMS"
TRACKED_PROTECTED=""
while IFS= read -r entry; do
  [[ -z "$entry" ]] && continue
  TRACKED_PROTECTED+="${TRACKED_PROTECTED:+$'\n'}$(entry_of "$entry")"
done <<< "$(get_protected_from_body "$TRACKER_BODY")"

only_in() { # $1 items not in $2 (comm exits 1 when sets differ — tolerated)
  comm -23 <(echo "$1" | sort -u) <(echo "$2" | sort -u) || true
}

ADDED_PROTECTED=$(only_in "$CURRENT_PROTECTED" "$TRACKED_PROTECTED")
REMOVED_PROTECTED=$(only_in "$TRACKED_PROTECTED" "$CURRENT_PROTECTED")

if [[ -z "$ADDED_PROTECTED" && -z "$REMOVED_PROTECTED" && "$DELETED_COUNT" -eq 0 ]]; then
  echo "Protected branches unchanged (duplicate run): no new issue, no comment."
  # Still close pre-INFRA-385 duplicates: same protected set, separate issues.
  close_duplicate_trackers
  echo "issue_action=reused-silent"
  exit 0
fi

NEW_BODY="## Automated Branch Cleanup (tracking)

$REPORT
---
*This tracking issue is managed by the [Branch Cleanup]($RUN_URL) workflow; it is updated in place instead of one issue per run ($MARKER).*"

COMMENT_BODY=""
if [[ "$DELETED_COUNT" -gt 0 ]]; then
  COMMENT_BODY+="**[$RUN_DATE] Deleted branches:**"$'\n'
  while IFS= read -r branch; do
    COMMENT_BODY+="- \`$branch\`"$'\n'
  done <<< "$DELETED_ITEMS"
fi
if [[ -n "$ADDED_PROTECTED" ]]; then
  [[ -n "$COMMENT_BODY" ]] && COMMENT_BODY+=$'\n'
  COMMENT_BODY+="**[$RUN_DATE] Newly protected branches (unmerged unique commits):**"$'\n'
  while IFS= read -r branch; do
    COMMENT_BODY+="- \`$branch\`"$'\n'
  done <<< "$ADDED_PROTECTED"
fi
if [[ -n "$REMOVED_PROTECTED" ]]; then
  [[ -n "$COMMENT_BODY" ]] && COMMENT_BODY+=$'\n'
  COMMENT_BODY+="**[$RUN_DATE] Resolved branches (no longer protected):**"$'\n'
  while IFS= read -r branch; do
    COMMENT_BODY+="- \`$branch\`"$'\n'
  done <<< "$REMOVED_PROTECTED"
fi

# Update body in place
gh issue edit "$TRACKER_NUMBER" --body "$NEW_BODY" >/dev/null 2>&1 || true
# Deletions are also reportable state changes; comment whenever we got here.
if gh issue comment "$TRACKER_NUMBER" --body "$COMMENT_BODY" >/dev/null 2>&1; then
  echo "issue_action=updated"
else
  echo "issue_action=update-failed"
fi

# Close pre-INFRA-385 duplicate open issues (same label, not the tracker).
close_duplicate_trackers

exit 0
