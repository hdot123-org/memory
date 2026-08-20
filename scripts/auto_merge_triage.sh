#!/usr/bin/env bash
# Auto-merge triage script (INFRA-416 / INFRA-428)
# Classifies PRs by mergeable state, mergeStateStatus and statusCheckRollup.
#
# Input:  JSON array of PRs via stdin (gh pr view/list --json
#         number,mergeable,mergeStateStatus,isDraft,statusCheckRollup)
# Output: JSON with 6 categories:
#           mergeable   (action: merge)
#           behind      (action: update-branch)
#           conflicting (action: notify)
#           pending     (action: wait)
#           stalled     (action: wait)
#           unknown     (action: skip)
# Exit:   always 0 (triage never fails workflow)
#
# Modes:
#   default            classify stdin, emit full JSON
#   --get-action N     classify stdin, emit the single action for PR number N
#                      (merge|update-branch|notify|wait|skip; exit 0; empty or
#                      invalid input also emits skip — triage must never fail
#                      the workflow)
#   --get-category N   classify stdin, emit the single category for PR number N
#                      (mergeable|behind|conflicting|pending|stalled|unknown;
#                      missing PR -> unknown). Workflow uses this to derive
#                      auxiliary outputs (e.g. stalled flag) without
#                      duplicating classification logic.
#
# Classification precedence (one PR falls into exactly one category,
# decided by classify_pr in a single pass — categories are exclusive by
# construction, no cross-select races):
#   mergeable=UNKNOWN    -> unknown     (skip; GitHub still computing)
#   mergeable=CONFLICTING-> conflicting (notify)
#   mergeStateStatus=BEHIND -> behind   (update-branch)
#   isDraft / DRAFT / BLOCKED -> pending (wait)
#   rollup empty or has incomplete checks -> pending (wait; early-fire guard)
#   rollup all reported, some not SUCCESS -> stalled (wait + escalate)
#   otherwise (MERGEABLE + green rollup)  -> mergeable (merge)
#
# Why these categories exist (INFRA-428):
# - BLOCKED/DRAFT previously fell into "mergeable" → every 10-min sweep fired
#   a merge attempt at an un-mergeable PR → red leg + the shared action's own
#   failure check run poisoned the head SHA (2026-08-18 self-poisoning
#   deadlock, PR #779 mechanism). wait = benign skip, schedule re-sweeps.
# - early-fire: pull_request_target(opened) / workflow_run of one workflow
#   can arrive before all required checks reported. mergeStateStatus alone is
#   async/cached and can be stale-CLEAN in that window; cross-checking
#   statusCheckRollup makes merge fire only when every check run reports
#   conclusion=SUCCESS. Rollup empty = no checks reported yet → fail-closed
#   wait (CI runs on every PR without paths filter, so an empty rollup is
#   always "checks not reported yet", never "no checks configured").
# - CONFLICTING wins over BEHIND: a conflicting PR must never be
#   update-branched into a blind merge.

set -euo pipefail

GET_ACTION_PR=""
GET_CATEGORY_PR=""

MODE="default"
if [[ "${1:-}" == "--get-action" || "${1:-}" == "--get-category" ]]; then
  MODE="$1"
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 [--get-action PR_NUMBER | --get-category PR_NUMBER]" >&2
    echo '{"mergeable":[],"behind":[],"conflicting":[],"pending":[],"stalled":[],"unknown":[]}'
    exit 0
  fi
  if [[ "$MODE" == "--get-action" ]]; then
    GET_ACTION_PR="$2"
  else
    GET_CATEGORY_PR="$2"
  fi
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--get-action PR_NUMBER | --get-category PR_NUMBER]" >&2
  echo '{"mergeable":[],"behind":[],"conflicting":[],"pending":[],"stalled":[],"unknown":[]}'
  exit 0
fi

EMPTY_RESULT='{"mergeable":[],"behind":[],"conflicting":[],"pending":[],"stalled":[],"unknown":[]}'

