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
    killed = (repo_root / ".evolution" / "DISABLED").exists()
    if killed:
        print("[evolution] Kill switch active, exiting")
    return killed


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
    sev = raw.get("severity", "info")
    sev = sev if sev in ("critical", "warning", "info") else "info"
    return Finding(raw.get("rule_id", "UNKNOWN"), sev, raw.get("category", "unknown"),
                   raw.get("description", ""), raw.get("location", ""), raw.get("evidence", ""))


def _parse_issue_fields(body: str) -> tuple[str | None, str | None]:
    rule_id = location = None
    for line in body.split("\n"):
        if line.startswith("**Rule ID**:"):
            rule_id = line.split(":", 1)[1].strip()
        elif line.startswith("**Location**:"):
            location = line.split(":", 1)[1].strip()
    return rule_id, location


def get_open_issues(dedup_label: str) -> list[dict]:
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--label", dedup_label, "--state", "open",
             "--json", "title,body,number"],
            capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        issues = []
        for issue in json.loads(result.stdout):
            rule_id, location = _parse_issue_fields(issue.get("body", ""))
            if rule_id and location:
                issues.append({"rule_id": rule_id, "location": location,
                               "number": issue.get("number")})
        return issues
    except Exception:
        return []


def deduplicate(findings: list[Finding], open_issues: list[dict]) -> list[Finding]:
    issue_keys = {(i["rule_id"], i["location"]) for i in open_issues}
    return [f for f in findings if (f.rule_id, f.location) not in issue_keys]


def detect_regressions(findings: list[Finding], history_path: Path) -> list[Finding]:
    if not history_path.exists():
        return findings
    try:
        with open(history_path) as f:
            resolved = json.load(f).get("resolved_findings", [])
        for finding in findings:
            if any(r["rule_id"] == finding.rule_id and r["location"] == finding.location
                   for r in resolved):
                finding.severity = "critical"
    except Exception:
        pass
    return findings


def sort_by_severity(findings: list[Finding], severity_order: list[str]) -> list[Finding]:
    order = {s: i for i, s in enumerate(severity_order)}
    return sorted(findings, key=lambda f: order.get(f.severity, 99))


def create_issue(finding: Finding, dedup_label: str) -> bool:
    body = (f"@droid\n\n**Rule ID**: {finding.rule_id}\n**Severity**: {finding.severity}\n"
            f"**Category**: {finding.category}\n**Location**: {finding.location}\n"
            f"**Description**: {finding.description}\n**Evidence**: {finding.evidence}")
    try:
        result = subprocess.run(
            ["gh", "issue", "create", "--title", f"[evolution] {finding.rule_id}",
             "--label", dedup_label, "--body", body],
            capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def update_history(history_path: Path, findings: list[Finding],
                   issues_created: int, snapshot_limit: int):
    data: dict = {"snapshots": [], "resolved_findings": []}
    if history_path.exists():
        with open(history_path) as f:
            data = json.load(f)
    current_keys = {(f.rule_id, f.location) for f in findings}
    prev = data["snapshots"][-1].get("findings", []) if data.get("snapshots") else []
    now_iso = datetime.now(timezone.utc).isoformat()
    new_resolved = [{"rule_id": p["rule_id"], "location": p["location"], "resolved_at": now_iso}
                    for p in prev if (p.get("rule_id"), p.get("location")) not in current_keys]
    all_resolved = data.get("resolved_findings", []) + new_resolved
    data["resolved_findings"] = all_resolved[-snapshot_limit:]
    data["snapshots"].append({
        "timestamp": now_iso,
        "tick_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "findings": [asdict(f) for f in findings], "issues_created": issues_created})
    data["snapshots"] = data["snapshots"][-snapshot_limit:]
    with open(history_path, "w") as f:
        json.dump(data, f, indent=2)


def check_isolation(findings: list[Finding], history_path: Path, threshold: int,
                    failure_label: str, dedup_label: str):
    if not history_path.exists():
        return
    try:
        with open(history_path) as f:
            snapshots = json.load(f)["snapshots"]
        if len(snapshots) < threshold:
            return
        recent = snapshots[-threshold:]
        for finding in findings:
            count = sum(1 for s in recent if any(
                f["rule_id"] == finding.rule_id and f["location"] == finding.location
                for f in s["findings"]))
            if count < threshold:
                continue
            result = subprocess.run(
                ["gh", "issue", "list", "--label", dedup_label, "--state", "open",
                 "--json", "number,title,body"],
                capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                continue
            for issue in json.loads(result.stdout):
                rid, loc = _parse_issue_fields(issue.get("body", ""))
                if rid == finding.rule_id and loc == finding.location:
                    subprocess.run(
                        ["gh", "issue", "edit", str(issue["number"]),
                         "--add-label", failure_label],
                        capture_output=True, text=True, timeout=30)
                    break
    except Exception:
        pass


def main():
    repo_root = Path(__file__).parent.parent
    if check_kill_switch(repo_root):
        sys.exit(0)
    config = load_config(repo_root)
    history_path = repo_root / ".evolution" / "findings_over_time.json"
    raw_findings = [r for t in config["audit_tools"] for r in run_audit_tool(t)]
    all_findings = [normalize_finding(r) for r in raw_findings]
    findings = detect_regressions(all_findings, history_path)
    open_issues = get_open_issues(config["dedup_label"])
    deduped = sort_by_severity(deduplicate(findings, open_issues), config["severity_order"])
    issues_created = sum(
        1 for f in deduped[:config["max_issues_per_tick"]] if create_issue(f, config["dedup_label"]))
    update_history(history_path, all_findings, issues_created, config["snapshot_limit"])
    check_isolation(all_findings, history_path, config["isolation_threshold"],
                    config["failure_label"], config["dedup_label"])
    print(f"[evolution] Tick complete: {len(all_findings)} findings, {issues_created} issues created")


if __name__ == "__main__":
    main()
