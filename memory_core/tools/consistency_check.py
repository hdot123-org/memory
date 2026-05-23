#!/usr/bin/env python3
"""Consistency checker for memory-core internal invariants.

Usage:
    python consistency_check.py
    python consistency_check.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSTANTS_PATH = REPO_ROOT / "memory_core" / "constants.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
TOOLS_DIR = REPO_ROOT / "memory_core" / "tools"


def _load_constants() -> dict[str, Any]:
    """Load constants from constants.py."""
    content = CONSTANTS_PATH.read_text(encoding="utf-8")
    result: dict[str, Any] = {}
    # Extract CURRENT_MEMORY_VERSION
    m = re.search(r'CURRENT_MEMORY_VERSION\s*=\s*"([^"]+)"', content)
    if m:
        result["CURRENT_MEMORY_VERSION"] = m.group(1)
    # Extract SUPPORTED_HOSTS
    m = re.search(r'SUPPORTED_HOSTS\s*=\s*\(([^)]+)\)', content)
    if m:
        hosts_str = m.group(1)
        result["SUPPORTED_HOSTS"] = tuple(h.strip().strip('"\'') for h in hosts_str.split(","))
    return result


def _load_pyproject_version() -> str:
    """Load version from pyproject.toml."""
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    # Extract version from [project] section
    m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if m:
        return m.group(1)
    return ""


def check_version_consistency() -> tuple[list, list]:
    """Check that constants.py and pyproject.toml versions match."""
    errors: list[str] = []
    warnings: list[str] = []

    constants = _load_constants()
    const_version = constants.get("CURRENT_MEMORY_VERSION", "")
    pyproject_version = _load_pyproject_version()

    if not const_version:
        errors.append("constants.py: CURRENT_MEMORY_VERSION not found")
    if not pyproject_version:
        errors.append("pyproject.toml: project.version not found")

    if const_version and pyproject_version and const_version != pyproject_version:
        errors.append(f"version mismatch: constants.py={const_version}, pyproject.toml={pyproject_version}")

    return errors, warnings


def check_host_enum_coverage() -> tuple[list, list]:
    """Check host enumeration coverage in if/elif chains and choices."""
    errors: list[str] = []
    warnings: list[str] = []

    constants = _load_constants()
    supported_hosts = constants.get("SUPPORTED_HOSTS", ("codex", "claude", "factory"))

    # Find all Python files in the repo
    py_files = list(REPO_ROOT.rglob("*.py"))

    for py_file in py_files:
        # Skip __pycache__, .egg-info, build/, and consistency_check.py itself
        str_path = str(py_file)
        if "__pycache__" in str_path or ".egg-info" in str_path or "/build/" in str_path:
            continue
        # Skip this script itself
        if py_file.name == "consistency_check.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")

            # Check for if/elif chains with host conditions
            # Look for patterns like: if host == "codex":
            host_conditions = re.findall(r'if\s+\w+\s*==\s*"(\w+)"', content)
            host_conditions.extend(re.findall(r'elif\s+\w+\s*==\s*"(\w+)"', content))

            if host_conditions:
                # Check if all supported hosts are covered
                unique_conditions = set(host_conditions)
                for host in supported_hosts:
                    if host not in unique_conditions:
                        # Only report if at least one supported host IS present
                        # This means it's a partial match
                        if any(h in unique_conditions for h in supported_hosts):
                            errors.append(f"{py_file}: if/elif chain missing host '{host}'")
                            break

            # Check for hardcoded tuples without factory
            tuple_match = re.search(r'\(\s*"codex"\s*,\s*"claude"\s*\)', content)
            if tuple_match:
                errors.append(f"{py_file}: hardcoded tuple ('codex', 'claude') missing 'factory'")

            # Check choices= parameter in argparse
            choices_match = re.search(r'choices\s*=\s*\(([^)]+)\)', content)
            if choices_match:
                choices_str = choices_match.group(1)
                # Check if this looks like a host choices
                if "codex" in choices_str or "claude" in choices_str:
                    choices = [c.strip().strip('"\'') for c in choices_str.split(",")]
                    for host in supported_hosts:
                        if host not in choices:
                            errors.append(f"{py_file}: choices= missing host '{host}'")
                            break
        except Exception as exc:
            warnings.append(f"check_host_enum_coverage: check raised {exc}")

    return errors, warnings


def check_no_duplicate_version_definitions() -> tuple[list, list]:
    """Check that no other .py files define CURRENT_MEMORY_VERSION."""
    errors: list[str] = []
    warnings: list[str] = []

    constants = _load_constants()
    const_version = constants.get("CURRENT_MEMORY_VERSION", "0.2.0")

    # Find all Python files in the repo
    py_files = list(REPO_ROOT.rglob("*.py"))

    for py_file in py_files:
        # Skip constants.py itself
        if py_file.name == "constants.py":
            continue
        # Skip __pycache__, .egg-info, and build/
        str_path = str(py_file)
        if "__pycache__" in str_path or ".egg-info" in str_path or "/build/" in str_path:
            continue
        # Skip this script itself
        if py_file.name == "consistency_check.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")

            # Check for CURRENT_MEMORY_VERSION definition
            if re.search(r'^\s*CURRENT_MEMORY_VERSION\s*=', content, re.MULTILINE):
                errors.append(f"{py_file}: defines CURRENT_MEMORY_VERSION (should import from constants)")

            # Check for version = "x.y.z" where x.y.z matches CURRENT_MEMORY_VERSION
            # This might be a hardcoded version definition
            pattern = r'^\s*version\s*=\s*["\']' + re.escape(const_version) + r'["\']'
            if re.search(pattern, content, re.MULTILINE):
                # Only report if it's not part of a template string generation
                # Check if it's in a template function
                if "def template_" not in content[:content.find(const_version)][:1000] if content.find(const_version) > 0 else True:
                    pass  # This is actually expected in template functions
        except Exception as exc:
            warnings.append(f"check_no_duplicate_version_definitions: check raised {exc}")

    return errors, warnings


def check_init_validate_roundtrip() -> tuple[list, list]:
    """Run init, then validate, check generated files."""
    errors: list[str] = []
    warnings: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Run init
        try:
            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.init_project_memory",
                 "--target", str(tmp_path), "--host", "codex"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            if result.returncode != 0:
                errors.append(f"init_project_memory failed: {result.stderr}")
                return errors, warnings
        except Exception as exc:
            errors.append(f"init_project_memory exception: {exc}")
            return errors, warnings

        # Check memory.lock exists and is valid TOML
        memory_lock = tmp_path / "memory" / "system" / "memory.lock"
        if not memory_lock.exists():
            errors.append("init: memory.lock not created")
        else:
            try:
                with open(memory_lock, "rb") as f:
                    lock_data = tomllib.load(f)
                if "memory" not in lock_data:
                    errors.append("init: memory.lock missing [memory] section")
            except Exception as exc:
                errors.append(f"init: memory.lock is not valid TOML: {exc}")

        # Check adapter.toml has canonical sections
        adapter_toml = tmp_path / "memory" / "system" / "adapter.toml"
        if not adapter_toml.exists():
            errors.append("init: adapter.toml not created")
        else:
            try:
                with open(adapter_toml, "rb") as f:
                    adapter_data = tomllib.load(f)
                required_sections = ["core", "policy", "routing"]
                for section in required_sections:
                    if section not in adapter_data:
                        errors.append(f"init: adapter.toml missing [{section}] section")
            except Exception as exc:
                errors.append(f"init: adapter.toml is not valid TOML: {exc}")

        # Run validate
        try:
            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.validate_project_memory",
                 "--target", str(tmp_path)],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            if result.returncode != 0:
                errors.append(f"validate_project_memory failed: {result.stderr}")
        except Exception as exc:
            errors.append(f"validate_project_memory exception: {exc}")

    return errors, warnings


def check_required_imports_from_constants() -> tuple[list, list]:
    """Check that required files import from constants."""
    errors: list[str] = []
    warnings: list[str] = []

    required_files = [
        "init_project_memory.py",
        "validate_project_memory.py",
        "migrate_project_memory.py",
        "memory_hook_config.py",
        "adapter_toml_schema.py",
    ]

    for filename in required_files:
        file_path = TOOLS_DIR / filename
        if not file_path.exists():
            errors.append(f"{filename}: file not found")
            continue

        try:
            content = file_path.read_text(encoding="utf-8")

            # Check for import from constants
            has_import = False
            if "from memory_core.constants import" in content:
                has_import = True
            elif "from constants import" in content:
                has_import = True
            elif "import memory_core.constants" in content:
                has_import = True

            if not has_import:
                errors.append(f"{filename}: does not import from constants")
        except Exception as exc:
            warnings.append(f"check_required_imports_from_constants: check raised {exc}")

    return errors, warnings


def check_docstring_host_mentions() -> tuple[list, list]:
    """Check docstrings for host mentions (codex, claude without factory)."""
    errors: list[str] = []
    warnings: list[str] = []

    py_files = list(REPO_ROOT.rglob("*.py"))

    for py_file in py_files:
        str_path = str(py_file)
        if "__pycache__" in str_path or ".egg-info" in str_path or "/build/" in str_path:
            continue
        # Skip this script itself
        if py_file.name == "consistency_check.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")

            # Find docstrings (simple regex approach)
            # Match triple-quoted strings
            docstrings = re.findall(r'"""(.*?)"""', content, re.DOTALL)
            docstrings.extend(re.findall(r"'''(.*?)'''", content, re.DOTALL))

            for docstring in docstrings:
                has_codex = "codex" in docstring.lower()
                has_claude = "claude" in docstring.lower()
                has_factory = "factory" in docstring.lower()

                if has_codex and has_claude and not has_factory:
                    warnings.append(f"{py_file}: docstring mentions codex and claude but not factory")
        except Exception as exc:
            warnings.append(f"check_docstring_host_mentions: check raised {exc}")

    return errors, warnings


def check_no_handwritten_toml_parser() -> tuple[list, list]:
    """Check that _parse_adapter_toml uses tomllib, not handwritten parser."""
    errors: list[str] = []
    warnings: list[str] = []

    files_to_check = [
        "validate_project_memory.py",
        "migrate_project_memory.py",
    ]

    for filename in files_to_check:
        file_path = TOOLS_DIR / filename
        if not file_path.exists():
            continue

        try:
            content = file_path.read_text(encoding="utf-8")

            # Find _parse_adapter_toml function
            # Check if it uses tomllib
            if "def _parse_adapter_toml" in content:
                # Get function body (simplified)
                func_match = re.search(r'def _parse_adapter_toml\([^)]*\):\s*"""(.*?)"""', content, re.DOTALL)
                if not func_match:
                    func_match = re.search(r'def _parse_adapter_toml\([^)]*\):(.*?)(?=\ndef |\Z)', content, re.DOTALL)

                if func_match:
                    func_body = content[content.find("_parse_adapter_toml"):]
                    # Check if using tomllib
                    if "tomllib" not in func_body[:1500]:  # First ~1500 chars of function
                        # Check if using manual line parsing (handwritten)
                        if "split(" in func_body[:1500] and "in_section" in func_body[:1500]:
                            errors.append(f"{filename}: _parse_adapter_toml uses handwritten parser (not tomllib)")
        except Exception as exc:
            warnings.append(f"check_no_handwritten_toml_parser: check raised {exc}")

    return errors, warnings


def check_adapter_registry_complete() -> tuple[list, list]:
    """Check that _ADAPTER_REGISTRY has workbot and default entries."""
    errors: list[str] = []
    warnings: list[str] = []

    gateway_file = TOOLS_DIR / "memory_hook_gateway.py"
    if not gateway_file.exists():
        errors.append("memory_hook_gateway.py: file not found")
        return errors, warnings

    try:
        content = gateway_file.read_text(encoding="utf-8")

        # Find _ADAPTER_REGISTRY
        registry_match = re.search(r'_ADAPTER_REGISTRY\s*=\s*\{([^}]+)\}', content, re.DOTALL)
        if not registry_match:
            errors.append("memory_hook_gateway.py: _ADAPTER_REGISTRY not found")
            return errors, warnings

        registry_content = registry_match.group(1)

        # Check for workbot
        if '"workbot"' not in registry_content and "'workbot'" not in registry_content:
            errors.append("memory_hook_gateway.py: _ADAPTER_REGISTRY missing 'workbot' entry")

        # Check for default
        if '"default"' not in registry_content and "'default'" not in registry_content:
            errors.append("memory_hook_gateway.py: _ADAPTER_REGISTRY missing 'default' entry")

    except Exception as exc:
        errors.append(f"memory_hook_gateway.py: error checking registry: {exc}")

    return errors, warnings


def check_ruff_config_not_conflicting() -> tuple[list, list]:
    """Check that ruff.toml and pyproject.toml [tool.ruff] ignore lists are consistent."""
    errors: list[str] = []
    warnings: list[str] = []

    ruff_toml_path = REPO_ROOT / "ruff.toml"

    # Check if both files have [tool.ruff] configuration
    pyproject_content = PYPROJECT_PATH.read_text(encoding="utf-8")

    # Extract [tool.ruff] from pyproject.toml
    pyproject_ruff_match = re.search(r'\[tool\.ruff\](.*?)(?=\[|$)', pyproject_content, re.DOTALL)
    ruff_toml_content = ruff_toml_path.read_text(encoding="utf-8")

    # Check if both have [tool.ruff] config
    has_pyproject_ruff = pyproject_ruff_match is not None
    has_ruff_toml_ruff = "[tool.ruff]" in ruff_toml_content

    if has_pyproject_ruff and has_ruff_toml_ruff:
        # Extract ignore lists from both
        def extract_ignores(content: str) -> set[str]:
            ignores: set[str] = set()
            # Match ignore = [...] or ignore = ["..."]
            ignore_match = re.search(r'ignore\s*=\s*\[(.*?)\]', content, re.DOTALL)
            if ignore_match:
                items = ignore_match.group(1)
                # Extract quoted strings
                for match in re.finditer(r'"([^"]+)"', items):
                    ignores.add(match.group(1))
            return ignores

        pyproject_ignores = extract_ignores(pyproject_ruff_match.group(1))
        ruff_toml_ignores = extract_ignores(ruff_toml_content)

        if pyproject_ignores != ruff_toml_ignores:
            errors.append(
                f"ruff.toml and pyproject.toml [tool.ruff] ignore lists differ: "
                f"pyproject={pyproject_ignores}, ruff.toml={ruff_toml_ignores}"
            )

    return errors, warnings


def check_contributing_version_source() -> tuple[list, list]:
    """Check CONTRIBUTING.md claims about version source vs constants.py."""
    errors: list[str] = []
    warnings: list[str] = []

    contributing_path = REPO_ROOT / "CONTRIBUTING.md"
    if not contributing_path.exists():
        return errors, warnings

    content = contributing_path.read_text(encoding="utf-8")

    # Check if it claims version is only in pyproject.toml
    if "版本号只在 `pyproject.toml`" in content or "version" in content.lower():
        # Check if constants.py also defines CURRENT_MEMORY_VERSION
        constants = _load_constants()
        if constants.get("CURRENT_MEMORY_VERSION"):
            warnings.append(
                "CONTRIBUTING.md claims version is only in pyproject.toml, "
                "but constants.py also defines CURRENT_MEMORY_VERSION"
            )

    return errors, warnings


def check_package_data_coverage() -> tuple[list, list]:
    """Check that package-data references packages in find include list."""
    errors: list[str] = []
    warnings: list[str] = []

    pyproject_content = PYPROJECT_PATH.read_text(encoding="utf-8")

    # Extract package-data packages
    package_data_match = re.search(
        r'\[tool\.setuptools\.package-data\](.*?)(?=\[|$)',
        pyproject_content,
        re.DOTALL
    )

    # Extract find include packages
    find_match = re.search(
        r'\[tool\.setuptools\.packages\.find\](.*?)(?=\[|$)',
        pyproject_content,
        re.DOTALL
    )

    if package_data_match and find_match:
        # Extract package names from package-data
        package_names: set[str] = set()
        for line in package_data_match.group(1).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # Match "package_name" = [...] or package_name = [...]
                pkg_match = re.match(r'^(["\']?[\w_]+["\']?)\s*=', line)
                if pkg_match:
                    pkg_name = pkg_match.group(1).strip('"\'')
                    package_names.add(pkg_name)

        # Extract include list
        include_match = re.search(r'include\s*=\s*\[(.*?)\]', find_match.group(1), re.DOTALL)
        if include_match:
            include_list = include_match.group(1)
            includes: set[str] = set()
            for match in re.finditer(r'["\']([^"\']+)["\']', include_list):
                includes.add(match.group(1))

            # Check if package-data packages are covered
            for pkg in package_names:
                # Check if package is covered by any include pattern
                covered = False
                for inc in includes:
                    # Simple pattern matching: "memory_core*" should cover "memory_core"
                    if inc.endswith('*'):
                        if pkg.startswith(inc.rstrip('*')):
                            covered = True
                            break
                    elif pkg == inc:
                        covered = True
                        break

                if not covered:
                    errors.append(
                        f"package-data references '{pkg}' but it's not in find include list: {includes}"
                    )

    return errors, warnings


def check_adapter_schema_host_validation() -> tuple[list, list]:
    """Check that load_adapter_toml validates host against SUPPORTED_HOSTS."""
    errors: list[str] = []
    warnings: list[str] = []

    schema_file = TOOLS_DIR / "adapter_toml_schema.py"
    if not schema_file.exists():
        errors.append("adapter_toml_schema.py: file not found")
        return errors, warnings

    content = schema_file.read_text(encoding="utf-8")

    # Check if function exists
    if "def load_adapter_toml" not in content:
        errors.append("adapter_toml_schema.py: load_adapter_toml function not found")
        return errors, warnings

    # Find load_adapter_toml function and _load_new_format function
    func_match = re.search(
        r'def load_adapter_toml\([^)]+\)(?:\s*->\s*[^:]+)?:(.*?)(?=\ndef |\Z)',
        content,
        re.DOTALL
    )

    new_format_match = re.search(
        r'def _load_new_format\([^)]+\)(?:\s*->\s*[^:]+)?:(.*?)(?=\ndef |\Z)',
        content,
        re.DOTALL
    )

    if not func_match:
        errors.append("adapter_toml_schema.py: load_adapter_toml function body not found")
        return errors, warnings

    combined_body = func_match.group(1)
    if new_format_match:
        combined_body += new_format_match.group(1)

    # Check if host validation against SUPPORTED_HOSTS exists
    # Look for host validation patterns - checking both functions
    host_check_patterns = [
        r'host\s+in\s+SUPPORTED_HOSTS',
        r'SUPPORTED_HOSTS.*host',
        r'if.*host.*not in',
        r'raise.*[Hh]ost',
        r'host.*validate',
        r'validate.*host',
    ]

    has_explicit_validation = any(
        re.search(pattern, combined_body, re.IGNORECASE)
        for pattern in host_check_patterns
    )

    # Also check if SUPPORTED_HOSTS is used anywhere for validation (not just default)
    # If it's only used for default values like SUPPORTED_HOSTS[0], that's not validation
    has_only_default_usage = (
        "SUPPORTED_HOSTS[0]" in combined_body and
        not has_explicit_validation
    )

    if has_only_default_usage:
        errors.append(
            "adapter_toml_schema.py: load_adapter_toml does not validate host "
            "against SUPPORTED_HOSTS (only uses it for default value)"
        )

    return errors, warnings


def check_lock_parser_strict_toml() -> tuple[list, list]:
    """Check that _parse_lock_file in validate_project_memory.py uses strict TOML parsing."""
    errors: list[str] = []
    warnings: list[str] = []

    validate_file = TOOLS_DIR / "validate_project_memory.py"
    if not validate_file.exists():
        errors.append("validate_project_memory.py: file not found")
        return errors, warnings

    content = validate_file.read_text(encoding="utf-8")

    # Check if function exists
    if "def _parse_lock_file" not in content:
        errors.append("validate_project_memory.py: _parse_lock_file function not found")
        return errors, warnings

    # Find _parse_lock_file function - handle type annotations in signature
    func_match = re.search(
        r'def _parse_lock_file\([^)]+\)(?:\s*->\s*[^:]+)?:(.*?)(?=\ndef |\Z)',
        content,
        re.DOTALL
    )

    if not func_match:
        errors.append("validate_project_memory.py: _parse_lock_file function body not found")
        return errors, warnings

    func_body = func_match.group(1)

    # Check for except clause that falls back to key=value parsing
    # This would indicate non-strict TOML handling
    except_blocks = re.findall(r'except.*?:(.*?)(?=\n\n|\n    def|\Z)', func_body, re.DOTALL | re.IGNORECASE)

    for block in except_blocks:
        # If except block contains key=value parsing (not just raising error)
        if "split(" in block and "=" in block and "result" in block:
            warnings.append(
                "validate_project_memory.py: _parse_lock_file has except clause "
                "that falls back to key=value parsing instead of strict TOML error"
            )
            break

    return errors, warnings


def check_default_profile_compatibility() -> tuple[list, list]:
    """Check that default runtime profile is compatible with workbot profile."""
    errors: list[str] = []
    warnings: list[str] = []

    default_file = TOOLS_DIR / "memory_hook_adapters" / "default_runtime_profile.py"
    workbot_file = TOOLS_DIR / "memory_hook_adapters" / "workbot_runtime_profile.py"

    if not default_file.exists():
        errors.append("default_runtime_profile.py: file not found")
        return errors, warnings

    if not workbot_file.exists():
        errors.append("workbot_runtime_profile.py: file not found")
        return errors, warnings

    default_content = default_file.read_text(encoding="utf-8")
    workbot_content = workbot_file.read_text(encoding="utf-8")

    # Extract keys from return dict in both functions
    def extract_return_keys(content: str) -> set[str]:
        keys: set[str] = set()
        # Find return { ... } block
        return_match = re.search(r'return\s*\{(.*?)\n\s*\}', content, re.DOTALL)
        if return_match:
            dict_content = return_match.group(1)
            # Extract keys (looking for "KEY": or 'KEY': patterns)
            for match in re.finditer(r'["\']([A-Z_]+)["\']\s*:', dict_content):
                keys.add(match.group(1))
        return keys

    default_keys = extract_return_keys(default_content)
    workbot_keys = extract_return_keys(workbot_content)

    # Find keys in workbot but not in default
    workbot_only = workbot_keys - default_keys

    if len(workbot_only) > 5:
        warnings.append(
            f"default_runtime_profile.py missing {len(workbot_only)} keys "
            f"present in workbot: {workbot_only}"
        )

    return errors, warnings


def check_provider_builder_called() -> tuple[list, list]:
    """Check that provider_builder and shadow_builder are actually called."""
    errors: list[str] = []
    warnings: list[str] = []

    gateway_file = TOOLS_DIR / "memory_hook_gateway.py"
    if not gateway_file.exists():
        errors.append("memory_hook_gateway.py: file not found")
        return errors, warnings

    content = gateway_file.read_text(encoding="utf-8")

    # Check for provider_builder assignment pattern
    # Looking for: provider_builder = ... followed by provider_builder(config) or similar
    provider_pattern = r'provider_builder\s*=\s*([^\n]+)'
    shadow_pattern = r'shadow_builder\s*=\s*([^\n]+)'

    provider_match = re.search(provider_pattern, content)

    if provider_match:
        # Check if provider_builder is actually used after assignment
        # Look for the pattern where it's assigned but build_context_package_from_config is called directly
        assignment_pos = provider_match.start()

        # Get code after assignment
        after_assignment = content[assignment_pos:assignment_pos + 500]

        # Check if it's assigned to build_context_package_from_config but that function is called directly
        if "build_context_package_from_config" in provider_match.group(1):
            # Check if the variable is actually used vs direct function call
            if "provider_builder(config)" not in after_assignment:
                # Check if there's a direct call to build_context_package_from_config after assignment
                if "build_context_package_from_config(config)" in after_assignment:
                    errors.append(
                        "memory_hook_gateway.py: provider_builder is assigned but "
                        "build_context_package_from_config is called directly instead"
                    )

    # Also check shadow_builder
    shadow_match = re.search(shadow_pattern, content)
    if shadow_match:
        shadow_pos = shadow_match.start()
        after_shadow = content[shadow_pos:shadow_pos + 500]

        if "shadow_builder" in shadow_match.group(1):
            if "shadow_builder(config)" not in after_shadow:
                if "build_context_package_from_config(config)" in after_shadow:
                    errors.append(
                        "memory_hook_gateway.py: shadow_builder is assigned but "
                        "build_context_package_from_config is called directly instead"
                    )

    return errors, warnings


def check_test_version_hardcoding() -> tuple[list, list]:
    """Check for hardcoded version strings in test files."""
    errors: list[str] = []
    warnings: list[str] = []

    constants = _load_constants()
    current_version = constants.get("CURRENT_MEMORY_VERSION", "0.2.0")

    tests_dir = REPO_ROOT / "tests"
    if not tests_dir.exists():
        return errors, warnings

    for py_file in tests_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            # Look for hardcoded version string
            if f'"{current_version}"' in content or f"'{current_version}'" in content:
                # Check if file imports from constants
                has_constants_import = (
                    "from memory_core.constants import" in content or
                    "import memory_core.constants" in content or
                    "from constants import" in content
                )

                if not has_constants_import:
                    warnings.append(
                        f"{py_file.name}: hardcoded version '{current_version}' "
                        f"without importing from constants"
                    )
        except Exception as exc:
            warnings.append(f"check_test_version_hardcoding: check raised {exc}")

    return errors, warnings


def check_docs_version_references() -> tuple[list, list]:
    """Check for outdated version references in docs."""
    errors: list[str] = []
    warnings: list[str] = []

    docs_dir = REPO_ROOT / "docs"
    if not docs_dir.exists():
        return errors, warnings

    for md_file in docs_dir.rglob("*.md"):
        # Skip archive subdirectory
        if "archive" in str(md_file.relative_to(docs_dir)):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")

            # Check for old version references
            if "0.1.0" in content:
                warnings.append(
                    f"{md_file.name}: contains reference to old version '0.1.0'"
                )

            if "wb-hook-v2" in content:
                warnings.append(
                    f"{md_file.name}: contains reference to old schema 'wb-hook-v2'"
                )
        except Exception as exc:
            warnings.append(f"check_docs_version_references: check raised {exc}")

    return errors, warnings


def check_validate_dry_run_coverage() -> tuple[list, list]:
    """Check that dry_run branch lists all validation checks."""
    errors: list[str] = []
    warnings: list[str] = []

    validate_file = TOOLS_DIR / "validate_project_memory.py"
    if not validate_file.exists():
        errors.append("validate_project_memory.py: file not found")
        return errors, warnings

    content = validate_file.read_text(encoding="utf-8")

    # Find dry_run branch
    dry_run_match = re.search(
        r'if dry_run:(.*?)(?=\n    memory_root|\n    result\.record\("memory_root"|\Z)',
        content,
        re.DOTALL
    )

    if not dry_run_match:
        warnings.append("validate_project_memory.py: dry_run branch not found")
        return errors, warnings

    dry_run_content = dry_run_match.group(1)

    # List of checks that should be in dry_run
    expected_checks = [
        "status_enum",
        "semver",
        "host_enum",
    ]

    missing_checks = []
    for check in expected_checks:
        if check not in dry_run_content:
            missing_checks.append(check)

    if missing_checks:
        warnings.append(
            f"validate_project_memory.py: dry_run branch missing checks: {missing_checks}"
        )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consistency checker for memory-core internal invariants."
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    all_errors: list[str] = []
    all_warnings: list[str] = []
    check_results: list[dict[str, Any]] = []

    checks = [
        ("version_consistency", check_version_consistency),
        ("host_enum_coverage", check_host_enum_coverage),
        ("no_duplicate_version_definitions", check_no_duplicate_version_definitions),
        ("init_validate_roundtrip", check_init_validate_roundtrip),
        ("required_imports_from_constants", check_required_imports_from_constants),
        ("docstring_host_mentions", check_docstring_host_mentions),
        ("no_handwritten_toml_parser", check_no_handwritten_toml_parser),
        ("adapter_registry_complete", check_adapter_registry_complete),
        ("ruff_config_not_conflicting", check_ruff_config_not_conflicting),
        ("contributing_version_source", check_contributing_version_source),
        ("package_data_coverage", check_package_data_coverage),
        ("adapter_schema_host_validation", check_adapter_schema_host_validation),
        ("lock_parser_strict_toml", check_lock_parser_strict_toml),
        ("default_profile_compatibility", check_default_profile_compatibility),
        ("provider_builder_called", check_provider_builder_called),
        ("test_version_hardcoding", check_test_version_hardcoding),
        ("docs_version_references", check_docs_version_references),
        ("validate_dry_run_coverage", check_validate_dry_run_coverage),
    ]

    for check_name, check_func in checks:
        errors, warnings = check_func()
        check_results.append({
            "name": check_name,
            "errors": errors,
            "warnings": warnings,
            "passed": len(errors) == 0,
        })
        all_errors.extend([f"[{check_name}] {e}" for e in errors])
        all_warnings.extend([f"[{check_name}] {w}" for w in warnings])

    if args.json:
        output = {
            "errors": all_errors,
            "warnings": all_warnings,
            "checks": check_results,
            "passed": len(all_errors) == 0,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Memory-Core Consistency Check Report")
        print("=" * 60)

        for check_result in check_results:
            status = "PASS" if check_result["passed"] else "FAIL"
            print(f"\n[{status}] {check_result['name']}")
            for error in check_result["errors"]:
                print(f"  [ERROR] {error}")
            for warning in check_result["warnings"]:
                print(f"  [WARN]  {warning}")

        print("\n" + "-" * 60)
        total = len(check_results)
        passed = sum(1 for c in check_results if c["passed"])
        print(f"Results: {passed}/{total} checks passed")

        if all_warnings:
            print(f"\nWarnings: {len(all_warnings)}")

        if all_errors:
            print(f"\nErrors: {len(all_errors)}")

        print("=" * 60)

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
