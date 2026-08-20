#!/usr/bin/env bash
# run_shard.sh — TD-DR-01 单 shard 执行脚本（7 缺陷修复版）
# 职责：
# 1. 解析 SHARD_FILES 环境变量（clean JSON，无引号包裹）
# 2. 校验文件存在性（head-src 或 BASE 任一侧存在即可——修已删除文件永久红）
# 3. 在 head-src 单 clone 内生成分片 diff（merge-base 已在 workflow 预计算）
# 4. 调用 droid exec，捕获 stdout（-o json），解析 findings
# 5. 校验 findings JSON schema（fail-closed）
# 6. 输出 findings + diff artifact
set -euo pipefail

# 环境变量（从 workflow 注入）
# SHARD_ID, SHARD_FILES（JSON 数组）, BASE_REF, HEAD_REF, MERGE_BASE, RUN_ID
# FACTORY_API_KEY, GH_TOKEN

# ── 前置校验（fail-closed）──
if [ -z "${SHARD_ID:-}" ]; then
  echo "::error::SHARD_ID not set"
  exit 1
fi
if [ -z "${SHARD_FILES:-}" ]; then
  echo "::error::SHARD_FILES not set or empty — fail-closed"
  exit 1
fi
if [ -z "${BASE_REF:-}" ] || [ -z "${HEAD_REF:-}" ] || [ -z "${MERGE_BASE:-}" ]; then
  echo "::error::Missing BASE_REF/HEAD_REF/MERGE_BASE — fail-closed"
  exit 1
fi

echo "::group::Shard $SHARD_ID setup"
echo "Shard ID: $SHARD_ID"
echo "BASE_REF: $BASE_REF"
echo "HEAD_REF: $HEAD_REF"
echo "MERGE_BASE: $MERGE_BASE"

# ── Fix #1: 解析文件列表（clean JSON, 无引号包裹）──
# SHARD_FILES 现在是干净的 JSON 数组（workflow 用 toJson() 注入，无字面量引号包裹）
echo "SHARD_FILES raw: $SHARD_FILES"

# Validate JSON first — fail-closed if jq can't parse
if ! echo "$SHARD_FILES" | jq empty 2>/dev/null; then
  echo "::error::SHARD_FILES is not valid JSON: $SHARD_FILES"
  exit 1
fi

readarray -t FILES < <(echo "$SHARD_FILES" | jq -r '.[]')

