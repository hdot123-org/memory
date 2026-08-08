#!/usr/bin/env python3
"""Evolution scanner: observe → normalize → create Issues → track progress."""
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


@dataclass
class Finding:
    rule_id: str
    severity: str
    category: str
    description: str
    location: str
    evidence: str


def load_config(repo_root: Path) -> dict:
    with open(repo_root / ".evolution" / "config.yml") as f:
        return yaml.safe_load(f)


def check_kill_switch(repo_root: Path) -> bool:
    if (repo_root / ".evolution" / "DISABLED").exists():
        print("[evolution] Kill switch active, exiting")
        return True
    return False


def run_audit_tool(tool: dict) -> list[dict]:
    try:
        result = subprocess.run(tool["command"].split(), capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"[evolution] Warning: {tool['name']} failed: {result.stderr}")
            return []
        return json.loads(result.stdout) if result.stdout.strip() else []
    except Exception as e:
        print(f"[evolution] Warning: {tool['name']} crashed: {e}")
        return []


def normalize_finding(raw: dict) -> Finding:
    severity = raw.get("severity", "info")
    if severity not in ["critical", "warning", "info"]:
        severity = "info"
    return Finding(
        rule_id=raw.get("rule_id", "UNKNOWN"),
        severity=severity,
        category=raw.get("category", "unknown"),
        description=raw.get("description", ""),
        location=raw.get("location", ""),
        evidence=raw.get("evidence", ""),
    )


def get_open_issues(dedup_label: str) -> list[str]:
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--label", dedup_label, "--state", "open", "--json", "title,body"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        return [f"{i['title']}|{i['body']}" for i in json.loads(result.stdout)]
    except Exception:
        return []


def deduplicate(findings: list[Finding], open_issues: list[str]) -> list[Finding]:
    return [f for f in findings if not any(f"{f.rule_id}|{f.location}" in issue for issue in open_issues)]


def detect_regressions(findings: list[Finding], history_path: Path) -> list[Finding]:
    if not history_path.exists():
        return findings
    try:
        with open(history_path) as f:
            resolved = json.load(f).get("resolved_findings", [])
        for finding in findings:
            for r in resolved:
                if r["rule_id"] == finding.rule_id and r["location"] == finding.location:
                    finding.severity = "critical"
                    break
    except Exception:
        pass
    return findings


def sort_by_severity(findings: list[Finding], severity_order: list[str]) -> list[Finding]:
    order = {s: i for i, s in enumerate(severity_order)}
    return sorted(findings, key=lambda f: order.get(f.severity, 99))


def create_issue(finding: Finding, dedup_label: str) -> bool:
    body = f"@droid\n\n**Rule ID**: {finding.rule_id}\n**Severity**: {finding.severity}\n**Category**: {finding.category}\n**Location**: {finding.location}\n**Description**: {finding.description}\n**Evidence**: {finding.evidence}"
    try:
        result = subprocess.run(
            ["gh", "issue", "create", "--title", f"[evolution] {finding.rule_id}", "--label", dedup_label, "--body", body],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def update_history(history_path: Path, findings: list[Finding], issues_created: int, snapshot_limit: int):
    data = {"snapshots": [], "resolved_findings": []}
    if history_path.exists():
        with open(history_path) as f:
            data = json.load(f)
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tick_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "findings": [asdict(f) for f in findings],
        "issues_created": issues_created,
    }
    data["snapshots"].append(snapshot)
    if len(data["snapshots"]) > snapshot_limit:
        data["snapshots"] = data["snapshots"][-snapshot_limit:]
    with open(history_path, "w") as f:
        json.dump(data, f, indent=2)


def check_isolation(findings: list[Finding], history_path: Path, threshold: int, failure_label: str):
    if not history_path.exists():
        return
    try:
        with open(history_path) as f:
            snapshots = json.load(f)["snapshots"]
        if len(snapshots) < threshold:
            return
        recent = snapshots[-threshold:]
        for finding in findings:
            count = sum(
                1 for s in recent if any(f["rule_id"] == finding.rule_id and f["location"] == finding.location for f in s["findings"])
            )
            if count >= threshold:
                subprocess.run(
                    ["gh", "issue", "list", "--label", "evolution-found", "--state", "open", "--json", "number,title,body"],
                    capture_output=True, text=True,
                )
    except Exception:
        pass


def main():
    repo_root = Path(__file__).parent.parent
    if check_kill_switch(repo_root):
        sys.exit(0)
    config = load_config(repo_root)
    history_path = repo_root / ".evolution" / "findings_over_time.json"
    raw_findings = []
    for tool in config["audit_tools"]:
        raw_findings.extend(run_audit_tool(tool))
    findings = [normalize_finding(r) for r in raw_findings]
    findings = detect_regressions(findings, history_path)
    open_issues = get_open_issues(config["dedup_label"])
    findings = deduplicate(findings, open_issues)
    findings = sort_by_severity(findings, config["severity_order"])
    issues_created = 0
    for finding in findings[: config["max_issues_per_tick"]]:
        if create_issue(finding, config["dedup_label"]):
            issues_created += 1
    update_history(history_path, findings, issues_created, config["snapshot_limit"])
    check_isolation(findings, history_path, config["isolation_threshold"], config["failure_label"])
    print(f"[evolution] Tick complete: {len(findings)} findings, {issues_created} issues created")


if __name__ == "__main__":
    main()
