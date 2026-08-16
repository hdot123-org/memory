#!/bin/bash
# MANIFEST.sh - 受管文件清单与环境差异声明
# 本文件定义 webhook-scripts/ 中受版本控制的脚本及其与生产环境的已知差异
#
# 注意：本文件被 source 时不应改变调用方的 shell 选项（如 errexit/nounset）
# 因此故意不使用 set -euo pipefail

# ============================================================================
# 受管文件清单 (Managed Files)
# ============================================================================
# 列出 webhook-scripts/ 中受版本控制的所有脚本
# sync-webhook-scripts.sh 会同步这些文件到生产环境

MANAGED_FILES=(
    "trigger-droid.sh"
    "trigger-ci-droid.sh"
    "reconcile-evolution.sh"
)

# ============================================================================
# 跨目录映射 (Cross-Directory Mappings)
# ============================================================================
# 列出仓库中非 webhook-scripts/ 目录下的依赖文件及其生产目标路径
# 格式： "仓库相对路径:生产相对路径"
# sync-webhook-scripts.sh 会同步这些文件到生产环境

# shellcheck disable=SC2034  # Used by sync-webhook-scripts.sh when sourced
CROSS_DIR_MAPPINGS=(
    # extract_anchor.py 被 reconcile-evolution.sh 和 trigger-droid.sh 引用
    # 仓库路径：scripts/extract_anchor.py
    # 生产路径：~/.factory/webhook/scripts/extract_anchor.py
    "scripts/extract_anchor.py:extract_anchor.py"
)

# ============================================================================
# 环境差异声明 (Environment-Specific Differences)
# ============================================================================
# 声明仓库副本与生产副本之间的已知环境特定差异
# 这些差异是预期的，不会导致同步失败
#
# 格式: "文件名:行号或模式:说明"
# 示例: "trigger-droid.sh:42:生产环境使用 /opt/homebrew/bin/python3"

ENV_DIFF_LINES=(
    # trigger-droid.sh 中的硬编码路径（macOS 特定）
    "trigger-droid.sh:硬编码路径:/Users/busiji/.factory/webhook - 生产环境基础路径"
    "trigger-droid.sh:硬编码路径:/opt/homebrew/bin/python3 - macOS Python 路径"
    "trigger-droid.sh:硬编码路径:/opt/homebrew/bin/flock - macOS flock 路径"
    "trigger-droid.sh:硬编码路径:/Users/busiji/.local/bin/droid - droid 二进制路径"
    "trigger-droid.sh:硬编码路径:/Users/busiji/.factory/config/repositories.yml - 仓库配置路径"

    # reconcile-evolution.sh 中的硬编码路径
    "reconcile-evolution.sh:硬编码路径:/Users/busiji/.factory/webhook - 生产环境基础路径"
    "reconcile-evolution.sh:硬编码路径:/opt/homebrew/bin/python3 - macOS Python 路径"

    # 权限差异（生产脚本可能需要特定权限位）
    "trigger-droid.sh:权限:生产环境可能需要可执行权限"
    "reconcile-evolution.sh:权限:生产环境可能需要可执行权限"

    # Shellcheck 指令差异（仓库侧添加以通过 CI 门禁）
    "trigger-droid.sh:shellcheck指令:仓库侧添加 disable=SC1091,SC2317,SC2054,SC2155 指令以通过 CI 静态分析"
)

# ============================================================================
# 辅助函数
# ============================================================================

# 获取受管文件列表
get_managed_files() {
    for file in "${MANAGED_FILES[@]}"; do
        echo "$file"
    done
}

# 检查文件是否在受管清单中
is_managed_file() {
    local file="$1"
    for managed in "${MANAGED_FILES[@]}"; do
        if [[ "$managed" == "$file" ]]; then
            return 0
        fi
    done
    return 1
}

# 获取文件的声明差异数量
get_declared_diff_count() {
    local file="$1"
    local count=0
    for diff_line in "${ENV_DIFF_LINES[@]}"; do
        if [[ "$diff_line" == "$file:"* ]]; then
            ((count++))
        fi
    done
    echo "$count"
}
