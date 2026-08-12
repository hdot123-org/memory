#!/bin/bash
# Check droid-review status for the current PR/commit
# Exit 0 if droid-review passed, exit 1 if failed or not found
# Skip gracefully for non-PR events (push to main)

set -e

# Input: GitHub event name, repository, commit SHA, GitHub token
EVENT_NAME="${1}"
REPOSITORY="${2}"
COMMIT_SHA="${3}"
GH_TOKEN="${4}"

# Retry configuration
# Model review takes 10-35+ minutes depending on PR complexity
MAX_ATTEMPTS=120
WAIT_SECONDS=30

# For push events (not pull_request), skip gracefully
if [ "$EVENT_NAME" != "pull_request" ]; then
  echo "Not a pull_request event, skipping droid-review check"
  exit 0
fi

# Dependabot PRs cannot access FACTORY_API_KEY (GitHub secret restriction),
# so droid-review cannot run for them. We check the PR author and allow
# Dependabot PRs to merge when droid-review is skipped/neutral/failed.

# Check if this commit belongs to a Dependabot PR.
# Dependabot PRs cannot access FACTORY_API_KEY (GitHub secret restriction),
# so droid-review cannot run for them.
# Returns 0 (true) if Dependabot, 1 (false) otherwise.
is_dependabot_pr() {
  local pr_info pr_author
  pr_info=$(curl -s -H "Authorization: token $GH_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPOSITORY}/commits/${COMMIT_SHA}/pulls")
  pr_author=$(echo "$pr_info" | jq -r '.[0].user.login // ""')
  if [ "$pr_author" = "dependabot[bot]" ]; then
    return 0
  fi
  return 1
}

# Poll for droid-review completion
for attempt in $(seq 1 $MAX_ATTEMPTS); do
  echo "Attempt $attempt/$MAX_ATTEMPTS: Querying check runs for commit $COMMIT_SHA in $REPOSITORY..."
  
  # Query check runs for this commit
  CHECKS=$(curl -s -H "Authorization: token $GH_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPOSITORY}/commits/${COMMIT_SHA}/check-runs?check_name=droid-review")
  
  # Extract the conclusion of the latest non-cancelled check run.
  # When dual triggers exist, two check runs are created and one is cancelled.
  # We must select the one that actually completed.
  # Note: "skipped" is NOT excluded here — Dependabot PRs cause the droid-review
  # job to be skipped (job-level if condition), and we need to see that conclusion
  # to apply the Dependabot exception below. Only "cancelled" is excluded
  # (dual-trigger race where one run is cancelled mid-flight).
  STATUS=$(echo "$CHECKS" | jq -r '
    .check_runs
    | map(select(.conclusion != null and .conclusion != "cancelled"))
    | sort_by(.started_at)
    | last
    | .conclusion // "pending"
  ')

  echo "droid-review conclusion: $STATUS"
  
  # Decision logic
  if [ "$STATUS" = "success" ]; then
    echo "✓ droid-review passed"
    exit 0
  elif [ "$STATUS" = "neutral" ] || [ "$STATUS" = "skipped" ]; then
    if is_dependabot_pr; then
      echo "○ droid-review was $STATUS but PR is from Dependabot (FACTORY_API_KEY not accessible), allowing merge"
      exit 0
    fi
    echo "✗ BLOCK: droid-review was skipped/neutral — security audit did not run. Merge not allowed."
    exit 1
  elif [ "$STATUS" = "failure" ]; then
    if is_dependabot_pr; then
      echo "○ droid-review failed but PR is from Dependabot (FACTORY_API_KEY not accessible), skipping"
      exit 0
    fi
    echo "✗ FAIL: droid-review failed"
    exit 1
  elif [ "$STATUS" = "pending" ] || [ "$STATUS" = "null" ] || [ -z "$STATUS" ]; then
    if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
      echo "⚠ droid-review still running, waiting ${WAIT_SECONDS}s before retry..."
      sleep "$WAIT_SECONDS"
    else
      echo "⚠ droid-review not complete after $MAX_ATTEMPTS attempts"
      echo "This may indicate:"
      echo "  - droid-review is stuck or taking too long"
      echo "  - droid-review was not triggered (check workflow configuration)"
      echo "  - droid-review check run was not created"
      exit 1
    fi
  else
    echo "? Unknown droid-review status: $STATUS"
    exit 1
  fi
done
