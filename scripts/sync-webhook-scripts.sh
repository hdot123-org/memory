#!/bin/bash
# sync-webhook-scripts.sh - 仓库→生产 webhook 脚本同步器
# 流程：备份 → 同步 → 校验（diff + shellcheck）
# 特性：幂等；--check 只读模式；fail-closed（校验失败退出非零，目标不半更新）
#
# 用法：
#   scripts/sync-webhook-scripts.sh [--check] [--repo-root PATH] [--prod-root PATH]
#
# 环境变量（覆盖默认路径）：
#   REPO_ROOT   - 仓库根目录（默认：git rev-parse --show-toplevel）
#   PROD_ROOT   - 生产目录（默认：~/.factory/webhook/scripts）
#   BACKUP_ROOT - 备份目录（默认：PROD_ROOT/.sync-backups）

set -uo pipefail

# === 参数解析 ===
CHECK_MODE=0
REPO_ROOT="${REPO_ROOT:-}"
PROD_ROOT="${PROD_ROOT:-}"
BACKUP_ROOT="${BACKUP_ROOT:-}"

usage() {
    echo "Usage: $0 [--check] [--repo-root PATH] [--prod-root PATH] [--backup-root PATH]"
    echo ""
    echo "Options:"
    echo "  --check        只读模式：报告差异，不做任何修改"
    echo "  --repo-root    仓库根目录（默认 git rev-parse --show-toplevel）"
    echo "  --prod-root    生产目标目录（默认 ~/.factory/webhook/scripts）"
    echo "  --backup-root  备份目录（默认 PROD_ROOT/.sync-backups）"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)
            CHECK_MODE=1
            shift
            ;;
        --repo-root)
            REPO_ROOT="$2"
            shift 2
            ;;
        --prod-root)
            PROD_ROOT="$2"
            shift 2
            ;;
        --backup-root)
            BACKUP_ROOT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            usage
            ;;
    esac
done

# === 路径解析 ===
if [[ -z "$REPO_ROOT" ]]; then
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        echo "ERROR: Not in a git repository and --repo-root not set" >&2
        exit 1
    }
fi

if [[ -z "$PROD_ROOT" ]]; then
    PROD_ROOT="${HOME}/.factory/webhook/scripts"
fi

if [[ -z "$BACKUP_ROOT" ]]; then
    BACKUP_ROOT="${PROD_ROOT}/.sync-backups"
fi

REPO_WEBHOOK="${REPO_ROOT}/webhook-scripts"
MANIFEST="${REPO_WEBHOOK}/MANIFEST.sh"

# === 日志 ===
log() {
    echo "[sync-webhook] $*"
}

# === 校验前置条件 ===
if [[ ! -d "$REPO_WEBHOOK" ]]; then
    echo "ERROR: Repo webhook-scripts/ not found at ${REPO_WEBHOOK}" >&2
    exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: MANIFEST.sh not found at ${MANIFEST}" >&2
    exit 1
fi

if [[ ! -d "$PROD_ROOT" ]]; then
    echo "ERROR: Production directory not found at ${PROD_ROOT}" >&2
    exit 1
fi

# === 加载 manifest ===
# 预定义可选数组，防止 MANIFEST 未声明时 set -u 报 unbound variable
CROSS_DIR_MAPPINGS=()
# shellcheck source=/dev/null disable=SC1091
source "$MANIFEST"

# === 校验函数 ===
# 校验指定路径的脚本文件（shellcheck + bash -n）
validate_file() {
    local filepath="$1"

    if [[ ! -f "$filepath" ]]; then
        return 0
    fi

    # Run shellcheck validation
    if command -v shellcheck >/dev/null 2>&1; then
        if ! shellcheck "$filepath" >/dev/null 2>&1; then
            return 1
        fi
    fi

    # bash -n 语法校验
    if ! bash -n "$filepath" 2>/dev/null; then
        return 1
    fi

    return 0
}

