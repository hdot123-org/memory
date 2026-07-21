"""Tests for v0.4.0 → v0.5.0 migration: scope resolution and template preservation.

Covers:
- Template files moved to correct scope directory
- Existing destination files not overwritten
- NOW.md moved from .memory/ to project root
- Scope read from adapter.toml routing.project_scope
- Idempotent second run (noop)
- Missing/empty scope raises clear error
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from memory_core.tools.migrate_project_memory import (
    migrate_project_memory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATE_FILES = ["CANONICAL.md", "STATE.md", "PLAN.md", "TASKS.md"]

_V040_ADAPTER_CONTENT = """\
[core]
version = "0.4.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "test-project"
project_scope = "test-scope"
host = "codex"
canonical_files = []
"""

_V040_ADAPTER_NO_SCOPE = """\
[core]
version = "0.4.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"

[routing]
project_name = "test-project"
host = "codex"
"""

_V040_ADAPTER_EMPTY_SCOPE = """\
[core]
version = "0.4.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"

[routing]
project_name = "test-project"
project_scope = ""
host = "codex"
"""


def _create_v040_project(
    tmp_path: Path,
    *,
    scope: str = "test-scope",
    adapter_content: str | None = None,
    with_now_md: bool = True,
    with_templates: bool = True,
) -> Path:
    """Create a v0.4.0-style .memory/ project skeleton.

    Returns the project root path.
    """
    memory_root = tmp_path / ".memory"
    memory_root.mkdir(parents=True)

    # Create adapter.toml
    if adapter_content is None:
        if scope:
            adapter_content = _V040_ADAPTER_CONTENT.replace("test-scope", scope)
        else:
            adapter_content = _V040_ADAPTER_NO_SCOPE

    (memory_root / "adapter.toml").write_text(adapter_content, encoding="utf-8")

    # Create other config files
    (memory_root / "ownership.toml").write_text("# ownership\n", encoding="utf-8")
    (memory_root / "memory.lock").write_text(
        f'# memory.lock\n[memory]\nmemory_version = "0.4.0"\n'
        f'schema_version = "context-package-v1"\nadapter_version = "builtin"\n'
        f'locked_at = "{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}"\n'
        f'lock_reason = "initial"\n',
        encoding="utf-8",
    )
    (memory_root / "migrations.log").write_text("# Migrations Log\n", encoding="utf-8")

    # Create template files
    if with_templates:
        for filename in _TEMPLATE_FILES:
            (memory_root / filename).write_text(
                f"# {filename}\nTemplate content for {filename}\n",
                encoding="utf-8",
            )

    # Create NOW.md
    if with_now_md:
        (memory_root / "NOW.md").write_text(
            "# NOW.md\nCurrent work in progress\n",
            encoding="utf-8",
        )

    # Create kb/ and skills/ dirs (possibly with content)
    (memory_root / "kb" / "projects").mkdir(parents=True, exist_ok=True)
    (memory_root / "skills").mkdir(parents=True, exist_ok=True)

    return tmp_path


# ---------------------------------------------------------------------------
# 1. Scope resolution from adapter.toml
# ---------------------------------------------------------------------------

def test_scope_from_adapter_toml(tmp_path: Path) -> None:
    """Migration reads scope from adapter.toml routing.project_scope."""
    project_root = _create_v040_project(tmp_path, scope="my-project")

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is True

    # Verify templates are in the correct scope directory
    scope_dir = project_root / "memory" / "kb" / "projects" / "my-project"
    assert scope_dir.is_dir(), f"Scope directory {scope_dir} should exist"

    for filename in _TEMPLATE_FILES:
        file_path = scope_dir / filename
        assert file_path.is_file(), f"{filename} should exist in scope directory"
        content = file_path.read_text(encoding="utf-8")
        assert f"# {filename}" in content


# ---------------------------------------------------------------------------
# 2. Template files moved to correct scope directory
# ---------------------------------------------------------------------------

def test_templates_moved_to_scope_dir(tmp_path: Path) -> None:
    """CANONICAL.md, STATE.md, PLAN.md, TASKS.md moved to memory/kb/projects/{scope}/."""
    project_root = _create_v040_project(tmp_path, scope="workbot")

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is True

    scope_dir = project_root / "memory" / "kb" / "projects" / "workbot"
    for filename in _TEMPLATE_FILES:
        assert (scope_dir / filename).is_file(), f"{filename} missing in scope dir"

    # Original files should be gone from .memory/ (which should also be gone)
    assert not (project_root / ".memory").exists(), ".memory/ should be removed"


# ---------------------------------------------------------------------------
# 3. Existing destination not overwritten
# ---------------------------------------------------------------------------

def test_existing_destination_not_overwritten(tmp_path: Path) -> None:
    """If destination file already exists, migration skips (doesn't overwrite)."""
    project_root = _create_v040_project(tmp_path, scope="test-scope")

    # Pre-create destination files with different content
    scope_dir = project_root / "memory" / "kb" / "projects" / "test-scope"
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / "CANONICAL.md").write_text(
        "# Pre-existing CANONICAL.md\n",
        encoding="utf-8",
    )

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is True

    # Pre-existing file should be unchanged
    canonical = scope_dir / "CANONICAL.md"
    content = canonical.read_text(encoding="utf-8")
    assert content == "# Pre-existing CANONICAL.md\n"

    # Other templates should still be moved
    assert (scope_dir / "STATE.md").is_file()
    assert (scope_dir / "PLAN.md").is_file()
    assert (scope_dir / "TASKS.md").is_file()


