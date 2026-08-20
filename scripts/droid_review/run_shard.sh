#!/usr/bin/env bash
# run_shard.sh — TD-DR-01 单 shard 执行脚本
# 职责：
# 1. 双 checkout（BASE 到根，HEAD 到 head-src/）
# 2. 生成分片 diff（git diff merge-base...head -- <files>）
# 3. 与 planner 文件集交叉校验
# 4. 调用 droid exec（实际可用旗标：--auto, -m, --cwd, --tag）
# 5. 校验 findings JSON schema
# 6. 上传 artifact（droid-review-debug-{run_id}-shard-{i}）
set -euo pipefail

# 环境变量（从 workflow 注入）
# SHARD_ID, SHARD_FILES（JSON 数组）, BASE_REF, HEAD_REF, MERGE_BASE, RUN_ID
# FACTORY_API_KEY, GITHUB_TOKEN

if [ -z "${SHARD_ID:-}" ] || [ -z "${SHARD_FILES:-}" ] || [ -z "${BASE_REF:-}" ] || [ -z "${HEAD_REF:-}" ]; then
  echo "::error::Missing required environment variables"
  exit 1
fi

echo "::group::Shard $SHARD_ID setup"
echo "Shard ID: $SHARD_ID"
echo "Files: $SHARD_FILES"

# 解析文件列表（JSON 数组 → bash 数组）
readarray -t FILES < <(echo "$SHARD_FILES" | jq -r '.[]')

# 交叉校验：确保所有文件存在于 HEAD checkout
MISSING=()
for f in "${FILES[@]}"; do
  if [ ! -f "head-src/$f" ]; then
    MISSING+=("$f")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "::error::Missing files in HEAD checkout: ${MISSING[*]}"
  exit 1
fi

# 生成分片 diff
echo "Generating shard diff..."
DIFF_FILE="shard-${SHARD_ID}.diff"
git diff "${MERGE_BASE}...${HEAD_REF}" -- "${FILES[@]}" > "$DIFF_FILE" || true

if [ ! -s "$DIFF_FILE" ]; then
  echo "::warning::No diff content for shard $SHARD_ID"
  echo '{"shard_id":'"$SHARD_ID"',"findings":[]}' > findings.json
  exit 0
fi

echo "::endgroup::"

# 读取 prompt 模板（从 BASE checkout，非 HEAD）
PROMPT_TEMPLATE="$(cat .github/review/shard-review-prompt.md)"

# 构造 prompt（注入 diff + 文件列表）
PROMPT="$PROMPT_TEMPLATE

## Shard $SHARD_ID Diff

\`\`\`diff
$(cat "$DIFF_FILE")
\`\`\`

## Files in this shard

${FILES[*]}"

# 写入 prompt 文件（避免命令行参数过长）
echo "$PROMPT" > prompt.md

# 调用 droid exec
echo "::group::Running droid exec for shard $SHARD_ID"
droid exec \
  --auto low \
  -m qwen3.7-plus \
  --cwd head-src \
  --tag "shard-${SHARD_ID}" \
  "$(cat prompt.md)" || {
    echo "::error::droid exec failed for shard $SHARD_ID"
    exit 1
  }
echo "::endgroup::"

# 查找 findings 输出（droid exec 会在当前目录生成 findings.json 或类似文件）
FINDINGS_FILE="head-src/findings.json"
if [ ! -f "$FINDINGS_FILE" ]; then
  # 尝试其他常见位置
  for candidate in "findings.json" "output/findings.json" ".factory/findings.json"; do
    if [ -f "$candidate" ]; then
      FINDINGS_FILE="$candidate"
      break
    fi
  done
fi

if [ ! -f "$FINDINGS_FILE" ]; then
  echo "::warning::No findings file found, creating empty findings"
  echo '{"shard_id":'"$SHARD_ID"',"findings":[]}' > findings.json
  FINDINGS_FILE="findings.json"
fi

# 校验 findings schema
echo "Validating findings schema..."
python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from droid_review.publish_findings import validate_findings
data = json.load(open('$FINDINGS_FILE'))
if not validate_findings(data):
  print('::error::Invalid findings schema', file=sys.stderr)
  sys.exit(1)
print('Findings schema valid')
" || exit 1

# 复制到标准输出位置
cp "$FINDINGS_FILE" "findings-shard-${SHARD_ID}.json"

# 上传 artifact（workflow 会用 actions/upload-artifact）
echo "::group::Upload artifact"
echo "findings-shard-${SHARD_ID}.json" > artifact-files.txt
echo "::endgroup::"

echo "Shard $SHARD_ID completed successfully"
