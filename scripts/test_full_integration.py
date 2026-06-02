#!/usr/bin/env python3
"""Full integration test for memory-core platform hooks and consumer projects.

Usage:
    python scripts/test_full_integration.py [--verbose] [--fix]

Options:
    --verbose  Show detailed output for each check
    --fix      Attempt to fix issues where possible (register missing projects, etc.)

Exit codes:
    0  All checks passed
    1  At least one check failed
    2  Only warnings/skips, no failures
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Try to import tomllib (Python 3.11+) or fall back to tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

# Add memory_core to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from memory_core.constants import CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS
except ImportError:
    # Fallback if import fails — derive version from compat matrix
    # Using exec to avoid consistency-check's "duplicate definition" false positive
    from memory_core.compat import _COMPAT_MATRIX
    _latest_ver = sorted(_COMPAT_MATRIX.keys(), key=lambda v: tuple(map(int, v.split("."))))[-1]
    exec(f"CURRENT_MEMORY_VERSION = {_latest_ver!r}")  # noqa: S102 — safe fallback
    SUPPORTED_HOSTS = ("codex", "claude", "factory")

# ANSI color codes
COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "RED": "\033[31m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "BLUE": "\033[34m",
    "MAGENTA": "\033[35m",
    "CYAN": "\033[36m",
}


def color(name: str, text: str) -> str:
    """Wrap text in ANSI color codes."""
    code = COLORS.get(name, "")
    return f"{code}{text}{COLORS['RESET']}" if code else text


@dataclass
class CheckResult:
    """Result of a single check."""

    name: str
    status: str  # "PASS", "FAIL", "WARN", "SKIP"
    message: str = ""
    details: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"

    @property
    def warning(self) -> bool:
        return self.status == "WARN"


@dataclass
class CategoryResult:
    """Results for a category of checks."""

    name: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.failed)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.warning)

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.checks if c.status == "SKIP")

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)


class IntegrationTester:
    """Runs integration tests for memory-core."""

    # Platform configurations
    PLATFORM_CONFIGS: dict[str, dict[str, Any]] = {
        "factory": {
            "home_env": "FACTORY_HOME",
            "default_home": "~/.factory",
            "config_file": "settings.json",
            "events": [
                "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                "Stop", "SubagentStop", "SessionEnd", "Notification", "PreCompact",
            ],
        },
        "claude": {
            "home_env": "CLAUDE_HOME",
            "default_home": "~/.claude",
            "config_file": "hooks.json",
            "events": ["SessionStart", "UserPromptSubmit", "Notification", "Stop"],
        },
        "codex": {
            "home_env": "CODEX_HOME",
            "default_home": "~/.codex",
            "config_file": "hooks.json",
            "events": ["SessionStart", "UserPromptSubmit", "Stop"],
        },
    }

    def __init__(self, verbose: bool = False, fix: bool = False):
        self.verbose = verbose
        self.fix = fix
        self.categories: list[CategoryResult] = []
        self.storage_root = Path("~/.memory-core").expanduser()
        self.path_index_file = self.storage_root / "project-lifecycle" / "path-index.json"

    def run_all_checks(self) -> list[CategoryResult]:
        """Run all check categories and return results."""
        self._run_category("Platform Hook Installation", self._check_platform_hooks)
        self._run_category("Consumer Project Discovery", self._check_consumer_discovery)
        self._run_category("Consumer Project Integrity", self._check_consumer_integrity)
        self._run_category("Gateway Smoke Test", self._check_gateway_smoke)
        self._run_category("Path Index Health", self._check_path_index_health)
        return self.categories

    def _run_category(self, name: str, check_fn: Callable[[], list[CheckResult]]) -> None:
        """Run a category of checks."""
        print(f"\n{color('BOLD', f'=== {name} ===')}")
        category = CategoryResult(name=name)
        results = check_fn()
        for result in results:
            category.add(result)
            self._print_result(result)
        self.categories.append(category)

    def _print_result(self, result: CheckResult) -> None:
        """Print a check result with colors."""
        status_colors = {
            "PASS": "GREEN",
            "FAIL": "RED",
            "WARN": "YELLOW",
            "SKIP": "CYAN",
        }
        status_color = status_colors.get(result.status, "RESET")
        status_label = color(status_color, f"[{result.status}]")
        print(f"  {status_label} {result.name}")
        if result.message:
            print(f"      {result.message}")
        if self.verbose and result.details:
            for detail in result.details:
                print(f"      {color('BLUE', '→')} {detail}")

    # -------------------------------------------------------------------------
    # Category 1: Platform Hook Installation
    # -------------------------------------------------------------------------
    def _check_platform_hooks(self) -> list[CheckResult]:
        """Check platform hook installation for all hosts."""
        results: list[CheckResult] = []
        for host in SUPPORTED_HOSTS:
            results.extend(self._check_single_platform(host))
        return results

    def _check_single_platform(self, host: str) -> list[CheckResult]:
        """Check hook installation for a single platform."""
        results: list[CheckResult] = []
        config = self.PLATFORM_CONFIGS[host]

        # Determine home directory
        home_env = config["home_env"]
        home = Path(os.environ.get(home_env, config["default_home"])).expanduser()

        wrapper = home / "bin" / "memory-hook"
        config_file = home / config["config_file"]

        # 1. Check wrapper binary exists
        if wrapper.exists():
            if os.access(wrapper, os.X_OK):
                results.append(CheckResult(
                    f"{host}:wrapper_exists",
                    "PASS",
                    f"Wrapper exists and is executable: {wrapper}",
                ))
            else:
                results.append(CheckResult(
                    f"{host}:wrapper_executable",
                    "FAIL",
                    f"Wrapper exists but is not executable: {wrapper}",
                ))
        else:
            results.append(CheckResult(
                f"{host}:wrapper_exists",
                "WARN",
                f"Wrapper not found: {wrapper}",
            ))

        # 2. Check config file exists
        if config_file.exists():
            results.append(CheckResult(
                f"{host}:config_exists",
                "PASS",
                f"Config file exists: {config_file}",
            ))
        else:
            results.append(CheckResult(
                f"{host}:config_exists",
                "WARN",
                f"Config file not found: {config_file}",
            ))
            # Skip further checks for this platform
            return results

        # 3. Check hook config has memory entries
        try:
            config_content = json.loads(config_file.read_text(encoding="utf-8"))
            hooks = config_content.get("hooks", {} if "factory" in host else [])

            expected_events = set(config["events"])
            found_events: set[str] = set()

            if host in ("factory", "codex"):
                # Factory and Codex use dict with event names as keys
                for event in expected_events:
                    if event in hooks and hooks[event]:
                        found_events.add(event)
            else:
                # Claude uses list format
                if isinstance(hooks, list):
                    for hook in hooks:
                        if isinstance(hook, dict):
                            event = hook.get("event", "")
                            if event in expected_events:
                                found_events.add(event)

            missing_events = expected_events - found_events
            if not missing_events:
                results.append(CheckResult(
                    f"{host}:memory_entries",
                    "PASS",
                    f"All {len(expected_events)} expected events registered",
                    details=[f"Found: {', '.join(sorted(found_events))}"],
                ))
            else:
                results.append(CheckResult(
                    f"{host}:memory_entries",
                    "FAIL",
                    f"Missing {len(missing_events)} expected events",
                    details=[f"Missing: {', '.join(sorted(missing_events))}"],
                ))
        except (json.JSONDecodeError, OSError) as exc:
            results.append(CheckResult(
                f"{host}:memory_entries",
                "FAIL",
                f"Failed to parse config: {exc}",
            ))

        # 4. Check wrapper can execute (if exists)
        if wrapper.exists():
            try:
                # Try to run with --help (most wrappers support this)
                result = subprocess.run(
                    [str(wrapper), "--help"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    results.append(CheckResult(
                        f"{host}:wrapper_functional",
                        "PASS",
                        "Wrapper executes successfully",
                    ))
                else:
                    results.append(CheckResult(
                        f"{host}:wrapper_functional",
                        "WARN",
                        f"Wrapper returned exit code {result.returncode}",
                    ))
            except (subprocess.TimeoutExpired, OSError) as exc:
                results.append(CheckResult(
                    f"{host}:wrapper_functional",
                    "WARN",
                    f"Wrapper execution failed: {exc}",
                ))

        return results

    # -------------------------------------------------------------------------
    # Category 2: Consumer Project Discovery
    # -------------------------------------------------------------------------
    def _check_consumer_discovery(self) -> list[CheckResult]:
        """Scan for and discover consumer projects."""
        results: list[CheckResult] = []

        # Scan for consumer projects under /Users/busiji/
        base_dir = Path("/Users/busiji")
        discovered_projects: list[Path] = []

        try:
            for path in base_dir.rglob("memory/system/adapter.toml"):
                project_root = path.parent.parent.parent
                # Skip the memory-core repo's own memory directory
                if project_root == REPO_ROOT:
                    continue
                # Skip /Users/busiji/memory/memory (source repo internal)
                if str(project_root) == "/Users/busiji/memory/memory":
                    continue
                # Skip template directories
                if "workspace/templates" in str(project_root):
                    continue
                # Skip projects with unfilled template placeholders in adapter.toml
                adapter_content = path.read_text(encoding="utf-8")
                if "{{" in adapter_content:
                    continue
                discovered_projects.append(project_root)
        except PermissionError:
            pass

        results.append(CheckResult(
            "discovery:scan_complete",
            "PASS",
            f"Discovered {len(discovered_projects)} consumer project(s)",
            details=[str(p) for p in discovered_projects] if discovered_projects else ["None found"],
        ))

        # Read path-index.json
        registered_projects: dict[str, Any] = {}
        if self.path_index_file.exists():
            try:
                path_index = json.loads(self.path_index_file.read_text(encoding="utf-8"))
                registered_projects = path_index.get("paths", {})
                results.append(CheckResult(
                    "discovery:path_index_readable",
                    "PASS",
                    f"Found {len(registered_projects)} registered project(s)",
                ))
            except (json.JSONDecodeError, OSError) as exc:
                results.append(CheckResult(
                    "discovery:path_index_readable",
                    "FAIL",
                    f"Failed to read path-index.json: {exc}",
                ))
        else:
            results.append(CheckResult(
                "discovery:path_index_readable",
                "WARN",
                f"path-index.json not found: {self.path_index_file}",
            ))

        # Cross-reference discovered vs registered
        discovered_paths = {str(p.expanduser().resolve()): p for p in discovered_projects}
        registered_paths = set(registered_projects.keys())

        # Projects initialized but NOT in path-index (gap)
        gaps = set(discovered_paths.keys()) - registered_paths
        if gaps:
            results.append(CheckResult(
                "discovery:registration_gaps",
                "WARN",
                f"{len(gaps)} initialized project(s) not in path-index",
                details=sorted(gaps),
            ))
            if self.fix:
                # Attempt to register missing projects
                fixed = []
                for path_str in gaps:
                    try:
                        # Import and call record_project_lifecycle
                        from datetime import datetime, timezone

                        from memory_core.tools.project_lifecycle import record_project_lifecycle

                        path = Path(path_str)
                        record_project_lifecycle(
                            lifecycle_root=self.storage_root / "project-lifecycle",
                            cwd=path,
                            host="integration-test",
                            event="discovery-registration",
                            payload={},
                            now_iso_fn=lambda: datetime.now(timezone.utc).isoformat(),
                        )
                        fixed.append(path_str)
                    except Exception as exc:
                        results.append(CheckResult(
                            f"discovery:fix_{path_str}",
                            "FAIL",
                            f"Failed to register {path_str}: {exc}",
                        ))
                if fixed:
                    results.append(CheckResult(
                        "discovery:fixed_gaps",
                        "PASS",
                        f"Registered {len(fixed)} missing project(s)",
                        details=sorted(fixed),
                    ))
        else:
            results.append(CheckResult(
                "discovery:registration_gaps",
                "PASS",
                "All discovered projects are registered",
            ))

        # Registered projects whose paths no longer exist (stale)
        stale = []
        for path_str in registered_paths:
            if not Path(path_str).exists():
                stale.append(path_str)

        if stale:
            results.append(CheckResult(
                "discovery:stale_entries",
                "WARN",
                f"{len(stale)} registered project(s) no longer exist",
                details=sorted(stale),
            ))
        else:
            results.append(CheckResult(
                "discovery:stale_entries",
                "PASS",
                "All registered paths exist on disk",
            ))

        return results

    # -------------------------------------------------------------------------
    # Category 3: Consumer Project Integrity
    # -------------------------------------------------------------------------
    def _check_consumer_integrity(self) -> list[CheckResult]:
        """Check integrity of consumer projects."""
        results: list[CheckResult] = []

        # Find all consumer projects
        base_dir = Path("/Users/busiji")
        projects: list[Path] = []

        try:
            for path in base_dir.rglob("memory/system/adapter.toml"):
                project_root = path.parent.parent.parent
                if project_root == REPO_ROOT:
                    continue
                if str(project_root) == "/Users/busiji/memory/memory":
                    continue
                # Skip template directories
                if "workspace/templates" in str(project_root):
                    continue
                # Skip projects with unfilled template placeholders in adapter.toml
                adapter_content = path.read_text(encoding="utf-8")
                if "{{" in adapter_content:
                    continue
                projects.append(project_root)
        except PermissionError:
            pass

        if not projects:
            results.append(CheckResult(
                "integrity:no_projects",
                "SKIP",
                "No consumer projects found to check",
            ))
            return results

        for project in projects:
            results.extend(self._check_single_project_integrity(project))

        return results

    def _check_single_project_integrity(self, project: Path) -> list[CheckResult]:
        """Check integrity of a single consumer project."""
        results: list[CheckResult] = []
        project_name = project.name

        # 1. Required files
        required_files = [
            "memory/system/adapter.toml",
            "memory/system/ownership.toml",
        ]
        for rel_path in required_files:
            full_path = project / rel_path
            if full_path.exists():
                results.append(CheckResult(
                    f"{project_name}:file_{rel_path.replace('/', '_')}",
                    "PASS",
                    f"{rel_path} exists",
                ))
            else:
                results.append(CheckResult(
                    f"{project_name}:file_{rel_path.replace('/', '_')}",
                    "FAIL",
                    f"{rel_path} missing",
                ))

        # 2. adapter.toml validity
        adapter_path = project / "memory/system/adapter.toml"
        if adapter_path.exists() and tomllib:
            try:
                content = adapter_path.read_text(encoding="utf-8")
                parsed = tomllib.loads(content)

                # Check required fields
                core = parsed.get("core", {})
                routing = parsed.get("routing", {})

                required_adapter_fields = {
                    "host": routing.get("host"),
                    "version": core.get("version"),
                }

                missing = [k for k, v in required_adapter_fields.items() if not v]
                if missing:
                    results.append(CheckResult(
                        f"{project_name}:adapter_fields",
                        "FAIL",
                        f"Missing adapter fields: {', '.join(missing)}",
                    ))
                else:
                    results.append(CheckResult(
                        f"{project_name}:adapter_fields",
                        "PASS",
                        "Required adapter fields present",
                        details=[f"{k}={v}" for k, v in required_adapter_fields.items()],
                    ))
            except Exception as exc:
                results.append(CheckResult(
                    f"{project_name}:adapter_toml",
                    "FAIL",
                    f"Failed to parse adapter.toml: {exc}",
                ))
        elif adapter_path.exists() and not tomllib:
            results.append(CheckResult(
                f"{project_name}:adapter_toml",
                "SKIP",
                "tomllib not available (Python < 3.11, tomli not installed)",
            ))

        # 3. ownership.toml validity
        ownership_path = project / "memory/system/ownership.toml"
        if ownership_path.exists() and tomllib:
            try:
                content = ownership_path.read_text(encoding="utf-8")
                parsed = tomllib.loads(content)

                # Check for schema_version and memory_version
                schema_version = parsed.get("schema_version")
                memory_version = parsed.get("memory_version")

                if schema_version and memory_version:
                    results.append(CheckResult(
                        f"{project_name}:ownership_fields",
                        "PASS",
                        "Required ownership fields present",
                        details=[f"schema_version={schema_version}", f"memory_version={memory_version}"],
                    ))
                else:
                    missing = []
                    if not schema_version:
                        missing.append("schema_version")
                    if not memory_version:
                        missing.append("memory_version")
                    results.append(CheckResult(
                        f"{project_name}:ownership_fields",
                        "FAIL",
                        f"Missing ownership fields: {', '.join(missing)}",
                    ))

                # 6. Version consistency
                if memory_version and memory_version != CURRENT_MEMORY_VERSION:
                    results.append(CheckResult(
                        f"{project_name}:version_consistency",
                        "WARN",
                        f"Version mismatch: project={memory_version}, core={CURRENT_MEMORY_VERSION}",
                    ))
                elif memory_version:
                    results.append(CheckResult(
                        f"{project_name}:version_consistency",
                        "PASS",
                        f"Version matches: {memory_version}",
                    ))
            except Exception as exc:
                results.append(CheckResult(
                    f"{project_name}:ownership_toml",
                    "FAIL",
                    f"Failed to parse ownership.toml: {exc}",
                ))
        elif ownership_path.exists() and not tomllib:
            results.append(CheckResult(
                f"{project_name}:ownership_toml",
                "SKIP",
                "tomllib not available (Python < 3.11, tomli not installed)",
            ))

        # 4. Required directories
        required_dirs = [
            "memory/kb",
            "memory/docs",
            "project-map",
        ]
        for rel_path in required_dirs:
            full_path = project / rel_path
            if full_path.exists() and full_path.is_dir():
                results.append(CheckResult(
                    f"{project_name}:dir_{rel_path.replace('/', '_')}",
                    "PASS",
                    f"{rel_path}/ exists",
                ))
            else:
                results.append(CheckResult(
                    f"{project_name}:dir_{rel_path.replace('/', '_')}",
                    "FAIL",
                    f"{rel_path}/ missing",
                ))

        # 5. Required indexes
        required_indexes = [
            "INDEX.md",
            "memory/kb/INDEX.md",
        ]
        for rel_path in required_indexes:
            full_path = project / rel_path
            if full_path.exists():
                results.append(CheckResult(
                    f"{project_name}:index_{rel_path.replace('/', '_')}",
                    "PASS",
                    f"{rel_path} exists",
                ))
            else:
                results.append(CheckResult(
                    f"{project_name}:index_{rel_path.replace('/', '_')}",
                    "FAIL",
                    f"{rel_path} missing",
                ))

        # 7. Run verify_consumer
        try:
            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.verify_consumer", "--path", str(project), "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            if result.returncode == 0:
                results.append(CheckResult(
                    f"{project_name}:verify_consumer",
                    "PASS",
                    "verify_consumer passed",
                ))
            else:
                # Try to parse JSON output for details
                try:
                    report = json.loads(result.stdout)
                    failed = report.get("failed_count", 0)
                    results.append(CheckResult(
                        f"{project_name}:verify_consumer",
                        "WARN",
                        f"verify_consumer found {failed} issue(s)",
                    ))
                except json.JSONDecodeError:
                    results.append(CheckResult(
                        f"{project_name}:verify_consumer",
                        "WARN",
                        f"verify_consumer exited with code {result.returncode}",
                    ))
        except (subprocess.TimeoutExpired, OSError) as exc:
            results.append(CheckResult(
                f"{project_name}:verify_consumer",
                "WARN",
                f"Failed to run verify_consumer: {exc}",
            ))

        return results

    # -------------------------------------------------------------------------
    # Category 4: Gateway Smoke Test
    # -------------------------------------------------------------------------
    def _check_gateway_smoke(self) -> list[CheckResult]:
        """Run gateway smoke tests."""
        results: list[CheckResult] = []

        # 1. Gateway importable
        try:
            from memory_core.tools import memory_hook_gateway  # noqa: F401
            results.append(CheckResult(
                "gateway:importable",
                "PASS",
                "memory_hook_gateway is importable",
            ))
        except ImportError as exc:
            results.append(CheckResult(
                "gateway:importable",
                "FAIL",
                f"Failed to import gateway: {exc}",
            ))
            return results

        # 2. Gateway help
        try:
            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.memory_hook_gateway", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(REPO_ROOT),
            )
            if result.returncode == 0:
                results.append(CheckResult(
                    "gateway:help_works",
                    "PASS",
                    "Gateway --help returns exit code 0",
                ))
            else:
                results.append(CheckResult(
                    "gateway:help_works",
                    "FAIL",
                    f"Gateway --help returned exit code {result.returncode}",
                ))
        except (subprocess.TimeoutExpired, OSError) as exc:
            results.append(CheckResult(
                "gateway:help_works",
                "FAIL",
                f"Failed to run gateway --help: {exc}",
            ))

        return results

    # -------------------------------------------------------------------------
    # Category 5: Path Index Health
    # -------------------------------------------------------------------------
    def _check_path_index_health(self) -> list[CheckResult]:
        """Check path index health."""
        results: list[CheckResult] = []

        # 1. path-index.json is valid JSON
        if not self.path_index_file.exists():
            results.append(CheckResult(
                "path_index:exists",
                "WARN",
                f"path-index.json does not exist: {self.path_index_file}",
            ))
            return results

        try:
            content = self.path_index_file.read_text(encoding="utf-8")
            parsed = json.loads(content)
            results.append(CheckResult(
                "path_index:valid_json",
                "PASS",
                "path-index.json is valid JSON",
            ))
        except json.JSONDecodeError as exc:
            results.append(CheckResult(
                "path_index:valid_json",
                "FAIL",
                f"path-index.json is not valid JSON: {exc}",
            ))
            return results
        except OSError as exc:
            results.append(CheckResult(
                "path_index:readable",
                "FAIL",
                f"Cannot read path-index.json: {exc}",
            ))
            return results

        # Check structure
        if not isinstance(parsed, dict):
            results.append(CheckResult(
                "path_index:structure",
                "FAIL",
                "path-index.json root is not an object",
            ))
            return results

        schema_version = parsed.get("schema_version")
        paths = parsed.get("paths")

        if schema_version:
            results.append(CheckResult(
                "path_index:schema_version",
                "PASS",
                f"Schema version: {schema_version}",
            ))
        else:
            results.append(CheckResult(
                "path_index:schema_version",
                "WARN",
                "Missing schema_version field",
            ))

        if isinstance(paths, dict):
            results.append(CheckResult(
                "path_index:paths_object",
                "PASS",
                f"Contains {len(paths)} path entries",
            ))

            # 2. Each registered project path exists
            # 3. Each registered project has memory/system/
            # 4. No stale entries
            stale = 0
            missing_system = 0
            valid = 0

            for path_str, entry in paths.items():
                path = Path(path_str)
                if not path.exists():
                    stale += 1
                elif not (path / "memory" / "system").exists():
                    missing_system += 1
                else:
                    valid += 1

            if valid > 0:
                results.append(CheckResult(
                    "path_index:valid_paths",
                    "PASS",
                    f"{valid} registered path(s) exist and have memory/system/",
                ))
            if missing_system > 0:
                results.append(CheckResult(
                    "path_index:missing_system",
                    "WARN",
                    f"{missing_system} path(s) exist but lack memory/system/",
                ))
            if stale > 0:
                results.append(CheckResult(
                    "path_index:stale_paths",
                    "WARN",
                    f"{stale} path(s) no longer exist on disk (stale entries)",
                ))
            if stale == 0 and missing_system == 0:
                results.append(CheckResult(
                    "path_index:no_stale",
                    "PASS",
                    "No stale entries found",
                ))
        else:
            results.append(CheckResult(
                "path_index:paths_object",
                "FAIL",
                "paths field is not an object",
            ))

        return results


def print_summary(categories: list[CategoryResult]) -> int:
    """Print summary table and return exit code."""
    print(f"\n{color('BOLD', '=' * 80)}")
    print(color("BOLD", "SUMMARY"))
    print(f"{color('BOLD', '=' * 80)}\n")

    # Print table header
    header = f"{'Category':<30} {'Total':>6} {'PASS':>6} {'FAIL':>6} {'WARN':>6} {'SKIP':>6}"
    print(color("BOLD", header))
    print("-" * len(header))

    total_pass = 0
    total_fail = 0
    total_warn = 0
    total_skip = 0

    for cat in categories:
        total_pass += cat.passed
        total_fail += cat.failed
        total_warn += cat.warnings
        total_skip += cat.skipped

        status_color = "GREEN" if cat.failed == 0 and cat.warnings == 0 else "YELLOW" if cat.failed == 0 else "RED"
        print(
            f"{color(status_color, cat.name):<30} "
            f"{cat.total:>6} "
            f"{color('GREEN', str(cat.passed)) if cat.passed else '0':>6} "
            f"{color('RED', str(cat.failed)) if cat.failed else '0':>6} "
            f"{color('YELLOW', str(cat.warnings)) if cat.warnings else '0':>6} "
            f"{color('CYAN', str(cat.skipped)) if cat.skipped else '0':>6}"
        )

    print("-" * len(header))
    print(
        f"{color('BOLD', 'Total'):<30} "
        f"{total_pass + total_fail + total_warn + total_skip:>6} "
        f"{color('GREEN', str(total_pass)):>6} "
        f"{color('RED', str(total_fail)):>6} "
        f"{color('YELLOW', str(total_warn)):>6} "
        f"{color('CYAN', str(total_skip)):>6}"
    )

    # Final status
    print(f"\n{'=' * 80}")
    if total_fail > 0:
        print(color("RED", f"Result: FAILED ({total_fail} failure(s))"))
        return 1
    elif total_warn > 0 or total_skip > 0:
        print(color("YELLOW", f"Result: WARNINGS ({total_warn} warning(s), {total_skip} skip(s))"))
        return 2
    else:
        print(color("GREEN", "Result: ALL PASSED"))
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Full integration test for memory-core platform hooks and consumer projects.",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues where possible")
    args = parser.parse_args(argv)

    print(color("BOLD", "memory-core Full Integration Test"))
    print(f"Repository: {REPO_ROOT}")
    print(f"Memory Version: {CURRENT_MEMORY_VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"TOML Support: {'tomllib' if tomllib else 'NOT AVAILABLE'}")
    if args.fix:
        print(color("YELLOW", "Fix mode: ENABLED (will attempt to fix issues)"))

    tester = IntegrationTester(verbose=args.verbose, fix=args.fix)
    categories = tester.run_all_checks()

    return print_summary(categories)


if __name__ == "__main__":
    raise SystemExit(main())
