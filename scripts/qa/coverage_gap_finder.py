#!/usr/bin/env python3
"""Coverage gap finder for memory-core.

Analyzes pytest coverage data and identifies untested modules, branches, and lines.
Generates a structured report with prioritized gaps.

Usage:
    python scripts/qa/coverage_gap_finder.py
    python scripts/qa/coverage_gap_finder.py --target 80
    python scripts/qa/coverage_gap_finder.py --json output.json

Prerequisites:
    Run pytest with coverage first:
    python -m pytest tests/ --cov=memory_core --cov-report=xml --cov-branch
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Core path modules that must have high coverage
CORE_MODULES = {
    "memory_hook_gateway",
    "memory_hook_core",
    "memory_hook_impls",
    "business_policy_checks",
    "pretooluse_guard",
    "_guard_classify",
    "init_project_memory",
    "validate_project_memory",
    "migrate_project_memory",
    "memory_hook_integrity_manifest",
    "memory_hook_integrity_verify",
    "telemetry_bridge",
    "memory_hook_config",
    "memory_hook_schema",
    "factory_global_hooks",
    "consistency_check",
    "audit_project_layout",
    "daily_kb_audit",
    "ownership_cli",
    "version_sync",
}


@dataclass
class ModuleCoverage:
    name: str
    path: str
    line_rate: float
    branch_rate: float
    total_lines: int
    covered_lines: int
    missed_lines: int
    is_core: bool = False

    @property
    def coverage_pct(self) -> float:
        return self.line_rate * 100

    @property
    def priority(self) -> str:
        if self.is_core:
            if self.coverage_pct < 50:
                return "P0"
            elif self.coverage_pct < 70:
                return "P1"
        if self.coverage_pct < 40:
            return "P2"
        if self.coverage_pct < 30:
            return "P3"
        return "OK"


def color(text: str, c: str) -> str:
    return f"{c}{text}{RESET}"


def run_coverage() -> Path:
    """Run pytest with coverage XML output."""
    xml_path = Path("coverage_gap.xml")
    print(color("Running pytest with coverage...", CYAN))
    subprocess.run(
        [
            sys.executable, "-m", "pytest", "tests/",
            "--cov=memory_core",
            "--cov-report=xml:coverage_gap.xml",
            "--cov-branch",
            "-q",
            "--no-header",
            "--tb=no",
        ],
        capture_output=True,
        timeout=600,
    )
    return xml_path


def parse_coverage_xml(xml_path: Path) -> list[ModuleCoverage]:
    """Parse coverage.xml and return per-module coverage."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Overall coverage parsed per-class below
    modules: list[ModuleCoverage] = []

    for cls in root.iter("class"):
        filename = cls.attrib.get("filename", "")
        if not filename.startswith("memory_core/"):
            continue
        if "/__pycache__/" in filename:
            continue

        # Skip __init__.py and constants
        basename = Path(filename).stem
        if basename in ("__init__", "constants"):
            continue

        line_rate = float(cls.attrib.get("line-rate", "0"))
        branch_rate = float(cls.attrib.get("branch-rate", "0"))

        # Count lines
        total_lines = 0
        covered_lines = 0
        for line in cls.iter("line"):
            total_lines += 1
            if line.attrib.get("hits", "0") != "0":
                covered_lines += 1

        missed = total_lines - covered_lines
        is_core = basename in CORE_MODULES

        modules.append(ModuleCoverage(
            name=basename,
            path=filename,
            line_rate=line_rate,
            branch_rate=branch_rate,
            total_lines=total_lines,
            covered_lines=covered_lines,
            missed_lines=missed,
            is_core=is_core,
        ))

    return modules