# Classify PRs and add action fields.
# `jq -e` would swallow the classification on unexpected shapes; plain jq
# with a fallback keeps triage total (empty result on any malformed input).
classify() {
  jq '
    def rollup(pr): (pr.statusCheckRollup // []);
    # green = every reported check succeeded (or was harmlessly skipped) AND
    # at least one check reported.
    # Acceptable conclusions: SUCCESS, SKIPPED, NEUTRAL — these are non-failures.
    # Failure conclusions: FAILURE, TIMED_OUT, CANCELLED, ACTION_REQUIRED.
    # Rationale (INFRA-428 + scrutiny R2): qa.yml #830 added two nightly jobs
    # (Coverage Audit / Full Regression) that report SKIPPED on PR events.
    # The old logic required conclusion == "SUCCESS" for every check, so every
    # PR rollup contained SKIPPED → checks_green was never true → sweep
    # always stalled → zero merges. SKIPPED/NEUTRAL are semantically "not a
    # failure" and must not block merge.
    def checks_green(pr):
      (rollup(pr) | length) > 0
      and all(rollup(pr)[]; .conclusion == "SUCCESS" or .conclusion == "SKIPPED" or .conclusion == "NEUTRAL");
    # complete = every check run has reported a non-null conclusion.
    # has("conclusion") alone is not enough: the rollup of a queued/
    # in_progress check contains "conclusion": null, and jq has() would
    # treat it as reported. A reported check has a conclusion STRING.
    def checks_complete(pr):
      (rollup(pr) | length) > 0
      and all(rollup(pr)[]; (.conclusion // "") | type == "string" and length > 0);

    def classify_pr(pr):
      if pr.mergeable == "UNKNOWN" then "unknown"
      elif pr.mergeable == "CONFLICTING" then "conflicting"
      elif pr.mergeStateStatus == "BEHIND" then "behind"
      elif (pr.isDraft // false) or pr.mergeStateStatus == "DRAFT" or pr.mergeStateStatus == "BLOCKED" then "pending"
      elif (rollup(pr) | length) == 0 then "pending"
      elif checks_green(pr) then "mergeable"
      elif checks_complete(pr) then "stalled"
      else "pending"
      end;

    def action_for(cat):
      if cat == "mergeable" then "merge"
      elif cat == "behind" then "update-branch"
      elif cat == "conflicting" then "notify"
      elif cat == "pending" then "wait"
      elif cat == "stalled" then "wait"
      else "skip"
      end;

    map(. as $pr | {pr: $pr, cat: classify_pr($pr)})
    | {
        mergeable: [.[] | select(.cat == "mergeable") | .pr + {action: action_for(.cat)}],
        behind: [.[] | select(.cat == "behind") | .pr + {action: action_for(.cat)}],
        conflicting: [.[] | select(.cat == "conflicting") | .pr + {action: action_for(.cat)}],
        pending: [.[] | select(.cat == "pending") | .pr + {action: action_for(.cat)}],
        stalled: [.[] | select(.cat == "stalled") | .pr + {action: action_for(.cat)}],
        unknown: [.[] | select(.cat == "unknown") | .pr + {action: action_for(.cat)}]
      }
  ' 2>/dev/null || echo "$EMPTY_RESULT"
}

# Read JSON from stdin
input=$(cat)

# Handle empty or invalid JSON
if ! echo "$input" | jq empty 2>/dev/null; then
  echo "Invalid or empty JSON input, returning empty triage result" >&2
  if [[ -n "$GET_ACTION_PR" ]]; then
    echo "skip"
  elif [[ -n "$GET_CATEGORY_PR" ]]; then
    echo "unknown"
  else
    echo "$EMPTY_RESULT"
  fi
  exit 0
fi

TRIAGE_RESULT=$(echo "$input" | classify)

if [[ -n "$GET_ACTION_PR" || -n "$GET_CATEGORY_PR" ]]; then
  # 每类只含互斥子集，按类别优先级查一次即可得到该 PR 的唯一归属
  CATEGORY=$(echo "$TRIAGE_RESULT" | jq -r --argjson pr "${GET_ACTION_PR:-$GET_CATEGORY_PR}" '
    if ([.behind[] | select(.number == $pr)] | length) > 0 then "behind"
    elif ([.conflicting[] | select(.number == $pr)] | length) > 0 then "conflicting"
    elif ([.pending[] | select(.number == $pr)] | length) > 0 then "pending"
    elif ([.stalled[] | select(.number == $pr)] | length) > 0 then "stalled"
    elif ([.mergeable[] | select(.number == $pr)] | length) > 0 then "mergeable"
    else "unknown"
    end
  ')
  if [[ -n "$GET_CATEGORY_PR" ]]; then
    echo "$CATEGORY"
  else
    case "$CATEGORY" in
      behind) echo "update-branch" ;;
      conflicting) echo "notify" ;;
      pending|stalled) echo "wait" ;;
      mergeable) echo "merge" ;;
      *) echo "skip" ;;
    esac
  fi
  exit 0
fi

echo "$TRIAGE_RESULT"
