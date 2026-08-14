#!/usr/bin/env bash
# audit_telemetry_coverage.sh — 审计 hook 入口文件的 telemetry 覆盖率
#
# 检查所有 hook 入口文件是否导入了 telemetry_bridge 模块。
# 输出覆盖率报告，退出码始终为 0（advisory only）。
#
# Usage: bash scripts/audit_telemetry_coverage.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="${REPO_ROOT}/memory_core/tools"

# Hook 入口文件列表（这些文件应导入 telemetry）
HOOK_ENTRY_FILES=(
    "pretooluse_guard.py"
    "session_end_logger.py"
    "memory_hook_gateway.py"
    "memory_hook_metrics.py"
    "auto_capture.py"
    "daily_summary_generator.py"
    "codex_session_analyzer.py"
    "hook_event_stats.py"
)

total=0
covered=0
uncovered_files=()

echo "========================================"
echo "  Telemetry Coverage Audit Report"
echo "========================================"
echo ""
echo "扫描目录: ${TOOLS_DIR}"
echo ""

for f in "${HOOK_ENTRY_FILES[@]}"; do
    filepath="${TOOLS_DIR}/${f}"
    total=$((total + 1))

    if [[ ! -f "$filepath" ]]; then
        echo "  [SKIP] ${f} — 文件不存在"
        total=$((total - 1))
        continue
    fi

    # 检查是否包含 telemetry 导入
    if grep -q "telemetry" "$filepath" 2>/dev/null; then
        covered=$((covered + 1))
        echo "  [OK]   ${f} — 已导入 telemetry"
    else
        uncovered_files+=("$f")
        echo "  [MISS] ${f} — 未导入 telemetry"
    fi
done

echo ""
echo "----------------------------------------"
if [[ $total -gt 0 ]]; then
    pct=$(( (covered * 100) / total ))
else
    pct=0
fi
echo "覆盖率: ${covered}/${total} (${pct}%)"
echo "----------------------------------------"

if [[ ${#uncovered_files[@]} -gt 0 ]]; then
    echo ""
    echo "未覆盖文件:"
    for f in "${uncovered_files[@]}"; do
        echo "  - ${f}"
    done
    echo ""
    echo "建议: 为以上文件添加 telemetry import 以实现完整覆盖。"
    echo "示例:"
    echo '  try:'
    echo '      from memory_core.tools.telemetry_bridge import telemetry'
    echo '  except Exception:'
    echo '      telemetry = None'
fi

echo ""
echo "========================================"
echo "  Audit complete (advisory, non-blocking)"
echo "========================================"

exit 0
