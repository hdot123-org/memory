"""Template rendering: KB templates, file templates, and special files."""

import logging
import os
from pathlib import Path
from typing import Any

from memory_core.ownership import load_memory_ownership

from ._init_config import (
    FILE_TEMPLATES,
    KB_TEMPLATES,
)
from ._init_pipeline import _should_skip_file, _write_template_file
from ._init_templates_core import (
    _decorate_index_content,
    template_adapter_toml,
    template_canonical_md,
)
from ._init_templates_misc import (
    template_inbox_md,
    template_project_scope_md,
)
from ._init_templates_plans import (
    template_now_md,
    template_plan_md,
    template_state_md,
    template_tasks_md,
)

logger = logging.getLogger(__name__)


def _render_standard_templates(
    target: Path,
    memory_root: Path,
    project_name: str,
    mode: str,
    force: bool,
    ownership: Any,
    authorized_maintenance: bool,
    result: dict[str, Any],
) -> tuple[bool, bool]:
    """Render KB_TEMPLATES and FILE_TEMPLATES.

    Returns (any_overwritten, any_skipped)
    """
    any_overwritten = False
    any_skipped = False

    for fname, template_fn in KB_TEMPLATES.items():
        is_business = fname == "INDEX.md" or fname.startswith("project-map/")
        overwritten, skipped = _write_template_file(
            target / fname,
            fname,
            template_fn,
            project_name,
            mode,
            force,
            ownership,
            authorized_maintenance,
            target,
            result,
            is_business,
            _decorate_index_content,
        )
        any_overwritten = any_overwritten or overwritten
        any_skipped = any_skipped or skipped

    for fname, template_fn in FILE_TEMPLATES.items():
        overwritten, skipped = _write_template_file(
            memory_root / fname,
            fname,
            template_fn,
            project_name,
            mode,
            force,
            ownership,
            authorized_maintenance,
            target,
            result,
        )
        any_overwritten = any_overwritten or overwritten
        any_skipped = any_skipped or skipped

    return any_overwritten, any_skipped


def _render_evidence_ref_files(
    target: Path,
    mode: str,
    force: bool,
    ownership: Any,
    authorized_maintenance: bool,
    result: dict[str, Any],
) -> tuple[bool, bool]:
    """Render evidence reference files (tests/.memory-anchor.md, tools/health-check.sh).

    Returns (any_overwritten, any_skipped)
    """
    any_overwritten = False
    any_skipped = False

    # tests/.memory-anchor.md
    anchor_path = target / "tests" / ".memory-anchor.md"
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_content = "# Memory Anchor\n\n# Evidence ref for Truth Basis sections in global-canonical files.\n# Created by init_project_memory.\n"
    anchor_existed = anchor_path.exists()
    should_skip, reason = _should_skip_file(anchor_path, mode, force, ownership, authorized_maintenance, target, result)
    if anchor_existed and should_skip:
        result["skipped"].append(f"file:tests/.memory-anchor.md ({reason})")
        any_skipped = True
    else:
        try:
            anchor_path.write_text(anchor_content, encoding="utf-8")
            result["created"].append(f"file:tests/.memory-anchor.md{' (overwritten)' if anchor_existed else ''}")
            if anchor_existed:
                any_overwritten = True
        except Exception as exc:
            action = "overwrite" if anchor_existed else "create"
            result["errors"].append(f"failed to {action} tests/.memory-anchor.md: {exc}")

    # tools/health-check.sh
    tools_dir = target / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    health_check_path = tools_dir / "health-check.sh"
    health_check_content = "#!/bin/bash\n# Health check script for memory-core validation.\n# Created by init_project_memory as lower-layer tooling evidence ref.\necho 'healthy'\n"
    health_check_existed = health_check_path.exists()
    should_skip, reason = _should_skip_file(
        health_check_path, mode, force, ownership, authorized_maintenance, target, result
    )
    if health_check_existed and should_skip:
        result["skipped"].append(f"file:tools/health-check.sh ({reason})")
        any_skipped = True
    else:
        try:
            health_check_path.write_text(health_check_content, encoding="utf-8")
            result["created"].append(f"file:tools/health-check.sh{' (overwritten)' if health_check_existed else ''}")
            if health_check_existed:
                any_overwritten = True
        except Exception as exc:
            action = "overwrite" if health_check_existed else "create"
            result["errors"].append(f"failed to {action} tools/health-check.sh: {exc}")

    return any_overwritten, any_skipped


