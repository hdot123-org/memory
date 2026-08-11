"""Evolution self-audit tool: 8 checks for pipeline health."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Module-level constants for testability (monkeypatch in tests)
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # memory/
EVOLUTION_DIR = PROJECT_ROOT / ".evolution"
SUPPRESS_JSON = EVOLUTION_DIR / "suppress.json"
FINDINGS_OVER_TIME = EVOLUTION_DIR / "findings_over_time.json"
STALE_THRESHOLD_HOURS = 48
EVOLUTION_CONFIG = EVOLUTION_DIR / "config.yml"

FACTORY_HOME = Path.home() / ".factory"
LOCK_DIR = FACTORY_HOME / "webhook" / "locks"
TRIGGER_DROID = FACTORY_HOME / "webhook" / "scripts" / "trigger-droid.sh"
RECONCILE_SCRIPT = FACTORY_HOME / "webhook" / "scripts" / "reconcile-evolution.sh"
REPOSITORIES_YML = FACTORY_HOME / "config" / "repositories.yml"

# GAP-A (INFRA-174): Linear 同步失败检测配置
# 被审计的 GitHub 仓库（evolution-found 标签所在仓库）
REPO_NAME = os.environ.get("EVOLUTION_AUDIT_REPO", "hdot123/memory")
# GitHub Issue 创建后超过此分钟数仍无 linear-linkback 视为同步失败
GAP_A_AUDIT_THRESHOLD_MIN = 30

CATEGORY = "evolution_self_audit"


def check_suppress_json() -> list[dict[str, Any]]:
    """Check 1: verify suppress.json exists and is valid."""
    findings: list[dict[str, Any]] = []

    if not SUPPRESS_JSON.exists():
        findings.append({
            "rule_id": "EVOLUTION_SUPPRESS_MISSING",
            "severity": "critical",
            "description": "suppress.json does not exist",
            "location": str(SUPPRESS_JSON),
            "evidence": "file missing",
            "category": CATEGORY,
        })
        return findings

    try:
        json.loads(SUPPRESS_JSON.read_text())
    except Exception as e:
        findings.append({
            "rule_id": "EVOLUTION_SUPPRESS_INVALID",
            "severity": "critical",
            "description": "suppress.json is invalid",
            "location": str(SUPPRESS_JSON),
            "evidence": str(e),
            "category": CATEGORY,
        })

    return findings


def check_findings_over_time() -> list[dict[str, Any]]:
    """Check 2: verify findings_over_time.json has recent data."""
    findings: list[dict[str, Any]] = []

    if not FINDINGS_OVER_TIME.exists():
        findings.append({
            "rule_id": "EVOLUTION_FINDINGS_MISSING",
            "severity": "warning",
            "description": "findings_over_time.json does not exist",
            "location": str(FINDINGS_OVER_TIME),
            "evidence": "file missing",
            "category": CATEGORY,
        })
        return findings

    try:
        data = json.loads(FINDINGS_OVER_TIME.read_text())
        snapshots = data.get("snapshots", [])
        if not snapshots:
            findings.append({
                "rule_id": "EVOLUTION_FINDINGS_INSUFFICIENT",
                "severity": "warning",
                "description": "findings_over_time.json has no snapshots",
                "location": str(FINDINGS_OVER_TIME),
                "evidence": "snapshots count=0",
                "category": CATEGORY,
            })
            return findings

        # Recency check: verify the last snapshot is recent enough
        last_snapshot = snapshots[-1]
        timestamp_str = last_snapshot.get("timestamp", "")
        if timestamp_str:
            try:
                last_time = datetime.fromisoformat(timestamp_str)
                now = datetime.now(timezone.utc)
                # Handle naive datetimes by assuming UTC
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)
                age_hours = (now - last_time).total_seconds() / 3600
                if age_hours > STALE_THRESHOLD_HOURS:
                    findings.append({
                        "rule_id": "EVOLUTION_FINDINGS_STALE",
                        "severity": "warning",
                        "description": "findings_over_time.json last snapshot is stale",
                        "location": str(FINDINGS_OVER_TIME),
                        "evidence": f"age={age_hours:.1f}h, threshold={STALE_THRESHOLD_HOURS}h",
                        "category": CATEGORY,
                    })
            except (ValueError, TypeError):
                # Malformed timestamp — skip recency check, don't crash
                pass
    except Exception as e:
        findings.append({
            "rule_id": "EVOLUTION_FINDINGS_INVALID",
            "severity": "critical",
            "description": "findings_over_time.json is invalid",
            "location": str(FINDINGS_OVER_TIME),
            "evidence": str(e),
            "category": CATEGORY,
        })

    return findings


def check_orphan_locks() -> list[dict[str, Any]]:
    """Check 3: detect orphan lock files older than 60 minutes."""
    findings: list[dict[str, Any]] = []

    if not LOCK_DIR.is_dir():
        # Skip in CI environments where ~/.factory/ files don't exist
        print(
            f"[evolution_self_audit] SKIP check_orphan_locks: "
            f"{LOCK_DIR} not found (expected in CI)",
            file=sys.stderr,
        )
        return findings

    now = time.time()
    max_age_seconds = 60 * 60

    for lock_file in LOCK_DIR.glob("*.lock"):
        try:
            mtime = lock_file.stat().st_mtime
            age = now - mtime
            if age > max_age_seconds:
                findings.append({
                    "rule_id": "EVOLUTION_ORPHAN_LOCK",
                    "severity": "warning",
                    "description": "Orphan lock file older than 60 minutes",
                    "location": str(lock_file),
                    "evidence": f"age={age/60:.1f}min",
                    "category": CATEGORY,
                })
        except Exception as e:
            findings.append({
                "rule_id": "EVOLUTION_LOCK_CHECK_ERROR",
                "severity": "warning",
                "description": "Failed to check lock file",
                "location": str(lock_file),
                "evidence": str(e),
                "category": CATEGORY,
            })

    return findings


def check_trigger_droid() -> list[dict[str, Any]]:
    """Check 4: verify trigger-droid.sh exists and contains key functions."""
    findings: list[dict[str, Any]] = []

    if not TRIGGER_DROID.exists():
        # Skip in CI environments where ~/.factory/ files don't exist
        print(
            f"[evolution_self_audit] SKIP check_trigger_droid: "
            f"{TRIGGER_DROID} not found (expected in CI)",
            file=sys.stderr,
        )
        return findings

    try:
        content = TRIGGER_DROID.read_text()
        required_functions = ["resolve_issue_ref", "resolve_pr_ref"]
        for func in required_functions:
            if f"function {func}" not in content and f"{func}()" not in content:
                findings.append({
                    "rule_id": "EVOLUTION_TRIGGER_REGRESSION",
                    "severity": "critical",
                    "description": "trigger-droid.sh missing required function",
                    "location": str(TRIGGER_DROID),
                    "evidence": f"function={func}",
                    "category": CATEGORY,
                })
    except Exception as e:
        findings.append({
            "rule_id": "EVOLUTION_TRIGGER_READ_ERROR",
            "severity": "critical",
            "description": "Failed to read trigger-droid.sh",
            "location": str(TRIGGER_DROID),
            "evidence": str(e),
            "category": CATEGORY,
        })

    return findings


def check_repositories_yml() -> list[dict[str, Any]]:
    """Check 5: verify repositories.yml has memory-core entry."""
    findings: list[dict[str, Any]] = []

    if not REPOSITORIES_YML.exists():
        # Skip in CI environments where ~/.factory/ files don't exist
        print(
            f"[evolution_self_audit] SKIP check_repositories_yml: "
            f"{REPOSITORIES_YML} not found (expected in CI)",
            file=sys.stderr,
        )
        return findings

    try:
        import yaml

        data = yaml.safe_load(REPOSITORIES_YML.read_text())
        if not isinstance(data, dict):
            findings.append({
                "rule_id": "EVOLUTION_ROUTING_MISCONFIG",
                "severity": "critical",
                "description": "repositories.yml is not a valid YAML mapping",
                "location": str(REPOSITORIES_YML),
                "evidence": f"type={type(data).__name__}",
                "category": CATEGORY,
            })
            return findings

        repos = data.get("repositories", {})
        if not isinstance(repos, dict):
            findings.append({
                "rule_id": "EVOLUTION_ROUTING_MISCONFIG",
                "severity": "critical",
                "description": "repositories.yml missing repositories section",
                "location": str(REPOSITORIES_YML),
                "evidence": "repositories key missing or invalid",
                "category": CATEGORY,
            })
            return findings

        if "memory-core" not in repos:
            findings.append({
                "rule_id": "EVOLUTION_ROUTING_MISCONFIG",
                "severity": "critical",
                "description": "repositories.yml missing memory-core entry",
                "location": str(REPOSITORIES_YML),
                "evidence": "memory-core not found",
                "category": CATEGORY,
            })
    except ImportError:
        findings.append({
            "rule_id": "EVOLUTION_ROUTING_MISCONFIG",
            "severity": "warning",
            "description": "PyYAML not available for repositories.yml check",
            "location": str(REPOSITORIES_YML),
            "evidence": "yaml module missing",
            "category": CATEGORY,
        })
    except Exception as e:
        findings.append({
            "rule_id": "EVOLUTION_ROUTING_READ_ERROR",
            "severity": "critical",
            "description": "Failed to read repositories.yml",
            "location": str(REPOSITORIES_YML),
            "evidence": str(e),
            "category": CATEGORY,
        })

    return findings


def check_config_yml() -> list[dict[str, Any]]:
    """Check 6: verify .evolution/config.yml has 6 audit tools."""
    findings: list[dict[str, Any]] = []

    if not EVOLUTION_CONFIG.exists():
        findings.append({
            "rule_id": "EVOLUTION_CONFIG_MISSING",
            "severity": "critical",
            "description": "config.yml does not exist",
            "location": str(EVOLUTION_CONFIG),
            "evidence": "file missing",
            "category": CATEGORY,
        })
        return findings

    try:
        import yaml

        data = yaml.safe_load(EVOLUTION_CONFIG.read_text())
        if not isinstance(data, dict):
            findings.append({
                "rule_id": "EVOLUTION_CONFIG_INVALID",
                "severity": "critical",
                "description": "config.yml is not a valid YAML mapping",
                "location": str(EVOLUTION_CONFIG),
                "evidence": f"type={type(data).__name__}",
                "category": CATEGORY,
            })
            return findings

        audit_tools = data.get("audit_tools", [])
        if not isinstance(audit_tools, list) or len(audit_tools) < 6:
            findings.append({
                "rule_id": "EVOLUTION_CONFIG_INSUFFICIENT",
                "severity": "warning",
                "description": "config.yml has insufficient audit tools",
                "location": str(EVOLUTION_CONFIG),
                "evidence": f"count={len(audit_tools) if isinstance(audit_tools, list) else 0}, min=6",
                "category": CATEGORY,
            })
    except ImportError:
        findings.append({
            "rule_id": "EVOLUTION_CONFIG_PARSE_ERROR",
            "severity": "warning",
            "description": "PyYAML not available for config.yml check",
            "location": str(EVOLUTION_CONFIG),
            "evidence": "yaml module missing",
            "category": CATEGORY,
        })
    except Exception as e:
        findings.append({
            "rule_id": "EVOLUTION_CONFIG_READ_ERROR",
            "severity": "critical",
            "description": "Failed to read config.yml",
            "location": str(EVOLUTION_CONFIG),
            "evidence": str(e),
            "category": CATEGORY,
        })

    return findings


def check_tool_health() -> list[dict[str, Any]]:
    """Check 7: detect tools that have failed for 3 consecutive ticks."""
    findings: list[dict[str, Any]] = []

    if not FINDINGS_OVER_TIME.exists():
        return findings

    try:
        data = json.loads(FINDINGS_OVER_TIME.read_text())
        snapshots = data.get("snapshots", [])

        # Need at least 3 snapshots to check for consecutive failures
        if len(snapshots) < 3:
            return findings

        # Get the last 3 snapshots
        recent_snapshots = snapshots[-3:]

        # Collect all tool names from the snapshots
        all_tools: set[str] = set()
        for snapshot in recent_snapshots:
            tool_status = snapshot.get("tool_status", {})
            all_tools.update(tool_status.keys())

        # Check each tool for 3 consecutive failures
        for tool_name in all_tools:
            failed_count = 0
            for snapshot in recent_snapshots:
                tool_status = snapshot.get("tool_status", {})
                if tool_status.get(tool_name) == "failed":
                    failed_count += 1

            if failed_count >= 3:
                findings.append({
                    "rule_id": "EVOLUTION_TOOL_HEALTH",
                    "severity": "warning",
                    "description": f"Tool '{tool_name}' has failed for 3 consecutive ticks",
                    "location": tool_name,
                    "evidence": f"failed_count={failed_count}/3",
                    "category": CATEGORY,
                })
    except json.JSONDecodeError as e:
        findings.append({
            "rule_id": "EVOLUTION_TOOL_HEALTH_ERROR",
            "severity": "warning",
            "description": "Failed to parse findings_over_time.json for tool health check",
            "location": str(FINDINGS_OVER_TIME),
            "evidence": str(e),
            "category": CATEGORY,
        })
    except Exception as e:
        findings.append({
            "rule_id": "EVOLUTION_TOOL_HEALTH_ERROR",
            "severity": "warning",
            "description": "Tool health check encountered an unexpected error",
            "location": str(FINDINGS_OVER_TIME),
            "evidence": str(e),
            "category": CATEGORY,
        })

    return findings


def check_linear_sync() -> list[dict[str, Any]]:
    """Check 8: GitHub evolution-found issues missing Linear sync (GAP-A / INFRA-174).

    When Linear's native GitHub integration fails to sync, a GitHub issue created
    by the evolution scanner has no corresponding Linear record. Such orphaned
    issues never receive a ``<!-- linear-linkback -->`` comment. This check
    queries GitHub for open evolution-found issues and flags any that are older
    than GAP_A_AUDIT_THRESHOLD_MIN minutes yet lack a Linear linkback.

    Uses ``gh`` CLI via subprocess. The elevated dispatch token
    (``GH_TOKEN``/``GITHUB_TOKEN``) is stripped from the subprocess environment so
    it is not leaked into a child process; ``gh`` falls back to keychain auth.
    When ``gh`` is unavailable or unauthenticated (typical in CI), the check is
    skipped gracefully rather than producing false positives.
    """
    findings: list[dict[str, Any]] = []

    # Strip elevated dispatch token so it is not leaked into the subprocess;
    # gh falls back to keychain auth. Matches run_audit_tool's security pattern.
    safe_env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}

    # Query all open evolution-found GitHub issues (recent set; age-filtered below)
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", REPO_NAME,
             "--label", "evolution-found", "--state", "open",
             "--json", "number,title,createdAt", "--limit", "50"],
            capture_output=True, text=True, timeout=30, env=safe_env,
        )
    except FileNotFoundError:
        print(
            "[evolution_self_audit] SKIP check_linear_sync: "
            "gh CLI not found (expected in CI)",
            file=sys.stderr,
        )
        return findings
    except Exception as e:
        findings.append({
            "rule_id": "LINEAR_SYNC_CHECK_ERROR",
            "severity": "warning",
            "description": "Failed to query GitHub for evolution-found issues",
            "location": "gh issue list",
            "evidence": str(e),
            "category": CATEGORY,
        })
        return findings

    if result.returncode != 0:
        # gh unavailable / unauthenticated (expected in CI) — skip
        print(
            f"[evolution_self_audit] SKIP check_linear_sync: "
            f"gh returned exit code {result.returncode} "
            f"(no auth or gh unavailable, expected in CI)",
            file=sys.stderr,
        )
        return findings

    try:
        issues = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as e:
        findings.append({
            "rule_id": "LINEAR_SYNC_CHECK_ERROR",
            "severity": "warning",
            "description": "Failed to parse GitHub issue list response",
            "location": "gh issue list",
            "evidence": str(e),
            "category": CATEGORY,
        })
        return findings

    now = datetime.now(timezone.utc)
    checked = 0
    for issue in issues:
        number = issue.get("number")
        created_at_str = issue.get("createdAt", "")
        if number is None:
            continue

        # Parse createdAt (ISO 8601, may end with 'Z')
        try:
            normalized = (created_at_str.replace("Z", "+00:00")
                          if created_at_str.endswith("Z") else created_at_str)
            created_at = datetime.fromisoformat(normalized)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        age_minutes = (now - created_at).total_seconds() / 60
        # Only check issues old enough that Linear should have synced by now
        if age_minutes <= GAP_A_AUDIT_THRESHOLD_MIN:
            continue

        checked += 1

        # Check for linear-linkback comment
        try:
            cresult = subprocess.run(
                ["gh", "issue", "view", str(number), "--repo", REPO_NAME,
                 "--json", "comments", "--jq", ".comments[].body"],
                capture_output=True, text=True, timeout=15, env=safe_env,
            )
            has_linkback = (
                cresult.returncode == 0
                and "linear-linkback" in (cresult.stdout or "")
            )
        except Exception:
            # Comment fetch failed — be conservative, treat as not-yet-checked
            has_linkback = False

        if not has_linkback:
            findings.append({
                "rule_id": "LINEAR_SYNC_GAP",
                "severity": "critical",
                "description": (
                    "GitHub evolution-found issue has no Linear linkback "
                    "(Linear sync may have failed)"
                ),
                "location": str(RECONCILE_SCRIPT),
                "evidence": (
                    f"GitHub Issue #{number} has no Linear linkback "
                    f"after {int(age_minutes)} minutes"
                ),
                "category": CATEGORY,
            })

    if checked == 0 and not findings:
        # No issues old enough to evaluate — nothing to report
        pass

    return findings


def main() -> int:
    """Run all 8 checks and output findings as JSON."""
    all_findings: list[dict[str, Any]] = []
    all_findings.extend(check_suppress_json())
    all_findings.extend(check_findings_over_time())
    all_findings.extend(check_orphan_locks())
    all_findings.extend(check_trigger_droid())
    all_findings.extend(check_repositories_yml())
    all_findings.extend(check_config_yml())
    all_findings.extend(check_tool_health())
    all_findings.extend(check_linear_sync())

    json.dump(all_findings, sys.stdout, indent=2)
    print()

    return 0 if not all_findings else 1


if __name__ == "__main__":
    sys.exit(main())