if [ ${#FILES[@]} -eq 0 ]; then
  echo "::error::SHARD_FILES parsed to empty file list — fail-closed"
  exit 1
fi

echo "Files in shard (${#FILES[@]}):"
printf '  %s\n' "${FILES[@]}"

# Log shard environment for debug artifact
{
  echo "SHARD_ID=$SHARD_ID"
  echo "BASE_REF=$BASE_REF"
  echo "HEAD_REF=$HEAD_REF"
  echo "MERGE_BASE=$MERGE_BASE"
  echo "RUN_ID=${RUN_ID:-unknown}"
  echo "FILES_COUNT=${#FILES[@]}"
  echo "FILES=${FILES[*]}"
} > shard-env.log

# ── Fix #3: 文件存在性校验——接受 head-src 或 BASE 任一侧 ──
# 已删除文件只存在于 BASE checkout（根目录），不在 head-src
# 过滤掉 deleted 状态的文件（它们在 diff 中作为删除出现，但不需要模型审查）
EXISTING_FILES=()
for f in "${FILES[@]}"; do
  if [ -f "head-src/$f" ]; then
    # 文件存在于 HEAD 侧（正常情况）
    EXISTING_FILES+=("$f")
  elif [ -f "$f" ]; then
    # 文件存在于 BASE 侧但不在 HEAD 侧 → 这是已删除文件
    # 仍然纳入 diff（作为删除），但记录日志
    echo "Note: $f exists in BASE but not HEAD (deleted file — included in diff for context)"
    EXISTING_FILES+=("$f")
  else
    echo "::warning::File $f not found in either HEAD or BASE checkout — skipping"
  fi
done

if [ ${#EXISTING_FILES[@]} -eq 0 ]; then
  echo "::warning::No reviewable files in shard $SHARD_ID after filtering"
  echo "{\"shard_id\":$SHARD_ID,\"findings\":[]}" > "findings-shard-${SHARD_ID}.json"
  : > "shard-${SHARD_ID}.diff"
  echo "::endgroup::"
  exit 0
fi

# ── Fix #2: 在 head-src 单 clone 内生成 diff ──
# merge-base 已在 workflow 的 shard_env 步骤中计算（fetch base SHA 后）
echo "Generating shard diff in head-src..."
DIFF_FILE="shard-${SHARD_ID}.diff"

cd head-src
git config --global --add safe.directory "$GITHUB_WORKSPACE/head-src" 2>/dev/null || true

# Build file list for git diff (relative to repo root)
# Use -- to separate paths; fail-closed if diff command fails
set +e
git diff "${MERGE_BASE}...HEAD" -- "${EXISTING_FILES[@]}" > "$GITHUB_WORKSPACE/$DIFF_FILE" 2>shard-diff-error.log
DIFF_EXIT=$?
set -e

if [ $DIFF_EXIT -ne 0 ]; then
  echo "::error::git diff failed (exit $DIFF_EXIT): $(cat shard-diff-error.log)"
  cd "$GITHUB_WORKSPACE"
  exit 1
fi

cd "$GITHUB_WORKSPACE"

if [ ! -s "$DIFF_FILE" ]; then
  echo "::warning::No diff content for shard $SHARD_ID (files may be unchanged in this range)"
  echo "{\"shard_id\":$SHARD_ID,\"findings\":[]}" > "findings-shard-${SHARD_ID}.json"
  : > "$DIFF_FILE"
  echo "::endgroup::"
  exit 0
fi

echo "Diff generated: $(wc -l < "$DIFF_FILE") lines"
echo "::endgroup::"

# ── 读取 prompt 模板（从 BASE checkout，非 HEAD）──
PROMPT_TEMPLATE="$(cat .github/review/shard-review-prompt.md)"

# ── Fix #4 (partial): 用文件传参避免 ARG_MAX ──
# 构造 prompt 文件（不用命令行参数传递）
cat > prompt.md << PROMPT_EOF
$PROMPT_TEMPLATE

## Shard $SHARD_ID Diff

\`\`\`diff
$(cat "$DIFF_FILE")
\`\`\`

## Files in this shard

$(printf '%s\n' "${EXISTING_FILES[@]}")

## Budget Instructions

You have a maximum of 30 minutes for this review. Focus on the most critical findings first.
Limit your output to the top 20 findings maximum. Return only valid JSON.
PROMPT_EOF

# ── Fix #4: 调用 droid exec，捕获 stdout (-o json)，解析 findings ──
echo "::group::Running droid exec for shard $SHARD_ID"

# Capture stdout for JSON findings output
DROID_OUTPUT_FILE="droid-exec-stdout.json"
set +e
droid exec \
  --auto low \
  -m qwen3.7-plus \
  --cwd head-src \
  --tag "shard-${SHARD_ID}" \
  -f prompt.md \
  -o json 2>shard-exec-error.log | tee "$DROID_OUTPUT_FILE"
DROID_EXIT=$?
set -e

echo "droid exec exit code: $DROID_EXIT"

# If droid exec failed AND we have no valid output, fail-closed
if [ $DROID_EXIT -ne 0 ]; then
  echo "::error::droid exec failed for shard $SHARD_ID (exit $DROID_EXIT)"
  # Check if there's still valid output despite non-zero exit
  if [ ! -s "$DROID_OUTPUT_FILE" ] || ! jq empty "$DROID_OUTPUT_FILE" 2>/dev/null; then
    echo "::error::No valid JSON output from droid exec — fail-closed"
    cd "$GITHUB_WORKSPACE"
    exit 1
  fi
  echo "::warning::droid exec returned non-zero but produced valid JSON output, continuing"
fi

if [ ! -s "$DROID_OUTPUT_FILE" ]; then
  echo "::error::droid exec produced no stdout output — fail-closed"
  echo "::error::stderr log:"
  cat shard-exec-error.log 2>/dev/null || true
  cd "$GITHUB_WORKSPACE"
  exit 1
fi

echo "::endgroup::"

# ── 解析 findings from droid exec stdout ──
echo "::group::Parsing findings from droid exec output"

# Try to extract findings JSON from stdout
# droid exec -o json may wrap the model output in its own JSON envelope
# Try direct parse first, then look for nested result/content fields
FINDINGS_PARSED="false"

# Attempt 1: Direct JSON parse (stdout IS the findings)
if jq -e '.shard_id != null and .findings != null' "$DROID_OUTPUT_FILE" >/dev/null 2>&1; then
  cp "$DROID_OUTPUT_FILE" "findings-shard-${SHARD_ID}.json"
  FINDINGS_PARSED="true"
  echo "Direct JSON parse succeeded"
fi

# Attempt 2: Look for result field (droid envelope)
if [ "$FINDINGS_PARSED" = "false" ]; then
  if jq -e '.result' "$DROID_OUTPUT_FILE" >/dev/null 2>&1; then
    RESULT=$(jq -r '.result' "$DROID_OUTPUT_FILE")
    
    # Try direct parse first
    if echo "$RESULT" | jq -e '.shard_id != null and .findings != null' >/dev/null 2>&1; then
      echo "$RESULT" | jq '.' > "findings-shard-${SHARD_ID}.json"
      FINDINGS_PARSED="true"
      echo "Envelope .result parse succeeded"
    else
      # Extract JSON from markdown code blocks
      # shellcheck disable=SC2016  # 单引号是有意的：```json/``` 是字面量 markdown 围栏，不需要展开
      JSON_BLOCK=$(echo "$RESULT" | sed -n '/```json/,/```/p' | sed '1d;$d' | sed '/^$/d')
      if [ -n "$JSON_BLOCK" ] && echo "$JSON_BLOCK" | jq -e '.shard_id != null and .findings != null' >/dev/null 2>&1; then
        echo "$JSON_BLOCK" | jq '.' > "findings-shard-${SHARD_ID}.json"
        FINDINGS_PARSED="true"
        echo "Markdown code block extraction succeeded"
      fi
    fi
  fi
fi

# Attempt 3: Look for content/output field with embedded JSON
if [ "$FINDINGS_PARSED" = "false" ]; then
  # Try extracting JSON block from text content
  JSON_BLOCK=$(jq -r '
    if .content then .content
    elif .output then .output
    elif .message then .message
    elif type == "string" then .
    else empty
    end' "$DROID_OUTPUT_FILE" 2>/dev/null || true)

  if [ -n "$JSON_BLOCK" ]; then
    # Try to extract JSON object from the text
    EXTRACTED=$(echo "$JSON_BLOCK" | sed -n 's/.*\({.*"shard_id".*"findings".*}\).*/\1/p' | head -1)
    if [ -n "$EXTRACTED" ] && echo "$EXTRACTED" | jq -e '.shard_id != null and .findings != null' >/dev/null 2>&1; then
      echo "$EXTRACTED" | jq '.' > "findings-shard-${SHARD_ID}.json"
      FINDINGS_PARSED="true"
      echo "Content field JSON extraction succeeded"
    fi
  fi
fi

# Fail-closed: no valid findings JSON found
if [ "$FINDINGS_PARSED" = "false" ]; then
  echo "::error::Could not parse valid findings JSON from droid exec output"
  echo "::error::Raw output (first 20 lines):"
  head -20 "$DROID_OUTPUT_FILE" 2>/dev/null || true
  echo "::error::— fail-closed: shard $SHARD_ID produces no valid findings"
  cd "$GITHUB_WORKSPACE"
  exit 1
fi

echo "Findings parsed successfully"
echo "::endgroup::"

# ── 校验 findings schema ──
echo "Validating findings schema..."
python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from droid_review.publish_findings import validate_findings
data = json.load(open('findings-shard-${SHARD_ID}.json'))
if not validate_findings(data):
  print('::error::Invalid findings schema', file=sys.stderr)
  sys.exit(1)
finding_count = len(data.get('findings', []))
print(f'Findings schema valid ({finding_count} findings)')
" || {
  echo "::error::Findings schema validation failed — fail-closed"
  exit 1
}

echo "Shard $SHARD_ID completed successfully"
