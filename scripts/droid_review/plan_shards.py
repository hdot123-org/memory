#!/usr/bin/env python3
"""
TD-DR-01 分片规划器：贪心装箱 + 目录亲和 + 溢出处理。

输入：文件列表（从 gh pr diff --name-only 获取）
输出：JSON，含 shards 列表（每片含 shard_id + files）
不变量：
  - 并集 = 输入全集（永不丢文件）
  - 两两不相交（文件不重复）
  - 同目录文件尽量聚集（目录亲和）
  - 单片不超 max_files（除非溢出放大）
  - 分片数尽量不超 max_count（溢出时可超，附告警）

溢出处理：当文件量大到无法塞入 max_count 个 max_files 容量的分片时，
自动放大分片数（突破 max_count 上限），并在输出中设 overflow_warning=true。
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _group_by_directory(files: list[str]) -> dict[str, list[str]]:
    """按父目录分组，保持目录亲和。"""
    groups = defaultdict(list)
    for f in files:
        parent = str(Path(f).parent)
        groups[parent].append(f)
    return dict(groups)


def plan_shards(
    files: list[str],
    max_files: int = 25,
    max_count: int = 6,
) -> dict[str, Any]:
    """
    贪心装箱 + 目录亲和。

    算法：
    1. 按目录分组
    2. 对每个目录组，若 <= max_files 则整组作为一个候选
    3. 若 > max_files，按 max_files 切块
    4. 贪心合并候选到分片（不超 max_files）
    5. 若分片数 > max_count，设 overflow_warning
    """
    if max_files <= 0:
        raise ValueError(f"max_files must be positive, got {max_files}")
    if max_count <= 0:
        raise ValueError(f"max_count must be positive, got {max_count}")

    if not files:
        return {
            "shards": [],
            "total_files": 0,
            "overflow_warning": False,
        }

    # Step 1: group by directory
    dir_groups = _group_by_directory(files)

    # Step 2: split large groups into chunks
    chunks = []
    for _dir_path, dir_files in dir_groups.items():
        if len(dir_files) <= max_files:
            chunks.append(dir_files)
        else:
            # Split into chunks of max_files
            for i in range(0, len(dir_files), max_files):
                chunks.append(dir_files[i : i + max_files])

    # Step 3: greedy bin-packing into shards
    shards_files: list[list[str]] = []
    for chunk in chunks:
        placed = False
        # Try to fit into existing shard
        for shard in shards_files:
            if len(shard) + len(chunk) <= max_files:
                shard.extend(chunk)
                placed = True
                break
        # Or create new shard
        if not placed:
            shards_files.append(list(chunk))

    # Step 4: check overflow
    overflow_warning = len(shards_files) > max_count

    # Step 5: build output
    shards = []
    for i, shard_files_list in enumerate(shards_files):
        shards.append(
            {
                "shard_id": i,
                "files": sorted(shard_files_list),
            }
        )

    return {
        "shards": shards,
        "total_files": len(files),
        "overflow_warning": overflow_warning,
    }


def main() -> None:
    """CLI entry: read files from stdin (one per line), output JSON."""
    if len(sys.argv) > 1:
        # Allow passing max_files/max_count as args for testing
        max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 25
        max_count = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    else:
        max_files = 25
        max_count = 6

    files = [line.strip() for line in sys.stdin if line.strip()]

    try:
        result = plan_shards(files, max_files=max_files, max_count=max_count)
        print(json.dumps(result, indent=2))
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
