#!/bin/bash
# Push all migration changes to GitLab via API
# Run from /Users/busiji/memory directory

cd /Users/busiji/memory

# Get all changed files
FILES=$(git status --porcelain | sed 's/^...//' | grep -v '^"')

# Build --file arguments
FILE_ARGS=""
for f in $FILES; do
  if [ -f "$f" ]; then
    FILE_ARGS="$FILE_ARGS --file \"$f\""
  elif [ -d "$f" ]; then
    # For directories, find all files recursively
    while IFS= read -r -d '' file; do
      FILE_ARGS="$FILE_ARGS --file \"$file\""
    done < <(find "$f" -type f -print0)
  fi
done

# Execute the push
eval "python3 scripts/gitlab_api_push.py \
  --project 'infra/memory-core' \
  --branch 'migrate-memory-to-root' \
  --message '重构: 将 memory_core/memory/ 统一迁移到 repo 根目录 memory/' \
  --auto-branch \
  --create-mr \
  --target-branch main \
  $FILE_ARGS"