def analyze_gaps(modules: list[ModuleCoverage], target: float) -> dict:
    """Analyze coverage gaps and generate report data."""
    overall = sum(m.covered_lines for m in modules)
    total = sum(m.total_lines for m in modules)
    overall_pct = (overall / total * 100) if total > 0 else 0

    # Sort by missed lines (most missed first)
    by_missed = sorted(modules, key=lambda m: m.missed_lines, reverse=True)

    # Core modules below target
    core_below = [m for m in modules if m.is_core and m.coverage_pct < target]

    # Zero coverage modules
    zero_coverage = [m for m in modules if m.coverage_pct == 0]

    # Priority groups
    p0 = [m for m in modules if m.priority == "P0"]
    p1 = [m for m in modules if m.priority == "P1"]
    p2 = [m for m in modules if m.priority == "P2"]
    p3 = [m for m in modules if m.priority == "P3"]

    # Lines needed to reach target
    target_covered = int(total * target / 100)
    lines_needed = max(0, target_covered - overall)

    return {
        "overall_pct": round(overall_pct, 1),
        "target_pct": target,
        "total_lines": total,
        "covered_lines": overall,
        "missed_lines": total - overall,
        "lines_needed_for_target": lines_needed,
        "module_count": len(modules),
        "core_below_target": len(core_below),
        "zero_coverage_count": len(zero_coverage),
        "priority_counts": {
            "P0": len(p0),
            "P1": len(p1),
            "P2": len(p2),
            "P3": len(p3),
        },
        "top_20_missed": [
            {
                "module": m.name,
                "path": m.path,
                "coverage_pct": round(m.coverage_pct, 1),
                "missed_lines": m.missed_lines,
                "total_lines": m.total_lines,
                "is_core": m.is_core,
                "priority": m.priority,
            }
            for m in by_missed[:20]
        ],
        "zero_coverage_modules": [
            {"module": m.name, "path": m.path, "total_lines": m.total_lines}
            for m in zero_coverage
        ],
    }


def print_report(data: dict) -> None:
    """Print human-readable coverage gap report."""
    pct = data["overall_pct"]
    target = data["target_pct"]
    status = color("PASS", GREEN) if pct >= target else color("FAIL", RED)

    print(color("\n" + "=" * 60, CYAN))
    print(color(" Coverage Gap Analysis Report", BOLD))
    print(color("=" * 60, CYAN))

    print(f"\n  Overall Coverage: {color(f'{pct:.1f}%', BOLD)} / Target: {target}% [{status}]")
    print(f"  Total Lines:     {data['total_lines']}")
    print(f"  Covered Lines:   {data['covered_lines']}")
    print(f"  Missed Lines:    {data['missed_lines']}")
    print(f"  Lines to Target: {color(str(data['lines_needed_for_target']), YELLOW)} more lines needed")

    pc = data["priority_counts"]
    print("\n  Priority Breakdown:")
    print(f"    {color('P0', RED)} (core < 50%): {pc['P0']} modules")
    print(f"    {color('P1', YELLOW)} (core < 70%): {pc['P1']} modules")
    print(f"    {color('P2', YELLOW)} (any < 40%):  {pc['P2']} modules")
    print(f"    {color('P3', YELLOW)} (any < 30%):  {pc['P3']} modules")

    print(f"\n  Zero Coverage: {data['zero_coverage_count']} modules")
    for m in data["zero_coverage_modules"][:10]:
        print(f"    {color('ZERO', RED)} {m['module']} ({m['total_lines']} lines)")

    print("\n  Top 20 Missed Modules:")
    print(f"  {'Module':<40} {'Coverage':>10} {'Missed':>8} {'Pri':>5} {'Core':>6}")
    print(f"  {'-'*40} {'-'*10} {'-'*8} {'-'*5} {'-'*6}")
    for m in data["top_20_missed"]:
        pct_str = f"{m['coverage_pct']:.1f}%"
        pri = m["priority"]
        pri_color = RED if pri == "P0" else YELLOW if pri in ("P1", "P2", "P3") else GREEN
        core_str = "YES" if m["is_core"] else ""
        print(f"  {m['module']:<40} {pct_str:>10} {m['missed_lines']:>8} {color(pri, pri_color):>5} {core_str:>6}")

    print(color("\n" + "=" * 60, CYAN))


def main() -> int:
    parser = argparse.ArgumentParser(description="memory-core coverage gap finder")
    parser.add_argument("--target", type=float, default=80.0, help="Coverage target percentage (default: 80)")
    parser.add_argument("--json", type=str, help="Write JSON results to file")
    parser.add_argument("--reuse-xml", action="store_true", help="Reuse existing coverage_gap.xml")
    args = parser.parse_args()

    # Run or reuse coverage
    xml_path = Path("coverage_gap.xml")
    if not args.reuse_xml or not xml_path.exists():
        xml_path = run_coverage()

    if not xml_path.exists():
        print(color("ERROR: coverage XML not found. Run pytest with --cov-report=xml first.", RED))
        return 1

    modules = parse_coverage_xml(xml_path)
    if not modules:
        print(color("ERROR: no modules found in coverage XML.", RED))
        return 1

    data = analyze_gaps(modules, args.target)
    print_report(data)

    if args.json:
        output_path = Path(args.json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\nJSON results written to {output_path}")

    # Cleanup temp XML
    if xml_path.exists() and not args.reuse_xml:
        xml_path.unlink()

    return 0 if data["overall_pct"] >= args.target else 1


if __name__ == "__main__":
    sys.exit(main())
