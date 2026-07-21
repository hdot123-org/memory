"""Templates for memory-init skill workflows.

This module produces **only text** -- no remote API calls, no credential
access, no side effects beyond file writes (handled by the caller).
"""

from pathlib import Path


def generate_skill_memory_init_fill_yaml(project_name: str = "") -> str:
    """Generate memory-init-fill skill workflow YAML from template file.

    Reads the YAML template from ``workspace/templates/skills/memory-init-fill.yaml``
    and returns its content. This skill is static (no variable substitution needed)
    because it defines a workflow rather than project-specific configuration.

    Parameters
    ----------
    project_name:
        Optional project identifier (currently unused, reserved for future templating).

    Returns
    -------
    str
        The complete YAML string for the memory-init-fill skill workflow,
        or empty string if the template file is not found.
    """
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _template_path = _repo_root / "workspace" / "templates" / "skills" / "memory-init-fill.yaml"

    if _template_path.is_file():
        return _template_path.read_text(encoding="utf-8")

    # Template not found — skill is optional, return empty
    return ""