# ---------------------------------------------------------------------------
# 4. NOW.md moved from .memory/ to project root
# ---------------------------------------------------------------------------

def test_now_md_moved_to_root(tmp_path: Path) -> None:
    """NOW.md moved from .memory/ to project root."""
    project_root = _create_v040_project(tmp_path, scope="test-scope", with_now_md=True)

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is True

    # NOW.md should be at project root
    now_md = project_root / "NOW.md"
    assert now_md.is_file(), "NOW.md should exist at project root"
    content = now_md.read_text(encoding="utf-8")
    assert "Current work in progress" in content


# ---------------------------------------------------------------------------
# 5. No scope raises error
# ---------------------------------------------------------------------------

def test_no_scope_raises_error(tmp_path: Path) -> None:
    """Migration fails gracefully when project_scope is missing from adapter.toml."""
    project_root = _create_v040_project(
        tmp_path,
        adapter_content=_V040_ADAPTER_NO_SCOPE,
    )

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is False
    assert result.get("error") == "missing_project_scope"
    assert any("project_scope" in e for e in result.get("errors", []))


def test_empty_scope_raises_error(tmp_path: Path) -> None:
    """Migration fails gracefully when project_scope is empty string."""
    project_root = _create_v040_project(
        tmp_path,
        adapter_content=_V040_ADAPTER_EMPTY_SCOPE,
    )

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is False
    assert result.get("error") == "missing_project_scope"
    assert any("project_scope" in e for e in result.get("errors", []))


# ---------------------------------------------------------------------------
# 6. Idempotent second run
# ---------------------------------------------------------------------------

def test_idempotent_second_run(tmp_path: Path) -> None:
    """Second migration run is a noop (already migrated)."""
    project_root = _create_v040_project(tmp_path, scope="test-scope")

    # First run
    result1 = migrate_project_memory(project_root, "0.4.0", "0.5.0")
    assert result1["success"] is True

    # Second run - should be noop
    result2 = migrate_project_memory(project_root, "0.4.0", "0.5.0")
    assert result2["success"] is True
    assert result2.get("noop") is True


# ---------------------------------------------------------------------------
# 7. Backup created before migration
# ---------------------------------------------------------------------------

def test_backup_created_before_migration(tmp_path: Path) -> None:
    """Backup exists at memory/system/backups/pre-0.5/ with template files."""
    project_root = _create_v040_project(tmp_path, scope="test-scope")

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")

    assert result["success"] is True

    backup_dir = project_root / "memory" / "system" / "backups" / "pre-0.5"
    assert backup_dir.is_dir(), "Backup directory should exist"

    # Backup should contain template files
    for filename in _TEMPLATE_FILES:
        assert (backup_dir / filename).is_file(), f"{filename} should be in backup"

    # Backup manifest should exist
    manifest_path = backup_dir / "BACKUP_MANIFEST.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["from_version"] == "0.4.0"
    assert manifest["to_version"] == "0.5.0"


# ---------------------------------------------------------------------------
# 8. Content preservation - template files retain content
# ---------------------------------------------------------------------------

def test_template_content_preserved(tmp_path: Path) -> None:
    """Template file content is preserved during migration (not regenerated)."""
    project_root = _create_v040_project(tmp_path, scope="test-scope")

    # Record original content
    original_content = {}
    for filename in _TEMPLATE_FILES:
        original_content[filename] = (project_root / ".memory" / filename).read_text(
            encoding="utf-8",
        )

    result = migrate_project_memory(project_root, "0.4.0", "0.5.0")
    assert result["success"] is True

    # Verify content matches
    scope_dir = project_root / "memory" / "kb" / "projects" / "test-scope"
    for filename in _TEMPLATE_FILES:
        migrated_content = (scope_dir / filename).read_text(encoding="utf-8")
        assert migrated_content == original_content[filename], (
            f"{filename} content not preserved"
        )
