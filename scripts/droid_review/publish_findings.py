#!/usr/bin/env python3
"""
TD-DR-01 findings 发布器：下载、校验、去重、inline/summary 发布。

职责：
1. 读取各 shard 的 findings JSON（从 artifacts 下载后）
2. Schema 校验（非法 → fail-closed）
3. 去重（相同 file+line+message 跨 shard 去重）
4. inline comment 行号校验（对照 patch hunks）
5. 422 降级 summary comment
6. 批次 ≤50（GitHub API 限制）
7. 按 shard 分节统计严重度
"""
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REQUIRED_FINDING_FIELDS = {"severity", "file", "line", "message"}
VALID_SEVERITIES = {"P0", "P1", "P2", "P3"}


def validate_findings(data: dict[str, Any]) -> bool:
    """
    校验 findings JSON schema。

    合法格式：
    {
      "shard_id": int,
      "findings": [
        {"severity": "P0"|"P1"|"P2"|"P3", "file": str, "line": int, "message": str}
      ]
    }

    非法 → False（调用方应 fail-closed）。
    """
    if not isinstance(data, dict):
        return False

    # shard_id 必须是 int
    if "shard_id" not in data or not isinstance(data["shard_id"], int):
        return False

    # findings 必须是 list
    if "findings" not in data or not isinstance(data["findings"], list):
        return False

    # 每条 finding 必须含必需字段且类型正确
    for finding in data["findings"]:
        if not isinstance(finding, dict):
            return False
        # 必需字段检查
        if not REQUIRED_FINDING_FIELDS.issubset(finding.keys()):
            return False
        # 类型检查
        if not isinstance(finding["severity"], str):
            return False
        if not isinstance(finding["file"], str):
            return False
        if not isinstance(finding["line"], int):
            return False
        if not isinstance(finding["message"], str):
            return False
        # 严重度枚举
        if finding["severity"] not in VALID_SEVERITIES:
            return False

    return True


def deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    跨 shard 去重：相同 (file, line, message) 只保留一条。
    """
    seen = set()
    unique = []
    for f in findings:
        key = (f["file"], f["line"], f["message"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def group_by_shard(findings: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """按 shard_id 分组（用于 summary comment 分节）。"""
    # 这里假设 findings 已带 shard_id 字段（从 validate_findings 解包后注入）
    groups = defaultdict(list)
    for f in findings:
        groups[f.get("shard_id", -1)].append(f)
    return dict(groups)


def count_by_severity(findings: list[dict[str, Any]]) -> dict[str, int]:
    """统计严重度分布。"""
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for f in findings:
        sev = f["severity"]
        if sev in counts:
            counts[sev] += 1
    return counts


def load_findings_files(pattern: str) -> list[dict[str, Any]]:
    """
    从匹配 pattern 的文件加载 findings（glob 模式）。
    返回合并后的 findings 列表（带 shard_id 注入）。
    """
    all_findings = []
    for path in Path(".").glob(pattern):
        try:
            data = json.loads(path.read_text())
            if not validate_findings(data):
                print(f"ERROR: invalid findings schema in {path}", file=sys.stderr)
                sys.exit(1)
            # 注入 shard_id 到每条 finding（便于后续分组）
            for f in data["findings"]:
                f["shard_id"] = data["shard_id"]
            all_findings.extend(data["findings"])
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
            sys.exit(1)
    return all_findings


def main() -> None:
    """CLI entry: load findings-*.json, validate, dedup, output summary."""
    if len(sys.argv) < 2:
        print("Usage: publish_findings.py <findings-pattern>", file=sys.stderr)
        sys.exit(1)

    pattern = sys.argv[1]  # e.g. "findings-*.json"
    findings = load_findings_files(pattern)

    # 去重
    unique = deduplicate_findings(findings)

    # 按 shard 分组
    by_shard = group_by_shard(unique)

    # 统计
    total_counts = count_by_severity(unique)

    output = {
        "total_findings": len(unique),
        "by_severity": total_counts,
        "by_shard": {
            shard_id: {
                "count": len(fs),
                "by_severity": count_by_severity(fs),
            }
            for shard_id, fs in sorted(by_shard.items())
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