# === --check 模式 ===
if [[ "$CHECK_MODE" -eq 1 ]]; then
    log "CHECK MODE: comparing repo vs production (read-only)"
    drift_found=0

    # Check MANAGED_FILES
    for file in "${MANAGED_FILES[@]}"; do
        repo_file="${REPO_WEBHOOK}/${file}"
        prod_file="${PROD_ROOT}/${file}"

        if [[ ! -f "$repo_file" ]]; then
            log "ERROR: ${file} listed in MANIFEST but missing from repo"
            drift_found=1
            continue
        fi

        if [[ ! -f "$prod_file" ]]; then
            log "DRIFT: ${file} exists in repo but not in production"
            drift_found=1
            continue
        fi

        if ! diff -q "$repo_file" "$prod_file" >/dev/null 2>&1; then
            log "DRIFT: ${file} differs between repo and production"
            drift_found=1
        else
            log "OK: ${file} in sync"
        fi
    done

    # Check CROSS_DIR_MAPPINGS
    if [[ ${#CROSS_DIR_MAPPINGS[@]} -gt 0 ]]; then
        for mapping in "${CROSS_DIR_MAPPINGS[@]}"; do
            source_path="${mapping%%:*}"
            target_file="${mapping##*:}"
            repo_file="${REPO_ROOT}/${source_path}"
            prod_file="${PROD_ROOT}/${target_file}"

            if [[ ! -f "$repo_file" ]]; then
                log "ERROR: ${source_path} listed in CROSS_DIR_MAPPINGS but missing from repo"
                drift_found=1
                continue
            fi

            if [[ ! -f "$prod_file" ]]; then
                log "DRIFT: ${source_path} exists in repo but not in production as ${target_file}"
                drift_found=1
                continue
            fi

            if ! diff -q "$repo_file" "$prod_file" >/dev/null 2>&1; then
                log "DRIFT: ${source_path} -> ${target_file} differs between repo and production"
                drift_found=1
            else
                log "OK: ${source_path} -> ${target_file} in sync"
            fi
        done
    fi

    if [[ "$drift_found" -eq 1 ]]; then
        log "CHECK RESULT: drift detected (run without --check to sync)"
        exit 1
    else
        log "CHECK RESULT: all managed files in sync"
        exit 0
    fi
fi

# === 清扫遗留 .sync-tmp-* 临时目录（kill -9 残留防御）===
# 在开始新的同步前，先清理任何遗留的临时目录
if [[ -d "$PROD_ROOT" ]]; then
    orphan_count=0
    for orphan_dir in "$PROD_ROOT"/.sync-tmp-*; do
        if [[ -d "$orphan_dir" ]]; then
            rm -rf "$orphan_dir"
            ((orphan_count++))
        fi
    done
    if [[ $orphan_count -gt 0 ]]; then
        log "Cleaned up $orphan_count orphan .sync-tmp-* director(y/ies)"
    fi
fi

# === 正常同步模式 ===
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

# Phase 1: 备份
log "Phase 1: Backing up production files"
mkdir -p "$BACKUP_ROOT"

# 为每个受管文件创建带时间戳的备份（.bak.TIMESTAMP 模式）
for file in "${MANAGED_FILES[@]}"; do
    prod_file="${PROD_ROOT}/${file}"
    if [[ -f "$prod_file" ]]; then
        backup_file="${BACKUP_ROOT}/${file}.bak.${TIMESTAMP}"
        # 不覆盖已存在的备份（幂等性）
        if [[ -f "$backup_file" ]]; then
            log "  Backup exists: ${file}.bak.${TIMESTAMP}, skipping"
        else
            cp -p "$prod_file" "$backup_file"
            log "  Backed up: ${file} -> ${file}.bak.${TIMESTAMP}"
        fi
    fi
done

# 为跨目录映射文件创建备份
if [[ ${#CROSS_DIR_MAPPINGS[@]} -gt 0 ]]; then
    for mapping in "${CROSS_DIR_MAPPINGS[@]}"; do
        target_file="${mapping##*:}"
        prod_file="${PROD_ROOT}/${target_file}"
        if [[ -f "$prod_file" ]]; then
            backup_file="${BACKUP_ROOT}/${target_file}.bak.${TIMESTAMP}"
            if [[ -f "$backup_file" ]]; then
                log "  Backup exists: ${target_file}.bak.${TIMESTAMP}, skipping"
            else
                cp -p "$prod_file" "$backup_file"
                log "  Backed up: ${target_file} -> ${target_file}.bak.${TIMESTAMP}"
            fi
        fi
    done
fi

# Phase 2: 同步
log "Phase 2: Syncing repo -> production"

# 先同步到临时目录，校验通过后再原子替换
sync_tmp="${PROD_ROOT}/.sync-tmp-${TIMESTAMP}"
mkdir -p "$sync_tmp"

for file in "${MANAGED_FILES[@]}"; do
    repo_file="${REPO_WEBHOOK}/${file}"
    if [[ ! -f "$repo_file" ]]; then
        log "WARN: ${file} listed in MANIFEST but missing from repo, skipping"
        continue
    fi
    cp -p "$repo_file" "${sync_tmp}/${file}"
    log "  Staged: ${file}"
done

# 同步跨目录映射文件
if [[ ${#CROSS_DIR_MAPPINGS[@]} -gt 0 ]]; then
    for mapping in "${CROSS_DIR_MAPPINGS[@]}"; do
        source_path="${mapping%%:*}"
        target_file="${mapping##*:}"
        repo_file="${REPO_ROOT}/${source_path}"
        if [[ ! -f "$repo_file" ]]; then
            log "WARN: ${source_path} listed in CROSS_DIR_MAPPINGS but missing from repo, skipping"
            continue
        fi
        cp -p "$repo_file" "${sync_tmp}/${target_file}"
        log "  Staged: ${source_path} -> ${target_file}"
    done
fi

# Phase 3: 校验
log "Phase 3: Validating synced files"
validation_ok=1

for file in "${MANAGED_FILES[@]}"; do
    sync_file="${sync_tmp}/${file}"
    if [[ ! -f "$sync_file" ]]; then
        continue
    fi

    if ! validate_file "$sync_file"; then
        log "FAIL: Validation failed for ${file}"
        validation_ok=0
    else
        log "  PASS: ${file}"
    fi
done

# 校验跨目录映射文件
if [[ ${#CROSS_DIR_MAPPINGS[@]} -gt 0 ]]; then
    for mapping in "${CROSS_DIR_MAPPINGS[@]}"; do
        target_file="${mapping##*:}"
        sync_file="${sync_tmp}/${target_file}"
        if [[ ! -f "$sync_file" ]]; then
            continue
        fi

        if ! validate_file "$sync_file"; then
            log "FAIL: Validation failed for ${target_file}"
            validation_ok=0
        else
            log "  PASS: ${target_file}"
        fi
    done
fi

# fail-closed: 校验失败 → 清理临时文件，保留备份，退出非零
if [[ "$validation_ok" -eq 0 ]]; then
    log "FAIL: Validation failed — rolling back (production unchanged)"
    rm -rf "$sync_tmp"
    log "Backups preserved in: ${BACKUP_ROOT}"
    exit 1
fi

# 校验通过：原子替换
log "Phase 4: Committing sync (atomic replace)"
for file in "${MANAGED_FILES[@]}"; do
    sync_file="${sync_tmp}/${file}"
    prod_file="${PROD_ROOT}/${file}"
    if [[ -f "$sync_file" ]]; then
        mv "$sync_file" "$prod_file"
        log "  Committed: ${file}"
    fi
done

# 提交跨目录映射文件
if [[ ${#CROSS_DIR_MAPPINGS[@]} -gt 0 ]]; then
    for mapping in "${CROSS_DIR_MAPPINGS[@]}"; do
        target_file="${mapping##*:}"
        sync_file="${sync_tmp}/${target_file}"
        prod_file="${PROD_ROOT}/${target_file}"
        if [[ -f "$sync_file" ]]; then
            mv "$sync_file" "$prod_file"
            log "  Committed: ${target_file}"
        fi
    done
fi

# 清理临时目录
rm -rf "$sync_tmp"

log "Sync complete. Backups in: ${BACKUP_ROOT}"
exit 0
