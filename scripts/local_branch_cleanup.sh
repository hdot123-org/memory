#!/bin/bash
# local_branch_cleanup.sh - 本地分支自动清理
# 扫描 gone 分支（远端已删除），使用 git cherry 验证 patch 等价性后安全删除
# 
# 安全不变量：
# - 只删除 patch 等价的 gone 分支（git cherry 全 - 号）
# - 含独立内容的 gone 分支保留并上报 PostHog 事件
# - worktree 占用的分支跳过
# - 永远不触碰 main 或非 gone 分支
# - 删除前备份 tip SHA，可通过 git branch <name> <sha> 恢复
#
# 环境变量（可选覆盖默认值）：
#   REPO_ROOT - 仓库路径（默认当前目录）
#   BACKUP_DIR - 备份文件目录（默认 ~/.factory/webhook/locks/branch_cleanup_backup）
#   POSTHOG_API_KEY - PostHog API key（未设则跳过事件上报）
#   DRY_RUN - 设为 1 时只打印不执行

set -uo pipefail

REPO_ROOT="${REPO_ROOT:-.}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.factory/webhook/locks/branch_cleanup_backup}"
DRY_RUN="${DRY_RUN:-0}"

# === Logging ===
log() {
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "[$timestamp] $*"
}

log_error() {
  log "ERROR: $*" >&2
}

# === PostHog event reporting ===
send_posthog_event() {
  local event_type="$1"
  local branch_name="$2"
  local tip_sha="$3"
  local detail="$4"

  # POSTHOG_API_KEY must come from environment; never hardcode keys in repo.
  # If unset, skip reporting (non-fatal) so the script remains offline-safe.
  if [[ -z "${POSTHOG_API_KEY:-}" ]]; then
    log "POSTHOG_API_KEY not set, skip event"
    return 0
  fi

  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  
  if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY-RUN: Would send PostHog event: $event_type for branch $branch_name"
    return 0
  fi
  
  curl -s -X POST "https://us.posthog.com/batch/" \
    -H "Content-Type: application/json" \
    -d "{
      \"api_key\": \"${POSTHOG_API_KEY}\",
      \"batch\": [{
        \"event\": \"$event_type\",
        \"distinct_id\": \"local-branch-cleanup\",
        \"timestamp\": \"$timestamp\",
        \"properties\": {
          \"branch\": \"$branch_name\",
          \"tip_sha\": \"$tip_sha\",
          \"detail\": \"$detail\"
        }
      }]
    }" > /dev/null 2>&1 || true
}

# === Backup tip SHA before deletion ===
backup_tip_sha() {
  local branch_name="$1"
  local tip_sha="$2"
  
  mkdir -p "$BACKUP_DIR"
  # Replace slashes with underscores so feat/xxx becomes feat_xxx (avoids subdirectory creation)
  local safe_name="${branch_name//\//_}"
  local backup_file="$BACKUP_DIR/$safe_name"
  echo "$tip_sha" > "$backup_file"
  log "Backed up tip SHA for $branch_name: $tip_sha"
}

# === Check if branch is occupied by worktree ===
is_worktree_occupied() {
  local branch_name="$1"
  local worktree_list
  worktree_list=$(git worktree list --porcelain 2>/dev/null | grep -A 2 "^branch refs/heads/$branch_name$" || true)
  [[ -n "$worktree_list" ]]
}

# === Main cleanup logic ===
cleanup_gone_branches() {
  cd "$REPO_ROOT" || { log_error "Cannot cd to $REPO_ROOT"; return 1; }
  
  # Step 1: Fetch and prune
  log "Fetching and pruning remote branches..."
  if ! git fetch --prune origin 2>&1; then
    log_error "git fetch --prune failed"
    return 1
  fi
  
  # Step 2: Find gone branches
  log "Scanning for gone branches..."
  local gone_branches
  # Parse branch name from git branch -vv output, handling both * (current) and + (worktree) prefixes
  gone_branches=$(git branch -vv | grep '\[origin/.*: gone\]' | sed -E 's/^[*+ ]+//' | awk '{print $1}' || true)
  
  if [[ -z "$gone_branches" ]]; then
    log "No gone branches found"
    return 0
  fi
  
  local deleted_count=0
  local skipped_count=0
  local preserved_count=0
  
  # Step 3: Process each gone branch
  while IFS= read -r branch; do
    [[ -z "$branch" ]] && continue
    
    # Never touch main
    if [[ "$branch" == "main" || "$branch" == "master" ]]; then
      log "Skipping main/master branch: $branch"
      ((skipped_count++))
      continue
    fi
    
    log "Processing gone branch: $branch"
    
    # Check worktree occupation
    if is_worktree_occupied "$branch"; then
      log "Skipping worktree-occupied branch: $branch"
      ((skipped_count++))
      continue
    fi
    
    # Get tip SHA
    local tip_sha
    tip_sha=$(git rev-parse "$branch" 2>/dev/null || echo "")
    if [[ -z "$tip_sha" ]]; then
      log_error "Cannot get tip SHA for $branch"
      ((skipped_count++))
      continue
    fi
    
    # Use git cherry to check patch equivalence with origin/main
    # Fail-closed: only delete if git cherry succeeds AND output is all '-' lines
    # If git cherry fails or output is malformed, preserve the branch
    log "Checking patch equivalence for $branch..."
    local cherry_output
    local cherry_exit_code=0
    cherry_output=$(git cherry origin/main "$branch" 2>&1) || cherry_exit_code=$?
    
    # If git cherry failed, preserve the branch (fail-closed)
    if [[ $cherry_exit_code -ne 0 ]]; then
      log_error "git cherry failed for $branch (exit code $cherry_exit_code), preserving branch"
      send_posthog_event "local_branch_cherry_failed" "$branch" "$tip_sha" "git cherry exit code: $cherry_exit_code"
      ((preserved_count++))
      continue
    fi
    
    # Validate output format: must contain only '^-' or '^+' lines
    # If any line doesn't match, treat as malformed and preserve
    if ! echo "$cherry_output" | grep -qE '^[+-] '; then
      log_error "git cherry output malformed for $branch, preserving branch"
      send_posthog_event "local_branch_cherry_malformed" "$branch" "$tip_sha" "Output doesn't match expected format"
      ((preserved_count++))
      continue
    fi
    
    # Check if there are any '+' signs (unique commits)
    if echo "$cherry_output" | grep -q '^+'; then
      log "Branch $branch contains unique content (git cherry has + signs), preserving"
      send_posthog_event "local_branch_orphan_content" "$branch" "$tip_sha" "Branch contains commits not in origin/main"
      ((preserved_count++))
      continue
    fi
    
    # All patches are equivalent (all '-' signs), safe to delete
    log "Branch $branch is patch-equivalent to origin/main, preparing to delete"
    
    # Backup tip SHA
    backup_tip_sha "$branch" "$tip_sha"
    
    # Delete branch
    if [[ "$DRY_RUN" == "1" ]]; then
      log "DRY-RUN: Would delete branch: $branch"
    else
      if git branch -D "$branch" 2>&1; then
        log "Deleted branch: $branch"
        ((deleted_count++))
      else
        log_error "Failed to delete branch: $branch"
        ((skipped_count++))
      fi
    fi
    
  done <<< "$gone_branches"
  
  log "Cleanup complete: deleted=$deleted_count, skipped=$skipped_count, preserved=$preserved_count"
}

# === Entry point ===
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  cleanup_gone_branches
fi