def _render_special_files(
    target: Path,
    memory_root: Path,
    project_name: str,
    host: str,
    mode: str,
    force: bool,
    ownership: Any,
    authorized_maintenance: bool,
    result: dict[str, Any],
) -> tuple[bool, bool]:
    """Render special files (adapter.toml, inbox.md, anchor, health-check, scope.md).

    Args:
        host: Host platform for adapter.toml routing.host (e.g., "factory", "zcode")

    Returns (any_overwritten, any_skipped)
    """
    any_overwritten = False
    any_skipped = False

    # adapter.toml — pass host so template_adapter_toml renders the correct routing.host
    overwritten, skipped = _write_template_file(
        memory_root / "adapter.toml",
        "adapter.toml",
        template_adapter_toml,
        project_name,
        mode,
        force,
        ownership,
        authorized_maintenance,
        target,
        result,
        host=host,
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    # memory/inbox.md
    overwritten, skipped = _write_template_file(
        target / "memory" / "inbox.md",
        "memory/inbox.md",
        template_inbox_md,
        project_name,
        mode,
        force,
        ownership,
        authorized_maintenance,
        target,
        result,
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    # Evidence ref files
    overwritten, skipped = _render_evidence_ref_files(target, mode, force, ownership, authorized_maintenance, result)
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    # memory/kb/projects/{scope}.md
    scope_md_path = target / "memory" / "kb" / "projects" / f"{project_name}.md"
    overwritten, skipped = _write_template_file(
        scope_md_path,
        f"memory/kb/projects/{project_name}.md",
        template_project_scope_md,
        project_name,
        mode,
        force,
        ownership,
        authorized_maintenance,
        target,
        result,
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    return any_overwritten, any_skipped


def _render_per_scope_files(
    target: Path,
    project_name: str,
    mode: str,
    force: bool,
    ownership: Any,
    authorized_maintenance: bool,
    result: dict[str, Any],
) -> tuple[bool, bool]:
    """Render per-scope control loop files (CANONICAL.md, STATE.md, PLAN.md, TASKS.md, NOW.md).

    Returns (any_overwritten, any_skipped)
    """
    any_overwritten = False
    any_skipped = False

    scope_dir = target / "memory" / "kb" / "projects" / project_name
    try:
        scope_dir.mkdir(parents=True, exist_ok=True)
        result["created"].append(f"dir:memory/kb/projects/{project_name}/")
    except Exception as exc:
        result["errors"].append(f"failed to create per-scope directory: {exc}")

    for fname, template_fn in [
        ("CANONICAL.md", template_canonical_md),
        ("STATE.md", template_state_md),
        ("PLAN.md", template_plan_md),
        ("TASKS.md", template_tasks_md),
    ]:
        file_path = scope_dir / fname
        overwritten, skipped = _write_template_file(
            file_path,
            f"memory/kb/projects/{project_name}/{fname}",
            template_fn,
            project_name,
            mode,
            force,
            ownership,
            authorized_maintenance,
            target,
            result,
        )
        any_overwritten = any_overwritten or overwritten
        any_skipped = any_skipped or skipped

    # NOW.md
    overwritten, skipped = _write_template_file(
        target / "NOW.md",
        "NOW.md",
        template_now_md,
        project_name,
        mode,
        force,
        ownership,
        authorized_maintenance,
        target,
        result,
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    return any_overwritten, any_skipped


def _render_all_templates(
    target: Path,
    memory_root: Path,
    project_name: str,
    host: str,
    mode: str,
    force: bool,
    result: dict[str, Any],
) -> tuple[bool, bool]:
    """Render all template files with mode-aware handling.

    Args:
        host: Host platform for adapter.toml routing.host

    Returns (any_overwritten, any_skipped)
    """
    ownership = load_memory_ownership(target)
    authorized_maintenance = mode == "repair" or os.environ.get("MEMORY_INIT_RUNNING") == "1"

    any_overwritten = False
    any_skipped = False

    overwritten, skipped = _render_standard_templates(
        target, memory_root, project_name, mode, force, ownership, authorized_maintenance, result
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    overwritten, skipped = _render_special_files(
        target, memory_root, project_name, host, mode, force, ownership, authorized_maintenance, result
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    overwritten, skipped = _render_per_scope_files(
        target, project_name, mode, force, ownership, authorized_maintenance, result
    )
    any_overwritten = any_overwritten or overwritten
    any_skipped = any_skipped or skipped

    return any_overwritten, any_skipped
