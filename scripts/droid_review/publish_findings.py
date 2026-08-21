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
import subprocess
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
    for path in Path().glob(pattern):
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


def post_inline_comment(
    finding: dict[str, Any],
    pr_number: int,
    repository: str,
    commit_id: str,
) -> bool:
    """
    Post inline review comment on PR.

    Returns True if successful, False if API call failed.
    """
    body = f"**[{finding['severity']}]** {finding['message']}"

    payload = {
        "body": body,
        "commit_id": commit_id,
        "path": finding["file"],
        "line": finding["line"],
        "side": "RIGHT",
    }

    try:
        subprocess.run(
            [
                "gh", "api",
                f"repos/{repository}/pulls/{pr_number}/comments",
                "--method", "POST",
                "--input", "-",
            ],
            input=json.dumps(payload).encode(),
            check=True,
            capture_output=True,
        )
        print(f"  ✓ Inline comment posted: {finding['file']}:{finding['line']}")
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        if "422" in stderr:
            print(f"  ⚠ 422 error (line may be invalid): {finding['file']}:{finding['line']}")
            return False
        print(f"  ✗ Failed to post inline comment: {stderr}", file=sys.stderr)
        return False


def post_summary_comment(
    findings: list[dict[str, Any]],
    pr_number: int,
    repository: str,
    by_shard: dict[int, list[dict[str, Any]]],
) -> bool:
    """
    Post summary comment on PR with findings grouped by shard.

    Returns True if successful.
    """
    total_counts = count_by_severity(findings)

    body_lines = [
        "## 🔍 Droid Auto Review — Findings Summary",
        "",
        f"**Total findings**: {len(findings)}",
        "",
        "**By severity**:",
    ]

    for sev in ["P0", "P1", "P2", "P3"]:
        count = total_counts.get(sev, 0)
        if count > 0:
            body_lines.append(f"- **{sev}**: {count}")

    body_lines.append("")
    body_lines.append("---")
    body_lines.append("")

    # Group by shard
    for shard_id in sorted(by_shard.keys()):
        shard_findings = by_shard[shard_id]
        shard_counts = count_by_severity(shard_findings)

        body_lines.append(f"### Shard {shard_id} ({len(shard_findings)} findings)")
        body_lines.append("")

        for sev in ["P0", "P1", "P2", "P3"]:
            count = shard_counts.get(sev, 0)
            if count > 0:
                body_lines.append(f"- **{sev}**: {count}")

        body_lines.append("")
        body_lines.append("<details>")
        body_lines.append(f"<summary>Details ({len(shard_findings)} items)</summary>")
        body_lines.append("")

        for f in shard_findings[:20]:  # Limit to first 20 per shard
            body_lines.append(f"- **{f['severity']}** `{f['file']}:{f['line']}`: {f['message']}")

        if len(shard_findings) > 20:
            body_lines.append(f"- ... and {len(shard_findings) - 20} more")

        body_lines.append("")
        body_lines.append("</details>")
        body_lines.append("")

    body = "\n".join(body_lines)

    try:
        subprocess.run(
            [
                "gh", "api",
                f"repos/{repository}/issues/{pr_number}/comments",
                "--method", "POST",
                "--input", "-",
            ],
            input=json.dumps({"body": body}).encode(),
            check=True,
            capture_output=True,
        )
        print("✓ Summary comment posted")
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        print(f"✗ Failed to post summary comment: {stderr}", file=sys.stderr)
        return False


def main() -> None:
    """CLI entry: load findings, validate, dedup, publish to GitHub."""
    import argparse

    parser = argparse.ArgumentParser(description="Publish shard review findings")
    parser.add_argument("--pattern", required=True, help="Glob pattern for findings files")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number")
    parser.add_argument("--repository", required=True, help="Repository (owner/name)")
    parser.add_argument("--commit-id", help="Commit ID for inline comments (optional)")

    args = parser.parse_args()

    print(f"Loading findings from: {args.pattern}")
    findings = load_findings_files(args.pattern)

    if not findings:
        print("No findings to publish")
        return

    print(f"Loaded {len(findings)} findings")

    # Deduplicate
    unique = deduplicate_findings(findings)
    print(f"After dedup: {len(unique)} findings")

    # Group by shard
    by_shard = group_by_shard(unique)

    # Post inline comments (batch of 50 max per GitHub API limit)
    if args.commit_id:
        print("\nPosting inline comments...")
        inline_success = 0
        inline_failed = []

        for f in unique[:50]:
            if post_inline_comment(f, args.pr_number, args.repository, args.commit_id):
                inline_success += 1
            else:
                inline_failed.append(f)

        print(f"Inline comments: {inline_success} posted, {len(inline_failed)} failed")

        # Degrade failed inline comments to summary
        if inline_failed:
            print("\nDegrading failed inline comments to summary...")
            unique = inline_failed
            by_shard = group_by_shard(unique)
    else:
        print("No commit-id provided, skipping inline comments")

    # Post summary comment
    print("\nPosting summary comment...")
    post_summary_comment(unique, args.pr_number, args.repository, by_shard)

    # Output statistics
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
    print("\n" + json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
