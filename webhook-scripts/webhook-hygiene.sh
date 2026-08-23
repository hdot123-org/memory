#!/usr/bin/env bash
# webhook-hygiene.sh — TTL 清理任务（locks/logs/status）
#
# 职责：
#   locks/  — ci-complete-*.lock、l2d-*.lock、ci-fallback-*.lock mtime >7d 删除
#             pending-ci-*.json 不动（归 watchdog 管）
#             infra-failed-*.marker、stale-orphan-*.count 不动（归 reconcile 管）
#   logs/   — >30d gzip 压缩归档，>90d 直接删除
#   status/ — 终态（completed/failed/canceled/infra_failed）且 mtime >30d
#             移入 status/.archived-terminal/
#
# 安全不变量：
#   DRY_RUN=1 默认开启，仅列清单不动文件
#   mtime <7d 的文件一律不动（活跃保护）
#   pending-ci-*.json 永远不碰（watchdog 30min 兜底消费）
#   infra-failed-*.marker / stale-orphan-*.count 不碰（reconcile 冻结语义）
#   status/ running 状态文件永不归档
#   PostHog 上报清理统计（键值对事件）
#
# 环境变量：
#   DRY_RUN         — 设为 0 才真执行（默认 1）
#   WEBHOOK_BASE    — webhook 根目录（默认 ~/.factory/webhook）
#   POSTHOG_API_KEY — PostHog API key（缺失跳过上报）
#   POSTHOG_DRY_RUN — 设为 1 仅打印 PostHog payload
#
# launchd: com.factory.webhook-hygiene 每日 04:30

set -uo pipefail

# === Configuration ===
DRY_RUN="${DRY_RUN:-1}"
WEBHOOK_BASE="${WEBHOOK_BASE:-${HOME}/.factory/webhook}"
LOCK_DIR="${WEBHOOK_BASE}/locks"
LOG_DIR="${WEBHOOK_BASE}/logs"
STATUS_DIR="${WEBHOOK_BASE}/status"
ARCHIVE_DIR="${STATUS_DIR}/.archived-terminal"

# TTL thresholds (days)
LOCK_TTL_DAYS=7
LOG_COMPRESS_DAYS=30
LOG_DELETE_DAYS=90
STATUS_ARCHIVE_DAYS=30

# === Logging ===
log() {
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "[$timestamp] $*"
}

log_dry() {
  log "[DRY-RUN] $*"
}

# === PostHog event reporting (lib/posthog.sh) ===
POSTHOG_EVENT_NAME="webhook_hygiene_run"
POSTHOG_DISTINCT_ID="webhook-hygiene"
# shellcheck source=/dev/null
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/posthog.sh"

# === Counters ===
locks_deleted=0
logs_compressed=0
logs_deleted=0
status_archived=0
locks_scanned=0
logs_scanned=0
status_scanned=0

# === Phase 1: Locks cleanup ===
# Uses find -mtime for bulk discovery (fast on 1000+ files)
cleanup_locks() {
  log "=== Phase 1: Locks cleanup (TTL ${LOCK_TTL_DAYS}d) ==="

  if [[ ! -d "$LOCK_DIR" ]]; then
    log "WARN: Lock dir not found: $LOCK_DIR"
    return 0
  fi

  # find -mtime +N means mtime > N*24h ago
  # Process three lock patterns separately for clarity
  for pattern in "ci-complete-*.lock" "l2d-*.lock" "ci-fallback-*.lock"; do
    count=$(find "$LOCK_DIR" -maxdepth 1 -name "$pattern" 2>/dev/null | wc -l | tr -d ' ')
    locks_scanned=$((locks_scanned + count))

    # Find files older than TTL
    while IFS= read -r f; do
      [[ -f "$f" ]] || continue
      if [[ "$DRY_RUN" == "1" ]]; then
        log_dry "Would delete lock: $(basename "$f")"
      else
        rm -f "$f"
        log "Deleted lock: $(basename "$f")"
      fi
      locks_deleted=$((locks_deleted + 1))
    done < <(find "$LOCK_DIR" -maxdepth 1 -name "$pattern" -mtime "+${LOCK_TTL_DAYS}" 2>/dev/null)
  done

  log "Locks: scanned=$locks_scanned to_delete=$locks_deleted"
}

# === Phase 2: Logs compression/deletion ===
# Uses find -mtime for bulk discovery (critical for 14k files)
cleanup_logs() {
  log "=== Phase 2: Logs cleanup (compress >${LOG_COMPRESS_DAYS}d, delete >${LOG_DELETE_DAYS}d) ==="

  if [[ ! -d "$LOG_DIR" ]]; then
    log "WARN: Log dir not found: $LOG_DIR"
    return 0
  fi

  # Count total .log files (excluding stdout/stderr active streams)
  logs_scanned=$(find "$LOG_DIR" -maxdepth 1 -name '*.log' \
    ! -name '*-stdout.log' ! -name '*-stderr.log' 2>/dev/null | wc -l | tr -d ' ')

  # Step 1: Delete logs >90d (must run before compress to avoid compressing then deleting)
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if [[ "$DRY_RUN" == "1" ]]; then
      log_dry "Would delete log: $(basename "$f")"
    else
      rm -f "$f"
      log "Deleted log: $(basename "$f")"
    fi
    ((logs_deleted++))
  done < <(find "$LOG_DIR" -maxdepth 1 -name '*.log' \
    ! -name '*-stdout.log' ! -name '*-stderr.log' \
    -mtime "+${LOG_DELETE_DAYS}" 2>/dev/null)

  # Step 2: Compress logs >30d (but not >90d, those were already handled)
  # find -mtime +30 -mtime -90 gets files between 30-90 days
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if [[ "$DRY_RUN" == "1" ]]; then
      log_dry "Would compress log: $(basename "$f")"
    else
      gzip -f "$f"
      log "Compressed log: $(basename "$f") -> $(basename "$f").gz"
    fi
    ((logs_compressed++))
  done < <(find "$LOG_DIR" -maxdepth 1 -name '*.log' \
    ! -name '*-stdout.log' ! -name '*-stderr.log' \
    -mtime "+${LOG_COMPRESS_DAYS}" ! -mtime "+${LOG_DELETE_DAYS}" 2>/dev/null)

  # Step 3: Also clean up old .gz files past deletion threshold
  local gz_count
  gz_count=$(find "$LOG_DIR" -maxdepth 1 -name '*.gz' 2>/dev/null | wc -l | tr -d ' ')
  logs_scanned=$((logs_scanned + gz_count))

  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if [[ "$DRY_RUN" == "1" ]]; then
      log_dry "Would delete archive: $(basename "$f")"
    else
      rm -f "$f"
      log "Deleted archive: $(basename "$f")"
    fi
    ((logs_deleted++))
  done < <(find "$LOG_DIR" -maxdepth 1 -name '*.gz' \
    -mtime "+${LOG_DELETE_DAYS}" 2>/dev/null)

  log "Logs: scanned=$logs_scanned compressed=$logs_compressed deleted=$logs_deleted"
}

# === Phase 3: Status archiving ===
# Status dir is small (~300 files), per-file python3 parsing is acceptable
cleanup_status() {
  log "=== Phase 3: Status archival (terminal + ${STATUS_ARCHIVE_DAYS}d) ==="

  if [[ ! -d "$STATUS_DIR" ]]; then
    log "WARN: Status dir not found: $STATUS_DIR"
    return 0
  fi

  # Find all .json files older than threshold and process directly
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    status_scanned=$((status_scanned + 1))

    # Read status field via python3 (safe JSON parsing)
    state=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('status', 'unknown'))
except Exception:
    print('unknown')
" "$f" 2>/dev/null) || state="unknown"

    # Never archive running state
    if [[ "$state" == "running" ]]; then
      continue
    fi

    # Check if terminal state
    case "$state" in
      completed|failed|canceled|infra_failed)
        ;;
      *)
        continue
        ;;
    esac

    bname=$(basename "$f")

    if [[ "$DRY_RUN" == "1" ]]; then
      log_dry "Would archive status: $bname (state=$state)"
    else
      mkdir -p "$ARCHIVE_DIR"
      mv -f "$f" "$ARCHIVE_DIR/$bname"
      log "Archived status: $bname -> .archived-terminal/ (state=$state)"
    fi
    status_archived=$((status_archived + 1))
  done < <(find "$STATUS_DIR" -maxdepth 1 -name '*.json' \
    -mtime "+${STATUS_ARCHIVE_DAYS}" 2>/dev/null)

  log "Status: scanned=$status_scanned to_archive=$status_archived"
}

# === Main ===
main() {
  log "webhook-hygiene.sh starting (DRY_RUN=$DRY_RUN)"
  log "WEBHOOK_BASE=$WEBHOOK_BASE"

  if [[ "$DRY_RUN" == "1" ]]; then
    log "*** DRY-RUN MODE — no files will be modified ***"
  fi

  cleanup_locks
  cleanup_logs
  cleanup_status

  log "=== Summary ==="
  log "Locks: scanned=$locks_scanned deleted=$locks_deleted"
  log "Logs: scanned=$logs_scanned compressed=$logs_compressed deleted=$logs_deleted"
  log "Status: scanned=$status_scanned archived=$status_archived"

  # PostHog stats
  send_posthog_event_kv "webhook_hygiene_run" \
    "dry_run=${DRY_RUN}" \
    "locks_deleted=${locks_deleted}" \
    "logs_compressed=${logs_compressed}" \
    "logs_deleted=${logs_deleted}" \
    "status_archived=${status_archived}"

  log "webhook-hygiene.sh complete"
}

main "$@"
